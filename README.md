# Clue — Board Game Server

A real-time board game server for **Clue (Cluedo)** built with Vue 3, FastAPI, and Redis.

## Architecture

```
frontend/   Vue 3 + Vite SPA
backend/    FastAPI + Redis + WebSockets
```

## Features

- Create or join games with a short shareable ID (e.g. `ABC123`)
- Real-time updates via WebSockets — dice rolls, suggestions, accusations all pushed to every player instantly
- Full Clue logic: cards dealt, suggestion resolution (other players show matching cards), final accusations, player elimination
- Move log recorded in Redis for every action
- Human **and** LLM agent players supported (`player_type: "human" | "llm"`)
- 24-hour TTL on all Redis game state

## Quick Start

### Docker Compose (recommended for development)

```bash
docker compose up
```

- Frontend (Vite dev server with HMR): http://localhost:5173
- Backend API: http://localhost:8000
- Redis: localhost:6379

Code changes in `backend/` and `frontend/src/` are reflected immediately without rebuilding images.

### Manual Setup

#### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires a local Redis instance (`redis://localhost:6379` by default).
Set `CORS_ORIGINS=https://yourdomain.com` to restrict CORS in production.

#### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server with HMR (proxies API to :8000)
npm run build      # builds into backend/static/ for production
```

### Tests

```bash
cd backend
pytest tests/ -v
```

## Kubernetes Deployment

Build, push, and deploy with the helper script:

```bash
./scripts/deploy.sh -r ghcr.io/<owner>/clue -t <tag>
```

Deploy through SSH to a remote machine that has `kubectl` configured:

```bash
./scripts/deploy.sh -r ghcr.io/<owner>/clue -t <tag> --ssh <user>@<host>
```

Enable cert-manager TLS (Let's Encrypt) during deploy:

```bash
./scripts/deploy.sh -r ghcr.io/<owner>/clue -t <tag> --ssh <user>@<host> --cert-manager
```

You can also use `--skip-build` to only apply manifests and update image tags.

The `k8s/` directory contains:

| File | Description |
|------|-------------|
| `redis.yaml` | Redis deployment and ClusterIP service |
| `backend.yaml` | FastAPI backend deployment and ClusterIP service |
| `frontend.yaml` | nginx-based frontend deployment and ClusterIP service |
| `clusterissuer.yaml` | cert-manager `ClusterIssuer` (`letsencrypt-prod`) for TLS certificates |
| `ingress.yaml` | Ingress for `clue.melloy.life`, routing `/games` and `/ws` to backend, `/` to frontend |

`scripts/deploy.sh` sets deployment images automatically via `kubectl set image`.

For cert-manager, update the ACME email in `k8s/clusterissuer.yaml` before first deploy.

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/games` | Create a new game |
| `GET`  | `/games/{id}` | Get game state |
| `POST` | `/games/{id}/join` | Join a game (`player_name`, `player_type`) |
| `POST` | `/games/{id}/start` | Start the game (deal cards) |
| `POST` | `/games/{id}/action` | Submit an action (`move`, `suggest`, `accuse`, `end_turn`) |
| `WS`   | `/ws/{id}/{player_id}` | WebSocket connection for real-time updates |

## WebSocket Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `game_state` | server→client | Full game state snapshot |
| `player_joined` | server→all | New player joined |
| `game_started` | server→all | Game started; includes `your_cards` for each player |
| `player_moved` | server→all | Player moved to a room |
| `suggestion_made` | server→all | Suggestion made (card shown omitted) |
| `card_shown` | server→suggester | Which card was shown to the suggesting player |
| `accusation_made` | server→all | Accusation made |
| `game_over` | server→all | Game over; includes winner and solution |
| `your_turn` | server→player | Notify specific player it is their turn |
| `ping` / `pong` | client↔server | Keep-alive |
