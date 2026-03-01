import asyncio
import json
import logging
import os
import random
import string
import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agents import BaseAgent, LLMAgent, RandomAgent
from .game import ClueGame
from .models import (
    ActionRequest,
    ChatMessage,
    ChatRequest,
    GameState,
    JoinRequest,
    Player,
    PlayerState,
)
from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    yield
    # Cancel any running agent loops
    for task in _agent_tasks.values():
        task.cancel()
    _agent_tasks.clear()
    _game_agents.clear()
    await redis_client.aclose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Clue Game Server", lifespan=lifespan)

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

# Track agent instances and background tasks per game
_game_agents: dict[str, dict[str, BaseAgent]] = {}
_agent_tasks: dict[str, asyncio.Task] = {}

# Player types that trigger the automated agent loop
_AGENT_PLAYER_TYPES = {"agent", "llm_agent"}


def _new_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _new_player_id() -> str:
    return _new_id(8)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player_name(state: GameState, player_id: str) -> str:
    for p in state.players:
        if p.id == player_id:
            return p.name
    return player_id


async def _broadcast_chat(game_id: str, text: str, player_id: str | None = None):
    """Broadcast a chat message to all connected players and persist it."""
    message = ChatMessage(
        player_id=player_id,
        text=text,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    game = ClueGame(game_id, redis_client)
    await game.add_chat_message(message)
    await manager.broadcast(game_id, {"type": "chat_message", **message.model_dump()})


# ---------------------------------------------------------------------------
# Action execution (shared by HTTP endpoint and agent loop)
# ---------------------------------------------------------------------------


async def _execute_action(game_id: str, player_id: str, action: dict) -> dict:
    """Process a game action and broadcast WebSocket messages.

    Returns the action result dict. Raises ValueError on invalid actions.
    """
    game = ClueGame(game_id, redis_client)
    result = await game.process_action(player_id, action)
    state = await game.get_state()
    action_type = action.get("type")

    if action_type == "move":
        actor_name = _player_name(state, player_id)
        room = result.get("room")
        dice = result.get("dice")
        await manager.broadcast(
            game_id,
            {
                "type": "player_moved",
                "player_id": player_id,
                "dice": dice,
                "room": room,
                "position": result.get("position"),
            },
        )
        room_text = f" to {room}" if room else ""
        await _broadcast_chat(
            game_id,
            f"{actor_name} rolled {dice} and moved{room_text}.",
            player_id,
        )
        await manager.send_to_player(
            game_id,
            player_id,
            {
                "type": "your_turn",
                "available_actions": game.get_available_actions(player_id, state),
            },
        )

    elif action_type == "suggest":
        pending_show_by = result.get("pending_show_by")
        moved_suspect_player = result.get("moved_suspect_player")
        actor_name = _player_name(state, player_id)
        suggestion_msg = {
            "type": "suggestion_made",
            "player_id": player_id,
            "suspect": result["suspect"],
            "weapon": result["weapon"],
            "room": result["room"],
            "pending_show_by": pending_show_by,
        }
        if moved_suspect_player:
            suggestion_msg["moved_suspect_player"] = moved_suspect_player
            suggestion_msg["player_positions"] = dict(state.player_positions)
        await manager.broadcast(game_id, suggestion_msg)
        if pending_show_by:
            pending_by_name = _player_name(state, pending_show_by)
            await manager.send_to_player(
                game_id,
                pending_show_by,
                {
                    "type": "show_card_request",
                    "suggesting_player_id": player_id,
                    "suspect": result["suspect"],
                    "weapon": result["weapon"],
                    "room": result["room"],
                    "available_actions": game.get_available_actions(
                        pending_show_by, state
                    ),
                },
            )
            # Update suggesting player's actions (they must wait for card to be shown)
            await manager.send_to_player(
                game_id,
                player_id,
                {
                    "type": "your_turn",
                    "available_actions": game.get_available_actions(player_id, state),
                },
            )
            chat_text = (
                f"{actor_name} suggests {result['suspect']} with the {result['weapon']}"
                f" in the {result['room']}. {pending_by_name} must show a card."
            )
        else:
            chat_text = (
                f"{actor_name} suggests {result['suspect']} with the {result['weapon']}"
                f" in the {result['room']}. No one could show a card."
            )
            await manager.send_to_player(
                game_id,
                player_id,
                {
                    "type": "your_turn",
                    "available_actions": game.get_available_actions(player_id, state),
                },
            )
        await _broadcast_chat(game_id, chat_text, player_id)

    elif action_type == "show_card":
        card = result.get("card")
        suggesting_player_id = result.get("suggesting_player_id")
        shown_by_name = _player_name(state, player_id)
        shown_to_name = _player_name(state, suggesting_player_id)
        await manager.send_to_player(
            game_id,
            suggesting_player_id,
            {
                "type": "card_shown",
                "shown_by": player_id,
                "card": card,
                "available_actions": game.get_available_actions(
                    suggesting_player_id, state
                ),
            },
        )
        await manager.broadcast(
            game_id,
            {
                "type": "card_shown_public",
                "shown_by": player_id,
                "shown_to": suggesting_player_id,
            },
        )
        await _broadcast_chat(
            game_id,
            f"{shown_by_name} showed a card to {shown_to_name}.",
            player_id,
        )

    elif action_type == "accuse":
        actor_name = _player_name(state, player_id)
        msg = {
            "type": "accusation_made",
            "player_id": player_id,
            "correct": result.get("correct"),
        }
        if result.get("correct"):
            msg["type"] = "game_over"
            msg["winner"] = result.get("winner")
            msg["solution"] = result.get("solution")
            chat_text = (
                f"{actor_name} accuses {action.get('suspect')} with the"
                f" {action.get('weapon')} in the {action.get('room')}."
                f" Correct! {actor_name} wins!"
            )
        else:
            chat_text = (
                f"{actor_name} accuses {action.get('suspect')} with the"
                f" {action.get('weapon')} in the {action.get('room')}."
                f" Wrong! {actor_name} is eliminated."
            )
        await manager.broadcast(game_id, msg)
        await _broadcast_chat(game_id, chat_text, player_id)

    elif action_type == "end_turn":
        next_pid = result.get("next_player_id")
        actor_name = _player_name(state, player_id)
        next_name = _player_name(state, next_pid) if next_pid else "?"
        await manager.broadcast(
            game_id,
            {
                "type": "game_state",
                "whose_turn": state.whose_turn,
                "turn_number": state.turn_number,
                "dice_rolled": state.dice_rolled,
                "last_roll": state.last_roll,
                "suggestions_this_turn": [
                    s.model_dump() for s in state.suggestions_this_turn
                ],
                "pending_show_card": (
                    state.pending_show_card.model_dump()
                    if state.pending_show_card
                    else None
                ),
                "player_positions": state.player_positions,
            },
        )
        if next_pid:
            await manager.send_to_player(
                game_id,
                next_pid,
                {
                    "type": "your_turn",
                    "available_actions": game.get_available_actions(next_pid, state),
                },
            )
        await _broadcast_chat(
            game_id,
            f"{actor_name} ended their turn. It is now {next_name}'s turn.",
            player_id,
        )

    # Update agent observations for any active agents in this game
    _update_agent_observations(game_id, player_id, action, result)

    return result


def _update_agent_observations(
    game_id: str, player_id: str, action: dict, result: dict
):
    """Update agent observations based on action results."""
    agents = _game_agents.get(game_id)
    if not agents:
        return

    action_type = action.get("type")

    if action_type == "show_card":
        # The suggesting player learns which card was shown
        suggesting_pid = result.get("suggesting_player_id")
        card = result.get("card")
        if suggesting_pid and suggesting_pid in agents and card:
            agents[suggesting_pid].observe_shown_card(card, shown_by=player_id)

    elif action_type == "suggest":
        # If no one could show a card, the suggesting agent notes this
        if result.get("pending_show_by") is None and player_id in agents:
            agents[player_id].observe_suggestion_no_show(
                action["suspect"],
                action["weapon"],
                action["room"],
            )


# ---------------------------------------------------------------------------
# Agent background loop
# ---------------------------------------------------------------------------


async def _run_agent_loop(game_id: str):
    """Background task that drives agent players in a game."""
    agents = _game_agents.get(game_id)
    if not agents:
        return

    logger.info("Agent loop started for game %s with %d agent(s)", game_id, len(agents))

    try:
        while True:
            game = ClueGame(game_id, redis_client)
            state = await game.get_state()
            if state is None or state.status != "playing":
                break

            pending = state.pending_show_card
            if pending and pending.player_id in agents:
                # An agent needs to show a card
                await asyncio.sleep(1)
                # Re-check state (may have changed during sleep)
                state = await game.get_state()
                if not state or state.status != "playing":
                    break
                pending = state.pending_show_card
                if not pending or pending.player_id not in agents:
                    continue

                pid = pending.player_id
                agent = agents[pid]
                matching = pending.matching_cards
                suggesting_pid = pending.suggesting_player_id
                card = await agent.decide_show_card(matching, suggesting_pid)

                logger.info("Agent %s showing card in game %s", pid, game_id)
                await _execute_action(game_id, pid, {"type": "show_card", "card": card})

            elif pending:
                # A non-agent (human) player must show a card — wait for them
                await asyncio.sleep(0.5)

            elif state.whose_turn in agents:
                # It's an agent's turn — pace actions for human observers
                await asyncio.sleep(1.5)
                # Re-check state
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
                await _execute_action(game_id, pid, action)

            else:
                # Human player's turn — poll periodically
                await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("Agent loop cancelled for game %s", game_id)
    except Exception:
        logger.exception("Agent loop error in game %s", game_id)
    finally:
        _game_agents.pop(game_id, None)
        _agent_tasks.pop(game_id, None)
        logger.info("Agent loop ended for game %s", game_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/games", status_code=201)
async def create_game():
    game_id = _new_id(6)
    game = ClueGame(game_id, redis_client)
    state = await game.create()
    return {"game_id": game_id, "status": state.status}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/games/{game_id}")
async def get_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state.model_dump()


@app.post("/games/{game_id}/join")
async def join_game(game_id: str, req: JoinRequest):
    game = ClueGame(game_id, redis_client)
    player_id = _new_player_id()
    try:
        player = await game.add_player(player_id, req.player_name, req.player_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = await game.get_state()
    await manager.broadcast(
        game_id,
        {
            "type": "player_joined",
            "player": player.model_dump(),
            "players": [p.model_dump() for p in state.players],
        },
    )
    await _broadcast_chat(game_id, f"{player.name} joined the game.")
    return {"player_id": player_id, "player": player.model_dump()}


@app.post("/games/{game_id}/start")
async def start_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    try:
        state = await game.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Notify all players
    for player in state.players:
        pid = player.id
        cards = await game._load_player_cards(pid)
        await manager.send_to_player(
            game_id,
            pid,
            {
                "type": "game_started",
                "your_cards": cards,
                "whose_turn": state.whose_turn,
                "available_actions": game.get_available_actions(pid, state),
            },
        )

    await manager.broadcast(
        game_id, {"type": "game_started", "state": state.model_dump()}
    )
    first_player_name = _player_name(state, state.whose_turn)
    await _broadcast_chat(game_id, f"Game started! {first_player_name} goes first.")

    # Start background agent loop for any agent players
    agent_players = [p for p in state.players if p.type in _AGENT_PLAYER_TYPES]
    if agent_players:
        agents: dict[str, BaseAgent] = {}
        for player in agent_players:
            pid = player.id
            ptype = player.type
            if ptype == "llm_agent":
                agent: BaseAgent = LLMAgent()
            else:
                agent = RandomAgent()
            cards = await game._load_player_cards(pid)
            agent.observe_own_cards(cards)
            agents[pid] = agent
            logger.info(
                "Created %s agent for player %s in game %s", ptype, pid, game_id
            )
        _game_agents[game_id] = agents
        _agent_tasks[game_id] = asyncio.create_task(_run_agent_loop(game_id))

    return state.model_dump()


@app.post("/games/{game_id}/action")
async def submit_action(game_id: str, req: ActionRequest):
    try:
        result = await _execute_action(game_id, req.player_id, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Include current available actions so the frontend can stay in sync
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state:
        result["available_actions"] = game.get_available_actions(req.player_id, state)
    return result


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    await manager.connect(game_id, player_id, websocket)
    game = ClueGame(game_id, redis_client)
    try:
        player_state = await game.get_player_state(player_id)
        if player_state:
            await manager.send_to_player(
                game_id,
                player_id,
                {
                    "type": "game_state",
                    "state": player_state.model_dump(),
                },
            )
        while True:
            data = await websocket.receive_text()
            # Clients can send ping/keep-alive or chat messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_to_player(game_id, player_id, {"type": "pong"})
                elif msg.get("type") == "chat":
                    text = str(msg.get("text", "")).strip()
                    if text:
                        g = ClueGame(game_id, redis_client)
                        s = await g.get_state()
                        name = _player_name(s, player_id) if s else player_id
                        await _broadcast_chat(game_id, f"{name}: {text}", player_id)
            except Exception:
                logger.debug(
                    "Ignoring non-JSON WebSocket message from %s/%s", game_id, player_id
                )
    except WebSocketDisconnect:
        manager.disconnect(game_id, player_id)


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.get("/games/{game_id}/chat")
async def get_chat(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    messages = await game.get_chat_messages()
    return {"messages": [m.model_dump() for m in messages]}


@app.post("/games/{game_id}/chat")
async def send_chat(game_id: str, req: ChatRequest):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    text = str(req.text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty")
    name = _player_name(state, req.player_id)
    await _broadcast_chat(game_id, f"{name}: {text}", req.player_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# SPA fallback for /game/{id} routes
# ---------------------------------------------------------------------------

_static_dir = Path(__file__).parent.parent / "static"


@app.get("/game/{game_id}")
async def spa_game_route(game_id: str):
    """Serve index.html for /game/{id} so the Vue SPA can handle routing."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    # In dev mode (no static build), return a minimal redirect
    return FileResponse(str(index)) if index.exists() else {"detail": "Not found"}


# ---------------------------------------------------------------------------
# Static files (Vue build output)
# ---------------------------------------------------------------------------

# NOTE: Static files must be mounted LAST — it acts as a catch-all and would
# shadow any API routes defined after this point.
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
