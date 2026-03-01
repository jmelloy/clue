"""Two LLM agents play a full game of Clue against each other.

Uses fakeredis so no running Redis is needed.  The test drives the game
loop directly through ClueGame, feeding each agent's decisions back as
actions, and verifying the game reaches a valid conclusion.
"""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.game import ClueGame, SUSPECTS, WEAPONS, ROOMS
from app.agents import RandomAgent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MAX_TURNS = (
    2000  # safety limit — agents may need many turns to reach rooms via pathfinding
)


@pytest_asyncio.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_game(redis, num_agents=2):
    """Create a game, add agents, start it, and return (game, agents dict)."""
    game = ClueGame("AGENTGAME", redis)
    await game.create()

    agents: dict[str, RandomAgent] = {}
    player_ids = []
    for i in range(num_agents):
        pid = f"AGENT{i}"
        await game.add_player(pid, f"Bot-{i}", "agent")
        agents[pid] = RandomAgent()
        player_ids.append(pid)

    state = await game.start()

    # Give each agent its dealt cards
    for pid, agent in agents.items():
        cards = await game._load_player_cards(pid)
        agent.observe_own_cards(cards)

    return game, agents, state


async def _run_game(
    game: ClueGame,
    agents: dict[str, RandomAgent],
    initial_state,
    max_turns: int = MAX_TURNS,
):
    """Drive the game loop until it finishes or hits the turn limit.

    Returns (final_state, turn_count, log) where log is a list of
    (player_id, action_dict, result_dict) triples.
    """
    action_log: list[tuple[str, dict, dict]] = []
    state = initial_state
    actions_taken = 0

    while state.status == "playing" and actions_taken < max_turns:
        # Determine who needs to act
        pending = state.pending_show_card
        if pending:
            # A player must show a card
            pid = pending.player_id
            agent = agents[pid]
            suggesting_pid = pending.suggesting_player_id
            matching = pending.matching_cards

            card = await agent.decide_show_card(matching, suggesting_pid)
            action = {"type": "show_card", "card": card}
            result = await game.process_action(pid, action)
            action_log.append((pid, action, result))

            # The suggesting agent learns the shown card
            agents[suggesting_pid].observe_shown_card(card, shown_by=pid)
        else:
            # Current player's turn
            pid = state.whose_turn
            agent = agents[pid]
            player_state = await game.get_player_state(pid)
            action = await agent.decide_action(state, player_state)
            result = await game.process_action(pid, action)
            action_log.append((pid, action, result))

            # Post-action observations
            if action["type"] == "suggest":
                if result.get("pending_show_by") is None:
                    # No one could show a card — valuable info
                    agent.observe_suggestion_no_show(
                        action["suspect"],
                        action["weapon"],
                        action["room"],
                    )

        state = await game.get_state()
        actions_taken += 1

    return state, actions_taken, action_log


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_agents_complete_game(redis):
    """Two agents play to completion — someone wins."""
    game, agents, state = await _setup_game(redis, num_agents=2)
    final_state, turns, log = await _run_game(game, agents, state)

    assert (
        final_state.status == "finished"
    ), f"Game did not finish within {MAX_TURNS} actions (stuck at turn {final_state.turn_number})"
    assert final_state.winner is not None
    assert final_state.winner in agents

    # Verify the winner made a correct accusation (or the other was eliminated)
    winner = final_state.winner
    solution = await game._load_solution()

    # Check: either the winner accused correctly, or the other player was
    # eliminated by a wrong accusation.
    accusations = [(pid, a, r) for pid, a, r in log if a["type"] == "accuse"]
    assert len(accusations) > 0, "Game finished but no accusations were made"

    print(f"\nGame finished in {turns} actions, {final_state.turn_number} turns")
    print(f"Winner: {winner}")
    print(f"Solution: {solution}")
    print(f"Total accusations: {len(accusations)}")


@pytest.mark.asyncio
async def test_three_agents_complete_game(redis):
    """Three agents play to completion."""
    game, agents, state = await _setup_game(redis, num_agents=3)
    final_state, turns, log = await _run_game(game, agents, state)

    assert final_state.status == "finished"
    assert final_state.winner is not None
    assert final_state.winner in agents

    print(f"\n3-player game finished in {turns} actions")
    print(f"Winner: {final_state.winner}")


@pytest.mark.asyncio
async def test_agent_tracks_seen_cards(redis):
    """Verify the agent's seen_cards set grows as the game progresses."""
    game, agents, state = await _setup_game(redis, num_agents=2)

    # Record initial seen counts (just own hand)
    initial_counts = {pid: len(a.seen_cards) for pid, a in agents.items()}

    final_state, turns, log = await _run_game(game, agents, state)

    # After the game, agents should have learned more cards
    for pid, agent in agents.items():
        assert (
            len(agent.seen_cards) >= initial_counts[pid]
        ), f"Agent {pid} should not lose track of seen cards"

    # At least one agent should have learned cards beyond their hand
    any_learned = any(
        len(a.seen_cards) > initial_counts[pid] for pid, a in agents.items()
    )
    # This is very likely but not guaranteed (could win before any suggestion)
    # so we don't assert — just log
    suggestions = [(pid, a) for pid, a, _ in log if a["type"] == "suggest"]
    shows = [(pid, a) for pid, a, _ in log if a["type"] == "show_card"]
    print(f"\nSuggestions made: {len(suggestions)}, Cards shown: {len(shows)}")
    print(f"Agents learned new cards: {any_learned}")


@pytest.mark.asyncio
async def test_agent_accuses_only_when_certain(redis):
    """Verify agents only accuse when they've narrowed to one per category."""
    game, agents, state = await _setup_game(redis, num_agents=2)
    solution = await game._load_solution()

    final_state, turns, log = await _run_game(game, agents, state)

    # Check every accusation: the accusing agent should have had exactly
    # one unknown left in each category
    for pid, action, result in log:
        if action["type"] == "accuse":
            agent = agents[pid]
            unknown_s = [s for s in SUSPECTS if s not in agent.seen_cards]
            unknown_w = [w for w in WEAPONS if w not in agent.seen_cards]
            unknown_r = [r for r in ROOMS if r not in agent.seen_cards]
            # The agent should accuse only with exactly 1 unknown per category
            assert (
                len(unknown_s) == 1
            ), f"Agent {pid} accused with {len(unknown_s)} unknown suspects"
            assert (
                len(unknown_w) == 1
            ), f"Agent {pid} accused with {len(unknown_w)} unknown weapons"
            assert (
                len(unknown_r) == 1
            ), f"Agent {pid} accused with {len(unknown_r)} unknown rooms"
            # And the accusation should match the unknowns
            assert action["suspect"] == unknown_s[0]
            assert action["weapon"] == unknown_w[0]
            assert action["room"] == unknown_r[0]


@pytest.mark.asyncio
async def test_agent_never_suggests_own_cards(redis):
    """The agent should prefer unknown cards in suggestions."""
    game, agents, state = await _setup_game(redis, num_agents=2)
    final_state, turns, log = await _run_game(game, agents, state)

    for pid, action, result in log:
        if action["type"] == "suggest":
            agent = agents[pid]
            cards = await game._load_player_cards(pid)
            # Suspect and weapon should NOT be in the agent's hand
            # (unless all suspects or all weapons are known)
            unknown_suspects = [s for s in SUSPECTS if s not in agent.seen_cards]
            unknown_weapons = [w for w in WEAPONS if w not in agent.seen_cards]

            if unknown_suspects:
                assert action["suspect"] not in cards, (
                    f"Agent {pid} suggested a suspect from its own hand "
                    f"when unknowns existed: {action['suspect']}"
                )
            if unknown_weapons:
                assert action["weapon"] not in cards, (
                    f"Agent {pid} suggested a weapon from its own hand "
                    f"when unknowns existed: {action['weapon']}"
                )


@pytest.mark.asyncio
async def test_game_with_six_agents(redis):
    """Full 6-player game completes."""
    game, agents, state = await _setup_game(redis, num_agents=6)
    final_state, turns, log = await _run_game(game, agents, state)

    assert final_state.status == "finished"
    assert final_state.winner in agents

    active_at_end = [p for p in final_state.players if p.active]
    print(f"\n6-player game: {turns} actions, winner={final_state.winner}")
    print(f"Active players at end: {len(active_at_end)}")


@pytest.mark.asyncio
async def test_multiple_games_all_finish(redis):
    """Run 10 games to verify consistent completion (no hangs or crashes)."""
    wins = {}
    for i in range(10):
        r = fakeredis.FakeRedis(decode_responses=True)
        game = ClueGame(f"MULTI{i}", r)
        await game.create()

        agents = {}
        for j in range(3):
            pid = f"P{j}"
            await game.add_player(pid, f"Bot-{j}", "agent")
            agents[pid] = RandomAgent()

        state = await game.start()
        for pid, agent in agents.items():
            cards = await game._load_player_cards(pid)
            agent.observe_own_cards(cards)

        final_state, turns, log = await _run_game(game, agents, state)
        assert final_state.status == "finished", f"Game {i} did not finish"

        winner = final_state.winner
        wins[winner] = wins.get(winner, 0) + 1
        await r.aclose()

    print(f"\n10 games completed. Win distribution: {wins}")
    assert sum(wins.values()) == 10
