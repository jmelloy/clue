"""Standalone agent runner process.

Runs as a separate process from the FastAPI/uvicorn backend, so uvicorn
reloads (dev mode) and pod restarts (k8s) don't kill running agents.

Discovery:
  - Polls Redis for ``game:{id}:agent_config`` keys written by the backend
    when a game with agent players starts.

Communication:
  - Connects to the backend via WebSocket for real-time game events.
  - Submits actions via the backend HTTP API (POST /api/clue/games/{game_id}/action).
  - Fetches player state via HTTP GET when making decisions.
"""

import asyncio
import json
import logging
import os
import random
import socket
import sys

import httpx
import redis.asyncio as aioredis
import websockets

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.games.clue.agents import BaseAgent, LLMAgent, RandomAgent, WandererAgent
from app.games.clue.game import ClueGame
from app.logging import get_logging_config
from app.games.clue.models import ChatContext, GameState, PlayerState, ShowCardAction

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = float(os.getenv("AGENT_POLL_INTERVAL", "2"))

# Derive WebSocket URL from the HTTP backend URL
_WS_URL = BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://")

# Unique identity for this runner instance used as the Redis lock value so that
# only the holder can release it.
_RUNNER_ID = f"{socket.gethostname()}:{os.getpid()}"

# Distributed-lock settings: the lock TTL must be long enough that a single
# heartbeat interval never starves it, but short enough that a dead runner
# releases games quickly.
_LOCK_TTL = 30          # seconds — Redis key expiry
_LOCK_RENEW_INTERVAL = 10  # seconds — how often the heartbeat refreshes the TTL


def _player_name(state: GameState, player_id: str) -> str:
    for p in state.players:
        if p.id == player_id:
            return p.name
    return player_id


async def _release_lock(redis: aioredis.Redis, lock_key: str) -> bool:
    """Atomically delete *lock_key* only if its current value equals *_RUNNER_ID*.

    Uses WATCH/MULTI/EXEC to prevent deleting a lock that was re-acquired by a
    different runner after ours expired.  Returns True if the lock was released,
    False if it was already gone or owned by another runner.
    """
    async with redis.pipeline(transaction=True) as pipe:
        try:
            await pipe.watch(lock_key)
            current = await pipe.get(lock_key)
            if current != _RUNNER_ID:
                await pipe.reset()
                return False
            pipe.multi()
            pipe.delete(lock_key)
            await pipe.execute()
            return True
        except Exception:
            return False


async def _renew_lock(redis: aioredis.Redis, lock_key: str) -> bool:
    """Atomically extend the TTL of *lock_key* only if it is still owned by us.

    Uses WATCH/MULTI/EXEC so the check-then-extend is atomic.  Returns True if
    the TTL was refreshed, False if the lock was lost.
    """
    async with redis.pipeline(transaction=True) as pipe:
        try:
            await pipe.watch(lock_key)
            current = await pipe.get(lock_key)
            if current != _RUNNER_ID:
                await pipe.reset()
                return False
            pipe.multi()
            pipe.expire(lock_key, _LOCK_TTL)
            await pipe.execute()
            return True
        except Exception:
            return False


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

            try:
                config = json.loads(config_raw)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Malformed agent config for game %s, skipping: %s",
                    game_id,
                    exc,
                )
                continue

            # Check if game is still active
            try:
                game = ClueGame(game_id, self.redis)
                state = await game.get_state()
            except Exception:
                logger.exception(
                    "Failed to fetch game state for %s during discovery",
                    game_id,
                )
                continue
            if not state or state.status != "playing":
                # Game is over or doesn't exist — clean up config
                await self.redis.delete(key)
                continue

            # Try to acquire the distributed lock for this game.  The lock
            # prevents a second runner instance from also managing the same
            # game.  SET NX EX means "set only if not already set, with an
            # expiry" — if another runner holds the lock this returns None.
            lock_key = f"game:{game_id}:agent_lock"
            acquired = await self.redis.set(
                lock_key, _RUNNER_ID, nx=True, ex=_LOCK_TTL
            )
            if not acquired:
                logger.debug(
                    "Game %s is already locked by another runner — skipping",
                    game_id,
                )
                continue

            logger.info(
                "Acquired lock for game %s, starting %d agent(s)",
                game_id,
                len(config),
            )
            task = asyncio.create_task(self._run_game(game_id, config))
            self.managed_games[game_id] = task

    async def _run_game(self, game_id: str, config: dict):
        """Manage agents for a single game via WebSocket connections."""
        lock_key = f"game:{game_id}:agent_lock"

        # Keep the Redis lock alive for as long as this task is running.
        heartbeat_task = asyncio.create_task(self._renew_lock(lock_key))

        agents: dict[str, BaseAgent] = {}

        for pid, info in config.items():
            ptype = info["type"]
            if ptype == "llm_agent":
                agent: BaseAgent = LLMAgent(
                    player_id=pid,
                    character=info["character"],
                    cards=info["cards"],
                    redis_client=self.redis,
                    game_id=game_id,
                )
            elif ptype == "wanderer":
                agent = WandererAgent(
                    player_id=pid,
                    character=info["character"],
                    cards=info["cards"],
                    redis_client=self.redis,
                    game_id=game_id,
                )
            else:
                agent = RandomAgent(
                    player_id=pid,
                    character=info["character"],
                    cards=info["cards"],
                    redis_client=self.redis,
                    game_id=game_id,
                )

            if ptype == "llm_agent":
                await agent.load_memory()
            await agent.load_knowledge()
            agents[pid] = agent
            logger.info(
                "Created %s agent for %s (%s) in game %s",
                ptype,
                pid,
                info["character"],
                game_id,
            )

        # Replay wanderer seeds stored in the config so that restarted runners
        # give each wanderer the same initial card knowledge as the first run.
        # Only seed when no persisted knowledge was loaded (i.e. seen_cards is
        # still just the dealt hand), to avoid re-applying a seed on top of
        # already-restored state.
        # Track which wanderers received a config seed to avoid double-seeding.
        wanderers_seeded: set[str] = set()
        for pid, info in config.items():
            if info.get("type") == "wanderer":
                seed = info.get("wanderer_seed")
                agent = agents[pid]
                if seed and len(agent.seen_cards) <= len(agent.own_cards):
                    agent.observe_shown_card(seed["card"], shown_by=seed["shown_by"])
                    wanderers_seeded.add(pid)

        # Fall back to the legacy random-seeding approach for wanderers in old
        # configs that pre-date the wanderer_seed field (i.e. the key is absent).
        # Only seed wanderers that have not had persisted knowledge restored.
        wanderers_needing_legacy_seed = [
            (pid, a)
            for pid, a in agents.items()
            if a.agent_type == "wanderer"
            and pid not in wanderers_seeded
            and len(a.seen_cards) <= len(a.own_cards)
        ]
        if wanderers_needing_legacy_seed:
            real_agents = {
                pid: a for pid, a in agents.items()
                if a.agent_type != "wanderer" and a.own_cards
            }
            if real_agents:
                for pid, a in wanderers_needing_legacy_seed:
                    donor_pid, donor = random.choice(list(real_agents.items()))
                    card = random.choice(list(donor.own_cards))
                    a.observe_shown_card(card, shown_by=donor_pid)

        try:
            # Launch a WebSocket connection per agent
            tasks = [
                asyncio.create_task(
                    self._run_agent_ws(game_id, pid, agent)
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
            # Stop heartbeat
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Always release the lock so another runner can take over if
            # the game is still active.  The WATCH/MULTI/EXEC pattern makes
            # the check-and-delete atomic so we never accidentally delete a
            # lock that was re-acquired by a different runner after ours
            # expired.
            try:
                await _release_lock(self.redis, lock_key)
                logger.debug("Released lock for game %s", game_id)
            except Exception:
                logger.exception("Error releasing lock for game %s", game_id)

            # Clean up the agent config key only when the game has actually
            # ended.  If the task exits early (e.g. reconnect limit reached),
            # leave the config so the discovery loop can restart management.
            try:
                game = ClueGame(game_id, self.redis)
                state = await game.get_state()
                if state and state.status == "playing":
                    logger.warning(
                        "Agent task for game %s exited while game is still active; "
                        "lock released, it will be rediscovered on the next poll",
                        game_id,
                    )
                else:
                    await self.redis.delete(f"game:{game_id}:agent_config")
                    logger.info("Agents finished for game %s", game_id)
            except Exception:
                logger.exception(
                    "Error during agent cleanup for game %s", game_id
                )

    # ------------------------------------------------------------------
    # Lock heartbeat
    # ------------------------------------------------------------------

    async def _renew_lock(self, lock_key: str):
        """Periodically refresh the TTL on *lock_key* to keep the lock alive.

        Runs until cancelled.  If the key no longer belongs to this runner
        (e.g. it expired and was taken by a peer), we stop renewing silently.
        The WATCH/MULTI/EXEC pipeline makes the read-then-extend atomic so the
        renewal never accidentally refreshes a lock owned by another runner.
        """
        try:
            while True:
                await asyncio.sleep(_LOCK_RENEW_INTERVAL)
                renewed = await _renew_lock(self.redis, lock_key)
                if not renewed:
                    logger.warning(
                        "Lock %s is no longer held by this runner — stopping heartbeat",
                        lock_key,
                    )
                    return
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Per-agent WebSocket connection
    # ------------------------------------------------------------------

    async def _run_agent_ws(
        self,
        game_id: str,
        player_id: str,
        agent: BaseAgent,
    ):
        """Drive a single agent via a WebSocket connection to the backend."""
        ws_url = f"{_WS_URL}/api/ws/clue/{game_id}/{player_id}"
        logger.info("Connecting agent %s to WebSocket %s", player_id, ws_url)

        max_reconnects = 5
        reconnects = 0

        async for ws in websockets.connect(ws_url):
            try:
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "Malformed WebSocket message for agent %s in game %s, skipping",
                            player_id,
                            game_id,
                        )
                        continue
                    done = await self._handle_message(
                        game_id, player_id, agent, msg
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
        msg: dict,
    ) -> bool:
        """Process a WebSocket message. Returns True when the game is over."""
        msg_type = msg.get("type")

        if msg_type == "your_turn":
            await self._handle_your_turn(game_id, player_id, agent)

        elif msg_type == "show_card_request":
            await self._handle_show_card(game_id, player_id, agent, msg)

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
        resp = await self.http.get(f"/api/clue/games/{game_id}/player/{player_id}")
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

        # If no actions are available (e.g. waiting for another player to
        # show a card), skip this turn notification — we'll act when the
        # next relevant message arrives.
        if not player_state.available_actions:
            logger.debug(
                "No available actions for %s in game %s, skipping",
                player_id,
                game_id,
            )
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
            action.type,
            game_id,
        )

        action_dict = action.model_dump()
        result = await self._send_action(game_id, player_id, action_dict)
        if isinstance(result, dict) and result.get("error"):
            detail = result.get("detail", "")
            agent.agent_trace(
                "action_rejected",
                status=result.get("status"),
                detail=detail,
                action=action_dict,
            )
            # Retry once with rejection detail for LLM agents, then fallback
            if agent.agent_type == "llm":
                logger.info(
                    "Retrying action for %s in game %s after rejection: %s",
                    player_id, game_id, detail,
                )
                try:
                    action = await agent.decide_action(
                        game_state, player_state, rejection_detail=detail
                    )
                except Exception:
                    logger.exception(
                        "Agent %s retry failed in game %s", player_id, game_id
                    )
                    return
                action_dict = action.model_dump()
                result = await self._send_action(game_id, player_id, action_dict)
                if isinstance(result, dict) and result.get("error"):
                    agent.agent_trace(
                        "action_rejected_retry_failed",
                        detail=result.get("detail", ""),
                        action=action_dict,
                    )
                    # Fall back to rule-based agent
                    logger.warning(
                        "Retry also rejected for %s in game %s, using fallback",
                        player_id, game_id,
                    )
                    fallback_action = await agent._fallback.decide_action(
                        game_state, player_state
                    )
                    agent.agent_trace(
                        "fallback_after_rejection",
                        action=fallback_action.model_dump(),
                    )
                    action = fallback_action
                    action_dict = action.model_dump()
                    result = await self._send_action(game_id, player_id, action_dict)
                    if isinstance(result, dict) and result.get("error"):
                        return
            else:
                return

        await agent.save_knowledge()

        # Post debug info to backend for observers
        await self._send_debug(game_id, player_id, agent, action)

        # Broadcast personality chat after the action
        chat_context = ChatContext(
            dice=result.get("dice", ""),
            room=result.get("room") or action_dict.get("room") or "",
            suspect=action_dict.get("suspect", ""),
            weapon=action_dict.get("weapon", ""),
        )
        chat_msg = agent.generate_chat(action.type, chat_context.model_dump())
        if chat_msg:
            await self._send_chat(game_id, player_id, chat_msg)

    async def _handle_show_card(
        self,
        game_id: str,
        player_id: str,
        agent: BaseAgent,
        msg: dict,
    ):
        """React to a show_card_request: decide which card to show."""
        suggesting_pid = msg["suggesting_player_id"]
        matching = msg.get("matching_cards", [])
        if not matching:
            # Fallback: compute from own hand
            matching = [
                c
                for c in agent.own_cards
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
        await self._send_action(
            game_id, player_id, ShowCardAction(card=card).model_dump()
        )
        await agent.save_knowledge()

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

    async def _send_debug(
        self, game_id: str, player_id: str, agent: BaseAgent, action=None
    ):
        """Post agent debug info to the backend for observer visibility."""
        try:
            debug_info = agent.get_debug_info(
                status="decided",
                action_description=str(action.type) if action else "",
                decided_action=action.model_dump() if action else None,
            )
            await self.http.post(
                f"/api/clue/games/{game_id}/agent_debug",
                json=debug_info,
            )
        except Exception:
            logger.debug(
                "Failed to send debug for %s in game %s", player_id, game_id
            )

    async def _send_action(self, game_id: str, player_id: str, action: dict) -> dict:
        """Send an action to the backend via the HTTP API."""
        resp = await self.http.post(
            f"/api/clue/games/{game_id}/action",
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
                f"/api/clue/games/{game_id}/chat",
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
    trace_level = os.getenv("LLM_TRACE_LOG_LEVEL", "").strip().upper()
    logging.config.dictConfig(
        get_logging_config(
            log_level=log_level, trace_level=trace_level, log_format=log_format
        )
    )
    asyncio.run(main())
