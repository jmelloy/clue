# CLAUDE.md

## Project Overview

Real-time multiplayer board game server — currently **Clue** (Cluedo) and **Texas Hold'em** poker. Players (human or AI agents) create/join games via WebSockets. Games are pluggable via a registry (`app/games/__init__.py`).

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Redis (async), WebSockets
- **Frontend**: Vue 3 (Composition API, `<script setup>`), Vite 7
- **Agents**: Pluggable — Clue (RandomAgent, WandererAgent, LLMAgent), Hold'em (HoldemAgent)
- **Infra**: Docker Compose (dev), Kubernetes (prod), nginx (prod)
- **Testing**: pytest + fakeredis (backend), Playwright (E2E)
- **Tooling**: uv (Python), Mise (tool versions)

## Repository Structure

```
backend/
  app/
    main.py              # FastAPI app, routes, WebSocket handlers
    ws_manager.py        # WebSocket ConnectionManager
    logging.py           # Structured logging (colored, JSON, access)
    games/
      __init__.py        # Game registry (GAME_TYPES)
      clue/              # ClueGame, board, agents, models, images
      holdem/            # HoldemGame, hand_eval, agents, models
  agent_runner.py        # Standalone agent process (external mode)
  tests/                 # pytest + fakeredis tests for all modules
frontend/
  src/
    App.vue              # Root: game flow, WebSocket, URL routing
    components/          # Lobby, WaitingRoom, GameBoard, BoardMap,
                         # DetectiveNotes, ChatPanel, AgentDebugPanel
    composables/         # useWebSocket.js
scripts/                 # dump_game.py, live_ws_test.py
tests/playwright/        # E2E browser tests
k8s/                     # Kubernetes manifests
```

## Common Commands

```bash
# Docker dev environment
docker compose up
# Frontend :5173 | Backend :8000 | Redis :6379

# Backend tests (no Redis needed — uses fakeredis)
cd backend && uv sync && pytest

# Frontend dev
cd frontend && npm install && npm run dev

# Playwright E2E (requires running frontend + backend)
npm install && npx playwright install && npm test

# Debug: inspect game state in Redis
python scripts/dump_game.py --list-games
python scripts/dump_game.py <GAME_ID> --show-cards --show-solution
```

## Git Worktrees

Use worktrees to work on multiple branches simultaneously without stashing. Useful for parallel Claude agent tasks.

```bash
# Create a worktree (installs deps automatically)
mise run worktree <branch>
# Worktree created at .worktree/<branch>/

# Remove when done
mise run worktree-rm <branch>
```

Worktrees share the same git repo but have independent working directories. Each gets its own `backend/.venv` and `node_modules`.

## Parallel Claude Agents

For multi-part tasks with independent subtasks, parallelize using:

- **`EnterWorktree`** — built-in tool that creates a git worktree and runs a subagent inside it. Use for changes that need their own branch (e.g. separate PRs).
- **`Agent` subagents** — use for parallel research, independent file edits, or tasks that don't touch the same files.

Good candidates for parallelization:
- Backend + frontend changes that don't depend on each other
- Multiple unrelated test fixes
- Research/exploration in a subagent while implementing in the main context

Don't parallelize when tasks have sequential dependencies or touch the same files.

## Architecture & Key Patterns

### Game Registry

`GAME_TYPES` in `backend/app/games/__init__.py` maps slugs to modules: `"clue"`, `"holdem"`.

### Redis Key Schema

All state in Redis with 24h TTL. Backend is stateless.

- **Clue**: `game:{id}`, `game:{id}:solution`, `game:{id}:cards:{player_id}`, `game:{id}:log`, `game:{id}:chat`, `game:{id}:agent_config`, `game:{id}:agent_events`, `game:{id}:memory:{player_id}`
- **Hold'em**: `holdem:{id}`, `holdem:{id}:chat`

### Clue Game (`backend/app/games/clue/`)

- `game.py` — ClueGame: state machine, turn tracking, action processing (`move`, `suggest`, `accuse`, `show_card`, `end_turn`)
- `board.py` — 25x24 grid, BFS pathfinding, secret passages (Study<->Kitchen, Lounge<->Conservatory)
- `agents.py` — BaseAgent, RandomAgent (elimination logic), WandererAgent (ambient), LLMAgent (OpenAI-compatible, falls back to RandomAgent)
- `models.py` — Pydantic models: GameState, PlayerState, Player, action requests
- Constants: `SUSPECTS`, `WEAPONS`, `ROOMS`, `ALL_CARDS` in `game.py`

### Hold'em Game (`backend/app/games/holdem/`)

- `game.py` — HoldemGame: betting rounds, pot splitting, side pots
- `hand_eval.py` — best 5-card hand from 7
- `agents.py` — HoldemAgent: rule-based with hand evaluation
- Agents run inline (background asyncio task), not via agent_runner

### Agent Runner (`backend/agent_runner.py`)

Separate process for Clue agents (when `AGENT_MODE=external`). Polls Redis, creates agent instances, submits actions via HTTP.

### Frontend (Vue 3)

- Reactive refs only (no Vuex/Pinia), scoped CSS
- WebSocket at App.vue level with auto-reconnect
- URL routing via `history.pushState` (`/game/{gameId}`)
- Board layout in `BoardMap.vue` must stay in sync with `board.py`

### API Routes

- **Clue**: `/games/{game_id}/[join|start|action|chat|add_agent|notes|agent_debug]`
- **Hold'em**: `/holdem/games/{game_id}/[join|start|action|chat|add_agent]`
- **WebSocket**: `/ws/{game_id}/{player_id}`, `/ws/holdem/{game_id}/{player_id}`

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Backend, Agent Runner |
| `AGENT_MODE` | `inline` | `inline` or `external` |
| `BACKEND_URL` | `http://localhost:8000` | Frontend proxy, Agent Runner |
| `LLM_API_KEY` | _(empty)_ | OpenAI-compatible API key |
| `LLM_MODEL` | `gpt-5-mini` | LLM Agent (complex decisions) |
| `LLM_NANO_MODEL` | `gpt-5-nano` | LLM Agent (quick ops) |
| `LOG_FORMAT` | `colored` | `colored`, `json`, `plain` |

## Coding Conventions

- **Python**: async/await everywhere, Pydantic for validation, `ValueError` -> `HTTPException(400)`, no ORM (JSON to/from Redis), pytest + fakeredis
- **Vue**: Composition API with `<script setup>`, reactive refs only, Vite dev proxy
- **General**: minimal dependencies, no unnecessary abstractions, game types in `backend/app/games/`, Redis data expires after 24h

## CI/CD

- **CI** (`.github/workflows/ci.yml`): frontend build + backend pytest on pushes to main and PRs
- **CD** (`.github/workflows/deploy.yml`): Docker build -> GHCR -> K8s rollout on main
