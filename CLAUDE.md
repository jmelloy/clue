# CLAUDE.md

## Project Overview

Clue is a real-time multiplayer board game server implementing the classic "Clue" (Cluedo) detective game. Players (human or LLM agents) create/join games, move around a board, make suggestions and accusations, and chat — all via WebSockets for live updates.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Redis (async via `redis.asyncio`), WebSockets
- **Frontend**: Vue 3 (Composition API with `<script setup>`), Vite 5
- **Infrastructure**: Docker Compose (dev), Kubernetes (prod), nginx (prod serving)

## Repository Structure

```
backend/
  app/
    main.py          # FastAPI app, HTTP routes, WebSocket handler
    game.py          # ClueGame class — core game logic and state machine
    board.py         # 25x24 grid, room graph, BFS pathfinding
    llm_agent.py     # LLM agent decision-making
    ws_manager.py    # WebSocket ConnectionManager
  tests/
    test_game.py     # Game logic tests (pytest + fakeredis)
    test_board.py    # Board and pathfinding tests
  requirements.txt   # Pinned Python dependencies
  pytest.ini         # pytest-asyncio config (asyncio_mode = auto)
  Dockerfile

frontend/
  src/
    App.vue                    # Root component, game flow, WebSocket connection
    main.js                    # Entry point
    components/
      Lobby.vue                # Game creation and joining
      WaitingRoom.vue          # Pre-game player list
      GameBoard.vue            # Main gameplay UI
      ChatPanel.vue            # In-game chat
    composables/
      useWebSocket.js          # WebSocket composable
  vite.config.js               # Build to ../backend/static, dev proxy
  nginx.conf                   # Production nginx config
  package.json
  Dockerfile                   # Multi-stage: Node 22 build -> nginx

k8s/                           # Kubernetes manifests
  backend.yaml, frontend.yaml, redis.yaml, ingress.yaml

docker-compose.yml             # Local dev: redis + backend + frontend
.github/workflows/ci.yml       # CI: frontend build + backend pytest
```

## Common Commands

### Running locally with Docker

```bash
docker compose up
# Frontend: http://localhost:5173 (Vite HMR)
# Backend:  http://localhost:8000 (Uvicorn --reload)
# Redis:    localhost:6379
```

### Running backend tests

```bash
cd backend
pip install -r requirements.txt
pytest                    # runs all tests
pytest tests/ -v          # verbose output
pytest tests/test_game.py # game logic only
pytest tests/test_board.py # board/pathfinding only
```

Tests use `fakeredis` — no running Redis instance needed.

### Running backend manually

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Running frontend manually

```bash
cd frontend
npm install
npm run dev          # dev server at :5173, proxies /games and /ws to backend
npm run build        # outputs to ../backend/static/
```

## Architecture & Key Patterns

### Game State in Redis

All state lives in Redis with 24-hour TTL. Key schema:
- `game:{id}` — primary game state (JSON)
- `game:{id}:solution` — the hidden solution cards (JSON)
- `game:{id}:cards:{player_id}` — a player's hand (JSON)
- `game:{id}:log` — move log (Redis list)
- `game:{id}:chat` — chat messages (Redis list)

The backend is stateless — every request fetches fresh state from Redis.

### Game Logic (backend/app/game.py)

`ClueGame` is the core class. It manages:
- Player join/leave, card dealing (round-robin)
- Turn tracking via `whose_turn`
- Action processing: `"move"`, `"suggest"`, `"accuse"`, `"show_card"`, `"end_turn"`
- `get_available_actions()` computes valid next actions from current state
- `process_action()` validates and applies actions, enforcing the action matrix
- Errors are raised as `ValueError`, caught in `main.py` and returned as HTTP 400/404

### Board (backend/app/board.py)

- 25x24 grid with rooms, hallways, doors
- Graph-based BFS pathfinding for reachability
- Secret passages: Study<->Kitchen, Lounge<->Conservatory
- `get_reachable()` — squares reachable within N steps
- `move_towards()` — optimal path toward a target room

### WebSocket Communication (backend/app/main.py, ws_manager.py)

Message types broadcast to clients:
- `game_state`, `player_joined`, `game_started`, `player_moved`
- `suggestion_made`, `card_shown`, `card_shown_public`
- `accusation_made`, `game_over`
- `your_turn` — sent only to the active player
- `show_card_request` — sent to a player who must reveal a card
- `chat_message`
- `ping`/`pong` — keep-alive

### Frontend (Vue 3)

- Composition API with `<script setup>` throughout
- Reactive refs for local state (no Vuex/Pinia)
- Components communicate via emits
- Scoped CSS per component
- WebSocket managed at the App.vue level

## Environment Variables

| Variable | Default | Used By |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Backend |
| `CORS_ORIGINS` | `*` | Backend |
| `BACKEND_URL` | `http://localhost:8000` | Frontend (vite.config.js proxy) |

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes to `main` and all PRs:
- **Frontend job**: `npm install` + `npm run build` (Node 20)
- **Backend job**: `pip install -r requirements.txt` + `pytest` (Python 3.12)

## Coding Conventions

### Python (backend)
- Async/await everywhere (FastAPI + asyncio)
- Pydantic models for request body validation
- Business logic errors as `ValueError` -> `HTTPException(400)` in route handlers
- No ORM — direct JSON serialization to/from Redis
- Tests use `pytest` with `pytest-asyncio` (auto mode) and `fakeredis`

### JavaScript/Vue (frontend)
- Vue 3 Composition API with `<script setup>` syntax
- No state management library — reactive refs only
- Vite dev proxy for `/games` (HTTP) and `/ws` (WebSocket) routes

### General
- Keep dependencies minimal; no unnecessary abstractions
- Game constants (SUSPECTS, WEAPONS, ROOMS) are defined in `game.py`
- All game data expires from Redis after 24 hours
