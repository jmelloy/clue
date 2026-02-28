import json
import logging
import os
import random
import string
import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .game import ClueGame
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


def _new_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _new_player_id() -> str:
    return _new_id(8)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class JoinRequest(BaseModel):
    player_name: str
    player_type: str = "human"


class ActionRequest(BaseModel):
    player_id: str
    action: dict


class ChatRequest(BaseModel):
    player_id: str
    text: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player_name(state: dict, player_id: str) -> str:
    for p in state.get("players", []):
        if p["id"] == player_id:
            return p["name"]
    return player_id


async def _broadcast_chat(game_id: str, text: str, player_id: str | None = None):
    """Broadcast a chat message to all connected players and persist it."""
    message = {
        "player_id": player_id,
        "text": text,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    game = ClueGame(game_id, redis_client)
    await game.add_chat_message(message)
    await manager.broadcast(game_id, {"type": "chat_message", **message})


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/games", status_code=201)
async def create_game():
    game_id = _new_id(6)
    game = ClueGame(game_id, redis_client)
    state = await game.create()
    return {"game_id": game_id, "status": state["status"]}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/games/{game_id}")
async def get_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state


@app.post("/games/{game_id}/join")
async def join_game(game_id: str, req: JoinRequest):
    game = ClueGame(game_id, redis_client)
    player_id = _new_player_id()
    try:
        player = await game.add_player(player_id, req.player_name, req.player_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = await game.get_state()
    await manager.broadcast(game_id, {"type": "player_joined", "player": player, "players": state["players"]})
    await _broadcast_chat(game_id, f"{player['name']} joined the game.")
    return {"player_id": player_id, "player": player}


@app.post("/games/{game_id}/start")
async def start_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    try:
        state = await game.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Notify all players
    for player in state["players"]:
        pid = player["id"]
        cards = await game._load_player_cards(pid)
        await manager.send_to_player(game_id, pid, {
            "type": "game_started",
            "your_cards": cards,
            "whose_turn": state["whose_turn"],
            "available_actions": game.get_available_actions(pid, state),
        })

    await manager.broadcast(game_id, {"type": "game_started", "state": state})
    first_player_name = _player_name(state, state["whose_turn"])
    await _broadcast_chat(game_id, f"Game started! {first_player_name} goes first.")
    return state


@app.post("/games/{game_id}/action")
async def submit_action(game_id: str, req: ActionRequest):
    game = ClueGame(game_id, redis_client)
    try:
        result = await game.process_action(req.player_id, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = await game.get_state()
    action_type = req.action.get("type")

    if action_type == "move":
        actor_name = _player_name(state, req.player_id)
        room = result.get("room")
        dice = result.get("dice")
        await manager.broadcast(game_id, {
            "type": "player_moved",
            "player_id": req.player_id,
            "dice": dice,
            "room": room,
        })
        room_text = f" to {room}" if room else ""
        await _broadcast_chat(
            game_id,
            f"{actor_name} rolled {dice} and moved{room_text}.",
            req.player_id,
        )
        # Notify the current player of their updated available actions
        await manager.send_to_player(game_id, req.player_id, {
            "type": "your_turn",
            "available_actions": game.get_available_actions(req.player_id, state),
        })

    elif action_type == "suggest":
        pending_show_by = result.get("pending_show_by")
        actor_name = _player_name(state, req.player_id)
        # Broadcast without the card info
        await manager.broadcast(game_id, {
            "type": "suggestion_made",
            "player_id": req.player_id,
            "suspect": result["suspect"],
            "weapon": result["weapon"],
            "room": result["room"],
            "pending_show_by": pending_show_by,
        })
        if pending_show_by:
            pending_by_name = _player_name(state, pending_show_by)
            # Ask the player who needs to show a card
            await manager.send_to_player(game_id, pending_show_by, {
                "type": "show_card_request",
                "suggesting_player_id": req.player_id,
                "suspect": result["suspect"],
                "weapon": result["weapon"],
                "room": result["room"],
                "available_actions": game.get_available_actions(pending_show_by, state),
            })
            chat_text = (
                f"{actor_name} suggests {result['suspect']} with the {result['weapon']}"
                f" in the {result['room']}. {pending_by_name} must show a card."
            )
        else:
            chat_text = (
                f"{actor_name} suggests {result['suspect']} with the {result['weapon']}"
                f" in the {result['room']}. No one could show a card."
            )
            # No card to show -- update suggesting player's available actions
            await manager.send_to_player(game_id, req.player_id, {
                "type": "your_turn",
                "available_actions": game.get_available_actions(req.player_id, state),
            })
        await _broadcast_chat(game_id, chat_text, req.player_id)

    elif action_type == "show_card":
        card = result.get("card")
        suggesting_player_id = result.get("suggesting_player_id")
        shown_by_name = _player_name(state, req.player_id)
        shown_to_name = _player_name(state, suggesting_player_id)
        # Only the suggesting player sees the card
        await manager.send_to_player(game_id, suggesting_player_id, {
            "type": "card_shown",
            "shown_by": req.player_id,
            "card": card,
            "available_actions": game.get_available_actions(suggesting_player_id, state),
        })
        # Broadcast that a card was shown (without revealing which card)
        await manager.broadcast(game_id, {
            "type": "card_shown_public",
            "shown_by": req.player_id,
            "shown_to": suggesting_player_id,
        })
        await _broadcast_chat(
            game_id,
            f"{shown_by_name} showed a card to {shown_to_name}.",
            req.player_id,
        )

    elif action_type == "accuse":
        actor_name = _player_name(state, req.player_id)
        msg = {
            "type": "accusation_made",
            "player_id": req.player_id,
            "correct": result.get("correct"),
        }
        if result.get("correct"):
            msg["type"] = "game_over"
            msg["winner"] = result.get("winner")
            msg["solution"] = result.get("solution")
            chat_text = (
                f"{actor_name} accuses {req.action.get('suspect')} with the"
                f" {req.action.get('weapon')} in the {req.action.get('room')}."
                f" Correct! {actor_name} wins!"
            )
        else:
            chat_text = (
                f"{actor_name} accuses {req.action.get('suspect')} with the"
                f" {req.action.get('weapon')} in the {req.action.get('room')}."
                f" Wrong! {actor_name} is eliminated."
            )
        await manager.broadcast(game_id, msg)
        await _broadcast_chat(game_id, chat_text, req.player_id)

    elif action_type == "end_turn":
        next_pid = result.get("next_player_id")
        actor_name = _player_name(state, req.player_id)
        next_name = _player_name(state, next_pid) if next_pid else "?"
        await manager.broadcast(game_id, {
            "type": "game_state",
            "whose_turn": state["whose_turn"],
            "turn_number": state["turn_number"],
        })
        if next_pid:
            await manager.send_to_player(game_id, next_pid, {
                "type": "your_turn",
                "available_actions": game.get_available_actions(next_pid, state),
            })
        await _broadcast_chat(
            game_id,
            f"{actor_name} ended their turn. It is now {next_name}'s turn.",
            req.player_id,
        )

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
            await manager.send_to_player(game_id, player_id, {
                "type": "game_state",
                "state": player_state,
            })
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
                logger.debug("Ignoring non-JSON WebSocket message from %s/%s", game_id, player_id)
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
    return {"messages": messages}


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
# Static files (Vue build output)
# ---------------------------------------------------------------------------

# NOTE: Static files must be mounted LAST — it acts as a catch-all and would
# shadow any API routes defined after this point.
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
