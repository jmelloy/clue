"""Tests for Clue game logic using fakeredis (no real Redis required)."""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.game import ClueGame, SUSPECTS, WEAPONS, ROOMS, ALL_CARDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def game(redis):
    g = ClueGame("TESTGAME", redis)
    await g.create()
    return g


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_two_players(game: ClueGame):
    p1 = await game.add_player("P1", "Alice", "human")
    p2 = await game.add_player("P2", "Bob", "human")
    return p1, p2


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_game(redis):
    g = ClueGame("NEWGAME", redis)
    state = await g.create()

    assert state["game_id"] == "NEWGAME"
    assert state["status"] == "waiting"
    assert state["players"] == []

    # Solution stored separately and valid
    solution = await g._load_solution()
    assert solution["suspect"] in SUSPECTS
    assert solution["weapon"] in WEAPONS
    assert solution["room"] in ROOMS


@pytest.mark.asyncio
async def test_add_players(game: ClueGame):
    p1, p2 = await _add_two_players(game)

    state = await game.get_state()
    assert len(state["players"]) == 2
    assert state["players"][0]["name"] == "Alice"
    assert state["players"][1]["name"] == "Bob"
    # Characters assigned and unique
    chars = {p["character"] for p in state["players"]}
    assert len(chars) == 2
    assert all(c in SUSPECTS for c in chars)


@pytest.mark.asyncio
async def test_cannot_join_started_game(game: ClueGame):
    await _add_two_players(game)
    await game.start()
    with pytest.raises(ValueError, match="already started"):
        await game.add_player("P3", "Charlie", "human")


@pytest.mark.asyncio
async def test_start_game_deals_cards(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    assert state["status"] == "playing"
    assert state["whose_turn"] in ("P1", "P2")

    solution = await game._load_solution()
    solution_cards = {solution["suspect"], solution["weapon"], solution["room"]}

    p1_cards = await game._load_player_cards("P1")
    p2_cards = await game._load_player_cards("P2")

    all_dealt = set(p1_cards) | set(p2_cards)

    # No solution card should be dealt
    assert all_dealt.isdisjoint(solution_cards)

    # All non-solution cards dealt
    expected = set(ALL_CARDS) - solution_cards
    assert all_dealt == expected

    # Each player has some cards
    assert len(p1_cards) > 0
    assert len(p2_cards) > 0


@pytest.mark.asyncio
async def test_start_requires_two_players(game: ClueGame):
    await game.add_player("P1", "Alice", "human")
    with pytest.raises(ValueError, match="at least 2"):
        await game.start()


@pytest.mark.asyncio
async def test_make_suggestion(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state["whose_turn"]
    other_id = "P2" if whose_turn == "P1" else "P1"

    # Move to a room first
    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    # Give the other player a known card
    other_cards = await game._load_player_cards(other_id)

    if other_cards:
        # Make a suggestion using one of their cards
        card = other_cards[0]
        if card in SUSPECTS:
            suspect = card
            weapon = WEAPONS[0]
        elif card in WEAPONS:
            suspect = SUSPECTS[0]
            weapon = card
        else:
            # card is a room
            suspect = SUSPECTS[0]
            weapon = WEAPONS[0]

        result = await game.process_action(whose_turn, {
            "type": "suggest",
            "suspect": suspect,
            "weapon": weapon,
            "room": room,
        })
        assert result["type"] == "suggest"
        assert result["shown_by"] == other_id or result["shown_card"] is not None


@pytest.mark.asyncio
async def test_correct_accusation_wins(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state["whose_turn"]
    solution = await game._load_solution()

    result = await game.process_action(whose_turn, {
        "type": "accuse",
        "suspect": solution["suspect"],
        "weapon": solution["weapon"],
        "room": solution["room"],
    })

    assert result["correct"] is True
    assert result["winner"] == whose_turn

    final_state = await game.get_state()
    assert final_state["status"] == "finished"
    assert final_state["winner"] == whose_turn


@pytest.mark.asyncio
async def test_incorrect_accusation_eliminates_player(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state["whose_turn"]
    solution = await game._load_solution()

    # Find a wrong suspect
    wrong_suspect = next(s for s in SUSPECTS if s != solution["suspect"])

    result = await game.process_action(whose_turn, {
        "type": "accuse",
        "suspect": wrong_suspect,
        "weapon": solution["weapon"],
        "room": solution["room"],
    })

    assert result["correct"] is False

    # With only 2 players, the other player should win
    final_state = await game.get_state()
    assert final_state["status"] == "finished"


@pytest.mark.asyncio
async def test_move_logging(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state["whose_turn"]
    room = ROOMS[2]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    log = await game.get_log()
    # log[0] = game_started, log[1] = move
    assert any(entry["type"] == "move" for entry in log)
    move_entry = next(e for e in log if e["type"] == "move")
    assert move_entry["player_id"] == whose_turn
    assert move_entry["room"] == room


@pytest.mark.asyncio
async def test_end_turn_advances_player(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    first_player = state["whose_turn"]
    second_player = "P2" if first_player == "P1" else "P1"

    result = await game.process_action(first_player, {"type": "end_turn"})
    assert result["next_player_id"] == second_player

    new_state = await game.get_state()
    assert new_state["whose_turn"] == second_player


@pytest.mark.asyncio
async def test_player_state_shows_cards(game: ClueGame):
    await _add_two_players(game)
    await game.start()

    p_state = await game.get_player_state("P1")
    assert "your_cards" in p_state
    assert isinstance(p_state["your_cards"], list)


@pytest.mark.asyncio
async def test_cannot_act_out_of_turn(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    not_their_turn = "P2" if state["whose_turn"] == "P1" else "P1"
    with pytest.raises(ValueError, match="not your turn"):
        await game.process_action(not_their_turn, {"type": "end_turn"})


@pytest.mark.asyncio
async def test_chat_message_stored_and_retrieved(game: ClueGame):
    await _add_two_players(game)

    await game.add_chat_message({"player_id": "P1", "text": "Hello!", "timestamp": "2024-01-01T00:00:00+00:00"})
    await game.add_chat_message({"player_id": None, "text": "Game started!", "timestamp": "2024-01-01T00:00:01+00:00"})

    messages = await game.get_chat_messages()
    assert len(messages) == 2
    assert messages[0]["text"] == "Hello!"
    assert messages[0]["player_id"] == "P1"
    assert messages[1]["text"] == "Game started!"
    assert messages[1]["player_id"] is None


@pytest.mark.asyncio
async def test_chat_messages_empty_initially(game: ClueGame):
    messages = await game.get_chat_messages()
    assert messages == []
