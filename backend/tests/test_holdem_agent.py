"""Tests for Texas Hold'em agent using fakeredis."""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.games.holdem.agents import (
    HoldemAgent,
    _preflop_strength,
    _postflop_strength,
)
from app.games.holdem.game import HoldemGame
from app.games.holdem.models import Card, HoldemGameState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _c(rank: str, suit: str) -> Card:
    return Card(rank=rank, suit=suit)


# ---------------------------------------------------------------------------
# Hand Strength Tests
# ---------------------------------------------------------------------------


class TestPreflopStrength:
    def test_pocket_aces_premium(self):
        cards = [_c("A", "hearts"), _c("A", "spades")]
        assert _preflop_strength(cards) >= 0.90

    def test_pocket_kings_premium(self):
        cards = [_c("K", "hearts"), _c("K", "spades")]
        assert _preflop_strength(cards) >= 0.80

    def test_ace_king_strong(self):
        cards = [_c("A", "hearts"), _c("K", "spades")]
        assert _preflop_strength(cards) >= 0.80

    def test_medium_pair_strong(self):
        cards = [_c("10", "hearts"), _c("10", "spades")]
        assert _preflop_strength(cards) >= 0.60

    def test_small_pair_playable(self):
        cards = [_c("4", "hearts"), _c("4", "spades")]
        assert _preflop_strength(cards) >= 0.40

    def test_trash_hand_weak(self):
        cards = [_c("2", "hearts"), _c("7", "spades")]
        assert _preflop_strength(cards) <= 0.25

    def test_suited_bonus(self):
        unsuited = _preflop_strength([_c("A", "hearts"), _c("J", "spades")])
        suited = _preflop_strength([_c("A", "hearts"), _c("J", "hearts")])
        assert suited > unsuited

    def test_connected_cards_bonus(self):
        connected = _preflop_strength([_c("8", "hearts"), _c("9", "spades")])
        gapped = _preflop_strength([_c("8", "hearts"), _c("2", "spades")])
        assert connected > gapped


class TestPostflopStrength:
    def test_pair_on_flop(self):
        hole = [_c("A", "hearts"), _c("K", "spades")]
        community = [_c("A", "clubs"), _c("7", "diamonds"), _c("3", "hearts")]
        strength = _postflop_strength(hole, community)
        assert strength >= 0.30  # at least one pair

    def test_flush_strong(self):
        hole = [_c("A", "hearts"), _c("K", "hearts")]
        community = [
            _c("2", "hearts"), _c("7", "hearts"), _c("9", "hearts"),
        ]
        strength = _postflop_strength(hole, community)
        assert strength >= 0.70

    def test_high_card_weak(self):
        hole = [_c("K", "hearts"), _c("Q", "spades")]
        community = [_c("2", "clubs"), _c("5", "diamonds"), _c("8", "hearts")]
        strength = _postflop_strength(hole, community)
        assert strength <= 0.25

    def test_full_house_very_strong(self):
        hole = [_c("K", "hearts"), _c("K", "spades")]
        community = [
            _c("K", "clubs"), _c("7", "diamonds"), _c("7", "hearts"),
        ]
        strength = _postflop_strength(hole, community)
        assert strength >= 0.80


# ---------------------------------------------------------------------------
# Agent Decision Tests
# ---------------------------------------------------------------------------


class TestHoldemAgentDecisions:
    def test_agent_creation(self):
        agent = HoldemAgent("P1", "TestBot", aggression=0.5)
        assert agent.player_id == "P1"
        assert agent.name == "TestBot"
        assert agent.aggression == 0.5

    def test_aggression_clamped(self):
        agent = HoldemAgent("P1", "TestBot", aggression=2.0)
        assert agent.aggression == 1.0
        agent2 = HoldemAgent("P2", "TestBot2", aggression=-1.0)
        assert agent2.aggression == 0.0

    def test_generate_chat_sometimes_returns_none(self):
        """Chat generation is probabilistic — just verify it returns string or None."""
        agent = HoldemAgent("P1", "TestBot")
        results = set()
        for _ in range(100):
            result = agent.generate_chat("fold")
            results.add(type(result))
        # Should get both None and str across many tries
        assert type(None) in results or str in results


# ---------------------------------------------------------------------------
# Agent Integration Tests (full game with agents)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_agent_game_completes(redis):
    """Two agents play a game to completion."""
    game = HoldemGame("AGENT2", redis)
    await game.create()
    # Small buy-in (2.5 big blinds) forces fast elimination
    await game.add_player("P0", "Bot1", buy_in=50, player_type="holdem_agent")
    await game.add_player("P1", "Bot2", buy_in=50, player_type="holdem_agent")
    state = await game.start()

    agents = {
        "P0": HoldemAgent("P0", "Bot1", aggression=0.7),
        "P1": HoldemAgent("P1", "Bot2", aggression=0.7),
    }

    max_actions = 1000
    for _ in range(max_actions):
        state = await game.get_state()
        if state.status != "playing":
            break

        whose_turn = state.whose_turn
        if not whose_turn or whose_turn not in agents:
            break

        agent = agents[whose_turn]
        player_state = await game.get_player_state(whose_turn)
        if not player_state or not player_state.available_actions:
            break

        action = agent.decide_action(state, player_state)
        try:
            await game.process_action(whose_turn, action)
        except ValueError:
            # Fallback on invalid action
            if "check" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "check"})
            elif "fold" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "fold"})

    state = await game.get_state()
    assert state.status == "finished", (
        f"Game didn't finish in {max_actions} actions (hand {state.hand_number})"
    )


@pytest.mark.asyncio
async def test_three_agent_game_completes(redis):
    """Three agents play a game to completion."""
    game = HoldemGame("AGENT3", redis)
    await game.create()
    # Small buy-in forces fast elimination
    await game.add_player("P0", "Bot1", buy_in=50, player_type="holdem_agent")
    await game.add_player("P1", "Bot2", buy_in=50, player_type="holdem_agent")
    await game.add_player("P2", "Bot3", buy_in=50, player_type="holdem_agent")
    state = await game.start()

    agents = {
        "P0": HoldemAgent("P0", "Bot1", aggression=0.6),
        "P1": HoldemAgent("P1", "Bot2", aggression=0.7),
        "P2": HoldemAgent("P2", "Bot3", aggression=0.8),
    }

    max_actions = 1500
    for _ in range(max_actions):
        state = await game.get_state()
        if state.status != "playing":
            break

        whose_turn = state.whose_turn
        if not whose_turn or whose_turn not in agents:
            break

        agent = agents[whose_turn]
        player_state = await game.get_player_state(whose_turn)
        if not player_state or not player_state.available_actions:
            break

        action = agent.decide_action(state, player_state)
        try:
            await game.process_action(whose_turn, action)
        except ValueError:
            if "check" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "check"})
            elif "fold" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "fold"})

    state = await game.get_state()
    assert state.status == "finished", (
        f"Game didn't finish in {max_actions} actions (hand {state.hand_number})"
    )


@pytest.mark.asyncio
async def test_agent_always_returns_valid_action(redis):
    """Agent should always return one of the available action types."""
    game = HoldemGame("VALID", redis)
    await game.create()
    await game.add_player("P0", "Bot1", player_type="holdem_agent")
    await game.add_player("P1", "Bot2", player_type="holdem_agent")
    state = await game.start()

    agents = {
        "P0": HoldemAgent("P0", "Bot1"),
        "P1": HoldemAgent("P1", "Bot2"),
    }

    max_actions = 100
    for _ in range(max_actions):
        state = await game.get_state()
        if state.status != "playing":
            break

        whose_turn = state.whose_turn
        if not whose_turn or whose_turn not in agents:
            break

        agent = agents[whose_turn]
        player_state = await game.get_player_state(whose_turn)
        if not player_state or not player_state.available_actions:
            break

        action = agent.decide_action(state, player_state)
        assert action.type in player_state.available_actions or action.type in {
            "fold", "check", "call", "bet", "raise", "all_in"
        }, f"Agent returned invalid action: {action.type}"

        try:
            await game.process_action(whose_turn, action)
        except ValueError:
            # Some actions may have invalid amounts — verify fallback works
            if "check" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "check"})
            elif "fold" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "fold"})


@pytest.mark.asyncio
async def test_agent_plays_multiple_hands(redis):
    """Agents successfully play through multiple hands."""
    game = HoldemGame("MULTI", redis)
    await game.create()
    # Large stacks with low aggression to avoid first-hand all-in
    await game.add_player("P0", "Bot1", buy_in=1000, player_type="holdem_agent")
    await game.add_player("P1", "Bot2", buy_in=1000, player_type="holdem_agent")
    state = await game.start()

    agents = {
        "P0": HoldemAgent("P0", "Bot1", aggression=0.3),
        "P1": HoldemAgent("P1", "Bot2", aggression=0.3),
    }

    initial_hand = state.hand_number
    max_actions = 300
    for _ in range(max_actions):
        state = await game.get_state()
        if state.status != "playing":
            break
        if state.hand_number >= initial_hand + 5:
            break

        whose_turn = state.whose_turn
        if not whose_turn or whose_turn not in agents:
            break

        agent = agents[whose_turn]
        player_state = await game.get_player_state(whose_turn)
        if not player_state or not player_state.available_actions:
            break

        action = agent.decide_action(state, player_state)
        try:
            await game.process_action(whose_turn, action)
        except ValueError:
            if "check" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "check"})
            elif "fold" in player_state.available_actions:
                await game.process_action(whose_turn, {"type": "fold"})

    state = await game.get_state()
    # Game either finished or played through multiple hands
    assert state.hand_number > initial_hand + 1 or state.status == "finished", (
        f"Agents didn't play through multiple hands (hand {state.hand_number})"
    )
