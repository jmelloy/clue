"""Standalone agent runner process.

Runs as a separate process from the FastAPI/uvicorn backend, so uvicorn
reloads (dev mode) and pod restarts (k8s) don't kill running agents.

Discovery:
  - Polls Redis for ``game:{id}:agent_config`` keys written by the backend
    when a game with agent players starts.

Communication:
  - Connects to the backend via WebSocket for real-time game events.
  - Submits actions via the backend HTTP API (POST /games/{game_id}/action).
  - Fetches player state via HTTP GET when making decisions.
"""

import asyncio
import json
import logging
import os
import sys

import httpx
import redis.asyncio as aioredis
import websockets

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.agents import BaseAgent, LLMAgent, RandomAgent, WandererAgent
from app.game import ClueGame
from app.logging import get_logging_config
from app.models import GameState, PlayerState

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = float(os.getenv("AGENT_POLL_INTERVAL", "2"))

# Derive WebSocket URL from the HTTP backend URL
_WS_URL = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://")


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
        """Manage agents for a single game via WebSocket connections."""
        agents: dict[str, BaseAgent] = {}
        agent_cards: dict[str, list[str]] = {}

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
            agent_cards[pid] = info["cards"]
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
            # Launch a WebSocket connection per agent
            tasks = [
                asyncio.create_task(
                    self._run_agent_ws(game_id, pid, agent, agent_cards[pid])
                )
                for pid, agent in agents.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    pid = list(agents.keys())[i]
                    logger.error(
                        "Agent %s in game %s failed: %s", pid, game_id, result
                    )
        except asyncio.CancelledError:
            logger.info("Agent tasks cancelled for game %s", game_id)
        finally:
            await self.redis.delete(f"game:{game_id}:agent_config")
            logger.info("Agents finished for game %s", game_id)

    # ------------------------------------------------------------------
    # Per-agent WebSocket connection
    # ------------------------------------------------------------------

    async def _run_agent_ws(
        self,
        game_id: str,
        player_id: str,
        agent: BaseAgent,
        cards: list[str],
    ):
        """Drive a single agent via a WebSocket connection to the backend."""
        ws_url = f"{_WS_URL}/ws/{game_id}/{player_id}"
        logger.info("Connecting agent %s to WebSocket %s", player_id, ws_url)

        max_reconnects = 5
        reconnects = 0

        async for ws in websockets.connect(ws_url):
            try:
                async for raw_msg in ws:
                    msg = json.loads(raw_msg)
                    done = await self._handle_message(
                        game_id, player_id, agent, cards, msg
                    )
                    if done:
                        return
                # Server closed the connection cleanly
                return
            except websockets.ConnectionClosed:
                reconnects += 1
                if reconnects > max_reconnects:
                    logger.error(
                        "Too many reconnections for agent %s in game %s",
                        player_id,
                        game_id,
                    )
                    return
                logger.warning(
                    "WebSocket disconnected for agent %s in game %s, "
                    "reconnecting (%d/%d)...",
                    player_id,
                    game_id,
                    reconnects,
                    max_reconnects,
                )

    async def _handle_message(
        self,
        game_id: str,
        player_id: str,
        agent: BaseAgent,
        cards: list[str],
        msg: dict,
    ) -> bool:
        """Process a WebSocket message. Returns True when the game is over."""
        msg_type = msg.get("type")

        if msg_type == "your_turn":
            await self._handle_your_turn(game_id, player_id, agent)

        elif msg_type == "show_card_request":
            await self._handle_show_card(game_id, player_id, agent, cards, msg)

        elif msg_type == "suggestion_made":
            self._handle_suggestion_observation(player_id, agent, msg)

        elif msg_type == "card_shown":
            # This agent was the suggesting player — it sees the actual card
            agent.observe_shown_card(msg["card"], shown_by=msg["shown_by"])

        elif msg_type == "card_shown_public":
            # Someone showed a card to someone else
            shown_by = msg["shown_by"]
            shown_to = msg["shown_to"]
            if player_id not in (shown_by, shown_to):
                agent.observe_card_shown_to_other(
                    shown_by=shown_by,
                    shown_to=shown_to,
                    suspect=msg.get("suspect", ""),
                    weapon=msg.get("weapon", ""),
                    room=msg.get("room", ""),
                )

        elif msg_type == "game_over":
            logger.info("Game %s is over, stopping agent %s", game_id, player_id)
            return True

        return False

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _handle_your_turn(
        self, game_id: str, player_id: str, agent: BaseAgent
    ):
        """React to a your_turn message: fetch state, decide, and send action."""
        # Pace non-LLM agents for human observers
        if agent.agent_type != "llm":
            await asyncio.sleep(1.35)

        # Fetch fresh player state from the backend
        resp = await self.http.get(f"/games/{game_id}/player/{player_id}")
        if resp.status_code != 200:
            logger.warning(
                "Failed to fetch player state for %s in game %s: %s",
                player_id,
                game_id,
                resp.status_code,
            )
            return

        ps_data = resp.json()
        game_state = GameState(
            **{k: v for k, v in ps_data.items() if k in GameState.model_fields}
        )
        player_state = PlayerState(**ps_data)

        if game_state.status != "playing":
            return

        try:
            action = await agent.decide_action(game_state, player_state)
        except Exception:
            logger.exception(
                "Agent %s failed to decide action in game %s", player_id, game_id
            )
            return

        logger.info(
            "Agent %s taking action %s in game %s",
            player_id,
            action.get("type"),
            game_id,
        )

        result = await self._send_action(game_id, player_id, action)
        if isinstance(result, dict) and result.get("error"):
            return

        # Broadcast personality chat after the action
        chat_context = {
            "dice": result.get("dice", ""),
            "room": result.get("room") or action.get("room") or "",
            "suspect": action.get("suspect", ""),
            "weapon": action.get("weapon", ""),
        }
        chat_msg = agent.generate_chat(action.get("type", ""), chat_context)
        if chat_msg:
            await self._send_chat(game_id, player_id, chat_msg)

    async def _handle_show_card(
        self,
        game_id: str,
        player_id: str,
        agent: BaseAgent,
        cards: list[str],
        msg: dict,
    ):
        """React to a show_card_request: decide which card to show."""
        suggesting_pid = msg["suggesting_player_id"]
        matching = msg.get("matching_cards", [])
        if not matching:
            # Fallback: compute from own hand
            matching = [
                c
                for c in cards
                if c
                in [msg.get("suspect", ""), msg.get("weapon", ""), msg.get("room", "")]
            ]

        if not matching:
            logger.warning(
                "Agent %s has no matching cards for show_card_request in game %s",
                player_id,
                game_id,
            )
            return

        try:
            card = await agent.decide_show_card(matching, suggesting_pid)
        except Exception:
            logger.exception(
                "Agent %s failed to decide show_card in game %s",
                player_id,
                game_id,
            )
            card = matching[0]

        logger.info("Agent %s showing card in game %s", player_id, game_id)
        await self._send_action(game_id, player_id, {"type": "show_card", "card": card})

        chat_msg = agent.generate_chat("show_card")
        if chat_msg:
            await self._send_chat(game_id, player_id, chat_msg)

    @staticmethod
    def _handle_suggestion_observation(
        player_id: str, agent: BaseAgent, msg: dict
    ):
        """Update agent observations from a suggestion_made broadcast."""
        suggesting_pid = msg.get("player_id")
        agent.observe_suggestion(
            suggesting_player_id=suggesting_pid,
            suspect=msg.get("suspect", ""),
            weapon=msg.get("weapon", ""),
            room=msg.get("room", ""),
            shown_by=msg.get("pending_show_by"),
            players_without_match=msg.get("players_without_match", []),
        )
        # If nobody could show, and this agent made the suggestion
        if msg.get("pending_show_by") is None and suggesting_pid == player_id:
            agent.observe_suggestion_no_show(
                msg.get("suspect", ""),
                msg.get("weapon", ""),
                msg.get("room", ""),
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
