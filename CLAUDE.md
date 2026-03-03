# CLAUDE.md

## Project Overview

Clue is a real-time multiplayer board game server implementing the classic "Clue" (Cluedo) detective game. Players (human or LLM-powered agents) create/join games, move around a board, make suggestions and accusations, and chat — all via WebSockets for live updates.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Redis (async via `redis.asyncio`), WebSockets
- **Frontend**: Vue 3 (Composition API with `<script setup>`), Vite 7
- **Agents**: Pluggable agent system (RandomAgent, WandererAgent, LLMAgent) with OpenAI-compatible LLM integration
- **Infrastructure**: Docker Compose (dev), Kubernetes (prod), nginx (prod serving)
- **Tooling**: uv (Python package manager), Mise (tool version management)

## Repository Structure

```
backend/
  app/
    main.py          # FastAPI app, HTTP routes, WebSocket handler
    game.py          # ClueGame class — core game logic and state machine
    board.py         # 25x24 grid, room graph, BFS pathfinding
    board.txt        # ASCII diagram of the board layout
    agents.py        # Agent system: BaseAgent, RandomAgent, WandererAgent, LLMAgent
    llm_agent.py     # Legacy LLM agent (superseded by agents.py)
    models.py        # Pydantic models for API requests and game state
    ws_manager.py    # WebSocket ConnectionManager
    logging.py       # Structured logging (colored, JSON, access formats)
  agent_runner.py    # Standalone agent process (polls Redis, submits actions via HTTP)
  main.py            # Uvicorn entry point with logging config
  tests/
    test_game.py     # Game logic tests (pytest + fakeredis)
    test_board.py    # Board and pathfinding tests
    test_agent_game.py  # Agent integration tests (full game simulations)
    test_ws_e2e.py   # End-to-end WebSocket tests (HTTP + WS stack)
  pyproject.toml     # Python project config (dependencies, build)
  pytest.ini         # pytest-asyncio config (asyncio_mode = auto)
  uv.lock            # Locked dependency versions
  Dockerfile

frontend/
  src/
    App.vue                    # Root component, game flow, WebSocket connection, URL routing
    main.js                    # Entry point
    components/
      Lobby.vue                # Game creation and joining
      WaitingRoom.vue          # Pre-game player list
      GameBoard.vue            # Main gameplay UI, action panel, player legend
      BoardMap.vue             # Interactive 25x24 grid board with player tokens
      DetectiveNotes.vue       # Card tracking notepad (auto-marks shown cards)
      ChatPanel.vue            # In-game chat
    composables/
      useWebSocket.js          # WebSocket composable
  vite.config.js               # Build to ../backend/static, dev proxy
  nginx.conf                   # Production nginx config
  package.json
  Dockerfile                   # Multi-stage: Node 22 build -> nginx

scripts/
  deploy.sh          # Manual K8s deployment script
  dump_game.py       # Debug tool: inspect game state in Redis
  live_ws_test.py    # Live end-to-end test against running Docker environment

k8s/                           # Kubernetes manifests
  namespace.yaml               # "clue" namespace
  backend.yaml                 # Backend Deployment + Service
  agent-runner.yaml            # Agent runner Deployment
  redis.yaml                   # Redis Deployment + Service
  ingress.yaml                 # Ingress routing
  clusterissuer.yaml           # Optional cert-manager for HTTPS

docker-compose.yml             # Local dev: redis + backend + agent-runner + frontend
.github/
  workflows/
    ci.yml                     # CI: frontend build + backend pytest
    deploy.yml                 # CD: build Docker image, push to GHCR, deploy to K8s
  dependabot.yml               # Automated dependency updates
.mise.toml                     # Tool version management (Python venv config)
```

## Common Commands

### Running locally with Docker

```bash
docker compose up
# Frontend: http://localhost:5173 (Vite HMR)
# Backend:  http://localhost:8000 (Uvicorn --reload)
# Agent Runner: separate container (polls Redis, sends actions to backend)
# Redis:    localhost:6379
```

### Running backend tests

```bash
cd backend
pip install .              # or: uv sync
pytest                     # runs all tests
pytest tests/ -v           # verbose output
pytest tests/test_game.py  # game logic only
pytest tests/test_board.py # board/pathfinding only
pytest tests/test_agent_game.py  # agent integration tests
pytest tests/test_ws_e2e.py      # end-to-end WebSocket tests
```

Tests use `fakeredis` — no running Redis instance needed.

### Running backend manually

```bash
cd backend
pip install .              # or: uv sync
uvicorn app.main:app --reload
```

### Running frontend manually

```bash
cd frontend
npm install
npm run dev          # dev server at :5173, proxies /games and /ws to backend
npm run build        # outputs to ../backend/static/
```

### Debug scripts

```bash
# Inspect game state in Redis
python scripts/dump_game.py --list-games
python scripts/dump_game.py <GAME_ID> --show-cards --show-solution --show-chat

# Run live end-to-end test against running environment
python scripts/live_ws_test.py --base-url http://localhost:8000 --agents 3
```

## Architecture & Key Patterns

### Game State in Redis

All state lives in Redis with 24-hour TTL. Key schema:

- `game:{id}` — primary game state (JSON)
- `game:{id}:solution` — the hidden solution cards (JSON)
- `game:{id}:cards:{player_id}` — a player's hand (JSON)
- `game:{id}:log` — move log (Redis list)
- `game:{id}:chat` — chat messages (Redis list)
- `game:{id}:agent_config` — agent configuration for agent runner (JSON)
- `game:{id}:agent_events` — observation events for agents (Redis list)
- `game:{id}:memory:{player_id}` — LLM agent memory entries (Redis list)

The backend is stateless — every request fetches fresh state from Redis.

### Game Logic (backend/app/game.py)

`ClueGame` is the core class. It manages:

- Player join/leave, card dealing (round-robin)
- Turn tracking via `whose_turn`
- Action processing: `"move"`, `"suggest"`, `"accuse"`, `"show_card"`, `"end_turn"`
- `get_available_actions()` computes valid next actions from current state
- `process_action()` validates and applies actions, enforcing the action matrix
- `append_memory()` / `get_memory()` for LLM agent memory persistence
- Errors are raised as `ValueError`, caught in `main.py` and returned as HTTP 400/404

Constants: `SUSPECTS`, `WEAPONS`, `ROOMS`, `ALL_CARDS`, `SECRET_PASSAGE_MAP`

### Board (backend/app/board.py)

- 25x24 grid with rooms, hallways, doors
- Graph-based BFS pathfinding for reachability
- Secret passages: Study<->Kitchen, Lounge<->Conservatory
- `get_reachable()` — squares reachable within N steps
- `move_towards()` — optimal path toward a target room

### Agent System (backend/app/agents.py)

Three agent types, all inheriting from `BaseAgent`:

- **`RandomAgent`** — Rule-based elimination player. Moves toward unknown rooms, suggests with unknown cards, accuses when narrowed to exactly 1 candidate per category. Shows strategically (prefers already-known cards).
- **`WandererAgent`** — Ambient character that just rolls and moves to random rooms. Never suggests or accuses. Used for unplayed suspect characters.
- **`LLMAgent`** — Calls an OpenAI-compatible API with character-specific system prompts. Falls back to `RandomAgent` on failure. Supports persistent memory across turns.

All agents share:
- `seen_cards` tracking (own hand + shown cards)
- Card inference logic (`observe_suggestion`, `observe_card_shown_to_other`, `_try_infer_shown_card`)
- Cascading deduction engine
- Character personality chat generation

Player types: `"human"`, `"agent"` (RandomAgent), `"llm_agent"` (LLMAgent), `"wanderer"` (WandererAgent)

### Agent Runner (backend/agent_runner.py)

Runs as a separate process/container (when `AGENT_MODE=external`):
- Polls Redis for `game:*:agent_config` keys to discover active games
- Creates agent instances and drives them through the game loop
- Consumes observation events from `game:{id}:agent_events` (Redis list)
- Submits actions back to the backend via HTTP POST
- Broadcasts personality chat messages via HTTP

### Pydantic Models (backend/app/models.py)

API contracts and game state:
- `GameState` — full game snapshot (status, players, positions, turn state)
- `PlayerState` — extends GameState with player-specific info (cards, available_actions)
- `Player` — id, name, type, character, active
- Request models: `JoinRequest`, `AddAgentRequest`, `ActionRequest`, `ChatRequest`
- `Solution`, `Suggestion`, `PendingShowCard`

### WebSocket Communication (backend/app/main.py, ws_manager.py)

Message types broadcast to clients:
- `game_state`, `player_joined`, `game_started`, `player_moved`
- `suggestion_made`, `card_shown`, `card_shown_public`
- `accusation_made`, `game_over`
- `your_turn` — sent only to the active player
- `show_card_request` — sent to a player who must reveal a card
- `auto_end_timer` — countdown timer for auto-ending idle turns (7s)
- `dice_rolled` — dice result with reachable rooms/positions
- `chat_message`
- `ping`/`pong` — keep-alive

### Frontend (Vue 3)

- Composition API with `<script setup>` throughout
- Reactive refs for local state (no Vuex/Pinia)
- Components communicate via props and emits
- Scoped CSS per component
- WebSocket managed at the App.vue level with auto-reconnect
- URL routing via `history.pushState` (pattern: `/game/{gameId}`)
- Observer mode for spectating games

Key components:
- **BoardMap.vue** — Interactive CSS Grid board (24 cols x 25 rows) with player tokens, reachability highlighting, room/position selection
- **DetectiveNotes.vue** — Card tracking notepad with auto-marking of shown cards, state cycling (unknown/eliminated/maybe)
- **GameBoard.vue** — Main gameplay UI: action panel, player legend, auto-end timer display, suggestion/accusation forms

### Logging (backend/app/logging.py)

Structured logging with multiple formatters:
- `ColoredFormatter` — ANSI colors for terminal output
- `JSONFormatter` — JSON lines for production
- `AccessFormatter` — HTTP access logs with status code coloring
- Separate trace logger (`app.agents.trace`) for LLM prompt/response debugging

## Environment Variables

| Variable | Default | Used By |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Backend, Agent Runner |
| `CORS_ORIGINS` | `*` | Backend |
| `AGENT_MODE` | `inline` | Backend (`inline` or `external`) |
| `BACKEND_URL` | `http://localhost:8000` | Frontend (vite proxy), Agent Runner |
| `DEBUG` | `false` | Backend (enables --reload) |
| `LOG_LEVEL` | `INFO` | Backend, Agent Runner |
| `LOG_FORMAT` | `colored` | Backend, Agent Runner (`colored`, `json`, `plain`) |
| `LLM_API_KEY` | _(empty)_ | LLM Agent (OpenAI-compatible API key) |
| `LLM_API_URL` | `https://api.openai.com/v1/chat/completions` | LLM Agent |
| `LLM_MODEL` | `gpt-5-mini` | LLM Agent |
| `LLM_TRACE_LOG_LEVEL` | _(empty)_ | Backend (trace-level logging for LLM calls) |
| `AGENT_POLL_INTERVAL` | `2` | Agent Runner (seconds between Redis polls) |

## CI/CD

### CI (`.github/workflows/ci.yml`)
Runs on pushes to `main` and all PRs:
- **Frontend job**: `npm install` + `npm run build` (Node 20)
- **Backend job**: `pip install .` + `pytest` (Python 3.12)

### CD (`.github/workflows/deploy.yml`)
Runs on pushes to `main`:
1. **test** — Calls CI workflow
2. **build-backend** — Docker buildx, pushes to ghcr.io with SHA + branch + latest tags
3. **deploy** — K8s rollout: namespace, secrets, Redis, backend, agent-runner, ingress

### Dependabot
Automated dependency updates for npm (frontend), pip (backend), and GitHub Actions.

## Coding Conventions

### Python (backend)
- Async/await everywhere (FastAPI + asyncio)
- Pydantic models for request body validation
- Business logic errors as `ValueError` -> `HTTPException(400)` in route handlers
- No ORM — direct JSON serialization to/from Redis
- Tests use `pytest` with `pytest-asyncio` (auto mode) and `fakeredis`
- Dependencies managed via `pyproject.toml` + `uv.lock`

### JavaScript/Vue (frontend)
- Vue 3 Composition API with `<script setup>` syntax
- No state management library — reactive refs only
- Vite dev proxy for `/games` (HTTP) and `/ws` (WebSocket) routes

### General
- Keep dependencies minimal; no unnecessary abstractions
- Game constants (SUSPECTS, WEAPONS, ROOMS) are defined in `game.py`
- All game data expires from Redis after 24 hours
- Board layout is defined in both `board.py` (backend) and `BoardMap.vue` (frontend) — keep in sync
