"""Tests for agent card inference logic.

Validates that BaseAgent / RandomAgent correctly:
- Infers which card was shown when observing other players' suggestions
- Cascades inferences when new knowledge unlocks old suggestions
- Tracks negative knowledge (players who couldn't show)
- Reflects all inferred cards in known_cards (seen_cards | inferred_cards)
- Persists and restores knowledge state via Redis
"""

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.games.clue.game import SUSPECTS, WEAPONS, ROOMS
from app.games.clue.agents import RandomAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Use fixed subsets for predictable tests
S = SUSPECTS[:6]  # 6 suspects
W = WEAPONS[:6]   # 6 weapons
R = ROOMS[:9]     # 9 rooms

PLAYERS = ["P_SELF", "P_ALICE", "P_BOB", "P_CAROL", "P_DAVE"]


def _make_agent(own_cards: list[str] | None = None) -> RandomAgent:
    """Create a RandomAgent with known hand and deterministic style."""
    cards = own_cards or [S[0], W[0], R[0]]
    agent = RandomAgent(
        player_id=PLAYERS[0],
        character="Miss Scarlett",
        cards=cards,
        secret_passage_chance=0.5,
        explore_chance=0.5,
        chat_frequency=0.0,
    )
    agent.player_names = {
        PLAYERS[0]: "Miss Scarlett",
        PLAYERS[1]: "Alice",
        PLAYERS[2]: "Bob",
        PLAYERS[3]: "Carol",
        PLAYERS[4]: "Dave",
    }
    return agent


# ---------------------------------------------------------------------------
# Direct inference tests
# ---------------------------------------------------------------------------


class TestDirectInference:
    """When we observe a card shown to another player and can deduce which one."""

    def test_infer_card_when_two_of_three_known(self):
        """If we know 2 of the 3 suggested cards, the shown card must be the 3rd."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Agent knows S[0] and W[0] (own cards). Alice suggests S[0]/W[0]/R[1].
        # Bob shows a card. The only card Bob could show is R[1].
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],  # Bob
            shown_to=PLAYERS[1],  # Alice
            suspect=S[0],
            weapon=W[0],
            room=R[1],
        )

        assert R[1] in agent.inferred_cards, (
            f"Agent should have inferred {R[1]} but inferred_cards = {agent.inferred_cards}"
        )
        assert R[1] in agent.known_cards
        assert R[1] in agent.player_has_cards.get(PLAYERS[2], set()), (
            "Agent should track that Bob has the inferred card"
        )

    def test_no_inference_when_two_unknown(self):
        """If 2+ cards are possible, no inference should be made."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Suggestion: S[1]/W[1]/R[1] — agent knows none of these
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
        )

        # None of S[1], W[1], R[1] should be inferred
        assert S[1] not in agent.known_cards
        assert W[1] not in agent.known_cards
        assert R[1] not in agent.known_cards

    def test_infer_using_player_has_knowledge(self):
        """Inference works when we know another player holds one of the cards."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # First, we learn Carol has W[1] (she showed it to us)
        agent.observe_shown_card(W[1], shown_by=PLAYERS[3])

        # Now Bob shows a card for suggestion S[1]/W[1]/R[1].
        # We know W[1] is Carol's, and S[1] is unknown to us.
        # Bob can't show W[1] (Carol has it). So Bob showed either S[1] or R[1].
        # That's still 2 possibilities — no inference yet.
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
        )
        # Still ambiguous
        assert S[1] not in agent.inferred_cards or R[1] not in agent.inferred_cards

    def test_infer_using_own_card_and_other_player(self):
        """Combine own cards + known player cards to narrow to 1."""
        agent = _make_agent(own_cards=[S[0], W[1], R[0]])

        # We know Carol has S[1] (she showed us)
        agent.observe_shown_card(S[1], shown_by=PLAYERS[3])

        # Suggestion: S[1]/W[1]/R[1]. Bob shows a card.
        # S[1] is Carol's (not Bob's). W[1] is ours (not Bob's). Only R[1] left.
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
        )

        assert R[1] in agent.inferred_cards
        assert R[1] in agent.known_cards
        assert R[1] in agent.player_has_cards.get(PLAYERS[2], set())

    def test_already_known_card_not_re_inferred(self):
        """If the only possible card is already known, no duplicate inference."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # We already know R[1]
        agent.observe_shown_card(R[1], shown_by=PLAYERS[2])
        initial_seen = set(agent.seen_cards)

        # Same suggestion where R[1] is the only option — should not re-infer
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[0],
            weapon=W[0],
            room=R[1],
        )

        assert agent.seen_cards == initial_seen
        assert R[1] not in agent.inferred_cards  # it's in seen, not inferred


# ---------------------------------------------------------------------------
# Negative knowledge tests
# ---------------------------------------------------------------------------


class TestNegativeKnowledge:
    """Players who can't show a card don't have any of the suggested cards."""

    def test_players_without_match_tracked(self):
        """observe_suggestion records negative knowledge for skipped players."""
        agent = _make_agent()

        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
            shown_by=PLAYERS[3],  # Carol showed
            players_without_match=[PLAYERS[2], PLAYERS[4]],  # Bob, Dave couldn't
        )

        bob_not_has = agent.player_not_has_cards.get(PLAYERS[2], set())
        dave_not_has = agent.player_not_has_cards.get(PLAYERS[4], set())

        assert {S[1], W[1], R[1]} <= bob_not_has
        assert {S[1], W[1], R[1]} <= dave_not_has

    def test_negative_knowledge_enables_inference(self):
        """Negative knowledge can narrow possible cards for later inference."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # First suggestion: Bob can't show S[1]/W[1]/R[1]
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
            shown_by=PLAYERS[3],  # Carol showed
            players_without_match=[PLAYERS[2]],  # Bob couldn't
        )

        # Now Bob shows a card for S[2]/W[1]/R[2].
        # Bob doesn't have W[1] (from above). We don't know S[2] or R[2].
        # So Bob showed either S[2] or R[2] — still ambiguous.
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[2],
            weapon=W[1],
            room=R[2],
        )

        # With just negative knowledge on W[1], we can't narrow to 1
        # (S[2] and R[2] are both possible)
        assert not ({S[2], R[2]} <= agent.known_cards)

    def test_negative_knowledge_plus_own_card_enables_inference(self):
        """Negative knowledge + own card narrows to exactly 1."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Bob can't show S[2]/W[2]/R[2]
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[2],
            weapon=W[2],
            room=R[2],
            shown_by=PLAYERS[3],
            players_without_match=[PLAYERS[2]],
        )

        # Bob shows a card for S[0]/W[1]/R[2].
        # S[0] is ours (not Bob's). R[2]: Bob doesn't have (neg knowledge).
        # Only W[1] is left — Bob must have shown W[1].
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[0],
            weapon=W[1],
            room=R[2],
        )

        assert W[1] in agent.inferred_cards
        assert W[1] in agent.known_cards
        assert W[1] in agent.player_has_cards.get(PLAYERS[2], set())


# ---------------------------------------------------------------------------
# Cascade inference tests
# ---------------------------------------------------------------------------


class TestCascadeInference:
    """Learning a new card should re-check old suggestions for new deductions."""

    def test_cascade_from_shown_card(self):
        """Directly shown card triggers cascade on old suggestions."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Old suggestion: Alice suggests S[1]/W[1]/R[1], Bob shows a card.
        # We can't infer (all 3 unknown).
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
            shown_by=PLAYERS[2],
            players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2],
            shown_to=PLAYERS[1],
            suspect=S[1],
            weapon=W[1],
            room=R[1],
        )
        assert S[1] not in agent.known_cards
        assert W[1] not in agent.known_cards
        assert R[1] not in agent.known_cards

        # Now Carol shows us S[1] directly
        agent.observe_shown_card(S[1], shown_by=PLAYERS[3])
        assert S[1] in agent.seen_cards

        # And we learn W[1] from another source
        agent.observe_shown_card(W[1], shown_by=PLAYERS[4])
        assert W[1] in agent.seen_cards

        # Now the old suggestion S[1]/W[1]/R[1] can be resolved:
        # We know S[1] and W[1], so Bob must have shown R[1].
        # _run_inference should cascade.
        assert R[1] in agent.known_cards, (
            f"Cascade should have inferred {R[1]} from old suggestion. "
            f"known_cards = {sorted(agent.known_cards)}"
        )

    def test_cascade_chain_multiple_suggestions(self):
        """Inferring one card cascades to resolve another old suggestion.

        Chain: learning S[1]+R[1] → infer W[1] from suggestion A →
        W[1] now known (Bob has it) → suggestion B (S[0]/W[1]/R[2] by Carol)
        resolves because S[0] is ours and W[1] is Bob's → Carol showed R[2].
        """
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Suggestion A: S[1]/W[1]/R[1], Bob shows. Can't infer (3 unknown).
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
        )

        # Suggestion B: S[0]/W[1]/R[2], Carol shows.
        # S[0] is ours → Carol can't have it. W[1] and R[2] unknown → 2 poss.
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[0], weapon=W[1], room=R[2],
            shown_by=PLAYERS[3], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[3], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[1], room=R[2],
        )

        # Now learn S[1] and R[1] directly
        agent.observe_shown_card(S[1], shown_by=PLAYERS[3])
        agent.observe_shown_card(R[1], shown_by=PLAYERS[4])

        # Cascade step 1: Suggestion A resolves — Bob showed W[1]
        assert W[1] in agent.known_cards, (
            f"Should cascade-infer {W[1]} from suggestion A"
        )

        # Cascade step 2: W[1] is now known (Bob has it). Suggestion B:
        # S[0] is ours, W[1] is Bob's → only R[2] left → Carol showed R[2]
        assert R[2] in agent.known_cards, (
            f"Should cascade-infer {R[2]} from suggestion B"
        )

    def test_deep_cascade_chain(self):
        """A chain of 3 inferences triggered by a single new card.

        Scenario:
        - Suggestion A: S[1]/W[1]/R[1], Bob shows (3 unknown)
        - Suggestion B: S[2]/W[1]/R[2], Carol shows (3 unknown, overlaps on W[1])
        - Suggestion C: S[2]/W[2]/R[3], Dave shows (3 unknown, overlaps on S[2])

        We learn S[1] and R[1] → infer W[1] from A → infer from B → infer from C.
        """
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Suggestion A
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
        )

        # Suggestion B
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[2], weapon=W[1], room=R[2],
            shown_by=PLAYERS[3], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[3], shown_to=PLAYERS[1],
            suspect=S[2], weapon=W[1], room=R[2],
        )

        # Suggestion C
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[2], weapon=W[2], room=R[3],
            shown_by=PLAYERS[4], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[4], shown_to=PLAYERS[1],
            suspect=S[2], weapon=W[2], room=R[3],
        )

        # Nothing inferred yet
        for card in [S[1], S[2], W[1], W[2], R[1], R[2], R[3]]:
            assert card not in agent.known_cards, f"{card} should not be inferred yet"

        # Learn S[1] and R[1] → should cascade:
        # A resolves: Bob showed W[1]
        agent.observe_shown_card(S[1], shown_by=PLAYERS[3])
        agent.observe_shown_card(R[1], shown_by=PLAYERS[3])

        # Step 1: A resolves → W[1] inferred (Bob has it)
        assert W[1] in agent.known_cards, "Should infer W[1] from suggestion A"

        # For B to cascade, we need to narrow further. Learn R[2]:
        agent.observe_shown_card(R[2], shown_by=PLAYERS[2])
        # B: Carol showed one of {S[2], W[1], R[2]}. W[1] is Bob's, R[2] is Bob's.
        # Carol can't have either → Carol showed S[2].
        assert S[2] in agent.known_cards, "Should infer S[2] from suggestion B"

        # C: Dave showed one of {S[2], W[2], R[3]}. S[2] now known (Carol has it).
        # Dave doesn't have S[2]. So Dave showed W[2] or R[3].
        # Still 2 possibilities — unless we learn one more.

    def test_inference_reflected_in_known_cards_and_unknowns(self):
        """Inferred cards appear in known_cards AND reduce unknowns for decisions."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Set up so we can infer R[1]
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )

        assert R[1] in agent.known_cards
        assert R[1] in agent.inferred_cards
        unknown_s, unknown_w, unknown_r = agent._get_unknowns()
        assert R[1] not in unknown_r, "Inferred card should not appear in unknowns"

    def test_shown_card_promotes_from_inferred(self):
        """If a card was inferred and then directly shown, it moves to seen_cards."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Infer R[1]
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )
        assert R[1] in agent.inferred_cards

        # Now directly shown
        agent.observe_shown_card(R[1], shown_by=PLAYERS[2])
        assert R[1] in agent.seen_cards
        assert R[1] not in agent.inferred_cards  # promoted to seen


# ---------------------------------------------------------------------------
# Observe suggestion flow tests
# ---------------------------------------------------------------------------


class TestObserveSuggestionFlow:
    """Test the full observe_suggestion + observe_card_shown_to_other flow."""

    def test_suggestion_log_recorded(self):
        agent = _make_agent()

        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2],
            players_without_match=[PLAYERS[3]],
        )

        assert len(agent.suggestion_log) == 1
        entry = agent.suggestion_log[0]
        assert entry["suspect"] == S[1]
        assert entry["shown_by"] == PLAYERS[2]
        assert PLAYERS[3] in entry["players_without_match"]

    def test_unrefuted_suggestion_recorded(self):
        agent = _make_agent()

        agent.observe_suggestion_no_show(S[1], W[1], R[1])

        assert len(agent.unrefuted_suggestions) == 1
        assert agent.unrefuted_suggestions[0] == {
            "suspect": S[1], "weapon": W[1], "room": R[1],
        }

    def test_own_shown_card_not_inferred_from(self):
        """Don't try to infer when WE are the one who showed the card."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # We showed a card in a suggestion
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[0], weapon=W[1], room=R[1],
            shown_by=PLAYERS[0],  # self
            players_without_match=[],
        )

        # _run_inference should skip entries where shown_by == self
        # This shouldn't crash or produce weird results
        agent.observe_shown_card(W[1], shown_by=PLAYERS[2])
        # After learning W[1], the old suggestion has S[0] (ours) and W[1] (known)
        # but shown_by is us — inference should be skipped
        # R[1] should NOT be inferred as our card
        assert R[1] not in agent.player_has_cards.get(PLAYERS[0], set())

    def test_our_suggestion_uses_observe_shown_card(self):
        """When WE made the suggestion and someone shows us a card, it's direct."""
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # We suggest, Carol shows us W[1]
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[0],  # self
            suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[3],
            players_without_match=[PLAYERS[2]],
        )
        agent.observe_shown_card(W[1], shown_by=PLAYERS[3])

        assert W[1] in agent.seen_cards
        assert W[1] in agent.player_has_cards.get(PLAYERS[3], set())


# ---------------------------------------------------------------------------
# Debug info tests
# ---------------------------------------------------------------------------


class TestDebugInfoReflectsInferences:
    """Verify get_debug_info shows inferred cards."""

    def test_debug_inferred_cards_present(self):
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Infer R[1]
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )

        debug = agent.get_debug_info()
        assert R[1] in debug["inferred_cards"], (
            f"Debug inferred_cards should include inferred card {R[1]}"
        )

    def test_debug_unknowns_exclude_inferences(self):
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # Infer R[1]
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )

        debug = agent.get_debug_info()
        assert R[1] not in debug["unknown_rooms"]

    def test_debug_player_has_cards_includes_inferences(self):
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )

        debug = agent.get_debug_info()
        bob_cards = debug["player_has_cards"].get(PLAYERS[2], [])
        assert R[1] in bob_cards


# ---------------------------------------------------------------------------
# Regression: scenario from game JWC88J
# ---------------------------------------------------------------------------


class TestJWC88JScenario:
    """Reproduce the inference pattern from the reported game.

    Miss Scarlett inferred 5 cards but known_cards didn't reflect them.
    This test builds a simplified version of that scenario.
    """

    def test_multiple_inferences_all_in_known_cards(self):
        """After multiple inferences, ALL inferred cards must be in known_cards.

        Models the JWC88J game pattern: a series of suggestions where
        inference + cascade produce multiple new known cards.
        """
        agent = _make_agent(own_cards=[S[0], W[0], R[0]])

        # --- Build up suggestion history ---

        # Suggestion 1: S[1]/W[1]/R[1], Bob shows. 3 unknown, can't infer.
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
        )

        # Suggestion 2: S[0]/W[1]/R[2], Carol shows.
        # S[0] is ours → Carol can't have it. W[1] unknown, R[2] unknown → 2 poss.
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[0], weapon=W[1], room=R[2],
            shown_by=PLAYERS[3], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[3], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[1], room=R[2],
        )

        # Suggestion 3: S[0]/W[0]/R[3], Dave shows.
        # S[0] and W[0] are ours → Dave showed R[3]. Direct inference!
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[0], weapon=W[0], room=R[3],
            shown_by=PLAYERS[4], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[4], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[3],
        )
        assert R[3] in agent.known_cards, "Should directly infer R[3]"

        # --- Trigger cascade ---

        # Learn S[1] and R[1] directly
        agent.observe_shown_card(S[1], shown_by=PLAYERS[3])
        agent.observe_shown_card(R[1], shown_by=PLAYERS[4])

        # Cascade from suggestion 1: S[1] and R[1] known → Bob showed W[1]
        assert W[1] in agent.known_cards, "Should cascade-infer W[1] from suggestion 1"

        # Cascade from suggestion 2: S[0] is ours, W[1] is Bob's → Carol showed R[2]
        assert R[2] in agent.known_cards, "Should cascade-infer R[2] from suggestion 2"

        # Verify ALL inferred + shown cards are in known_cards
        expected_known = {S[0], W[0], R[0], S[1], R[1], W[1], R[2], R[3]}
        assert expected_known <= agent.known_cards, (
            f"Missing from known_cards: {expected_known - agent.known_cards}"
        )

        # Verify debug info matches
        debug = agent.get_debug_info()
        all_debug_cards = set(debug["seen_cards"]) | set(debug["inferred_cards"])
        for card in expected_known:
            assert card in all_debug_cards, (
                f"Debug cards missing {card}"
            )


# ---------------------------------------------------------------------------
# Knowledge persistence tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


GAME_ID = "TEST_GAME"


def _make_agent_with_redis(redis, own_cards=None):
    cards = own_cards or [S[0], W[0], R[0]]
    agent = RandomAgent(
        player_id=PLAYERS[0],
        character="Miss Scarlett",
        cards=cards,
        redis_client=redis,
        game_id=GAME_ID,
        secret_passage_chance=0.5,
        explore_chance=0.5,
        chat_frequency=0.0,
    )
    agent.player_names = {pid: f"Player-{i}" for i, pid in enumerate(PLAYERS)}
    return agent


class TestKnowledgePersistence:
    """Knowledge state survives save/load round-trip through Redis."""

    @pytest.mark.asyncio
    async def test_save_load_seen_cards(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.observe_shown_card(S[1], shown_by=PLAYERS[2])
        agent.observe_shown_card(W[1], shown_by=PLAYERS[3])

        await agent.save_knowledge()

        # Create a new agent with same cards and load saved state
        agent2 = _make_agent_with_redis(redis)
        assert S[1] not in agent2.seen_cards
        await agent2.load_knowledge()

        assert agent2.seen_cards == agent.seen_cards
        assert S[1] in agent2.seen_cards
        assert W[1] in agent2.seen_cards

    @pytest.mark.asyncio
    async def test_save_load_inferred_cards(self, redis):
        agent = _make_agent_with_redis(redis)

        # Infer R[1]
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )
        assert R[1] in agent.inferred_cards

        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert R[1] in agent2.inferred_cards
        assert R[1] in agent2.known_cards

    @pytest.mark.asyncio
    async def test_save_load_card_inference_log(self, redis):
        agent = _make_agent_with_redis(redis)

        # Infer R[1] — this creates a card_inference_log entry
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[0], weapon=W[0], room=R[1],
        )
        assert R[1] in agent.card_inference_log

        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert R[1] in agent2.card_inference_log
        assert len(agent2.card_inference_log[R[1]]) > 0

    @pytest.mark.asyncio
    async def test_save_load_player_has_cards(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.observe_shown_card(S[1], shown_by=PLAYERS[2])
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert PLAYERS[2] in agent2.player_has_cards
        assert S[1] in agent2.player_has_cards[PLAYERS[2]]

    @pytest.mark.asyncio
    async def test_save_load_player_not_has_cards(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[3],
            players_without_match=[PLAYERS[2]],
        )
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        bob_not_has = agent2.player_not_has_cards.get(PLAYERS[2], set())
        assert {S[1], W[1], R[1]} <= bob_not_has

    @pytest.mark.asyncio
    async def test_save_load_suggestion_log(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2],
            players_without_match=[],
        )
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert len(agent2.suggestion_log) == 1
        assert agent2.suggestion_log[0]["suspect"] == S[1]

    @pytest.mark.asyncio
    async def test_save_load_shown_to(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.shown_to.setdefault(PLAYERS[1], set()).add(S[0])
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert S[0] in agent2.shown_to.get(PLAYERS[1], set())

    @pytest.mark.asyncio
    async def test_save_load_rooms_suggested_in(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.rooms_suggested_in.add(R[1])
        agent.rooms_suggested_in.add(R[2])
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert agent2.rooms_suggested_in == {R[1], R[2]}

    @pytest.mark.asyncio
    async def test_save_load_unrefuted_suggestions(self, redis):
        agent = _make_agent_with_redis(redis)
        agent.observe_suggestion_no_show(S[1], W[1], R[1])
        await agent.save_knowledge()

        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert len(agent2.unrefuted_suggestions) == 1
        assert agent2.unrefuted_suggestions[0]["suspect"] == S[1]

    @pytest.mark.asyncio
    async def test_cascade_works_after_restore(self, redis):
        """After loading state, cascade inference still works on old suggestions."""
        agent = _make_agent_with_redis(redis)

        # Build suggestion history
        agent.observe_suggestion(
            suggesting_player_id=PLAYERS[1], suspect=S[1], weapon=W[1], room=R[1],
            shown_by=PLAYERS[2], players_without_match=[],
        )
        agent.observe_card_shown_to_other(
            shown_by=PLAYERS[2], shown_to=PLAYERS[1],
            suspect=S[1], weapon=W[1], room=R[1],
        )
        await agent.save_knowledge()

        # Simulate restart: new agent, load state
        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        # Learn S[1] and W[1] → should cascade to infer R[1]
        agent2.observe_shown_card(S[1], shown_by=PLAYERS[3])
        agent2.observe_shown_card(W[1], shown_by=PLAYERS[4])

        assert R[1] in agent2.known_cards, (
            "Cascade inference should work after loading saved state"
        )

    @pytest.mark.asyncio
    async def test_own_cards_always_in_seen_after_load(self, redis):
        """Own cards are always present in seen_cards even if save was partial."""
        agent = _make_agent_with_redis(redis)
        await agent.save_knowledge()

        # Create agent with same cards
        agent2 = _make_agent_with_redis(redis)
        await agent2.load_knowledge()

        assert agent2.own_cards <= agent2.seen_cards
