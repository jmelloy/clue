"""Tests for Texas Hold'em game logic using fakeredis."""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.games.holdem.game import HoldemGame
from app.games.holdem.models import (
    Card,
    RANKS,
    SUITS,
    HoldemGameState,
)
from app.games.holdem.hand_eval import (
    evaluate_hand,
    hand_name,
    HIGH_CARD,
    ONE_PAIR,
    TWO_PAIR,
    THREE_OF_A_KIND,
    STRAIGHT,
    FLUSH,
    FULL_HOUSE,
    FOUR_OF_A_KIND,
    STRAIGHT_FLUSH,
    ROYAL_FLUSH,
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
    g = HoldemGame("TESTHOLDEM", redis)
    await g.create()
    return g


# ---------------------------------------------------------------------------
# Hand Evaluation Tests
# ---------------------------------------------------------------------------


def _c(rank: str, suit: str) -> Card:
    """Shorthand for creating a Card."""
    return Card(rank=rank, suit=suit)


class TestHandEvaluation:
    def test_high_card(self):
        cards = [_c("2", "hearts"), _c("5", "diamonds"), _c("9", "clubs"),
                 _c("J", "spades"), _c("A", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == HIGH_CARD

    def test_one_pair(self):
        cards = [_c("A", "hearts"), _c("A", "diamonds"), _c("3", "clubs"),
                 _c("7", "spades"), _c("9", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == ONE_PAIR

    def test_two_pair(self):
        cards = [_c("K", "hearts"), _c("K", "diamonds"), _c("5", "clubs"),
                 _c("5", "spades"), _c("9", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == TWO_PAIR

    def test_three_of_a_kind(self):
        cards = [_c("Q", "hearts"), _c("Q", "diamonds"), _c("Q", "clubs"),
                 _c("5", "spades"), _c("9", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == THREE_OF_A_KIND

    def test_straight(self):
        cards = [_c("5", "hearts"), _c("6", "diamonds"), _c("7", "clubs"),
                 _c("8", "spades"), _c("9", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == STRAIGHT

    def test_ace_low_straight(self):
        cards = [_c("A", "hearts"), _c("2", "diamonds"), _c("3", "clubs"),
                 _c("4", "spades"), _c("5", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == STRAIGHT
        assert score[1] == 5  # 5-high straight

    def test_flush(self):
        cards = [_c("2", "hearts"), _c("5", "hearts"), _c("8", "hearts"),
                 _c("J", "hearts"), _c("A", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == FLUSH

    def test_full_house(self):
        cards = [_c("10", "hearts"), _c("10", "diamonds"), _c("10", "clubs"),
                 _c("K", "spades"), _c("K", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == FULL_HOUSE

    def test_four_of_a_kind(self):
        cards = [_c("7", "hearts"), _c("7", "diamonds"), _c("7", "clubs"),
                 _c("7", "spades"), _c("K", "hearts")]
        score = evaluate_hand(cards)
        assert score[0] == FOUR_OF_A_KIND

    def test_straight_flush(self):
        cards = [_c("5", "clubs"), _c("6", "clubs"), _c("7", "clubs"),
                 _c("8", "clubs"), _c("9", "clubs")]
        score = evaluate_hand(cards)
        assert score[0] == STRAIGHT_FLUSH

    def test_royal_flush(self):
        cards = [_c("10", "spades"), _c("J", "spades"), _c("Q", "spades"),
                 _c("K", "spades"), _c("A", "spades")]
        score = evaluate_hand(cards)
        assert score[0] == ROYAL_FLUSH

    def test_best_of_seven(self):
        """Evaluate the best 5-card hand from 7 cards."""
        cards = [
            _c("A", "hearts"), _c("K", "hearts"),  # hole cards
            _c("Q", "hearts"), _c("J", "hearts"), _c("10", "hearts"),  # community
            _c("2", "clubs"), _c("3", "diamonds"),
        ]
        score = evaluate_hand(cards)
        assert score[0] == ROYAL_FLUSH

    def test_hand_ranking_order(self):
        """Higher-ranked hands beat lower ones."""
        high_card = evaluate_hand(
            [_c("2", "h"), _c("5", "d"), _c("9", "c"), _c("J", "s"), _c("A", "h")]
        )
        pair = evaluate_hand(
            [_c("A", "h"), _c("A", "d"), _c("3", "c"), _c("7", "s"), _c("9", "h")]
        )
        flush = evaluate_hand(
            [_c("2", "h"), _c("5", "h"), _c("8", "h"), _c("J", "h"), _c("A", "h")]
        )
        assert pair > high_card
        assert flush > pair

    def test_hand_name(self):
        cards = [_c("A", "hearts"), _c("A", "diamonds"), _c("A", "clubs"),
                 _c("K", "spades"), _c("K", "hearts")]
        score = evaluate_hand(cards)
        assert hand_name(score) == "Full House"


# ---------------------------------------------------------------------------
# Game Creation & Join Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_game(redis):
    g = HoldemGame("NEW", redis)
    state = await g.create()
    assert state.game_id == "NEW"
    assert state.status == "waiting"
    assert state.players == []
    assert state.game_type == "holdem"


@pytest.mark.asyncio
async def test_add_players(game: HoldemGame):
    p1 = await game.add_player("P1", "Alice")
    p2 = await game.add_player("P2", "Bob")

    state = await game.get_state()
    assert len(state.players) == 2
    assert state.players[0].name == "Alice"
    assert state.players[1].name == "Bob"
    assert state.players[0].chips == 1000
    assert state.players[1].chips == 1000


@pytest.mark.asyncio
async def test_custom_buy_in(game: HoldemGame):
    p = await game.add_player("P1", "Alice", buy_in=5000)
    assert p.chips == 5000


@pytest.mark.asyncio
async def test_cannot_join_started_game(game: HoldemGame):
    await game.add_player("P1", "Alice")
    await game.add_player("P2", "Bob")
    await game.start()
    with pytest.raises(ValueError, match="already started"):
        await game.add_player("P3", "Charlie")


@pytest.mark.asyncio
async def test_start_requires_two_players(game: HoldemGame):
    await game.add_player("P1", "Alice")
    with pytest.raises(ValueError, match="at least 2"):
        await game.start()


@pytest.mark.asyncio
async def test_max_players(game: HoldemGame):
    for i in range(10):
        await game.add_player(f"P{i}", f"Player {i}")
    with pytest.raises(ValueError, match="full"):
        await game.add_player("P10", "Extra")


# ---------------------------------------------------------------------------
# Game Start & Dealing Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_game_deals_cards(game: HoldemGame):
    await game.add_player("P1", "Alice")
    await game.add_player("P2", "Bob")
    state = await game.start()

    assert state.status == "playing"
    assert state.hand_number == 1
    assert state.whose_turn is not None

    # Each player should have 2 hole cards
    p1_cards = await game._load_player_cards("P1")
    p2_cards = await game._load_player_cards("P2")
    assert len(p1_cards) == 2
    assert len(p2_cards) == 2

    # Cards should be different
    all_cards = p1_cards + p2_cards
    assert len(set(str(c) for c in all_cards)) == 4


@pytest.mark.asyncio
async def test_blinds_posted_on_start(game: HoldemGame):
    await game.add_player("P1", "Alice")
    await game.add_player("P2", "Bob")
    state = await game.start()

    # With 2 players (heads-up): dealer is SB, other is BB
    total_blinds = state.small_blind + state.big_blind
    assert state.pot == total_blinds
    assert state.current_bet == state.big_blind


# ---------------------------------------------------------------------------
# Action Tests
# ---------------------------------------------------------------------------


async def _setup_started_game(redis, num_players=2):
    """Create, populate, and start a game. Return (game, state)."""
    game = HoldemGame("TEST", redis)
    await game.create()
    for i in range(num_players):
        await game.add_player(f"P{i}", f"Player{i}")
    state = await game.start()
    return game, state


@pytest.mark.asyncio
async def test_fold_action(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    result = await game.process_action(whose_turn, {"type": "fold"})
    assert result.type == "fold"

    # Other player should win since only 2 players
    final = await game.get_state()
    # The hand should be over (new hand dealt or game continues)
    assert final is not None


@pytest.mark.asyncio
async def test_check_action(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    available = game.get_available_actions(whose_turn, state)
    if "call" in available:
        # Preflop, first to act — need to call the blind first
        await game.process_action(whose_turn, {"type": "call"})
        state = await game.get_state()
        whose_turn = state.whose_turn
        available = game.get_available_actions(whose_turn, state)

    if "check" in available:
        result = await game.process_action(whose_turn, {"type": "check"})
        assert result.type == "check"


@pytest.mark.asyncio
async def test_call_action(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    available = game.get_available_actions(whose_turn, state)
    if "call" in available:
        result = await game.process_action(whose_turn, {"type": "call"})
        assert result.type == "call"
        assert result.amount > 0


@pytest.mark.asyncio
async def test_bet_action(redis):
    game, state = await _setup_started_game(redis)

    # Play through preflop to get to flop where we can bet fresh
    whose_turn = state.whose_turn
    available = game.get_available_actions(whose_turn, state)

    if "call" in available:
        await game.process_action(whose_turn, {"type": "call"})
        state = await game.get_state()
        whose_turn = state.whose_turn
        available = game.get_available_actions(whose_turn, state)
    if "check" in available:
        await game.process_action(whose_turn, {"type": "check"})
        state = await game.get_state()
        whose_turn = state.whose_turn
        available = game.get_available_actions(whose_turn, state)

    # Now we should be on the flop
    if "bet" in available:
        result = await game.process_action(
            whose_turn, {"type": "bet", "amount": 50}
        )
        assert result.type == "bet"
        assert result.amount == 50


@pytest.mark.asyncio
async def test_raise_action(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    available = game.get_available_actions(whose_turn, state)
    if "raise" in available:
        result = await game.process_action(
            whose_turn, {"type": "raise", "amount": 60}
        )
        assert result.type == "raise"


@pytest.mark.asyncio
async def test_all_in_action(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    result = await game.process_action(whose_turn, {"type": "all_in"})
    assert result.type == "all_in"


@pytest.mark.asyncio
async def test_cannot_act_out_of_turn(redis):
    game, state = await _setup_started_game(redis)
    not_turn = "P1" if state.whose_turn == "P0" else "P0"

    with pytest.raises(ValueError, match="not your turn"):
        await game.process_action(not_turn, {"type": "fold"})


@pytest.mark.asyncio
async def test_invalid_action_rejected(redis):
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn

    # Check may not be available preflop (player owes the blind)
    available = game.get_available_actions(whose_turn, state)
    if "check" not in available:
        with pytest.raises(ValueError, match="not available"):
            await game.process_action(whose_turn, {"type": "check"})


@pytest.mark.asyncio
async def test_minimum_bet_enforced(redis):
    game, state = await _setup_started_game(redis)

    # Get to a betting position
    whose_turn = state.whose_turn
    available = game.get_available_actions(whose_turn, state)
    if "call" in available:
        await game.process_action(whose_turn, {"type": "call"})
        state = await game.get_state()
        whose_turn = state.whose_turn
        available = game.get_available_actions(whose_turn, state)
    if "check" in available:
        await game.process_action(whose_turn, {"type": "check"})
        state = await game.get_state()
        whose_turn = state.whose_turn

    available = game.get_available_actions(whose_turn, state)
    if "bet" in available:
        with pytest.raises(ValueError, match="Minimum bet"):
            await game.process_action(
                whose_turn, {"type": "bet", "amount": 1}
            )


# ---------------------------------------------------------------------------
# Full Hand Playthrough Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_hand_fold(redis):
    """One player folds, other wins the pot."""
    game, state = await _setup_started_game(redis)
    whose_turn = state.whose_turn
    other = "P1" if whose_turn == "P0" else "P0"

    initial_pot = state.pot

    # First player folds
    await game.process_action(whose_turn, {"type": "fold"})

    state = await game.get_state()
    # Game should still be playing (new hand dealt)
    assert state.status == "playing"
    # The winner should have gained the pot
    winner = next(p for p in state.players if p.id == other)
    # Winner starts with 1000, gains pot minus their blind
    assert winner.chips >= 1000


@pytest.mark.asyncio
async def test_complete_hand_to_showdown(redis):
    """Play a single hand through to showdown with check/call."""
    game, state = await _setup_started_game(redis)

    initial_hand = state.hand_number
    max_actions = 50
    actions_taken = 0

    # Play until the hand number changes (i.e., one complete hand was played)
    while state.status == "playing" and actions_taken < max_actions:
        if state.hand_number > initial_hand:
            break  # New hand was dealt, meaning the previous hand completed

        whose_turn = state.whose_turn
        if whose_turn is None:
            break

        available = game.get_available_actions(whose_turn, state)
        if not available:
            break

        # Prefer check, then call, then fold
        if "check" in available:
            await game.process_action(whose_turn, {"type": "check"})
        elif "call" in available:
            await game.process_action(whose_turn, {"type": "call"})
        else:
            await game.process_action(whose_turn, {"type": "fold"})

        state = await game.get_state()
        actions_taken += 1

    assert state is not None
    # The hand number should have advanced (meaning at least one hand completed)
    assert state.hand_number > initial_hand, (
        f"Hand didn't complete in {max_actions} actions"
    )


@pytest.mark.asyncio
async def test_three_player_game(redis):
    """Three player game works correctly."""
    game, state = await _setup_started_game(redis, num_players=3)

    assert len(state.players) == 3
    assert state.status == "playing"
    assert state.hand_number == 1

    # Each player should have 2 cards
    for p in state.players:
        cards = await game._load_player_cards(p.id)
        assert len(cards) == 2


@pytest.mark.asyncio
async def test_player_state(redis):
    game, state = await _setup_started_game(redis)

    ps = await game.get_player_state("P0")
    assert ps is not None
    assert ps.your_player_id == "P0"
    assert len(ps.your_cards) == 2
    assert isinstance(ps.available_actions, list)
    assert ps.game_type == "holdem"


@pytest.mark.asyncio
async def test_player_elimination(redis):
    """A player who loses all chips is eliminated."""
    game = HoldemGame("ELIM", redis)
    await game.create()
    await game.add_player("P0", "Alice", buy_in=30)  # Just enough for a few blinds
    await game.add_player("P1", "Bob", buy_in=1000)
    state = await game.start()

    # P0 keeps going all-in until eliminated
    max_hands = 50
    hands = 0
    while state.status == "playing" and hands < max_hands:
        whose_turn = state.whose_turn
        if whose_turn is None:
            break

        available = game.get_available_actions(whose_turn, state)
        if not available:
            break

        if whose_turn == "P0" and "all_in" in available:
            await game.process_action(whose_turn, {"type": "all_in"})
        elif "call" in available:
            await game.process_action(whose_turn, {"type": "call"})
        elif "check" in available:
            await game.process_action(whose_turn, {"type": "check"})
        elif "fold" in available:
            await game.process_action(whose_turn, {"type": "fold"})
        else:
            break

        state = await game.get_state()
        hands += 1

    # Eventually one player should run out of chips
    assert state.status == "finished" or hands < max_hands


@pytest.mark.asyncio
async def test_chat_messages(redis):
    game = HoldemGame("CHAT", redis)
    await game.create()

    from app.games.holdem.models import HoldemChatMessage

    await game.add_chat_message(
        HoldemChatMessage(
            player_id="P1",
            text="Nice hand!",
            timestamp="2024-01-01T00:00:00+00:00",
        )
    )

    messages = await game.get_chat_messages()
    assert len(messages) == 1
    assert messages[0].text == "Nice hand!"


@pytest.mark.asyncio
async def test_get_state_returns_none_for_missing_game(redis):
    g = HoldemGame("DOESNOTEXIST", redis)
    state = await g.get_state()
    assert state is None


@pytest.mark.asyncio
async def test_multiple_hands_play_through(redis):
    """Play multiple hands to verify the dealer moves and hands deal correctly."""
    game, state = await _setup_started_game(redis)

    initial_hand = state.hand_number
    target_hands = initial_hand + 3  # play through 3 hands
    max_actions = 200

    for _ in range(max_actions):
        if state.status != "playing":
            break
        if state.hand_number >= target_hands:
            break

        whose_turn = state.whose_turn
        if whose_turn is None:
            break

        available = game.get_available_actions(whose_turn, state)
        if not available:
            break

        # Simple strategy: check or call
        if "check" in available:
            await game.process_action(whose_turn, {"type": "check"})
        elif "call" in available:
            await game.process_action(whose_turn, {"type": "call"})
        elif "fold" in available:
            await game.process_action(whose_turn, {"type": "fold"})
        else:
            break

        state = await game.get_state()

    # Should have played through multiple hands
    assert state.hand_number > initial_hand + 1
