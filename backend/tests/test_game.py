"""Tests for Clue game logic using fakeredis (no real Redis required)."""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.games.clue.game import (
    ClueGame,
    SUSPECTS,
    WEAPONS,
    ROOMS,
    ALL_CARDS,
    ROOM_CENTERS,
    SECRET_PASSAGE_MAP,
)

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
    # Assign deterministic characters so P1 (Miss Scarlett) always goes first
    # and P2 (Colonel Mustard) is next in the official turn order.
    state = await game._load_state()
    state.players[0].character = "Miss Scarlett"
    state.players[1].character = "Colonel Mustard"
    await game._save_state(state)
    return state.players[0], state.players[1]


async def _advance_turn(game: ClueGame, player_id: str):
    """Advance past a player's turn by rolling, moving, and ending turn."""
    await game.process_action(player_id, {"type": "roll"})
    await game.process_action(player_id, {"type": "move", "room": ROOMS[0]})
    await game.process_action(player_id, {"type": "end_turn"})


async def _place_player_in_room(game: ClueGame, player_id: str, room: str):
    """Directly place a player in a room and mark dice as rolled and moved."""
    state = await game._load_state()
    state.current_room[player_id] = room
    state.dice_rolled = True
    state.moved = True
    state.last_roll = [3, 3]
    center = ROOM_CENTERS.get(room)
    if center:
        state.player_positions[player_id] = list(center)
    await game._save_state(state)


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
async def test_get_state_returns_none_for_missing_game(redis):
    """_load_state / get_state must return None for a game that was never created."""
    g = ClueGame("DOESNOTEXIST", redis)
    state = await g.get_state()
    assert state is None


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
    # Miss Scarlett always goes first (official rules)
    scarlett = next(p for p in state.players if p.character == "Miss Scarlett")
    assert state.whose_turn == scarlett.id

    solution = await game._load_solution()
    solution_cards = {solution.suspect, solution.weapon, solution.room}

    # Collect cards from real players only (wanderers get none)
    all_dealt = set()
    for p in state.players:
        cards = await game._load_player_cards(p.id)
        if p.type == "wanderer":
            assert len(cards) == 0, f"Wanderer {p.id} should have no cards"
        all_dealt.update(cards)

    # No solution card should be dealt
    assert all_dealt.isdisjoint(solution_cards)

    # All non-solution cards dealt
    expected = set(ALL_CARDS) - solution_cards
    assert all_dealt == expected

    # Human players have some cards
    p1_cards = await game._load_player_cards("P1")
    p2_cards = await game._load_player_cards("P2")
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

    # Place player in a room directly (bypass dice-based movement)
    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

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
            # card is a room — place the player in that room so the
            # suggestion room matches their current location (per the rules).
            suspect = SUSPECTS[0]
            weapon = WEAPONS[0]
            room = card
            await _place_player_in_room(game, whose_turn, room)

        result = await game.process_action(
            whose_turn,
            {
                "type": "suggest",
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
            },
        )
        assert result.type == "suggest"
        # The other player has a matching card, so they should be asked to show it
        assert result.pending_show_by == other_id


@pytest.mark.asyncio
async def test_correct_accusation_wins(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    solution = await game._load_solution()

    result = await game.process_action(
        whose_turn,
        {
            "type": "accuse",
            "suspect": solution.suspect,
            "weapon": solution.weapon,
            "room": solution.room,
        },
    )

    assert result.correct is True
    assert result.winner == whose_turn

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

    result = await game.process_action(
        whose_turn,
        {
            "type": "accuse",
            "suspect": wrong_suspect,
            "weapon": solution.weapon,
            "room": solution.room,
        },
    )

    assert result.correct is False

    # With only 2 players, the other player should win
    final_state = await game.get_state()
    assert final_state.status == "finished"


@pytest.mark.asyncio
async def test_eliminated_player_turn_is_skipped(game: ClueGame):
    """After a wrong accusation, the eliminated player's turn is skipped."""
    # Add 3 players so the game continues after one is eliminated
    await game.add_player("P1", "Alice", "human")
    await game.add_player("P2", "Bob", "human")
    await game.add_player("P3", "Carol", "human")

    # Assign deterministic characters: Miss Scarlett goes first, then Colonel
    # Mustard, then Mrs. Peacock.
    state = await game._load_state()
    state.players[0].character = "Miss Scarlett"
    state.players[1].character = "Colonel Mustard"
    state.players[2].character = "Mrs. Peacock"
    await game._save_state(state)

    state = await game.start()
    assert state.whose_turn == "P1"

    solution = await game._load_solution()
    wrong_suspect = next(s for s in SUSPECTS if s != solution.suspect)

    # P1 makes a wrong accusation and is eliminated
    result = await game.process_action(
        "P1",
        {
            "type": "accuse",
            "suspect": wrong_suspect,
            "weapon": solution.weapon,
            "room": solution.room,
        },
    )

    assert result.correct is False

    # Game should still be playing (other active players remain)
    state = await game.get_state()
    assert state.status == "playing"

    # P1 should be inactive
    p1_state = next(p for p in state.players if p.id == "P1")
    assert p1_state.active is False

    # Turn should have advanced away from the eliminated P1
    assert state.whose_turn != "P1"

    # P1 has no available actions
    p1_actions = game.get_available_actions("P1", state)
    assert p1_actions == []

    # The current player (whoever whose_turn points to) should have actions
    current_player_actions = game.get_available_actions(state.whose_turn, state)
    assert len(current_player_actions) > 0

    # Cycle through all remaining active players' turns and confirm P1 is
    # never assigned whose_turn again.
    active_real_ids = {
        p.id for p in state.players if p.active and p.type != "wanderer"
    }
    assert "P1" not in active_real_ids

    visited = set()
    current_state = state
    # len(players) * 2 gives enough iterations to cycle through every player
    # (including wanderers) at least twice, ensuring all real players get a
    # turn without looping forever if something goes wrong.
    for _ in range(len(state.players) * 2):
        current_turn = current_state.whose_turn
        assert current_turn != "P1", "Eliminated player got a turn"

        current_player = next(p for p in current_state.players if p.id == current_turn)
        if current_player.type == "wanderer":
            # Wanderers just roll and move; advance their turn by placing them
            # in a room and ending the turn.
            await _place_player_in_room(game, current_turn, ROOMS[1])
            await game.process_action(current_turn, {"type": "end_turn"})
        else:
            visited.add(current_turn)
            await game.process_action(current_turn, {"type": "roll"})
            await game.process_action(current_turn, {"type": "move", "room": ROOMS[0]})
            await game.process_action(current_turn, {"type": "end_turn"})

        current_state = await game.get_state()
        if visited >= active_real_ids:
            break

    # All remaining real players (P2, P3) were visited; P1 was never visited
    assert "P1" not in visited
    assert active_real_ids.issubset(visited)


@pytest.mark.asyncio
async def test_move_logging(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    room = ROOMS[2]
    # Roll first, then move
    await game.process_action(whose_turn, {"type": "roll"})
    await game.process_action(whose_turn, {"type": "move", "room": room})

    log = await game.get_log()
    assert any(entry.type == "roll" for entry in log)
    assert any(entry.type == "move" for entry in log)
    move_entry = next(e for e in log if e.type == "move")
    assert move_entry.player_id == whose_turn
    # Player either reaches the requested room or stops in a hallway
    assert move_entry.room == room or move_entry.room is None


@pytest.mark.asyncio
async def test_end_turn_advances_player(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    first_player = state.whose_turn
    # Next player is the next active player in character order
    active = [p for p in state.players if p.active]
    idx = next(i for i, p in enumerate(active) if p.id == first_player)
    second_player = active[(idx + 1) % len(active)].id

    # Player must roll and move before ending turn
    await game.process_action(first_player, {"type": "roll"})
    await game.process_action(first_player, {"type": "move", "room": ROOMS[0]})
    result = await game.process_action(first_player, {"type": "end_turn"})
    assert result.next_player_id == second_player

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

    from app.games.clue.models import ChatMessage

    await game.add_chat_message(
        ChatMessage(
            player_id="P1", text="Hello!", timestamp="2024-01-01T00:00:00+00:00"
        )
    )
    await game.add_chat_message(
        ChatMessage(
            player_id=None, text="Game started!", timestamp="2024-01-01T00:00:01+00:00"
        )
    )

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
    assert actions == []


@pytest.mark.asyncio
async def test_available_actions_before_roll(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    not_turn = "P2" if whose_turn == "P1" else "P1"

    actions = game.get_available_actions(whose_turn, state)
    assert "roll" in actions
    assert "move" not in actions
    assert "suggest" not in actions
    assert "accuse" in actions
    assert "end_turn" not in actions  # can't end turn without doing anything first

    # Other player has no actions available
    other_actions = game.get_available_actions(not_turn, state)
    assert other_actions == []


@pytest.mark.asyncio
async def test_available_actions_after_move_in_room(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    room = ROOMS[0]
    # Place directly in room to test actions (movement pathfinding tested separately)
    await _place_player_in_room(game, whose_turn, room)

    state = await game.get_state()
    actions = game.get_available_actions(whose_turn, state)
    assert "suggest" in actions
    assert "accuse" in actions
    assert "end_turn" in actions
    assert "move" not in actions


@pytest.mark.asyncio
async def test_available_actions_after_suggest_pending_show(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    other_cards = await game._load_player_cards(other_id)
    assert other_cards, "Other player must have cards"

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        # card is a room — place the player there so suggestion is valid
        room = card
        await _place_player_in_room(game, whose_turn, room)
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room}

    result = await game.process_action(
        whose_turn, {"type": "suggest", **suggest_kwargs}
    )
    assert result.pending_show_by == other_id

    state = await game.get_state()

    # Suggesting player has no actions while waiting
    turn_actions = game.get_available_actions(whose_turn, state)
    assert turn_actions == []

    # The player who must show a card gets show_card action
    other_actions = game.get_available_actions(other_id, state)
    assert "show_card" in other_actions


@pytest.mark.asyncio
async def test_show_card_action(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        # card is a room — place the player there so suggestion is valid
        room = card
        await _place_player_in_room(game, whose_turn, room)
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room}

    result = await game.process_action(
        whose_turn, {"type": "suggest", **suggest_kwargs}
    )
    assert result.pending_show_by == other_id

    # Other player shows the card
    show_result = await game.process_action(
        other_id, {"type": "show_card", "card": card}
    )
    assert show_result.card == card
    assert show_result.suggesting_player_id == whose_turn

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
    await _place_player_in_room(game, whose_turn, room)

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        # card is a room — move the player there so the suggestion is valid
        room = card
        await _place_player_in_room(game, whose_turn, room)
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room}

    result = await game.process_action(
        whose_turn, {"type": "suggest", **suggest_kwargs}
    )
    assert result.pending_show_by == other_id

    with pytest.raises(ValueError, match="not available at this time"):
        await game.process_action(whose_turn, {"type": "end_turn"})


@pytest.mark.asyncio
async def test_show_card_invalid_card_rejected(game: ClueGame):
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    other_cards = await game._load_player_cards(other_id)
    assert other_cards

    card = other_cards[0]
    if card in SUSPECTS:
        suggest_kwargs = {"suspect": card, "weapon": WEAPONS[0], "room": room}
    elif card in WEAPONS:
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": card, "room": room}
    else:
        # card is a room — move the player there so the suggestion is valid
        room = card
        await _place_player_in_room(game, whose_turn, room)
        suggest_kwargs = {"suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room}

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
    assert "roll" in p_state.available_actions


# ---------------------------------------------------------------------------
# Turn flow: roll -> move tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roll_then_move(game: ClueGame):
    """Roll dice first, then choose a room to move toward."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Before rolling: roll is available, move is not
    actions = game.get_available_actions(whose_turn, state)
    assert "roll" in actions
    assert "move" not in actions

    # Roll dice
    result = await game.process_action(whose_turn, {"type": "roll"})
    assert result.type == "roll"
    assert 2 <= result.dice <= 12

    # After rolling: move is available, roll and end_turn are not
    state = await game.get_state()
    assert state.dice_rolled is True
    assert state.moved is False
    actions = game.get_available_actions(whose_turn, state)
    assert "move" in actions
    assert "roll" not in actions
    assert "end_turn" not in actions  # must move before ending turn

    # Choose a room
    room = ROOMS[0]
    move_result = await game.process_action(whose_turn, {"type": "move", "room": room})
    assert move_result.type == "move"

    # After moving: neither roll nor move available
    state = await game.get_state()
    assert state.moved is True
    actions = game.get_available_actions(whose_turn, state)
    assert "roll" not in actions
    assert "move" not in actions


@pytest.mark.asyncio
async def test_cannot_move_without_rolling(game: ClueGame):
    """Move should fail if dice haven't been rolled yet."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    with pytest.raises(ValueError, match="not available at this time"):
        await game.process_action(whose_turn, {"type": "move", "room": ROOMS[0]})


@pytest.mark.asyncio
async def test_cannot_roll_twice(game: ClueGame):
    """Rolling dice twice in a turn should fail."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    await game.process_action(whose_turn, {"type": "roll"})
    with pytest.raises(ValueError, match="not available at this time"):
        await game.process_action(whose_turn, {"type": "roll"})


# ---------------------------------------------------------------------------
# Secret passage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_secret_passage_available_in_corner_room(game: ClueGame):
    """Secret passage should be offered when player is in a corner room."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Study (corner room with passage to Kitchen)
    st = await game._load_state()
    st.current_room[whose_turn] = "Study"
    center = ROOM_CENTERS.get("Study")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    state = await game.get_state()
    actions = game.get_available_actions(whose_turn, state)
    assert "secret_passage" in actions
    assert "roll" in actions


@pytest.mark.asyncio
async def test_secret_passage_not_available_in_non_corner_room(game: ClueGame):
    """Secret passage should NOT be offered in non-corner rooms."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Hall (no secret passage)
    st = await game._load_state()
    st.current_room[whose_turn] = "Hall"
    center = ROOM_CENTERS.get("Hall")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    state = await game.get_state()
    actions = game.get_available_actions(whose_turn, state)
    assert "secret_passage" not in actions
    assert "roll" in actions


@pytest.mark.asyncio
async def test_use_secret_passage(game: ClueGame):
    """Using a secret passage should move the player and skip rolling."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Study
    st = await game._load_state()
    st.current_room[whose_turn] = "Study"
    center = ROOM_CENTERS.get("Study")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    result = await game.process_action(whose_turn, {"type": "secret_passage"})
    assert result.type == "secret_passage"
    assert result.from_room == "Study"
    assert result.room == "Kitchen"

    # Player is now in Kitchen, moved=True, can suggest
    state = await game.get_state()
    assert state.current_room[whose_turn] == "Kitchen"
    assert state.moved is True
    actions = game.get_available_actions(whose_turn, state)
    assert "suggest" in actions
    assert "roll" not in actions
    assert "move" not in actions


@pytest.mark.asyncio
async def test_secret_passage_all_pairs(game: ClueGame):
    """Verify all four secret passage routes work."""
    for from_room, to_room in SECRET_PASSAGE_MAP.items():
        redis = fakeredis.FakeRedis(decode_responses=True)
        g = ClueGame(f"TEST_{from_room.replace(' ', '')}", redis)
        await g.create()
        await g.add_player("P1", "Alice", "human")
        await g.add_player("P2", "Bob", "human")
        state = await g.start()
        whose_turn = state.whose_turn

        st = await g._load_state()
        st.current_room[whose_turn] = from_room
        center = ROOM_CENTERS.get(from_room)
        if center:
            st.player_positions[whose_turn] = list(center)
        await g._save_state(st)

        result = await g.process_action(whose_turn, {"type": "secret_passage"})
        assert result.room == to_room
        assert result.from_room == from_room

        state = await g.get_state()
        assert state.current_room[whose_turn] == to_room
        await redis.aclose()


# ---------------------------------------------------------------------------
# Pawn moved by suggestion — free suggest on next turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_available_without_roll_after_moved_by_suggestion(game: ClueGame):
    """A player moved into a room by a suggestion can suggest without rolling."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    # Find the other player's character
    other_char = next(p.character for p in state.players if p.id == other_id)

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    # Make a suggestion naming the other player's character to pull them into the room
    result = await game.process_action(
        whose_turn,
        {"type": "suggest", "suspect": other_char, "weapon": WEAPONS[0], "room": room},
    )

    # Resolve show_card if pending
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    # End the current player's turn
    await game.process_action(whose_turn, {"type": "end_turn"})

    # Now it's other_id's turn — they were moved by suggestion
    state = await game.get_state()
    # Skip wanderers to find the actual next human turn
    while state.whose_turn != other_id:
        # Advance past wanderer turns
        wt = state.whose_turn
        await _advance_turn(game, wt)
        state = await game.get_state()

    assert state.whose_turn == other_id
    assert state.was_moved_by_suggestion.get(other_id) is True
    assert state.current_room.get(other_id) == room

    actions = game.get_available_actions(other_id, state)
    assert "suggest" in actions
    assert "roll" in actions  # can still choose to roll instead


@pytest.mark.asyncio
async def test_free_suggest_then_end_turn(game: ClueGame):
    """A player pulled into a room can suggest and then end their turn."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"
    other_char = next(p.character for p in state.players if p.id == other_id)

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    result = await game.process_action(
        whose_turn,
        {"type": "suggest", "suspect": other_char, "weapon": WEAPONS[0], "room": room},
    )
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    await game.process_action(whose_turn, {"type": "end_turn"})

    # Advance to other_id's turn
    state = await game.get_state()
    while state.whose_turn != other_id:
        wt = state.whose_turn
        await _advance_turn(game, wt)
        state = await game.get_state()

    # Use the free suggest
    result = await game.process_action(
        other_id,
        {"type": "suggest", "suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room},
    )
    assert result.type == "suggest"

    # Resolve show_card if pending
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    # After suggesting: only accuse and end_turn available (no roll/move)
    state = await game.get_state()
    actions = game.get_available_actions(other_id, state)
    assert "end_turn" in actions
    assert "accuse" in actions
    assert "suggest" not in actions  # already suggested this turn
    assert "roll" not in actions     # can't roll after suggesting
    assert "move" not in actions     # can't move after suggesting

    await game.process_action(other_id, {"type": "end_turn"})


@pytest.mark.asyncio
async def test_flag_cleared_after_turn_ends(game: ClueGame):
    """The was_moved_by_suggestion flag is cleared when the player ends their turn."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"
    other_char = next(p.character for p in state.players if p.id == other_id)

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    result = await game.process_action(
        whose_turn,
        {"type": "suggest", "suspect": other_char, "weapon": WEAPONS[0], "room": room},
    )
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    await game.process_action(whose_turn, {"type": "end_turn"})

    # Advance to other_id's turn
    state = await game.get_state()
    while state.whose_turn != other_id:
        wt = state.whose_turn
        await _advance_turn(game, wt)
        state = await game.get_state()

    # Flag is set
    assert state.was_moved_by_suggestion.get(other_id) is True

    # Roll, move, and end turn (choosing not to use free suggest)
    await game.process_action(other_id, {"type": "roll"})
    await game.process_action(other_id, {"type": "move", "room": ROOMS[1]})
    await game.process_action(other_id, {"type": "end_turn"})

    # Flag should be cleared
    state = await game.get_state()
    assert state.was_moved_by_suggestion.get(other_id) is None


@pytest.mark.asyncio
async def test_flag_cleared_on_roll(game: ClueGame):
    """The was_moved_by_suggestion flag is cleared as soon as the player rolls."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"
    other_char = next(p.character for p in state.players if p.id == other_id)

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    result = await game.process_action(
        whose_turn,
        {"type": "suggest", "suspect": other_char, "weapon": WEAPONS[0], "room": room},
    )
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    await game.process_action(whose_turn, {"type": "end_turn"})

    # Advance to other_id's turn
    state = await game.get_state()
    while state.whose_turn != other_id:
        wt = state.whose_turn
        await _advance_turn(game, wt)
        state = await game.get_state()

    # Flag is set before rolling
    assert state.was_moved_by_suggestion.get(other_id) is True

    # Roll — the player declines the free suggest
    await game.process_action(other_id, {"type": "roll"})
    state = await game.get_state()

    # Flag should be cleared immediately after rolling
    assert state.was_moved_by_suggestion.get(other_id) is None


@pytest.mark.asyncio
async def test_flag_cleared_on_free_suggest(game: ClueGame):
    """The was_moved_by_suggestion flag is cleared when the player uses the free suggest."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"
    other_char = next(p.character for p in state.players if p.id == other_id)

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    result = await game.process_action(
        whose_turn,
        {"type": "suggest", "suspect": other_char, "weapon": WEAPONS[0], "room": room},
    )
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    await game.process_action(whose_turn, {"type": "end_turn"})

    # Advance to other_id's turn
    state = await game.get_state()
    while state.whose_turn != other_id:
        wt = state.whose_turn
        await _advance_turn(game, wt)
        state = await game.get_state()

    # Flag is set before suggesting
    assert state.was_moved_by_suggestion.get(other_id) is True

    # Use the free suggest
    result = await game.process_action(
        other_id,
        {"type": "suggest", "suspect": SUSPECTS[0], "weapon": WEAPONS[0], "room": room},
    )
    if result.pending_show_by:
        st = await game._load_state()
        matching = st.pending_show_card.matching_cards
        await game.process_action(
            result.pending_show_by, {"type": "show_card", "card": matching[0]}
        )

    # Flag should be cleared after using the free suggest
    state = await game.get_state()
    assert state.was_moved_by_suggestion.get(other_id) is None


@pytest.mark.asyncio
async def test_no_free_suggest_without_being_moved(game: ClueGame):
    """A player NOT moved by suggestion should not get suggest before rolling."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn

    # Place player in a room but without the suggestion flag
    st = await game._load_state()
    st.current_room[whose_turn] = ROOMS[0]
    center = ROOM_CENTERS.get(ROOMS[0])
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    state = await game.get_state()
    actions = game.get_available_actions(whose_turn, state)
    assert "suggest" not in actions  # no free suggest
    assert "roll" in actions


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------


async def test_memory_empty_initially(game):
    """Memory for a player starts empty."""
    entries = await game.get_memory("player1")
    assert entries == []


async def test_memory_append_and_retrieve(game):
    """Appending memory entries persists and retrieves them in order."""
    await game.append_memory("player1", "I suspect Colonel Mustard.")
    await game.append_memory("player1", "Kitchen card has been shown to me.")

    entries = await game.get_memory("player1")
    assert len(entries) == 2
    assert entries[0] == "I suspect Colonel Mustard."
    assert entries[1] == "Kitchen card has been shown to me."


async def test_memory_per_player(game):
    """Each player has their own separate memory."""
    await game.append_memory("player1", "Note for player 1")
    await game.append_memory("player2", "Note for player 2")

    assert await game.get_memory("player1") == ["Note for player 1"]
    assert await game.get_memory("player2") == ["Note for player 2"]


# ---------------------------------------------------------------------------
# Pawn movement rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_reenter_same_room(game: ClueGame):
    """A player cannot move to the room they are already in."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Kitchen
    st = await game._load_state()
    st.current_room[whose_turn] = "Kitchen"
    center = ROOM_CENTERS.get("Kitchen")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    # Roll dice
    await game.process_action(whose_turn, {"type": "roll"})

    # Try to move to Kitchen (the room they're already in)
    with pytest.raises(ValueError, match="Cannot re-enter"):
        await game.process_action(whose_turn, {"type": "move", "room": "Kitchen"})


@pytest.mark.asyncio
async def test_current_room_excluded_from_reachable(game: ClueGame):
    """The player's current room should not appear in reachable_rooms."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Study
    st = await game._load_state()
    st.current_room[whose_turn] = "Study"
    center = ROOM_CENTERS.get("Study")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    state = await game._load_state()
    targets = game.get_reachable_targets(whose_turn, state, 6)
    assert "Study" not in targets.reachable_rooms


@pytest.mark.asyncio
async def test_occupied_hallway_blocks_movement(game: ClueGame):
    """A hallway square occupied by another pawn cannot be moved to."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    # Place both players in adjacent hallway positions
    st = await game._load_state()
    st.player_positions[whose_turn] = [7, 17]
    st.player_positions[other_id] = [7, 18]
    st.current_room.pop(whose_turn, None)
    st.current_room.pop(other_id, None)
    await game._save_state(st)

    state = await game._load_state()
    targets = game.get_reachable_targets(whose_turn, state, 1)
    # The occupied square (7, 18) must not be reachable
    assert [7, 18] not in targets.reachable_positions


@pytest.mark.asyncio
async def test_door_blocking_prevents_exit(game: ClueGame):
    """A pawn blocking the only door of a room traps players inside."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    # Place current player in Conservatory (1 door at (19,4))
    # Place other player on that door square
    st = await game._load_state()
    st.current_room[whose_turn] = "Conservatory"
    center = ROOM_CENTERS.get("Conservatory")
    if center:
        st.player_positions[whose_turn] = list(center)
    st.player_positions[other_id] = [19, 4]
    st.current_room.pop(other_id, None)
    await game._save_state(st)

    state = await game._load_state()
    targets = game.get_reachable_targets(whose_turn, state, 6)
    # No hallway positions reachable
    assert len(targets.reachable_positions) == 0
    # Secret passage rooms should NOT appear in dice-based reachability
    # (secret passages are used instead of rolling, not after rolling)
    assert "Lounge" not in targets.reachable_rooms


@pytest.mark.asyncio
async def test_secret_passage_rooms_excluded_from_dice_reachability(game: ClueGame):
    """Secret passage destinations should not appear in get_reachable_targets.

    Secret passages are an alternative to rolling the dice, so after rolling
    they must not show up as reachable rooms.
    """
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn

    # Place player in Study (has secret passage to Kitchen)
    st = await game._load_state()
    st.current_room[whose_turn] = "Study"
    center = ROOM_CENTERS.get("Study")
    if center:
        st.player_positions[whose_turn] = list(center)
    await game._save_state(st)

    state = await game._load_state()
    targets = game.get_reachable_targets(whose_turn, state, 6)
    # Kitchen (secret passage from Study) must NOT be in reachable rooms
    assert "Kitchen" not in targets.reachable_rooms
    # Study (current room) also excluded
    assert "Study" not in targets.reachable_rooms


@pytest.mark.asyncio
async def test_room_players_do_not_block(game: ClueGame):
    """Players inside a room do not block hallway squares."""
    await _add_two_players(game)
    state = await game.start()
    whose_turn = state.whose_turn
    other_id = "P2" if whose_turn == "P1" else "P1"

    # Both players in the same room — should not interfere
    st = await game._load_state()
    st.current_room[whose_turn] = "Kitchen"
    st.current_room[other_id] = "Kitchen"
    center = ROOM_CENTERS.get("Kitchen")
    if center:
        st.player_positions[whose_turn] = list(center)
        st.player_positions[other_id] = list(center)
    await game._save_state(st)

    state = await game._load_state()
    targets = game.get_reachable_targets(whose_turn, state, 6)
    # Should still be able to reach hallway/rooms (door is not blocked)
    assert (
        len(targets.reachable_positions) > 0 or len(targets.reachable_rooms) > 0
    )


@pytest.mark.asyncio
async def test_suggest_must_be_in_suggested_room(game: ClueGame):
    """A player cannot suggest a room they are not currently in."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn

    # Place the player in ROOMS[0]
    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    # Attempt to suggest a different room — should be rejected
    different_room = ROOMS[1]
    with pytest.raises(ValueError, match="must be in the room"):
        await game.process_action(
            whose_turn,
            {
                "type": "suggest",
                "suspect": SUSPECTS[0],
                "weapon": WEAPONS[0],
                "room": different_room,
            },
        )


@pytest.mark.asyncio
async def test_suggest_in_correct_room_succeeds(game: ClueGame):
    """A player can suggest the room they are currently in."""
    await _add_two_players(game)
    state = await game.start()

    whose_turn = state.whose_turn

    room = ROOMS[0]
    await _place_player_in_room(game, whose_turn, room)

    result = await game.process_action(
        whose_turn,
        {
            "type": "suggest",
            "suspect": SUSPECTS[0],
            "weapon": WEAPONS[0],
            "room": room,
        },
    )
    assert result.type == "suggest"
    assert result.room == room
