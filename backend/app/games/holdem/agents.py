"""Texas Hold'em agents — automated poker players.

HoldemAgent uses a simple rule-based strategy:
- Evaluates hand strength based on hole cards and community cards
- Makes betting decisions based on hand strength relative to pot odds
- Varies play style with configurable aggression
"""

import logging
import random
from itertools import combinations

from .hand_eval import evaluate_hand, HAND_NAMES, ONE_PAIR, TWO_PAIR, FLUSH, STRAIGHT
from .models import (
    AllInAction,
    BetAction,
    CallAction,
    Card,
    CheckAction,
    FoldAction,
    HoldemAction,
    HoldemGameState,
    HoldemPlayerState,
    MIN_CHIP,
    RANK_VALUES,
    RaiseAction,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Personality presets — classic poker archetypes
# ---------------------------------------------------------------------------

PERSONALITIES: dict[str, dict] = {
    "Rock": {
        "aggression": 0.15,
        "tightness": 0.75,
        "bluff_frequency": 0.03,
        "slowplay_frequency": 0.05,
        "chat_frequency": 0.15,
    },
    "Maniac": {
        "aggression": 0.90,
        "tightness": 0.10,
        "bluff_frequency": 0.45,
        "slowplay_frequency": 0.0,
        "chat_frequency": 0.60,
    },
    "Shark": {
        "aggression": 0.70,
        "tightness": 0.55,
        "bluff_frequency": 0.18,
        "slowplay_frequency": 0.20,
        "chat_frequency": 0.25,
    },
    "Fish": {
        "aggression": 0.25,
        "tightness": 0.20,
        "bluff_frequency": 0.05,
        "slowplay_frequency": 0.0,
        "chat_frequency": 0.40,
    },
    "Nit": {
        "aggression": 0.10,
        "tightness": 0.90,
        "bluff_frequency": 0.01,
        "slowplay_frequency": 0.05,
        "chat_frequency": 0.10,
    },
    "LAG": {
        "aggression": 0.80,
        "tightness": 0.25,
        "bluff_frequency": 0.30,
        "slowplay_frequency": 0.10,
        "chat_frequency": 0.35,
    },
}

PERSONALITY_NAMES = list(PERSONALITIES.keys())


def get_personality(name: str | None = None) -> tuple[str, dict]:
    """Return (personality_name, config_dict). Picks randomly if name is None."""
    if name and name in PERSONALITIES:
        return name, dict(PERSONALITIES[name])
    chosen_name = random.choice(PERSONALITY_NAMES)
    return chosen_name, dict(PERSONALITIES[chosen_name])


# ---------------------------------------------------------------------------
# Preflop hand strength — simple lookup for starting hand categories
# ---------------------------------------------------------------------------

# Premium hands (top ~5%): high pairs, AKs
_PREMIUM = {
    ("A", "A"),
    ("K", "K"),
    ("Q", "Q"),
    ("J", "J"),
    ("A", "K"),  # suited or unsuited
}

# Strong hands (top ~15%): medium pairs, strong aces/kings
_STRONG = {
    ("10", "10"),
    ("9", "9"),
    ("8", "8"),
    ("A", "Q"),
    ("A", "J"),
    ("A", "10"),
    ("K", "Q"),
    ("K", "J"),
}

# Playable hands (top ~30%): small pairs, suited connectors, suited aces
_PLAYABLE = {
    ("7", "7"),
    ("6", "6"),
    ("5", "5"),
    ("4", "4"),
    ("3", "3"),
    ("2", "2"),
    ("A", "9"),
    ("A", "8"),
    ("A", "7"),
    ("A", "6"),
    ("A", "5"),
    ("A", "4"),
    ("A", "3"),
    ("A", "2"),
    ("K", "10"),
    ("Q", "J"),
    ("Q", "10"),
    ("J", "10"),
}


def _hand_key(c1: Card, c2: Card) -> tuple[str, str]:
    """Normalize a 2-card hand to a canonical (high, low) rank pair."""
    v1, v2 = RANK_VALUES[c1.rank], RANK_VALUES[c2.rank]
    if v1 >= v2:
        return (c1.rank, c2.rank)
    return (c2.rank, c1.rank)


def _is_suited(c1: Card, c2: Card) -> bool:
    return c1.suit == c2.suit


def _preflop_strength(cards: list[Card]) -> float:
    """Rate preflop hand strength from 0.0 (trash) to 1.0 (premium).

    Returns a float score used for preflop decisions.
    """
    if len(cards) != 2:
        return 0.0

    key = _hand_key(cards[0], cards[1])
    suited = _is_suited(cards[0], cards[1])

    if key in _PREMIUM:
        return 0.95 if key == ("A", "A") else 0.85
    if key in _STRONG:
        return 0.70 + (0.05 if suited else 0.0)
    if key in _PLAYABLE:
        return 0.45 + (0.05 if suited else 0.0)

    # Connected cards (adjacent ranks) get a small bonus
    v1, v2 = RANK_VALUES[cards[0].rank], RANK_VALUES[cards[1].rank]
    gap = abs(v1 - v2)
    if gap == 1:
        return 0.30 + (0.05 if suited else 0.0)
    if gap == 2 and suited:
        return 0.25

    return 0.15


def _postflop_strength(hole_cards: list[Card], community: list[Card]) -> float:
    """Rate postflop hand strength from 0.0 to 1.0.

    Uses the actual hand evaluation and normalizes the rank.
    """
    all_cards = hole_cards + community
    if len(all_cards) < 5:
        return _preflop_strength(hole_cards)

    score = evaluate_hand(all_cards)
    hand_rank = score[0]  # 0=high card ... 9=royal flush

    # Normalize: high card=0.1, pair=0.3, two pair=0.5, trips=0.6,
    # straight=0.7, flush=0.75, full house=0.85, quads=0.95, sf/rf=1.0
    rank_map = {
        0: 0.10,  # high card
        1: 0.30,  # one pair
        2: 0.50,  # two pair
        3: 0.60,  # three of a kind
        4: 0.70,  # straight
        5: 0.75,  # flush
        6: 0.85,  # full house
        7: 0.95,  # four of a kind
        8: 0.98,  # straight flush
        9: 1.00,  # royal flush
    }
    base = rank_map.get(hand_rank, 0.10)

    # Kicker bonus for pairs: high pair is stronger than low pair
    if hand_rank == 1:  # one pair
        pair_val = score[1]  # value of the pair
        # Scale pair value (2-14) to a 0-0.15 bonus
        base += (pair_val - 2) / 12 * 0.15

    return min(base, 1.0)


class HoldemAgent:
    """Rule-based Texas Hold'em agent.

    Uses hand-strength evaluation to make betting decisions.

    Personality parameters (all 0.0–1.0):
    - aggression: how often it bets/raises vs. checks/calls
    - tightness: how selective with starting hands (high = fewer hands played)
    - bluff_frequency: how often it bets/raises with weak holdings
    - slowplay_frequency: how often it traps with strong hands (check/call)
    - chat_frequency: how often it sends chat messages after actions
    """

    agent_type: str = "holdem_agent"

    def __init__(
        self,
        player_id: str,
        name: str,
        aggression: float = 0.5,
        tightness: float = 0.5,
        bluff_frequency: float = 0.15,
        slowplay_frequency: float = 0.1,
        chat_frequency: float = 0.3,
        personality: str | None = None,
    ):
        self.player_id = player_id
        self.name = name
        self.personality = personality
        self.aggression = max(0.0, min(1.0, aggression))
        self.tightness = max(0.0, min(1.0, tightness))
        self.bluff_frequency = max(0.0, min(1.0, bluff_frequency))
        self.slowplay_frequency = max(0.0, min(1.0, slowplay_frequency))
        self.chat_frequency = max(0.0, min(1.0, chat_frequency))
        logger.info(
            "[holdem_agent] Created agent %s (%s) personality=%s aggression=%.2f "
            "tightness=%.2f bluff=%.2f slowplay=%.2f chat=%.2f",
            player_id,
            name,
            personality or "default",
            self.aggression,
            self.tightness,
            self.bluff_frequency,
            self.slowplay_frequency,
            self.chat_frequency,
        )

    def decide_action(
        self,
        state: HoldemGameState,
        player_state: HoldemPlayerState,
    ) -> HoldemAction:
        """Choose an action based on hand strength and game state."""
        available = player_state.available_actions
        if not available:
            return FoldAction()

        hole_cards = player_state.your_cards
        community = state.community_cards

        # Compute hand strength
        if community:
            strength = _postflop_strength(hole_cards, community)
        else:
            strength = _preflop_strength(hole_cards)

        player = next((p for p in state.players if p.id == self.player_id), None)
        if not player:
            return FoldAction()

        amount_to_call = state.current_bet - player.current_bet
        pot = state.pot

        # Pot odds: what fraction of the new pot are we risking?
        pot_odds = (
            amount_to_call / (pot + amount_to_call) if (pot + amount_to_call) > 0 else 0
        )

        # Tightness adjustment: tight players perceive their hands as weaker
        # (raises the bar for playing), loose players perceive them as stronger
        tightness_shift = (self.tightness - 0.5) * -0.15
        adjusted_strength = strength + tightness_shift

        # Add some randomness scaled by aggression
        effective_strength = adjusted_strength + (random.random() * 0.15 - 0.05) * (
            1 + self.aggression
        )
        effective_strength = max(0.0, min(1.0, effective_strength))

        # Bluff check: occasionally inflate perceived strength with a weak hand
        bluffing = False
        if strength < 0.35 and random.random() < self.bluff_frequency:
            effective_strength = (
                0.55 + random.random() * 0.30
            )  # pretend decent-to-strong
            bluffing = True

        # Slowplay check: occasionally deflate perceived strength with a strong hand
        slowplaying = False
        if strength >= 0.70 and random.random() < self.slowplay_frequency:
            effective_strength = 0.40 + random.random() * 0.10  # pretend medium
            slowplaying = True

        logger.debug(
            "[holdem_agent:%s] strength=%.2f effective=%.2f pot_odds=%.2f "
            "to_call=%d pot=%d available=%s round=%s bluff=%s slowplay=%s",
            self.player_id,
            strength,
            effective_strength,
            pot_odds,
            amount_to_call,
            pot,
            available,
            state.betting_round,
            bluffing,
            slowplaying,
        )

        return self._choose_action(
            available,
            effective_strength,
            pot_odds,
            amount_to_call,
            pot,
            player.chips,
            state,
        )

    def _choose_action(
        self,
        available: list[str],
        strength: float,
        pot_odds: float,
        amount_to_call: int,
        pot: int,
        chips: int,
        state: HoldemGameState,
    ) -> HoldemAction:
        """Select an action based on hand strength thresholds."""

        # Short stack adjustment: with few big blinds left, be more aggressive
        bb_remaining = chips / state.big_blind if state.big_blind > 0 else 999
        short_stack = bb_remaining <= 5

        # Very strong hand — raise or bet aggressively
        if strength >= 0.75:
            if "all_in" in available and (strength >= 0.90 or short_stack):
                return AllInAction()
            if "raise" in available:
                raise_amount = self._compute_raise(
                    pot, amount_to_call, chips, strength, state
                )
                last_raise = getattr(state, 'last_raise_size', state.big_blind)
                min_raise_total = amount_to_call + max(state.big_blind, last_raise)
                if (
                    raise_amount < min_raise_total
                    and "all_in" in available
                ):
                    return AllInAction()
                return RaiseAction(amount=raise_amount)
            if "bet" in available:
                bet_amount = self._compute_bet(pot, chips, strength, state)
                return BetAction(amount=bet_amount)
            if "call" in available:
                return CallAction()
            if "check" in available:
                return CheckAction()

        # Decent hand — call or check, sometimes raise
        if strength >= 0.45:
            if short_stack and "all_in" in available and strength >= 0.60:
                return AllInAction()
            if "check" in available:
                # Sometimes bet with a decent hand
                if "bet" in available and random.random() < self.aggression * 0.5:
                    bet_amount = self._compute_bet(pot, chips, strength, state)
                    return BetAction(amount=bet_amount)
                return CheckAction()
            if "call" in available:
                # Call if pot odds are favorable
                if strength > pot_odds + 0.1:
                    return CallAction()
                # Sometimes call anyway with moderate aggression
                if random.random() < self.aggression * 0.4:
                    return CallAction()
                if short_stack:
                    return CallAction()
                return FoldAction()
            if "raise" in available and random.random() < self.aggression * 0.3:
                raise_amount = self._compute_raise(
                    pot, amount_to_call, chips, strength, state
                )
                last_raise = getattr(state, 'last_raise_size', state.big_blind)
                min_raise_total = amount_to_call + max(state.big_blind, last_raise)
                if (
                    raise_amount < min_raise_total
                    and "all_in" in available
                ):
                    return AllInAction()
                return RaiseAction(amount=raise_amount)

        # Weak hand — check if free, otherwise fold
        if strength >= 0.25:
            if "check" in available:
                return CheckAction()
            if (
                "call" in available
                and amount_to_call <= state.big_blind
                and random.random() < 0.5
            ):
                return CallAction()
            if short_stack and "all_in" in available and random.random() < 0.3:
                return AllInAction()
            return FoldAction()

        # Trash hand — fold unless we can check
        if "check" in available:
            return CheckAction()
        return FoldAction()

    def _compute_bet(
        self, pot: int, chips: int, strength: float, state: HoldemGameState
    ) -> int:
        """Compute a bet amount based on pot size and hand strength."""
        min_bet = state.big_blind
        fraction = 0.33 + (strength - 0.5) * 1.3  # 0.33 to ~1.0
        fraction = max(0.33, min(1.0, fraction))
        amount = max(min_bet, int(pot * fraction))
        amount = min(amount, chips)
        amount = max(min_bet, min(amount, chips))
        # Round down to nearest chip denomination
        if amount < chips:
            amount = (amount // MIN_CHIP) * MIN_CHIP
        return max(min_bet, amount)

    def _compute_raise(
        self,
        pot: int,
        amount_to_call: int,
        chips: int,
        strength: float,
        state: HoldemGameState,
    ) -> int:
        """Compute a raise amount (total bet including call portion)."""
        last_raise = getattr(state, 'last_raise_size', state.big_blind)
        min_raise = amount_to_call + max(state.big_blind, last_raise)
        # Raise between min and 2.5x pot based on strength
        fraction = 0.5 + (strength - 0.5) * 2.0
        fraction = max(0.5, min(2.5, fraction))
        amount = max(min_raise, int(pot * fraction))
        # Cap at available chips — if we can't meet min_raise, go all-in
        amount = min(amount, chips)
        # Round down to nearest chip denomination
        if amount < chips:
            amount = (amount // MIN_CHIP) * MIN_CHIP
            amount = max(min_raise, amount)
        return amount

    def generate_chat(self, action_type: str, **kwargs) -> str | None:
        """Occasionally generate a personality-flavored chat message."""
        if random.random() > self.chat_frequency:
            return None

        options = _PERSONALITY_CHAT.get(self.personality, _DEFAULT_CHAT).get(
            action_type
        )

        if not options:
            options = _DEFAULT_CHAT.get(action_type, ["Hmm..."])

        return random.choice(options)


# ---------------------------------------------------------------------------
# Per-personality chat lines
# ---------------------------------------------------------------------------

_DEFAULT_CHAT: dict[str, list[str]] = {
    "fold": ["Not my hand.", "I'll sit this one out.", "Too rich for my blood."],
    "check": ["Check.", "I'll check here.", "Let's see what comes."],
    "call": ["I'll call.", "I'm in.", "Let's see the next card."],
    "bet": [
        "Putting some chips out there.",
        "Let's make it interesting.",
        "I like what I see.",
    ],
    "raise": ["Raising it up.", "Let's go bigger.", "I think I've got something here."],
    "all_in": ["All in!", "Going for it all!", "Let's gamble!"],
}

_PERSONALITY_CHAT: dict[str, dict[str, list[str]]] = {
    "Rock": {
        "fold": [
            "I'll wait for a better spot.",
            "Patience pays.",
            "Not worth the risk.",
        ],
        "check": ["Check.", "No need to rush."],
        "call": ["I'll see it.", "Alright, I'll call."],
        "bet": ["I've got something here.", "Time to value bet."],
        "raise": ["Premium hand. Raising.", "You're going to pay for that."],
        "all_in": ["I've got the goods. All in.", "Nuts. All in."],
    },
    "Maniac": {
        "fold": ["Fine, FINE. I fold.", "You got lucky.", "Whatever."],
        "check": ["Check… for now.", "I'm setting a trap!"],
        "call": ["Yeah yeah, I call.", "Can't scare me off."],
        "bet": ["BOOM! Bet!", "Let's gooo!", "Chips go in!"],
        "raise": ["RAISE! Let's party!", "You can't handle this!", "Scared yet?"],
        "all_in": ["ALL IN BABY!", "YOLO!", "Ship it! ALL IN!"],
    },
    "Shark": {
        "fold": ["Not this time.", "I'll pick a better spot."],
        "check": ["Check.", "Let's see the next card."],
        "call": ["Pot odds say call.", "I'll call."],
        "bet": ["Betting for value.", "Let's build the pot."],
        "raise": ["Raising.", "I like my equity here."],
        "all_in": ["All in. Your move.", "I'm putting you to the test."],
    },
    "Fish": {
        "fold": ["Aww, okay.", "I guess I'll fold…", "This game is hard."],
        "check": ["Check!", "I'll check, I guess?"],
        "call": ["Ooh, I'll call!", "I wanna see!", "Sounds fun, call!"],
        "bet": ["Let me try betting!", "I'll put some in.", "Bet!"],
        "raise": ["Raise! Is that right?", "More chips!", "I'm raising!"],
        "all_in": ["All in! Wheee!", "I'm going for it!", "All my chips!"],
    },
    "Nit": {
        "fold": ["Fold.", "Easy fold.", "Not even close."],
        "check": ["Check.", "Checking."],
        "call": ["…Fine. Call.", "I suppose I'll call."],
        "bet": ["Betting.", "I have a strong hand."],
        "raise": ["Raise. I have it.", "Big hand. Raising."],
        "all_in": ["I have the nuts. All in.", "All in."],
    },
    "LAG": {
        "fold": ["Alright, you got me.", "Nice hand.", "I'll let this one go."],
        "check": ["Check. For now.", "Trapping…"],
        "call": ["Call. Let's dance.", "I'm not going anywhere."],
        "bet": ["Bet. Put up or shut up.", "Applying pressure.", "Let's go."],
        "raise": [
            "Raise! Keep up.",
            "Re-raise. Your move.",
            "Putting you to the test.",
        ],
        "all_in": ["All in. Do you have it?", "Shove. Call me if you dare."],
    },
}
