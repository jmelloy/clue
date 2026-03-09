"""Texas Hold'em hand evaluation.

Evaluates the best 5-card hand from 7 cards (2 hole + 5 community).
Returns a comparable tuple: (hand_rank, tiebreakers...) where higher is better.
"""

from __future__ import annotations

from itertools import combinations

from .models import Card, RANK_VALUES

# Hand ranking constants (higher = better)
HIGH_CARD = 0
ONE_PAIR = 1
TWO_PAIR = 2
THREE_OF_A_KIND = 3
STRAIGHT = 4
FLUSH = 5
FULL_HOUSE = 6
FOUR_OF_A_KIND = 7
STRAIGHT_FLUSH = 8
ROYAL_FLUSH = 9

HAND_NAMES = {
    HIGH_CARD: "High Card",
    ONE_PAIR: "One Pair",
    TWO_PAIR: "Two Pair",
    THREE_OF_A_KIND: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    FOUR_OF_A_KIND: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
    ROYAL_FLUSH: "Royal Flush",
}


def _card_value(card: Card) -> int:
    return RANK_VALUES[card.rank]


def _evaluate_five(cards: list[Card]) -> tuple:
    """Evaluate exactly 5 cards and return a rank tuple for comparison."""
    values = sorted([_card_value(c) for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    is_flush = len(set(suits)) == 1

    # Check for straight
    is_straight = False
    straight_high = 0
    unique_vals = sorted(set(values), reverse=True)
    if len(unique_vals) >= 5:
        for i in range(len(unique_vals) - 4):
            window = unique_vals[i : i + 5]
            if window[0] - window[4] == 4:
                is_straight = True
                straight_high = window[0]
                break
        # Ace-low straight (A-2-3-4-5): ace=14, check {14,5,4,3,2}
        if not is_straight and set(unique_vals) >= {14, 2, 3, 4, 5}:
            is_straight = True
            straight_high = 5  # 5-high straight

    # Count rank groups
    from collections import Counter

    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if is_straight and is_flush:
        if straight_high == 14 and min(values) == 10:
            return (ROYAL_FLUSH, 14)
        return (STRAIGHT_FLUSH, straight_high)

    if groups[0][1] == 4:
        quad_val = groups[0][0]
        kicker = max(v for v in values if v != quad_val)
        return (FOUR_OF_A_KIND, quad_val, kicker)

    if groups[0][1] == 3 and groups[1][1] >= 2:
        trips_val = groups[0][0]
        pair_val = groups[1][0]
        return (FULL_HOUSE, trips_val, pair_val)

    if is_flush:
        return (FLUSH, *values)

    if is_straight:
        return (STRAIGHT, straight_high)

    if groups[0][1] == 3:
        trips_val = groups[0][0]
        kickers = sorted([v for v in values if v != trips_val], reverse=True)
        return (THREE_OF_A_KIND, trips_val, *kickers[:2])

    if groups[0][1] == 2 and groups[1][1] == 2:
        high_pair = groups[0][0]
        low_pair = groups[1][0]
        kicker = max(v for v in values if v not in (high_pair, low_pair))
        return (TWO_PAIR, high_pair, low_pair, kicker)

    if groups[0][1] == 2:
        pair_val = groups[0][0]
        kickers = sorted([v for v in values if v != pair_val], reverse=True)
        return (ONE_PAIR, pair_val, *kickers[:3])

    return (HIGH_CARD, *values)


def evaluate_hand(cards: list[Card]) -> tuple:
    """Evaluate the best 5-card hand from the given cards (up to 7).

    Returns a tuple where higher values beat lower values.
    """
    if len(cards) <= 5:
        return _evaluate_five(cards)

    best = None
    for combo in combinations(cards, 5):
        score = _evaluate_five(list(combo))
        if best is None or score > best:
            best = score
    return best


def hand_name(score: tuple) -> str:
    """Return a human-readable name for a hand score tuple."""
    return HAND_NAMES.get(score[0], "Unknown")
