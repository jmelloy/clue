import json
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # game_id -> {player_id: WebSocket}
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, game_id: str, player_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[game_id][player_id] = websocket

    def disconnect(self, game_id: str, player_id: str):
        game_conns = self._connections.get(game_id, {})
        game_conns.pop(player_id, None)
        if not game_conns:
            self._connections.pop(game_id, None)

    async def broadcast(self, game_id: str, message: dict):
        payload = json.dumps(message)
        dead = []
        for player_id, ws in list(self._connections.get(game_id, {}).items()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(player_id)
        for pid in dead:
            self.disconnect(game_id, pid)

    async def send_to_player(self, game_id: str, player_id: str, message: dict):
        ws = self._connections.get(game_id, {}).get(player_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.disconnect(game_id, player_id)
