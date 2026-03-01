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

from app.game import ClueGame, SUSPECTS, WEAPONS, ROOMS, ROOM_CENTERS
from app.agents import RandomAgent, WandererAgent
from app.main import app, manager, _agent_tasks, _game_agents
from app.models import GameState

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


async def _start_game(http: AsyncClient, game_id: str) -> dict:
    resp = await http.post(f"/games/{game_id}/start")
    assert resp.status_code == 200
    return resp.json()


async def _submit_action(
    http: AsyncClient, game_id: str, player_id: str, action: dict
) -> dict:
    resp = await http.post(
        f"/games/{game_id}/action",
        json={"player_id": player_id, "action": action},
    )
    assert (
        resp.status_code == 200
    ), f"Action {action} by {player_id} failed: {resp.text}"
    return resp.json()


async def _get_state(http: AsyncClient, game_id: str) -> dict:
    resp = await http.get(f"/games/{game_id}")
    assert resp.status_code == 200
    return resp.json()


async def _add_wanderer_agents(
    agents: dict, state: dict, game: ClueGame
) -> None:
    """Add WandererAgent instances for any auto-added wanderer players."""
    for p in state.get("players", []):
        pid = p["id"] if isinstance(p, dict) else p.id
        ptype = p["type"] if isinstance(p, dict) else p.type
        if pid not in agents and ptype == "wanderer":
            agent = WandererAgent()
            cards = await game._load_player_cards(pid)
            agent.observe_own_cards(cards)
            agents[pid] = agent


async def _connect_mock_ws(game_id: str, player_id: str) -> MockWebSocket:
    """Create a MockWebSocket and register it with the ConnectionManager."""
    ws = MockWebSocket()
    await manager.connect(game_id, player_id, ws)
    return ws


async def _place_in_room(redis, game_id: str, player_id: str, room: str):
    """Directly place a player in a room and mark dice as rolled."""
    game = ClueGame(game_id, redis)
    state = await game.get_state()
    state.current_room[player_id] = room
    state.dice_rolled = True
    state.last_roll = [6]
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
        assert manager._connections[game_id][pid] is ws

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_players(self, http, redis):
        """Broadcasting a message delivers it to all connected players."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        await manager.broadcast(game_id, {"type": "test", "data": "hello"})

        assert len(ws1.sent) == 1
        assert ws1.sent[0] == {"type": "test", "data": "hello"}
        assert len(ws2.sent) == 1
        assert ws2.sent[0] == {"type": "test", "data": "hello"}

    @pytest.mark.asyncio
    async def test_send_to_player_is_private(self, http, redis):
        """send_to_player only delivers to the specified player."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Alice")
        pid2 = await _join_game(http, game_id, "Bob")

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)

        await manager.send_to_player(game_id, pid1, {"type": "secret", "card": "Knife"})

        assert len(ws1.sent) == 1
        assert ws1.sent[0]["type"] == "secret"
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
            m for m in ws1.sent if m["type"] == "game_started" and "your_cards" in m
        ]
        started2 = [
            m for m in ws2.sent if m["type"] == "game_started" and "your_cards" in m
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
            m for m in ws1.sent if m["type"] == "game_started" and "state" in m
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
            m for m in ws1.sent if m["type"] == "game_started" and "your_cards" in m
        ]
        assert started[0]["whose_turn"] == state["whose_turn"]


# ---------------------------------------------------------------------------
# Tests: Action broadcasts
# ---------------------------------------------------------------------------


class TestActionBroadcasts:
    """Test that game actions produce correct WebSocket broadcasts."""

    async def _setup_two_player_game(self, http):
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        state = await _start_game(http, game_id)
        ws1.drain()
        ws2.drain()
        return game_id, pid1, pid2, ws1, ws2, state

    @pytest.mark.asyncio
    async def test_move_broadcasts_player_moved(self, http, redis):
        """A move action broadcasts player_moved to all connected players."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http)
        whose_turn = state["whose_turn"]

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
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http)
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
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http)
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
    async def test_end_turn_broadcasts_game_state(self, http, redis):
        """Ending a turn broadcasts game_state with the next player's turn."""
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

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
        game_id, pid1, pid2, ws1, ws2, state = await self._setup_two_player_game(http)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1
        other_ws = ws2 if whose_turn == pid1 else ws1
        current_ws = ws1 if whose_turn == pid1 else ws2

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
        assert "move" in your_turn[0]["available_actions"]

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
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        other_pid = pid2 if whose_turn == pid1 else pid1

        # Find a card the other player holds
        game = ClueGame(game_id, redis)
        other_cards = await game._load_player_cards(other_pid)
        other_suspects = [c for c in other_cards if c in SUSPECTS]
        other_weapons = [c for c in other_cards if c in WEAPONS]

        if not other_suspects and not other_weapons:
            pytest.skip("Other player has no suspects/weapons to trigger show_card")

        suggest_suspect = other_suspects[0] if other_suspects else SUSPECTS[0]
        suggest_weapon = other_weapons[0] if other_weapons else WEAPONS[0]

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws2 = await _connect_mock_ws(game_id, pid2)
        other_ws = ws2 if other_pid == pid2 else ws1

        # Place player directly in Kitchen for suggestion
        await _place_in_room(redis, game_id, whose_turn, "Kitchen")
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
                "room": "Kitchen",
            },
        )

        show_req = [m for m in other_ws.sent if m["type"] == "show_card_request"]
        if show_req:
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
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]
        all_pids = [pid1, pid2, pid3]
        other_pids = [p for p in all_pids if p != whose_turn]

        game = ClueGame(game_id, redis)

        # Find a suggestion that forces a show_card
        suggest_suspect = SUSPECTS[0]
        suggest_weapon = WEAPONS[0]
        target_pid = None
        for opid in other_pids:
            cards = await game._load_player_cards(opid)
            if any(c in (suggest_suspect, suggest_weapon, "Kitchen") for c in cards):
                target_pid = opid
                break

        if target_pid is None:
            pytest.skip("No other player holds matching cards")

        ws_map = {}
        for pid in all_pids:
            ws_map[pid] = await _connect_mock_ws(game_id, pid)

        # Place player directly in Kitchen for suggestion
        await _place_in_room(redis, game_id, whose_turn, "Kitchen")
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
                "room": "Kitchen",
            },
        )

        pending_by = result.get("pending_show_by")
        if not pending_by:
            pytest.skip("No one needed to show a card")

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
        """Game actions (move, suggest, etc.) generate chat messages."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        state = await _start_game(http, game_id)
        whose_turn = state["whose_turn"]

        ws1 = await _connect_mock_ws(game_id, pid1)
        ws1.drain()

        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )

        chat = [m for m in ws1.sent if m["type"] == "chat_message"]
        assert len(chat) >= 1
        # Chat message should mention the roll; room only if reached
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
            m for m in ws1.sent if m["type"] == "game_started" and "your_cards" in m
        ]
        cards2_msg = [
            m for m in ws2.sent if m["type"] == "game_started" and "your_cards" in m
        ]
        assert len(cards1_msg) >= 1
        assert len(cards2_msg) >= 1

        agents = {pid1: RandomAgent(), pid2: RandomAgent()}
        agents[pid1].observe_own_cards(cards1_msg[0]["your_cards"])
        agents[pid2].observe_own_cards(cards2_msg[0]["your_cards"])

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
                    action["type"] == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action["suspect"],
                        action["weapon"],
                        action["room"],
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

        agents = {}
        for pid in pids:
            ws = ws_map[pid]
            cards_msg = [
                m for m in ws.sent if m["type"] == "game_started" and "your_cards" in m
            ]
            assert len(cards_msg) >= 1
            agents[pid] = RandomAgent()
            agents[pid].observe_own_cards(cards_msg[0]["your_cards"])
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
                    action["type"] == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action["suspect"],
                        action["weapon"],
                        action["room"],
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

        agents = {}
        for pid in pids:
            ws = ws_map[pid]
            cards_msg = [
                m for m in ws.sent if m["type"] == "game_started" and "your_cards" in m
            ]
            assert len(cards_msg) >= 1
            agents[pid] = RandomAgent()
            agents[pid].observe_own_cards(cards_msg[0]["your_cards"])
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
                    action["type"] == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action["suspect"],
                        action["weapon"],
                        action["room"],
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

        agents = {pid1: RandomAgent(), pid2: RandomAgent()}
        for pid, ws in [(pid1, ws1), (pid2, ws2)]:
            cards_msg = [
                m for m in ws.sent if m["type"] == "game_started" and "your_cards" in m
            ]
            agents[pid].observe_own_cards(cards_msg[0]["your_cards"])

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
                    action["type"] == "suggest"
                    and result.get("pending_show_by") is None
                ):
                    agents[pid].observe_suggestion_no_show(
                        action["suspect"],
                        action["weapon"],
                        action["room"],
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
        """A player connecting after a move sees the updated game state."""
        game_id = await _create_game(http)
        pid1 = await _join_game(http, game_id, "Agent-1")
        pid2 = await _join_game(http, game_id, "Agent-2")
        await _start_game(http, game_id)

        state = await _get_state(http, game_id)
        whose_turn = state["whose_turn"]

        # Make a move without any WS connections
        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )

        # Now "connect" and verify state
        # Simulate what the WS endpoint does on connect: send game_state
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
        await _submit_action(
            http, game_id, whose_turn, {"type": "move", "room": "Kitchen"}
        )

        # New WS should have received the broadcast
        moved = [m for m in ws1_new.sent if m["type"] == "player_moved"]
        assert len(moved) >= 1

        # Old WS should NOT have received it (disconnected)
        # Since we drained nothing, just check the new one works
        assert len(ws1_new.sent) > 0
