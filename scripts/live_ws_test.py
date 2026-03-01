#!/usr/bin/env python3
"""Live end-to-end test that verifies agents work with WebSockets against
a running Docker environment.

Usage:
    # Start the Docker environment first:
    docker compose up -d

    # Then run this script (from the repo root):
    python scripts/live_ws_test.py

    # Or point at a different server:
    python scripts/live_ws_test.py --base-url http://myserver:8000

Prerequisites:
    pip install httpx websockets pydantic

This script:
  1. Creates a game via HTTP
  2. Joins 3 agents via HTTP
  3. Connects each agent to the WebSocket endpoint
  4. Starts the game and reads dealt cards from WebSocket messages
  5. Plays the full game using the real RandomAgent class, mirroring the
     server's _run_agent_loop: agents decide actions, submit via HTTP,
     observe all WebSocket broadcasts in real time
  6. Verifies the game reaches a valid conclusion
  7. Prints a summary of all WebSocket message types received
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add the backend directory to sys.path so we can import the app package
_backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import httpx

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

from app.agents import RandomAgent
from app.game import ClueGame, SUSPECTS, WEAPONS, ROOMS
from app.models import GameState, PlayerState


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

MAX_TURNS = 500


def _build_player_state(
    game_state: GameState, player_id: str, cards: list[str],
) -> PlayerState:
    """Build a PlayerState from a GameState, player ID, and known cards.

    Uses ClueGame.get_available_actions (which is pure logic, no Redis)
    to compute the available actions for the player.
    """
    game = ClueGame("_", None)
    available = game.get_available_actions(player_id, game_state)
    return PlayerState(
        **game_state.model_dump(),
        your_cards=cards,
        your_player_id=player_id,
        available_actions=available,
    )


async def run_live_test(base_url: str, num_agents: int = 3):
    """Run a full game against the live server.

    Mirrors the server-side _run_agent_loop pattern: check game state,
    handle pending show_card requests, then let the active agent decide
    and submit actions via HTTP.
    """
    ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    http = httpx.AsyncClient(base_url=base_url, timeout=10)

    print(f"Connecting to {base_url}...")
    print()

    # Step 1: Health check
    try:
        resp = await http.get("/healthz")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        print("[OK] Server is healthy")
    except Exception as e:
        print(f"[FAIL] Cannot reach server at {base_url}: {e}")
        print("       Make sure the Docker environment is running: docker compose up -d")
        await http.aclose()
        return False

    # Step 2: Create game
    resp = await http.post("/games")
    assert resp.status_code == 201
    game_id = resp.json()["game_id"]
    print(f"[OK] Created game: {game_id}")

    # Step 3: Join agents
    pids = []
    for i in range(num_agents):
        resp = await http.post(
            f"/games/{game_id}/join",
            json={"player_name": f"Bot-{i}", "player_type": "agent"},
        )
        assert resp.status_code == 200
        pids.append(resp.json()["player_id"])
    print(f"[OK] Joined {num_agents} agents: {pids}")

    # Step 4: Connect WebSockets
    ws_connections = {}
    ws_messages: dict[str, list[dict]] = {pid: [] for pid in pids}
    ws_type_counts: dict[str, dict[str, int]] = {pid: {} for pid in pids}

    async def ws_listener(pid: str, ws):
        """Background task that reads all WS messages for a player."""
        try:
            async for raw in ws:
                msg = json.loads(raw)
                ws_messages[pid].append(msg)
                t = msg["type"]
                ws_type_counts[pid][t] = ws_type_counts[pid].get(t, 0) + 1
        except websockets.exceptions.ConnectionClosed:
            pass

    for pid in pids:
        ws = await websockets.connect(f"{ws_base}/ws/{game_id}/{pid}")
        ws_connections[pid] = ws
    print(f"[OK] WebSocket connections established for all {num_agents} agents")

    # Start listener tasks
    listeners = []
    for pid in pids:
        listeners.append(asyncio.create_task(ws_listener(pid, ws_connections[pid])))

    # Give a moment for initial game_state messages
    await asyncio.sleep(0.3)

    # Verify initial game_state received
    for pid in pids:
        gs = [m for m in ws_messages[pid] if m["type"] == "game_state"]
        assert len(gs) >= 1, f"Player {pid} did not receive initial game_state"
    print("[OK] All agents received initial game_state via WebSocket")

    # Step 5: Start game
    resp = await http.post(f"/games/{game_id}/start")
    assert resp.status_code == 200
    print(f"[OK] Game started, first turn: {resp.json()['whose_turn']}")

    await asyncio.sleep(0.3)

    # Extract dealt cards from WebSocket messages and create agents
    agents: dict[str, RandomAgent] = {}
    agent_cards: dict[str, list[str]] = {}
    for pid in pids:
        cards_msg = [m for m in ws_messages[pid]
                     if m["type"] == "game_started" and "your_cards" in m]
        assert len(cards_msg) >= 1, f"Player {pid} missing game_started with cards"
        cards = cards_msg[0]["your_cards"]
        agent = RandomAgent()
        agent.observe_own_cards(cards)
        agents[pid] = agent
        agent_cards[pid] = cards
        print(f"     {pid}: {len(cards)} cards dealt")

    print(f"[OK] All agents received their cards via WebSocket")
    print()
    print("Playing game...")

    # Step 6: Main game loop (mirrors _run_agent_loop from main.py)
    actions_taken = 0
    start_time = time.time()

    # Fetch initial state as a GameState model
    resp = await http.get(f"/games/{game_id}")
    game_state = GameState.model_validate(resp.json())

    while game_state.status == "playing" and actions_taken < MAX_TURNS:
        pending = game_state.pending_show_card

        if pending and pending.player_id in agents:
            # An agent needs to show a card
            pid = pending.player_id
            agent = agents[pid]
            card = await agent.decide_show_card(
                pending.matching_cards,
                pending.suggesting_player_id,
            )
            resp = await http.post(
                f"/games/{game_id}/action",
                json={"player_id": pid, "action": {"type": "show_card", "card": card}},
            )
            assert resp.status_code == 200, f"show_card failed: {resp.text}"
            # The suggesting player learns which card was shown
            agents[pending.suggesting_player_id].observe_shown_card(
                card, shown_by=pid,
            )

        elif game_state.whose_turn in agents:
            # It's an agent's turn — build player state and decide
            pid = game_state.whose_turn
            agent = agents[pid]
            player_state = _build_player_state(
                game_state, pid, agent_cards[pid],
            )
            action = await agent.decide_action(game_state, player_state)
            resp = await http.post(
                f"/games/{game_id}/action",
                json={"player_id": pid, "action": action},
            )
            assert resp.status_code == 200, f"Action {action['type']} failed: {resp.text}"
            result = resp.json()

            # If no one could show a card, the agent notes it
            if action["type"] == "suggest" and result.get("pending_show_by") is None:
                agent.observe_suggestion_no_show(
                    action["suspect"], action["weapon"], action["room"],
                )

        # Give WebSocket messages time to arrive
        await asyncio.sleep(0.05)

        # Refresh game state
        resp = await http.get(f"/games/{game_id}")
        game_state = GameState.model_validate(resp.json())
        actions_taken += 1

    elapsed = time.time() - start_time

    # Step 7: Verify result
    print()
    assert game_state.status == "finished", f"Game did not finish in {MAX_TURNS} actions"
    print(f"[OK] Game finished in {actions_taken} actions ({elapsed:.1f}s)")
    print(f"     Winner: {game_state.winner}")
    print(f"     Turns: {game_state.turn_number}")

    # Close WebSocket connections
    for ws in ws_connections.values():
        await ws.close()
    await asyncio.sleep(0.2)

    # Cancel listeners
    for task in listeners:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Step 8: Report WebSocket message stats
    print()
    print("WebSocket message summary:")
    print("-" * 60)

    all_types: set[str] = set()
    for pid in pids:
        total = len(ws_messages[pid])
        types = ws_type_counts[pid]
        all_types.update(types.keys())
        print(f"  {pid}: {total} messages")
        for t, count in sorted(types.items()):
            print(f"    {t}: {count}")

    print()
    print(f"Unique message types seen: {sorted(all_types)}")

    # Verify key message types were received
    expected_types = {"game_state", "game_started", "player_moved", "chat_message"}
    missing = expected_types - all_types
    if missing:
        print(f"[WARN] Missing expected message types: {missing}")
    else:
        print(f"[OK] All expected message types received")

    # Verify every agent got messages
    for pid in pids:
        assert len(ws_messages[pid]) > 0, f"Agent {pid} got no WebSocket messages"
    print(f"[OK] All {num_agents} agents received WebSocket messages")

    print()
    print("ALL CHECKS PASSED")

    await http.aclose()
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Live WebSocket e2e test against a running Clue server"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000",
        help="Base URL of the Clue backend (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--agents", type=int, default=3, choices=range(2, 7),
        help="Number of agents to play (default: 3)",
    )
    args = parser.parse_args()

    success = asyncio.run(run_live_test(args.base_url, args.agents))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
