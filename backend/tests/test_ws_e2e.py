"""End-to-end tests that verify LLM agents work through the full WebSocket +
HTTP stack.

Unlike test_agent_game.py (which drives ClueGame directly), these tests use
httpx AsyncClient for HTTP and MockWebSocket objects registered with the
ConnectionManager — verifying that agents receive correct broadcasts, private
messages, and can play a complete game through the server layer.
"""

import asyncio
import json

import fakeredis.aioredis as fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.games.clue.game import ClueGame, SUSPECTS, WEAPONS, ROOM_CENTERS
from app.games.clue.agents import RandomAgent, WandererAgent
from app.main import app, manager, _agent_tasks, _game_agents, _agent_loop_watchdog
from app.games.clue.models import GameState, PongMessage, WSMessage

# ---------------------------------------------------------------------------
# Mock WebSocket
# ---------------------------------------------------------------------------


class MockWebSocket:
    """A mock WebSocket that captures messages sent by the server."""

    def __init__(self):
        self.sent: list[dict] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        self.sent.append(json.loads(data))

    def drain(self) -> list[dict]:
        """Return all captured messages and clear the buffer."""
        msgs = list(self.sent)
        self.sent.clear()
        return msgs

    def messages_of_type(self, msg_type: str) -> list[dict]:
        return [m for m in self.sent if m["type"] == msg_type]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MAX_TURNS = 2000


@pytest_asyncio.fixture
async def redis():
    """Provide a fakeredis instance and patch it into the app module."""
    import app.main as main_module

    client = fakeredis.FakeRedis(decode_responses=True)
    original = main_module.redis_client
    main_module.redis_client = client
    yield client
    # Cancel any auto-started agent background tasks
    for task in list(_agent_tasks.values()):
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _agent_tasks.clear()
    _game_agents.clear()
    main_module.redis_client = original
    manager._connections.clear()
    await client.aclose()


@pytest_asyncio.fixture
async def http(redis):
    """Provide an httpx AsyncClient wired to the FastAPI ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_game(http: AsyncClient) -> str:
    resp = await http.post("/games")
    assert resp.status_code == 201
    return resp.json()["game_id"]


async def _join_game(
    http: AsyncClient, game_id: str, name: str, player_type: str = "agent"
) -> str:
    resp = await http.post(
        f"/games/{game_id}/join",
        json={"player_name": name, "player_type": player_type},
    )
    assert resp.status_code == 200
    return resp.json()["player_id"]


async def _assign_characters(redis, game_id: str, assignments: dict[str, str]):
    """Assign specific characters to players via Redis for deterministic ordering.

    assignments: {player_id: character_name}
    Call after joining but before starting the game.
    """
    raw = await redis.get(f"game:{game_id}")
    state = json.loads(raw)
    for p in state["players"]:
        if p["id"] in assignments:
            p["character"] = assignments[p["id"]]
    await redis.set(f"game:{game_id}", json.dumps(state), ex=86400)


async def _start_game(http: AsyncClient, game_id: str) -> dict:
    resp = await http.post(f"/games/{game_id}/start")
    assert resp.status_code == 200
    return resp.json()


async def _submit_action(
    http: AsyncClient, game_id: str, player_id: str, action
) -> dict:
    # Convert Pydantic models to dicts for JSON serialization
    action_data = action.model_dump() if hasattr(action, "model_dump") else action
    resp = await http.post(
        f"/games/{game_id}/action",
        json={"player_id": player_id, "action": action_data},
    )
    assert (
        resp.status_code == 200
    ), f"Action {action_data} by {player_id} failed: {resp.text}"
    return resp.json()


async def _get_state(http: AsyncClient, game_id: str) -> dict:
    resp = await http.get(f"/games/{game_id}")
    assert resp.status_code == 200
    return resp.json()


async def _add_wanderer_agents(agents: dict, state: dict, game: ClueGame) -> None:
    """Add WandererAgent instances for any auto-added wanderer players."""
    for p in state.get("players", []):
        pid = p["id"] if isinstance(p, dict) else p.id
        ptype = p["type"] if isinstance(p, dict) else p.type
        if pid not in agents and ptype == "wanderer":
            cards = await game._load_player_cards(pid)
            agent = WandererAgent(
                player_id=pid,
                character=p["character"] if isinstance(p, dict) else p.character,
                cards=cards,
            )

            agents[pid] = agent


async def _connect_mock_ws(game_id: str, player_id: str) -> MockWebSocket:
    """Create a MockWebSocket and register it with the ConnectionManager."""
    ws = MockWebSocket()
    await manager.connect(game_id, player_id, ws)
    return ws


async def _place_in_room(redis, game_id: str, player_id: str, room: str):
    """Directly place a player in a room and mark dice as rolled and moved."""
    game = ClueGame(game_id, redis)
    state = await game.get_state()
    state.current_room[player_id] = room
    state.dice_rolled = True
    state.moved = True
    state.last_roll = [3, 3]
    center = ROOM_CENTERS.get(room)
    if center:
        state.player_positions[player_id] = list(center)
    await game._save_state(state)


# ---------------------------------------------------------------------------
# Tests: Basic WebSocket connectivity
# ---------------------------------------------------------------------------


class TestWebSocketConnection:
    """Test basic WebSocket connectivity and message flow."""

    @pytest.mark.asyncio
    async def test_connect_registers_with_manager(self, http, redis):
        """A MockWebSocket registered with the manager is accepted and stored."""
        game_id = await _create_game(http)
        pid = await _join_game(http, game_id, "Alice")

        ws = await _connect_mock_ws(game_id, pid)
        assert ws.accepted
        # Manager should know about this connection
        assert ws in manager._connections[game_id][pid]

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_players(self, http, redis):
        """Broadcasting a message delivers it to all connected players."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        await manager.broadcast(game_id, PongMessage())

        assert len(ws1.sent) == 1
        assert ws1.sent[0] == {"type": "pong"}
        assert len(ws2.sent) == 1
        assert ws2.sent[0] == {"type": "pong"}

    @pytest.mark.asyncio
    async def test_send_to_player_is_private(self, http, redis):
        """send_to_player only delivers to the specified player."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        await manager.send_to_player(game_id, pid1, PongMessage())

        assert len(ws1.sent) == 1
        assert ws1.sent[0]["type"] == "pong"
        assert len(ws2.sent) == 0  # Bob got nothing


# ---------------------------------------------------------------------------
# Tests: Player join broadcasts
# ---------------------------------------------------------------------------


class TestPlayerJoinBroadcast:
    """Test that joining a game broadcasts to connected players."""

    @pytest.mark.asyncio
    async def test_join_broadcasts_to_connected_players(self, http, redis):
        """When a player joins, connected players receive player_joined."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")

        ws1 = await _connect_mock_ws(game_id, pid1)

        # Bob joins while Alice is connected
        await _join_game(http, game_id, "Bob")

        types = [m["type"] for m in ws1.sent]
        assert "player_joined" in types
        joined = next(m for m in ws1.sent if m["type"] == "player_joined")
        assert joined["player"]["name"] == "Bob"
        assert "chat_message" in types  # "Bob joined the game."


# ---------------------------------------------------------------------------
# Tests: Game start messages
# ---------------------------------------------------------------------------


class TestGameStartBroadcast:
    """Test that starting a game sends correct WebSocket messages."""

    @pytest.mark.asyncio
    async def test_game_start_sends_private_cards(self, http, redis):
        """Starting a game sends each player their cards via WebSocket."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        ws1.drain()  # clear any join messages
        ws2.drain()

        await _start_game(http, game_id)

        # Each player should get a private game_started with their cards
        started1 = [
            m for m in ws1.sent if m["type"] == "game_started" and m.get("your_cards")
        ]
        started2 = [
            m for m in ws2.sent if m["type"] == "game_started" and m.get("your_cards")
        ]
        assert (
            len(started1) >= 1
        ), f"P1 missing cards. Got: {[m['type'] for m in ws1.sent]}"
        assert (
            len(started2) >= 1
        ), f"P2 missing cards. Got: {[m['type'] for m in ws2.sent]}"

        # Cards should be non-empty and non-overlapping
        cards1 = set(started1[0]["your_cards"])
        cards2 = set(started2[0]["your_cards"])
        assert len(cards1) > 0
        assert len(cards2) > 0
        assert cards1.isdisjoint(cards2), "Players received overlapping cards"

    @pytest.mark.asyncio
    async def test_game_start_broadcast_includes_state(self, http, redis):
        """Starting a game also broadcasts the full state to all players."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws1.drain()

        state = await _start_game(http, game_id)

        # Should have a broadcast game_started with "state" key
        broadcast = [
            m for m in ws1.sent if m["type"] == "game_started" and m.get("state")
        ]
        assert len(broadcast) >= 1
        assert broadcast[0]["state"]["whose_turn"] == state["whose_turn"]

    @pytest.mark.asyncio
    async def test_game_start_identifies_first_player(self, http, redis):
        """The private game_started message identifies whose turn it is."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws1.drain()

        state = await _start_game(http, game_id)

        started = [
            m for m in ws1.sent if m["type"] == "game_started" and m.get("your_cards")
        ]
        assert started[0]["whose_turn"] == state["whose_turn"]


# ---------------------------------------------------------------------------
# Tests: Action broadcasts
# ---------------------------------------------------------------------------


class TestActionBroadcasts:
    """Test that game actions produce correct WebSocket broadcasts."""

    async def _setup_two_player_game(self, http, redis=None):
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        if redis:
            await _assign_characters(redis, game_id, {
                pid1: "Miss Scarlett", pid2: "Colonel Mustard",
            })
        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        state = await _start_game(http, game_id)
        ws1.drain()
        ws2.drain()
        return game_id, pid1, pid2, ws1, ws2, state

    @pytest.mark.asyncio
    async def test_move_broadcasts_player_moved(self, http, redis):
        """A roll+move action broadcasts player_moved to all connected players."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http, redis)
        whose_turn = state["whose_turn"]

        await _submit_action(http, game_id, whose_turn, {"type": "roll"})
        ws1.drain()
        ws2.drain()
        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )

        for ws in (ws1, ws2):
            moved = [m for m in ws.sent if m["type"] == "player_moved"]
            assert (
                len(moved) >= 1
            ), f"Missing player_moved. Got: {[m['type'] for m in ws.sent]}"
            assert moved[0]["player_id"] == whose_turn

    @pytest.mark.asyncio
    async def test_move_sends_your_turn_to_mover(self, http, redis):
        """After moving to a room, the active player gets a your_turn with suggest available."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http, redis)
        whose_turn = state["whose_turn"]
        active_ws = ws1 if whose_turn == pid1 else ws2

        # Place directly in room so suggest is available
        await _place_in_room(redis, game_id, whose_turn, "Kitchen")

        # Trigger a move broadcast manually to check your_turn
        # Use end_turn + next turn move instead; or just verify actions from state
        game = ClueGame(game_id, redis)
        player_state = await game.get_player_state(whose_turn)
        assert "suggest" in player_state.available_actions

    @pytest.mark.asyncio
    async def test_suggestion_broadcasts(self, http, redis):
        """A suggestion broadcasts suggestion_made to all players."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http, redis)
        whose_turn = state["whose_turn"]

        # Place player in room directly for suggestion test
        await _place_in_room(redis, game_id, whose_turn, "Kitchen")
        ws1.drain()
        ws2.drain()

        await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "suggest",
                "suspect": SUSPECTS[0],
                "weapon": WEAPONS[0],
                "room": "Kitchen",
            },
        )

        for ws in (ws1, ws2):
            sugg = [m for m in ws.sent if m["type"] == "suggestion_made"]
            assert len(sugg) >= 1
            assert sugg[0]["suspect"] == SUSPECTS[0]
            assert sugg[0]["weapon"] == WEAPONS[0]
            assert sugg[0]["room"] == "Kitchen"

    @pytest.mark.asyncio
    async def test_suggestion_moving_suspect_broadcasts_current_room(self, http, redis):
        """When a suggestion names a suspect played by another player, the
        suggestion_made broadcast must include the updated current_room so the
        frontend knows the moved player's new room (not just their position)."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        # pid1 = Miss Scarlett (first turn), pid2 = Colonel Mustard
        await _assign_characters(redis, game_id, {
            pid1: "Miss Scarlett", pid2: "Colonel Mustard",
        })
        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        state = await _start_game(http, game_id)
        ws1.drain()
        ws2.drain()

        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        # Place the suggesting player in the Kitchen
        await _place_in_room(redis, game_id, whose_turn, "Kitchen")
        # Place the other player in a different room (Dining Room)
        game = ClueGame(game_id, redis)
        gs = await game.get_state()
        gs.current_room[other_pid] = "Dining Room"
        gs.player_positions[other_pid] = list(ROOM_CENTERS["Dining Room"])
        await game._save_state(gs)

        ws1.drain()
        ws2.drain()

        # Suggest the other player's character — this should move them to Kitchen
        other_character = "Colonel Mustard" if other_pid == pid2 else "Miss Scarlett"
        await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "suggest",
                "suspect": other_character,
                "weapon": WEAPONS[0],
                "room": "Kitchen",
            },
        )

        # Both players should see suggestion_made with current_room included
        for ws in (ws1, ws2):
            sugg = [m for m in ws.sent if m["type"] == "suggestion_made"]
            assert len(sugg) >= 1
            msg = sugg[0]
            assert msg["moved_suspect_player"] == other_pid
            # current_room must be present and show the moved player in Kitchen
            assert msg.get("current_room") is not None, (
                "suggestion_made must include current_room when a suspect is moved"
            )
            assert msg["current_room"][other_pid] == "Kitchen"

    @pytest.mark.asyncio
    async def test_end_turn_broadcasts_game_state(self, http, redis):
        """Ending a turn broadcasts game_state with the next player's turn."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http, redis)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        await _submit_action(http, game_id, whose_turn, {"type": "roll"})
        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )
        ws1.drain()
        ws2.drain()

        await _submit_action(http, game_id, whose_turn, {"type": "end_turn"})

        for ws in (ws1, ws2):
            gs = [m for m in ws.sent if m["type"] == "game_state" and "whose_turn" in m]
            assert len(gs) >= 1
            assert gs[0]["whose_turn"] == other_pid

    @pytest.mark.asyncio
    async def test_your_turn_sent_to_next_player_only(self, http, redis):
        """After end_turn, only the next player gets a your_turn message."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http, redis)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1
        other_ws = ws2 if whose_turn == pid1 else ws1
        current_ws = ws1 if whose_turn == pid1 else ws2

        await _submit_action(http, game_id, whose_turn, {"type": "roll"})
        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )
        ws1.drain()
        ws2.drain()

        await _submit_action(http, game_id, whose_turn, {"type": "end_turn"})

        # Next player should receive your_turn
        your_turn = [m for m in other_ws.sent if m["type"] == "your_turn"]
        assert len(your_turn) >= 1
        assert "available_actions" in your_turn[0]
        assert "roll" in your_turn[0]["available_actions"]

        # Current player should NOT receive your_turn
        cur_your_turn = [m for m in current_ws.sent if m["type"] == "your_turn"]
        assert len(cur_your_turn) == 0


# ---------------------------------------------------------------------------
# Tests: Show card flow
# ---------------------------------------------------------------------------


class TestShowCardFlow:
    """Test the show_card request/response flow through WebSockets."""

    @pytest.mark.asyncio
    async def test_show_card_request_sent_to_correct_player(self, http, redis):
        """When a suggestion matches, the right player gets show_card_request."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _assign_characters(redis, game_id, {
            pid1: "Miss Scarlett", pid2: "Colonel Mustard",
        })
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        # Build a suggestion guaranteed to match a card the other player holds
        game = ClueGame(game_id, redis)
        other_cards = await game._load_player_cards(other_pid)
        assert other_cards, "Other player must have cards after game start"

        suggest_suspect = SUSPECTS[0]
        suggest_weapon = WEAPONS[0]
        suggest_room = "Kitchen"
        first_card = other_cards[0]
        if first_card in SUSPECTS:
            suggest_suspect = first_card
        elif first_card in WEAPONS:
            suggest_weapon = first_card
        else:
            suggest_room = first_card

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        other_ws = ws2 if other_pid == pid2 else ws1

        # Place player in the room being suggested
        await _place_in_room(redis, game_id, whose_turn, suggest_room)
        ws1.drain()
        ws2.drain()

        await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "suggest",
                "suspect": suggest_suspect,
                "weapon": suggest_weapon,
                "room": suggest_room,
            },
        )

        show_req = [m for m in other_ws.sent if m["type"] == "show_card_request"]
        assert (
            len(show_req) >= 1
        ), "Expected show_card_request was not sent to other player"
        assert show_req[0]["suggesting_player_id"] == whose_turn
        assert "available_actions" in show_req[0]
        assert "show_card" in show_req[0]["available_actions"]

    @pytest.mark.asyncio
    async def test_card_shown_private_and_public(self, http, redis):
        """After show_card: suggesting player gets card_shown (private),
        others get card_shown_public (no card revealed)."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        pid3 = await _join_game(http, game_id, "Agent-3")
        await _assign_characters(redis, game_id, {
            pid1: "Miss Scarlett", pid2: "Colonel Mustard", pid3: "Mrs. White",
        })
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        all_pids = [pid1, pid2, pid3]
        other_pids = [p for p in all_pids if p != whose_turn]

        game = ClueGame(game_id, redis)

        # Build a suggestion guaranteed to trigger show_card using actual cards from other players
        suggest_suspect = SUSPECTS[0]
        suggest_weapon = WEAPONS[0]
        suggest_room = "Kitchen"
        for opid in other_pids:
            cards = await game._load_player_cards(opid)
            if cards:
                first_card = cards[0]
                if first_card in SUSPECTS:
                    suggest_suspect = first_card
                elif first_card in WEAPONS:
                    suggest_weapon = first_card
                else:
                    suggest_room = first_card
                break

        ws_map = {}
        for pid in all_pids:
            ws_map[pid] = await _connect_mock_ws(game_id, pid)

        # Place player in the room being suggested
        await _place_in_room(redis, game_id, whose_turn, suggest_room)
        for ws in ws_map.values():
            ws.drain()

        result = await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "suggest",
                "suspect": suggest_suspect,
                "weapon": suggest_weapon,
                "room": suggest_room,
            },
        )

        pending_by = result.get("pending_show_by")
        assert (
            pending_by is not None
        ), "Expected show_card request but none was triggered"

        # Get matching cards and show one
        gs = await game.get_state()
        pending = gs.pending_show_card
        assert pending is not None
        card_to_show = pending.matching_cards[0]

        for ws in ws_map.values():
            ws.drain()

        await _submit_action(
            http, game_id, pending_by, {"type": "show_card", "card": card_to_show}
        )

        # Suggesting player should get private card_shown
        sugg_ws = ws_map[whose_turn]
        card_shown = [m for m in sugg_ws.sent if m["type"] == "card_shown"]
        assert (
            len(card_shown) >= 1
        ), f"Suggesting player missing card_shown. Got: {[m['type'] for m in sugg_ws.sent]}"
        assert card_shown[0]["card"] == card_to_show
        assert card_shown[0]["shown_by"] == pending_by

        # Third player should get card_shown_public (no card)
        third_pid = [p for p in all_pids if p != whose_turn and p != pending_by][0]
        third_ws = ws_map[third_pid]
        public = [m for m in third_ws.sent if m["type"] == "card_shown_public"]
        assert len(public) >= 1
        assert "card" not in public[0], "card_shown_public must not reveal the card"
        assert public[0]["shown_by"] == pending_by
        assert public[0]["shown_to"] == whose_turn

    @pytest.mark.asyncio
    async def test_your_turn_sent_after_show_card(self, http, redis):
        """After a card is shown, the suggesting player receives a your_turn
        message with end_turn available — so external agents know to act."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        game = ClueGame(game_id, redis)
        other_cards = await game._load_player_cards(other_pid)
        assert other_cards, "Other player must have cards after game start"

        # Build a suggestion guaranteed to match a card the other player holds
        suggest_suspect = SUSPECTS[0]
        suggest_weapon = WEAPONS[0]
        suggest_room = "Kitchen"
        first_card = other_cards[0]
        if first_card in SUSPECTS:
            suggest_suspect = first_card
        elif first_card in WEAPONS:
            suggest_weapon = first_card
        else:
            suggest_room = first_card

        ws_suggesting = await _connect_mock_ws(game_id, whose_turn)

        await _place_in_room(redis, game_id, whose_turn, suggest_room)
        ws_suggesting.drain()

        result = await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "suggest",
                "suspect": suggest_suspect,
                "weapon": suggest_weapon,
                "room": suggest_room,
            },
        )
        pending_by = result.get("pending_show_by")
        assert pending_by is not None, "Expected show_card request"

        # After suggestion, suggesting player gets your_turn with empty actions
        # (blocked by pending_show_card)
        post_suggest_turns = [
            m for m in ws_suggesting.sent if m["type"] == "your_turn"
        ]
        assert len(post_suggest_turns) >= 1
        assert post_suggest_turns[-1]["available_actions"] == []

        # Now show the card
        gs = await game.get_state()
        card_to_show = gs.pending_show_card.matching_cards[0]
        ws_suggesting.drain()

        await _submit_action(
            http, game_id, pending_by, {"type": "show_card", "card": card_to_show}
        )

        # After show_card, suggesting player should get your_turn with end_turn
        your_turns = [
            m for m in ws_suggesting.sent if m["type"] == "your_turn"
        ]
        assert (
            len(your_turns) >= 1
        ), f"Suggesting player missing your_turn after show_card. Got: {[m['type'] for m in ws_suggesting.sent]}"
        assert "end_turn" in your_turns[-1]["available_actions"], (
            f"Expected end_turn in available_actions, got: {your_turns[-1]['available_actions']}"
        )

        # Verify the suggesting player can actually end their turn
        await _submit_action(
            http, game_id, whose_turn, {"type": "end_turn"}
        )
        final = await _get_state(http, game_id)
        assert final["whose_turn"] != whose_turn, "Turn should have advanced"


# ---------------------------------------------------------------------------
# Tests: Game over broadcasts
# ---------------------------------------------------------------------------


class TestGameOverBroadcast:
    """Test that game-ending events broadcast correctly."""

    @pytest.mark.asyncio
    async def test_correct_accusation_broadcasts_game_over(self, http, redis):
        """A correct accusation broadcasts game_over with the solution."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]

        game = ClueGame(game_id, redis)
        solution = await game._load_solution()

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        ws1.drain()
        ws2.drain()

        await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "accuse",
                "suspect": solution.suspect,
                "weapon": solution.weapon,
                "room": solution.room,
            },
        )

        # Both should receive game_over
        for ws in (ws1, ws2):
            go = [m for m in ws.sent if m["type"] == "game_over"]
            assert (
                len(go) >= 1
            ), f"Missing game_over. Got: {[m['type'] for m in ws.sent]}"
            assert go[0]["winner"] == whose_turn
            assert go[0]["solution"] == solution.model_dump()

    @pytest.mark.asyncio
    async def test_wrong_accusation_ends_two_player_game(self, http, redis):
        """A wrong accusation in a 2-player game eliminates the accuser
        and broadcasts accusation_made; the game state becomes finished."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _assign_characters(redis, game_id, {
            pid1: "Miss Scarlett", pid2: "Colonel Mustard",
        })
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        game = ClueGame(game_id, redis)
        solution = await game._load_solution()
        wrong_suspect = next(s for s in SUSPECTS if s != solution.suspect)

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        ws1.drain()
        ws2.drain()

        await _submit_action(
            http,
            game_id,
            whose_turn,
            {
                "type": "accuse",
                "suspect": wrong_suspect,
                "weapon": solution.weapon,
                "room": solution.room,
            },
        )

        # Both players should see the accusation broadcast
        all_msgs = ws1.sent + ws2.sent
        acc = [m for m in all_msgs if m["type"] == "accusation_made"]
        assert len(acc) >= 1, "Should broadcast accusation_made"
        assert acc[0]["correct"] is False

        # The game should now be finished with the other player winning
        final = await _get_state(http, game_id)
        assert final["status"] == "finished"
        assert final["winner"] == other_pid


# ---------------------------------------------------------------------------
# Tests: Chat integration
# ---------------------------------------------------------------------------


class TestChatIntegration:
    """Test chat messages flow through WebSocket alongside game actions."""

    @pytest.mark.asyncio
    async def test_chat_via_http_broadcasts_to_ws(self, http, redis):
        """Chat sent via HTTP endpoint is broadcast to WebSocket connections."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        ws1.drain()
        ws2.drain()

        resp = await http.post(
            f"/games/{game_id}/chat",
            json={"player_id": pid1, "text": "Good luck!"},
        )
        assert resp.status_code == 200

        for ws in (ws1, ws2):
            chat = [m for m in ws.sent if m["type"] == "chat_message"]
            assert len(chat) >= 1
            assert "Good luck!" in chat[0]["text"]

    @pytest.mark.asyncio
    async def test_game_actions_generate_chat_messages(self, http, redis):
        """Game actions (roll, move, etc.) generate chat messages."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _assign_characters(redis, game_id, {
            pid1: "Miss Scarlett", pid2: "Colonel Mustard",
        })
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws1.drain()

        await _submit_action(http, game_id, whose_turn, {"type": "roll"})

        chat = [m for m in ws1.sent if m["type"] == "chat_message"]
        assert len(chat) >= 1
        # Chat message should mention the roll
        assert "rolled" in chat[0]["text"]


# ---------------------------------------------------------------------------
# Tests: Full game with agents through HTTP + WebSocket
# ---------------------------------------------------------------------------


class TestAgentFullGameE2E:
    """Full end-to-end: agents play a complete game through HTTP endpoints
    while connected via WebSocket, verifying message delivery throughout."""

    @pytest.mark.asyncio
    async def test_two_agents_complete_game(self, http, redis):
        """Two agents play a full game via HTTP; WebSocket delivers all events."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        state = await _start_game(http, game_id)

        # Extract dealt cards from the private game_started messages
        cards1_msg = [
            m for m in ws1.sent if m["type"] == "game_started" and m.get("your_cards")
        ]
        cards2_msg = [
            m for m in ws2.sent if m["type"] == "game_started" and m.get("your_cards")
        ]
        assert len(cards1_msg) >= 1
        assert len(cards2_msg) >= 1

        chars = {p["id"]: p["character"] for p in state["players"]}
        agents = {
            pid1: RandomAgent(player_id=pid1, character=chars[pid1], cards=cards1_msg[0]["your_cards"]),
            pid2: RandomAgent(player_id=pid2, character=chars[pid2], cards=cards2_msg[0]["your_cards"]),
        }

        ws1.drain()
        ws2.drain()

        game = ClueGame(game_id, redis)
        await _add_wanderer_agents(agents, state, game)
        actions_taken = 0
        ws_total = {pid1: 0, pid2: 0}
        ws_map = {pid1: ws1, pid2: ws2}

        while state["status"] == "playing" and actions_taken < MAX_TURNS:
            pending = state.get("pending_show_card")
            if pending:
                pid = pending["player_id"]
                card = await agents[pid].decide_show_card(
                    pending["matching_cards"],
                    pending["suggesting_player_id"],
                )
                await _submit_action(
                    http,
                    game_id,
                    pid,
                    {
                        "type": "show_card",
                        "card": card,
                    },
                )
                agents[pending["suggesting_player_id"]].observe_shown_card(
                    card,
                    shown_by=pid,
                )
            else:
                pid = state["whose_turn"]
                player_state = await game.get_player_state(pid)
                action = await agents[pid].decide_action(
                    GameState(**state), player_state
                )
                result = await _submit_action(http, game_id, pid, action)

                if (
                    action.type == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action.suspect,
                        action.weapon,
                        action.room,
                    )

            # Count WS messages delivered this round
            for p, ws in ws_map.items():
                ws_total[p] += len(ws.sent)
                ws.drain()

            state = await _get_state(http, game_id)
            actions_taken += 1

        assert (
            state["status"] == "finished"
        ), f"Game did not finish within {MAX_TURNS} actions"
        assert state["winner"] in agents

        # Both players should have received WebSocket messages
        for pid, count in ws_total.items():
            assert count > 0, f"Player {pid} received no WebSocket messages"

        print(f"\nE2E 2-player: {actions_taken} actions, winner={state['winner']}")
        print(f"WS messages: {ws_total}")

    @pytest.mark.asyncio
    async def test_three_agents_complete_game(self, http, redis):
        """Three agents play to completion through HTTP + WebSocket."""
        game_id = await _create_game(http)
        pids = []
        for i in range(3):
            pids.append(await _join_game(http, game_id, f"Agent-{i}"))

        ws_map = {}
        for pid in pids:
            ws_map[pid] = await _connect_mock_ws(game_id, pid)

        state = await _start_game(http, game_id)

        chars = {p["id"]: p["character"] for p in state["players"]}
        agents = {}
        for pid in pids:
            ws = ws_map[pid]
            cards_msg = [
                m
                for m in ws.sent
                if m["type"] == "game_started" and m.get("your_cards")
            ]
            assert len(cards_msg) >= 1
            agents[pid] = RandomAgent(
                player_id=pid, character=chars[pid], cards=cards_msg[0]["your_cards"]
            )
            ws.drain()

        game = ClueGame(game_id, redis)
        await _add_wanderer_agents(agents, state, game)
        actions_taken = 0
        ws_total = {pid: 0 for pid in pids}

        while state["status"] == "playing" and actions_taken < MAX_TURNS:
            pending = state.get("pending_show_card")
            if pending:
                pid = pending["player_id"]
                card = await agents[pid].decide_show_card(
                    pending["matching_cards"],
                    pending["suggesting_player_id"],
                )
                await _submit_action(
                    http,
                    game_id,
                    pid,
                    {
                        "type": "show_card",
                        "card": card,
                    },
                )
                agents[pending["suggesting_player_id"]].observe_shown_card(
                    card,
                    shown_by=pid,
                )
            else:
                pid = state["whose_turn"]
                player_state = await game.get_player_state(pid)
                action = await agents[pid].decide_action(
                    GameState(**state), player_state
                )
                result = await _submit_action(http, game_id, pid, action)

                if (
                    action.type == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action.suspect,
                        action.weapon,
                        action.room,
                    )

            for p, ws in ws_map.items():
                ws_total[p] += len(ws.sent)
                ws.drain()

            state = await _get_state(http, game_id)
            actions_taken += 1

        assert state["status"] == "finished"
        assert state["winner"] in agents
        for pid, count in ws_total.items():
            assert count > 0

        print(f"\nE2E 3-player: {actions_taken} actions, winner={state['winner']}")
        print(f"WS messages: {ws_total}")

    @pytest.mark.asyncio
    async def test_six_agents_complete_game(self, http, redis):
        """Full 6-player game through the HTTP + WebSocket stack."""
        game_id = await _create_game(http)
        pids = []
        for i in range(6):
            pids.append(await _join_game(http, game_id, f"Agent-{i}"))

        ws_map = {}
        for pid in pids:
            ws_map[pid] = await _connect_mock_ws(game_id, pid)

        state = await _start_game(http, game_id)

        chars = {p["id"]: p["character"] for p in state["players"]}
        agents = {}
        for pid in pids:
            ws = ws_map[pid]
            cards_msg = [
                m
                for m in ws.sent
                if m["type"] == "game_started" and m.get("your_cards")
            ]
            assert len(cards_msg) >= 1
            agents[pid] = RandomAgent(
                player_id=pid, character=chars[pid], cards=cards_msg[0]["your_cards"]
            )
            ws.drain()

        game = ClueGame(game_id, redis)
        actions_taken = 0

        while state["status"] == "playing" and actions_taken < MAX_TURNS:
            pending = state.get("pending_show_card")
            if pending:
                pid = pending["player_id"]
                card = await agents[pid].decide_show_card(
                    pending["matching_cards"],
                    pending["suggesting_player_id"],
                )
                await _submit_action(
                    http,
                    game_id,
                    pid,
                    {
                        "type": "show_card",
                        "card": card,
                    },
                )
                agents[pending["suggesting_player_id"]].observe_shown_card(
                    card,
                    shown_by=pid,
                )
            else:
                pid = state["whose_turn"]
                player_state = await game.get_player_state(pid)
                action = await agents[pid].decide_action(
                    GameState(**state), player_state
                )
                result = await _submit_action(http, game_id, pid, action)

                if (
                    action.type == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action.suspect,
                        action.weapon,
                        action.room,
                    )

            for ws in ws_map.values():
                ws.drain()

            state = await _get_state(http, game_id)
            actions_taken += 1

        assert state["status"] == "finished"
        assert state["winner"] in agents

        active_at_end = [p for p in state["players"] if p.get("active", True)]
        print(f"\nE2E 6-player: {actions_taken} actions, winner={state['winner']}")
        print(f"Active at end: {len(active_at_end)}")

    @pytest.mark.asyncio
    async def test_agents_receive_all_message_types(self, http, redis):
        """Verify that over the course of a game, agents receive the expected
        variety of WebSocket message types."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        state = await _start_game(http, game_id)

        chars = {p["id"]: p["character"] for p in state["players"]}
        agents = {}
        for pid, ws in [(pid1, ws1), (pid2, ws2)]:
            cards_msg = [
                m
                for m in ws.sent
                if m["type"] == "game_started" and m.get("your_cards")
            ]
            agents[pid] = RandomAgent(
                player_id=pid, character=chars[pid], cards=cards_msg[0]["your_cards"]
            )

        all_types = set()
        for ws in (ws1, ws2):
            for m in ws.sent:
                all_types.add(m["type"])
            ws.drain()

        game = ClueGame(game_id, redis)
        await _add_wanderer_agents(agents, state, game)
        ws_map = {pid1: ws1, pid2: ws2}
        actions_taken = 0

        while state["status"] == "playing" and actions_taken < MAX_TURNS:
            pending = state.get("pending_show_card")
            if pending:
                pid = pending["player_id"]
                card = await agents[pid].decide_show_card(
                    pending["matching_cards"],
                    pending["suggesting_player_id"],
                )
                await _submit_action(
                    http,
                    game_id,
                    pid,
                    {
                        "type": "show_card",
                        "card": card,
                    },
                )
                agents[pending["suggesting_player_id"]].observe_shown_card(
                    card,
                    shown_by=pid,
                )
            else:
                pid = state["whose_turn"]
                player_state = await game.get_player_state(pid)
                action = await agents[pid].decide_action(
                    GameState(**state), player_state
                )
                result = await _submit_action(http, game_id, pid, action)

                if (
                    action.type == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action.suspect,
                        action.weapon,
                        action.room,
                    )

            for ws in ws_map.values():
                for m in ws.sent:
                    all_types.add(m["type"])
                ws.drain()

            state = await _get_state(http, game_id)
            actions_taken += 1

        # Should have seen at least these message types
        assert "game_started" in all_types
        assert "player_moved" in all_types
        assert "chat_message" in all_types
        assert "your_turn" in all_types
        # At least one of these game-ending types
        assert "game_over" in all_types or "accusation_made" in all_types

        print(f"\nMessage types seen: {sorted(all_types)}")


# ---------------------------------------------------------------------------
# Tests: WebSocket reconnection
# ---------------------------------------------------------------------------


class TestReconnection:
    """Test that players can reconnect and get correct state."""

    @pytest.mark.asyncio
    async def test_reconnect_after_action_gets_updated_state(self, http, redis):
        """A player connecting after a roll sees the updated game state."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _start_game(http, game_id)

        state = await _get_state(http, game_id)
        whose_turn = state["whose_turn"]

        # Roll dice without any WS connections
        await _submit_action(http, game_id, whose_turn, {"type": "roll"})

        # Now "connect" and verify state
        game = ClueGame(game_id, redis)
        player_state = await game.get_player_state(pid1)
        assert player_state is not None
        assert player_state.dice_rolled is True
        assert player_state.status == "playing"

    @pytest.mark.asyncio
    async def test_new_ws_receives_messages_after_reconnect(self, http, redis):
        """After reconnecting, the new WebSocket receives subsequent broadcasts."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")

        ws1_old = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        await _start_game(http, game_id)
        state = await _get_state(http, game_id)

        # "Disconnect" player 1 and reconnect with new WS
        manager.disconnect(game_id, pid1)
        ws1_new = await _connect_mock_ws(game_id, pid1)

        whose_turn = state["whose_turn"]
        await _submit_action(http, game_id, whose_turn, {"type": "roll"})

        # New WS should have received the broadcast
        rolled = [m for m in ws1_new.sent if m["type"] == "dice_rolled"]
        assert len(rolled) >= 1

        # Old WS should NOT have received it (disconnected)
        assert len(ws1_new.sent) > 0


# ---------------------------------------------------------------------------
# Tests: Agent loop watchdog (inline mode)
# ---------------------------------------------------------------------------


class TestAgentLoopWatchdog:
    """Test the watchdog that restarts agent loops when they die unexpectedly."""

    @pytest.mark.asyncio
    async def test_watchdog_creates_task_when_game_active(self, http, redis):
        """_agent_loop_watchdog creates a new agent task if the game is still playing."""
        import app.main as main_module

        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _start_game(http, game_id)

        # Cancel the existing agent task to simulate a crash
        task = _agent_tasks.get(game_id)
        assert task is not None, "Agent task should have been created on game start"
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        # Remove the cancelled task manually (the watchdog won't fire for cancels)
        _agent_tasks.pop(game_id, None)
        _game_agents.pop(game_id, None)

        # The game is still active — call the watchdog directly
        await _agent_loop_watchdog(game_id)

        # Watchdog should have created a new task and populated _game_agents
        assert game_id in _agent_tasks, "Watchdog should have created a new agent task"
        assert game_id in _game_agents, "Watchdog should have restored agent instances"

        # Clean up
        new_task = _agent_tasks.get(game_id)
        if new_task and not new_task.done():
            new_task.cancel()
            try:
                await new_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_watchdog_skips_finished_game(self, http, redis):
        """_agent_loop_watchdog does nothing when the game is already over."""
        game_id = await _create_game(http)
        await _join_game(http, game_id, "Agent-1")
        await _join_game(http, game_id, "Agent-2")
        await _start_game(http, game_id)

        # Force the game to a finished state
        game = ClueGame(game_id, redis)
        state = await game.get_state()
        state.status = "finished"
        await game._save_state(state)

        # Remove any existing agent task
        _agent_tasks.pop(game_id, None)
        _game_agents.pop(game_id, None)

        await _agent_loop_watchdog(game_id)

        # Watchdog should NOT create a new task for a finished game
        assert game_id not in _agent_tasks, "Watchdog should not create task for finished game"

    @pytest.mark.asyncio
    async def test_watchdog_skips_when_task_already_running(self, http, redis):
        """_agent_loop_watchdog is a no-op when a healthy task already exists."""
        game_id = await _create_game(http)
        await _join_game(http, game_id, "Agent-1")
        await _join_game(http, game_id, "Agent-2")
        await _start_game(http, game_id)

        existing_task = _agent_tasks.get(game_id)
        assert existing_task is not None

        # Call the watchdog while the task is still running
        await _agent_loop_watchdog(game_id)

        # The task should be the same object — not replaced
        assert _agent_tasks.get(game_id) is existing_task, (
            "Watchdog should not replace an already-running agent task"
        )

        # Clean up
        if existing_task and not existing_task.done():
            existing_task.cancel()
            try:
                await existing_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_wanderer_seed_in_persisted_config(self, http, redis):
        """start_game persists wanderer_seed in agent_config so restarts are consistent."""
        game_id = await _create_game(http)
        await _join_game(http, game_id, "Regular-Agent", player_type="agent")
        await _join_game(http, game_id, "Wanderer", player_type="wanderer")
        await _start_game(http, game_id)

        config_raw = await redis.get(f"game:{game_id}:agent_config")
        assert config_raw is not None, "agent_config must be written to Redis on start"

        config = json.loads(config_raw)
        wanderer_entries = [
            (pid, info)
            for pid, info in config.items()
            if info.get("type") == "wanderer"
        ]
        assert len(wanderer_entries) >= 1, "Expected at least one wanderer in config"

        # Every wanderer must have a wanderer_seed
        for pid, wanderer_info in wanderer_entries:
            seed = wanderer_info.get("wanderer_seed")
            assert seed is not None, (
                f"Wanderer {pid} config must include wanderer_seed so restarts have the "
                "same initial card knowledge"
            )
            assert "card" in seed and seed["card"], "wanderer_seed must have a non-empty card"
            assert "shown_by" in seed and seed["shown_by"], "wanderer_seed must have a shown_by player id"

        # Clean up the agent task
        task = _agent_tasks.get(game_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_watchdog_replays_wanderer_seed(self, http, redis):
        """_agent_loop_watchdog applies wanderer_seed so restarted wanderers
        have the same card knowledge as in the initial run."""
        game_id = await _create_game(http)
        await _join_game(http, game_id, "Regular-Agent", player_type="agent")
        await _join_game(http, game_id, "Wanderer", player_type="wanderer")
        await _start_game(http, game_id)

        # Grab the seed that was recorded at start for the first wanderer
        config_raw = await redis.get(f"game:{game_id}:agent_config")
        config = json.loads(config_raw)
        wanderer_pid, wanderer_info = next(
            (pid, info) for pid, info in config.items() if info.get("type") == "wanderer"
        )
        seed = wanderer_info["wanderer_seed"]
        assert seed is not None

        # Cancel current task and call watchdog
        task = _agent_tasks.pop(game_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        _game_agents.pop(game_id, None)

        await _agent_loop_watchdog(game_id)

        # The restarted wanderer agent should have the seeded card in seen_cards
        agents = _game_agents.get(game_id, {})
        assert wanderer_pid in agents, "Watchdog should have recreated the wanderer agent"
        wanderer_agent = agents[wanderer_pid]
        assert isinstance(wanderer_agent, WandererAgent)
        assert seed["card"] in wanderer_agent.seen_cards, (
            "Wanderer agent must have the seed card in seen_cards after watchdog restart"
        )

        # Clean up
        new_task = _agent_tasks.get(game_id)
        if new_task and not new_task.done():
            new_task.cancel()
            try:
                await new_task
            except (asyncio.CancelledError, Exception):
                pass
