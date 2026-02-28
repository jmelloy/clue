#!/usr/bin/env python3
"""Live end-to-end test that verifies agents work with WebSockets against
a running Docker environment.

Usage:
    # Start the Docker environment first:
    docker compose up -d

    # Then run this script:
    python scripts/live_ws_test.py

    # Or point at a different server:
    python scripts/live_ws_test.py --base-url http://myserver:8000

Prerequisites:
    pip install httpx websockets

This script:
  1. Creates a game via HTTP
  2. Joins 3 agents via HTTP
  3. Connects each agent to the WebSocket endpoint
  4. Starts the game and reads dealt cards from WebSocket messages
  5. Plays the full game: agents decide actions, submit via HTTP, observe
     all WebSocket broadcasts in real time
  6. Verifies the game reaches a valid conclusion
  7. Prints a summary of all WebSocket message types received
"""

import argparse
import asyncio
import json
import sys
import time

import httpx

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

# Inline a minimal version of the agent logic so we don't require the backend
# to be importable (this script is meant to run standalone).

SUSPECTS = [
    "Miss Scarlett", "Colonel Mustard", "Mrs. White",
    "Reverend Green", "Mrs. Peacock", "Professor Plum",
]
WEAPONS = ["Candlestick", "Knife", "Lead Pipe", "Revolver", "Rope", "Wrench"]
ROOMS = [
    "Kitchen", "Ballroom", "Conservatory", "Billiard Room",
    "Library", "Study", "Hall", "Lounge", "Dining Room",
]

import random


class SimpleAgent:
    """Minimal agent that uses elimination logic (same as LLMAgent)."""

    def __init__(self):
        self.seen_cards: set[str] = set()
        self.shown_to: dict[str, set[str]] = {}
        self.rooms_suggested_in: set[str] = set()

    def observe_own_cards(self, cards):
        self.seen_cards.update(cards)

    def observe_shown_card(self, card, shown_by=None):
        self.seen_cards.add(card)

    def observe_suggestion_no_show(self, suspect, weapon, room):
        pass  # simplified

    def decide_action(self, game_state, available_actions):
        player_id = game_state.get("whose_turn")
        current_room = (game_state.get("current_room") or {}).get(player_id)
        dice_rolled = game_state.get("dice_rolled", False)

        unknown_s = [s for s in SUSPECTS if s not in self.seen_cards]
        unknown_w = [w for w in WEAPONS if w not in self.seen_cards]
        unknown_r = [r for r in ROOMS if r not in self.seen_cards]

        if (len(unknown_s) == 1 and len(unknown_w) == 1 and len(unknown_r) == 1
                and "accuse" in available_actions):
            return {"type": "accuse", "suspect": unknown_s[0],
                    "weapon": unknown_w[0], "room": unknown_r[0]}

        if not dice_rolled and "move" in available_actions:
            fresh = [r for r in unknown_r if r not in self.rooms_suggested_in and r != current_room]
            target = random.choice(fresh) if fresh else random.choice(
                [r for r in ROOMS if r != current_room] or ROOMS
            )
            return {"type": "move", "room": target}

        if current_room and "suggest" in available_actions:
            suspect = random.choice(unknown_s) if unknown_s else random.choice(SUSPECTS)
            weapon = random.choice(unknown_w) if unknown_w else random.choice(WEAPONS)
            self.rooms_suggested_in.add(current_room)
            return {"type": "suggest", "suspect": suspect, "weapon": weapon, "room": current_room}

        return {"type": "end_turn"}

    def decide_show_card(self, matching_cards, suggesting_player_id):
        already_known = self.shown_to.get(suggesting_player_id, set())
        for card in matching_cards:
            if card in already_known:
                return card
        card = random.choice(matching_cards)
        self.shown_to.setdefault(suggesting_player_id, set()).add(card)
        return card


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

MAX_TURNS = 500


async def run_live_test(base_url: str, num_agents: int = 3):
    """Run a full game against the live server."""
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
    state = resp.json()
    print(f"[OK] Game started, first turn: {state['whose_turn']}")

    await asyncio.sleep(0.3)

    # Extract dealt cards from WebSocket messages
    agents: dict[str, SimpleAgent] = {}
    for pid in pids:
        cards_msg = [m for m in ws_messages[pid]
                     if m["type"] == "game_started" and "your_cards" in m]
        assert len(cards_msg) >= 1, f"Player {pid} missing game_started with cards"
        agents[pid] = SimpleAgent()
        agents[pid].observe_own_cards(cards_msg[0]["your_cards"])
        print(f"     {pid}: {len(cards_msg[0]['your_cards'])} cards dealt")

    print(f"[OK] All agents received their cards via WebSocket")
    print()
    print("Playing game...")

    # Step 6: Game loop
    actions_taken = 0
    start_time = time.time()

    while state["status"] == "playing" and actions_taken < MAX_TURNS:
        pending = state.get("pending_show_card")
        if pending:
            pid = pending["player_id"]
            card = agents[pid].decide_show_card(
                pending["matching_cards"],
                pending["suggesting_player_id"],
            )
            resp = await http.post(
                f"/games/{game_id}/action",
                json={"player_id": pid, "action": {"type": "show_card", "card": card}},
            )
            assert resp.status_code == 200, f"show_card failed: {resp.text}"
            agents[pending["suggesting_player_id"]].observe_shown_card(card, shown_by=pid)
        else:
            pid = state["whose_turn"]
            # Get available actions from the game state
            resp = await http.get(f"/games/{game_id}")
            full_state = resp.json()

            # Determine available actions
            avail = _compute_available_actions(pid, full_state)
            action = agents[pid].decide_action(full_state, avail)
            resp = await http.post(
                f"/games/{game_id}/action",
                json={"player_id": pid, "action": action},
            )
            assert resp.status_code == 200, f"Action {action['type']} failed: {resp.text}"
            result = resp.json()

            if action["type"] == "suggest" and result.get("pending_show_by") is None:
                agents[pid].observe_suggestion_no_show(
                    action["suspect"], action["weapon"], action["room"],
                )

        # Give WebSocket messages time to arrive
        await asyncio.sleep(0.05)

        resp = await http.get(f"/games/{game_id}")
        state = resp.json()
        actions_taken += 1

    elapsed = time.time() - start_time

    # Step 7: Verify result
    print()
    assert state["status"] == "finished", f"Game did not finish in {MAX_TURNS} actions"
    print(f"[OK] Game finished in {actions_taken} actions ({elapsed:.1f}s)")
    print(f"     Winner: {state['winner']}")
    print(f"     Turns: {state.get('turn_number', '?')}")

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


def _compute_available_actions(player_id: str, state: dict) -> list[str]:
    """Compute available actions (mirrors game.get_available_actions)."""
    actions = ["chat"]
    if state.get("status") != "playing":
        return actions

    pending = state.get("pending_show_card")
    if pending:
        if pending["player_id"] == player_id:
            actions.append("show_card")
        return actions

    if state.get("whose_turn") != player_id:
        return actions

    dice_rolled = state.get("dice_rolled", False)
    current_room = (state.get("current_room") or {}).get(player_id)
    suggestions_made = bool(state.get("suggestions_this_turn"))

    if not dice_rolled:
        actions.append("move")
    elif current_room and not suggestions_made:
        actions.append("suggest")

    actions.append("accuse")
    actions.append("end_turn")
    return actions


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
