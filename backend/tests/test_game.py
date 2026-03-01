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

    assert state.game_id == "NEWGAME"
    assert state.status == "waiting"
    assert state.players == []

    # Solution stored separately and valid
    solution = await g._load_solution()
    assert solution.suspect in SUSPECTS
    assert solution.weapon in WEAPONS
    assert solution.room in ROOMS


@pytest.mark.asyncio
async def test_add_players(game: ClueGame):
    p1, p2 = await _add_two_players(game)

    state = await game.get_state()
    assert len(state.players) == 2
    assert state.players[0].name == "Alice"
    assert state.players[1].name == "Bob"
    # Characters assigned and unique
    chars = {p.character for p in state.players}
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

    assert state.status == "playing"
    assert state.whose_turn in ("P1", "P2")

    solution = await game._load_solution()
    solution_cards = {solution.suspect, solution.weapon, solution.room}

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

    whose_turn = state.whose_turn
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
            # card is a room -- use it as the room in the suggestion
            suspect = SUSPECTS[0]
            weapon = WEAPONS[0]
            room = card

        result = await game.process_action(whose_turn, {
            "type": "suggest",
            "suspect": suspect,
            "weapon": weapon,
            "room": room,
        })
        assert result["type"] == "suggest"
        # The other player has a matching card, so they should be asked to show it
        assert result["pending_show_by"] == other_id


@pytest.mark.asyncio
async def test_correct_accusation_wins(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    solution = await game._load_solution()

    result = await game.process_action(whose_turn, {
        "type": "accuse",
        "suspect": solution.suspect,
        "weapon": solution.weapon,
        "room": solution.room,
    })

    assert result["correct"] is True
    assert result["winner"] == whose_turn

    final_state = await game.get_state()
    assert final_state.status == "finished"
    assert final_state.winner == whose_turn


@pytest.mark.asyncio
async def test_incorrect_accusation_eliminates_player(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    solution = await game._load_solution()

    # Find a wrong suspect
    wrong_suspect = next(s for s in SUSPECTS if s != solution.suspect)

    result = await game.process_action(whose_turn, {
        "type": "accuse",
        "suspect": wrong_suspect,
        "weapon": solution.weapon,
        "room": solution.room,
    })

    assert result["correct"] is False

    # With only 2 players, the other player should win
    final_state = await game.get_state()
    assert final_state.status == "finished"


@pytest.mark.asyncio
async def test_move_logging(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
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

    first_player = state.whose_turn
    second_player = "P2" if first_player == "P1" else "P1"

    result = await game.process_action(first_player, {"type": "end_turn"})
    assert result["next_player_id"] == second_player

    new_state = await game.get_state()
    assert new_state.whose_turn == second_player


@pytest.mark.asyncio
async def test_player_state_shows_cards(game: ClueGame):
    await _add_two_players(game)
    await game.start()

    p_state = await game.get_player_state("P1")
    assert p_state.your_cards is not None
    assert isinstance(p_state.your_cards, list)


@pytest.mark.asyncio
async def test_cannot_act_out_of_turn(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    not_their_turn = "P2" if state.whose_turn == "P1" else "P1"
    with pytest.raises(ValueError, match="not your turn"):
        await game.process_action(not_their_turn, {"type": "end_turn"})


@pytest.mark.asyncio
async def test_chat_message_stored_and_retrieved(game: ClueGame):
    await _add_two_players(game)

    from app.models import ChatMessage

    await game.add_chat_message(ChatMessage(player_id="P1", text="Hello!", timestamp="2024-01-01T00:00:00+00:00"))
    await game.add_chat_message(ChatMessage(player_id=None, text="Game started!", timestamp="2024-01-01T00:00:01+00:00"))

    messages = await game.get_chat_messages()
    assert len(messages) == 2
    assert messages[0].text == "Hello!"
    assert messages[0].player_id == "P1"
    assert messages[1].text == "Game started!"
    assert messages[1].player_id is None


@pytest.mark.asyncio
async def test_chat_messages_empty_initially(game: ClueGame):
    messages = await game.get_chat_messages()
    assert messages == []


# ---------------------------------------------------------------------------
# available_actions tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_available_actions_waiting_state(game: ClueGame):
    await _add_two_players(game)
    state = await game.get_state()
    actions = game.get_available_actions("P1", state)
    assert actions == ["chat"]


@pytest.mark.asyncio
async def test_available_actions_before_move(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    not_turn = "P2" if whose_turn == "P1" else "P1"

    actions = game.get_available_actions(whose_turn, state)
    assert "move" in actions
    assert "chat" in actions
    assert "suggest" not in actions
    assert "accuse" in actions
    assert "end_turn" in actions

    # Other player can only chat
    other_actions = game.get_available_actions(not_turn, state)
    assert other_actions == ["chat"]


@pytest.mark.asyncio
async def test_available_actions_after_move_in_room(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    state = await game.get_state()
    actions = game.get_available_actions(whose_turn, state)
    assert "suggest" in actions
    assert "accuse" in actions
    assert "end_turn" in actions
    assert "move" not in actions
    assert "chat" in actions


@pytest.mark.asyncio
async def test_available_actions_after_suggest_pending_show(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    other_cards = await game._load_player_cards(other_id)
    assert other_cards, "Other player must have cards"

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": card}

    result = await game.process_action(whose_turn, {"type": "suggest", **suggest_kwargs})
    assert result["pending_show_by"] == other_id

    state = await game.get_state()

    # Suggesting player can only chat while waiting
    turn_actions = game.get_available_actions(whose_turn, state)
    assert turn_actions == ["chat"]

    # The player who must show a card gets show_card action
    other_actions = game.get_available_actions(other_id, state)
    assert "show_card" in other_actions
    assert "chat" in other_actions


@pytest.mark.asyncio
async def test_show_card_action(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": card}

    result = await game.process_action(whose_turn, {"type": "suggest", **suggest_kwargs})
    assert result["pending_show_by"] == other_id

    # Other player shows the card
    show_result = await game.process_action(other_id, {"type": "show_card", "card": card})
    assert show_result["card"] == card
    assert show_result["suggesting_player_id"] == whose_turn

    # pending_show_card should be cleared
    state = await game.get_state()
    assert state.pending_show_card is None

    # Suggesting player can now act again
    actions = game.get_available_actions(whose_turn, state)
    assert "end_turn" in actions
    assert "accuse" in actions


@pytest.mark.asyncio
async def test_cannot_end_turn_while_pending_show_card(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": card}

    result = await game.process_action(whose_turn, {"type": "suggest", **suggest_kwargs})
    assert result["pending_show_by"] == other_id

    with pytest.raises(ValueError, match="not available at this time"):
        await game.process_action(whose_turn, {"type": "end_turn"})


@pytest.mark.asyncio
async def test_show_card_invalid_card_rejected(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await game.process_action(whose_turn, {"type": "move", "room": room})

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": card}

    await game.process_action(whose_turn, {"type": "suggest", **suggest_kwargs})

    # Find a card the other player does NOT have as a matching card
    state = await game.get_state()
    matching = state.pending_show_card.matching_cards
    non_matching = next(c for c in other_cards if c not in matching)

    with pytest.raises(ValueError, match="not valid to show"):
        await game.process_action(other_id, {"type": "show_card", "card": non_matching})


@pytest.mark.asyncio
async def test_player_state_includes_available_actions(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    p_state = await game.get_player_state(whose_turn)
    assert p_state.available_actions is not None
    assert "move" in p_state.available_actions
    assert "chat" in p_state.available_actions
