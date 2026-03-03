"""Standalone agent runner process.

Runs as a separate process from the FastAPI/uvicorn backend, so uvicorn
reloads (dev mode) and pod restarts (k8s) don't kill running agents.

Discovery:
  - Polls Redis for ``game:{id}:agent_config`` keys written by the backend
    when a game with agent players starts.

Actions:
  - Sends actions via the backend HTTP API (POST /games/{game_id}/action)
    so the backend handles WebSocket broadcasting.

Observations:
  - Reads observation events from ``game:{id}:agent_events`` (Redis list)
    published by the backend after every action.
"""

import asyncio
import json
import logging
import os
import sys

import httpx
import redis.asyncio as aioredis

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.agents import BaseAgent, LLMAgent, RandomAgent, WandererAgent
from app.game import ClueGame
from app.logging import get_logging_config
from app.models import GameState

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = float(os.getenv("AGENT_POLL_INTERVAL", "2"))


def _player_name(state: GameState, player_id: str) -> str:
    for p in state.players:
        if p.id == player_id:
            return p.name
    return player_id


class AgentRunner:
    """Manages agent players across all active games."""

    def __init__(self):
        self.redis: aioredis.Redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=BACKEND_URL, timeout=30
        )
        self.managed_games: dict[str, asyncio.Task] = {}

    async def start(self):
        logger.info(
            "Agent runner started (backend=%s, redis=%s)", BACKEND_URL, REDIS_URL
        )

        try:
            while True:
                await self._discover_games()
                # Clean up finished game tasks
                finished = [
                    gid for gid, task in self.managed_games.items() if task.done()
                ]
                for gid in finished:
                    task = self.managed_games.pop(gid)
                    # Log any exception that wasn't handled
                    if task.exception():
                        logger.error(
                            "Game %s agent task failed: %s", gid, task.exception()
                        )
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            for task in self.managed_games.values():
                task.cancel()
            if self.http:
                await self.http.aclose()
            if self.redis:
                await self.redis.aclose()

    async def _discover_games(self):
        """Scan Redis for games that need agent management."""
        async for key in self.redis.scan_iter("game:*:agent_config"):
            game_id = key.split(":")[1]
            if game_id in self.managed_games:
                continue

            config_raw = await self.redis.get(key)
            if not config_raw:
                continue

            config = json.loads(config_raw)

            # Check if game is still active
            game = ClueGame(game_id, self.redis)
            state = await game.get_state()
            if not state or state.status != "playing":
                # Game is over or doesn't exist — clean up config
                await self.redis.delete(key)
                continue

            logger.info("Discovered game %s with %d agent(s)", game_id, len(config))
            task = asyncio.create_task(self._run_game(game_id, config))
            self.managed_games[game_id] = task

    async def _run_game(self, game_id: str, config: dict):
        """Manage agents for a single game."""
        agents: dict[str, BaseAgent] = {}
        event_cursor = 0

        for pid, info in config.items():
            ptype = info["type"]
            if ptype == "llm_agent":
                agent: BaseAgent = LLMAgent(redis_client=self.redis, game_id=game_id)
            elif ptype == "wanderer":
                agent = WandererAgent()
            else:
                agent = RandomAgent()

            agent.character = info["character"]
            agent.player_id = pid
            agent.observe_own_cards(info["cards"])
            if ptype == "llm_agent":
                await agent.load_memory()
            agents[pid] = agent
            logger.info(
                "Created %s agent for %s (%s) in game %s",
                ptype,
                pid,
                info["character"],
                game_id,
            )

        try:
            await self._agent_loop(game_id, agents, event_cursor)
        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for game %s", game_id)
        except Exception:
            logger.exception("Agent loop error in game %s", game_id)
        finally:
            await self.redis.delete(f"game:{game_id}:agent_config")
            logger.info("Agent loop ended for game %s", game_id)

    # ------------------------------------------------------------------
    # Observation events
    # ------------------------------------------------------------------

    async def _consume_events(
        self, game_id: str, agents: dict[str, BaseAgent], cursor: int
    ) -> int:
        """Read new observation events from Redis and update agents.

        Returns the updated cursor position.
        """
        key = f"game:{game_id}:agent_events"
        events = await self.redis.lrange(key, cursor, -1)
        for event_raw in events:
            event = json.loads(event_raw)
            self._apply_event(agents, event)
        return cursor + len(events)

    @staticmethod
    def _apply_event(agents: dict[str, BaseAgent], event: dict):
        """Apply an observation event to all relevant agents."""
        etype = event.get("type")

        if etype == "show_card":
            shown_by = event["shown_by"]
            shown_to = event["shown_to"]
            card = event["card"]
            suspect = event.get("suspect", "")
            weapon = event.get("weapon", "")
            room = event.get("room", "")

            # The suggesting player learns which card was shown
            if shown_to in agents and card:
                agents[shown_to].observe_shown_card(card, shown_by=shown_by)

            # Other agents note that a card was shown (for inference)
            for aid, agent in agents.items():
                if aid not in (shown_to, shown_by) and suspect and weapon and room:
                    agent.observe_card_shown_to_other(
                        shown_by=shown_by,
                        shown_to=shown_to,
                        suspect=suspect,
                        weapon=weapon,
                        room=room,
                    )

        elif etype == "suggest":
            suggesting_pid = event["suggesting_player_id"]
            shown_by = event.get("shown_by")
            players_without = event.get("players_without_match", [])

            for _aid, agent in agents.items():
                agent.observe_suggestion(
                    suggesting_player_id=suggesting_pid,
                    suspect=event["suspect"],
                    weapon=event["weapon"],
                    room=event["room"],
                    shown_by=shown_by,
                    players_without_match=players_without,
                )

            # If no one could show a card, the suggesting agent also notes this
            if shown_by is None and suggesting_pid in agents:
                agents[suggesting_pid].observe_suggestion_no_show(
                    event["suspect"],
                    event["weapon"],
                    event["room"],
                )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _send_action(self, game_id: str, player_id: str, action: dict) -> dict:
        """Send an action to the backend via the HTTP API."""
        resp = await self.http.post(
            f"/games/{game_id}/action",
            json={"player_id": player_id, "action": action},
        )
        if resp.status_code == 400:
            body = resp.text
            logger.warning(
                "Action rejected (400) for %s in game %s: %s — action=%s",
                player_id,
                game_id,
                body,
                action,
            )
            return {"error": True, "status": 400, "detail": body}
        resp.raise_for_status()
        return resp.json()

    async def _send_chat(self, game_id: str, player_id: str, text: str):
        """Send a chat message via the HTTP API."""
        logger.info("Sending chat from %s in game %s: %s", player_id, game_id, text)
        try:
            await self.http.post(
                f"/games/{game_id}/chat",
                json={"player_id": player_id, "text": text},
            )
        except Exception:
            logger.debug("Failed to send chat for %s in game %s", player_id, game_id)

    # ------------------------------------------------------------------
    # Main agent loop
    # ------------------------------------------------------------------

    async def _agent_loop(
        self,
        game_id: str,
        agents: dict[str, BaseAgent],
        event_cursor: int,
    ):
        """Drive agent players — mirrors _run_agent_loop but uses HTTP."""
        logger.info(
            "Agent loop started for game %s with %d agent(s)",
            game_id,
            len(agents),
        )

        max_consecutive_errors = 5
        consecutive_errors = 0

        while True:
            # Consume any pending observation events
            event_cursor = await self._consume_events(game_id, agents, event_cursor)

            game = ClueGame(game_id, self.redis)
            state = await game.get_state()
            if state is None or state.status != "playing":
                break

            pending = state.pending_show_card
            if pending and pending.player_id in agents:
                # An agent needs to show a card
                await asyncio.sleep(1)
                event_cursor = await self._consume_events(game_id, agents, event_cursor)
                state = await game.get_state()
                if not state or state.status != "playing":
                    break
                pending = state.pending_show_card
                if not pending or pending.player_id not in agents:
                    continue

                pid = pending.player_id
                agent = agents[pid]
                card = await agent.decide_show_card(
                    pending.matching_cards, pending.suggesting_player_id
                )

                logger.info("Agent %s showing card in game %s", pid, game_id)
                try:
                    result = await self._send_action(
                        game_id, pid, {"type": "show_card", "card": card}
                    )
                except httpx.HTTPError as exc:
                    consecutive_errors += 1
                    logger.warning(
                        "Network error showing card for %s in game %s: %s",
                        pid,
                        game_id,
                        exc,
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            "Too many consecutive errors (%d) in game %s, exiting",
                            consecutive_errors,
                            game_id,
                        )
                        return
                    await asyncio.sleep(1)
                    continue

                if isinstance(result, dict) and result.get("error"):
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            "Too many consecutive errors (%d) in game %s, exiting",
                            consecutive_errors,
                            game_id,
                        )
                        return
                    await asyncio.sleep(0.5)
                    continue

                consecutive_errors = 0
                # Broadcast personality chat
                chat_msg = agent.generate_chat("show_card")

                if chat_msg:
                    s = await game.get_state()
                    name = _player_name(s, pid) if s else pid
                    await self._send_chat(game_id, pid, chat_msg)

            elif pending:
                # A human player must show a card — wait
                await asyncio.sleep(0.5)

            elif state.whose_turn in agents:
                # It's an agent's turn
                agent = agents[state.whose_turn]
                if agent.agent_type != "llm":
                    await asyncio.sleep(1.35)

                # Re-check state
                event_cursor = await self._consume_events(game_id, agents, event_cursor)
                state = await game.get_state()
                if not state or state.status != "playing":
                    break
                pid = state.whose_turn
                if pid not in agents:
                    continue

                agent = agents[pid]
                player_state = await game.get_player_state(pid)
                action = await agent.decide_action(state, player_state)

                logger.info(
                    "Agent %s taking action %s in game %s",
                    pid,
                    action.get("type"),
                    game_id,
                )
                try:
                    result = await self._send_action(game_id, pid, action)
                except httpx.HTTPError as exc:
                    consecutive_errors += 1
                    logger.warning(
                        "Network error for %s action %s in game %s: %s",
                        pid,
                        action.get("type"),
                        game_id,
                        exc,
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            "Too many consecutive errors (%d) in game %s, exiting",
                            consecutive_errors,
                            game_id,
                        )
                        return
                    await asyncio.sleep(1)
                    continue

                if isinstance(result, dict) and result.get("error"):
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(
                            "Too many consecutive errors (%d) in game %s, exiting",
                            consecutive_errors,
                            game_id,
                        )
                        return
                    # If the action was rejected, try ending the turn instead
                    if action.get("type") != "end_turn":
                        logger.info(
                            "Falling back to end_turn for %s in game %s",
                            pid,
                            game_id,
                        )
                        try:
                            fallback = await self._send_action(
                                game_id, pid, {"type": "end_turn"}
                            )
                            if not (
                                isinstance(fallback, dict) and fallback.get("error")
                            ):
                                consecutive_errors = 0
                        except httpx.HTTPError:
                            pass
                    await asyncio.sleep(0.5)
                    continue

                consecutive_errors = 0
                # Broadcast personality chat after the action
                chat_context = {
                    "dice": result.get("dice", ""),
                    "room": result.get("room") or action.get("room") or "",
                    "suspect": action.get("suspect", ""),
                    "weapon": action.get("weapon", ""),
                }
                chat_msg = agent.generate_chat(action.get("type", ""), chat_context)
                if chat_msg:
                    s = await game.get_state()
                    name = _player_name(s, pid) if s else pid
                    await self._send_chat(game_id, pid, chat_msg)

            else:
                # Human player's turn — poll periodically
                await asyncio.sleep(0.5)


async def main():
    runner = AgentRunner()
    await runner.start()


if __name__ == "__main__":
    import logging.config

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "colored")
    logging.config.dictConfig(
        get_logging_config(log_level=log_level, log_format=log_format)
    )
    asyncio.run(main())
