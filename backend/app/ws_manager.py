import logging
from collections import defaultdict

from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # game_id -> {player_id: [WebSocket, ...]}
        self._connections: dict[str, dict[str, list[WebSocket]]] = defaultdict(
            lambda: defaultdict(list)
        )

    async def connect(self, game_id: str, player_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[game_id][player_id].append(websocket)

    def disconnect(self, game_id: str, player_id: str, websocket: WebSocket = None):
        game_conns = self._connections.get(game_id, {})
        ws_list = game_conns.get(player_id, [])
        if websocket is not None:
            # Remove specific connection
            try:
                ws_list.remove(websocket)
            except ValueError:
                pass
        else:
            # Remove all connections for this player
            ws_list.clear()
        if not ws_list:
            game_conns.pop(player_id, None)
        if not game_conns:
            self._connections.pop(game_id, None)

    async def broadcast(self, game_id: str, message: BaseModel):
        payload = message.model_dump_json()
        dead: list[tuple[str, WebSocket]] = []
        for player_id, ws_list in list(self._connections.get(game_id, {}).items()):
            for ws in list(ws_list):
                try:
                    await ws.send_text(payload)
                except Exception as exc:
                    logger.warning(
                        "Failed to send to %s in game %s: %s",
                        player_id,
                        game_id,
                        exc,
                    )
                    dead.append((player_id, ws))
        for pid, ws in dead:
            self.disconnect(game_id, pid, ws)

    async def send_to_player(self, game_id: str, player_id: str, message: BaseModel):
        ws_list = self._connections.get(game_id, {}).get(player_id, [])
        payload = message.model_dump_json()
        dead: list[WebSocket] = []
        for ws in list(ws_list):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning(
                    "Failed to send to player %s in game %s: %s",
                    player_id,
                    game_id,
                    exc,
                )
                dead.append(ws)
        for ws in dead:
            self.disconnect(game_id, player_id, ws)
