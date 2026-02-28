import json
import logging
import os
import random
import string
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
    redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)
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


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/games", status_code=201)
async def create_game():
    game_id = _new_id(6)
    game = ClueGame(game_id, redis_client)
    state = await game.create()
    return {"game_id": game_id, "status": state["status"]}


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
        })

    await manager.broadcast(game_id, {"type": "game_started", "state": state})
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
        await manager.broadcast(game_id, {
            "type": "player_moved",
            "player_id": req.player_id,
            "dice": result.get("dice"),
            "room": result.get("room"),
        })

    elif action_type == "suggest":
        shown_card = result.get("shown_card")
        shown_by = result.get("shown_by")
        # Broadcast without the shown card
        await manager.broadcast(game_id, {
            "type": "suggestion_made",
            "player_id": req.player_id,
            "suspect": result["suspect"],
            "weapon": result["weapon"],
            "room": result["room"],
            "shown_by": shown_by,
        })
        # Send shown card only to the suggesting player
        if shown_card:
            await manager.send_to_player(game_id, req.player_id, {
                "type": "card_shown",
                "shown_by": shown_by,
                "card": shown_card,
            })

    elif action_type == "accuse":
        msg = {
            "type": "accusation_made",
            "player_id": req.player_id,
            "correct": result.get("correct"),
        }
        if result.get("correct"):
            msg["type"] = "game_over"
            msg["winner"] = result.get("winner")
            msg["solution"] = result.get("solution")
        await manager.broadcast(game_id, msg)

    elif action_type == "end_turn":
        next_pid = result.get("next_player_id")
        await manager.broadcast(game_id, {
            "type": "game_state",
            "whose_turn": state["whose_turn"],
            "turn_number": state["turn_number"],
        })
        if next_pid:
            await manager.send_to_player(game_id, next_pid, {"type": "your_turn"})

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
            # Clients can send ping/keep-alive; echo back
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_to_player(game_id, player_id, {"type": "pong"})
            except Exception:
                logger.debug("Ignoring non-JSON WebSocket message from %s/%s", game_id, player_id)
    except WebSocketDisconnect:
        manager.disconnect(game_id, player_id)


# ---------------------------------------------------------------------------
# Static files (Vue build output)
# ---------------------------------------------------------------------------

# NOTE: Static files must be mounted LAST — it acts as a catch-all and would
# shadow any API routes defined after this point.
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
