import random
from .game import SUSPECTS, WEAPONS, ROOMS


class LLMAgent:
    """Rule-based Clue agent that tracks seen cards and uses elimination logic.

    The agent maintains a ``seen_cards`` set of all cards it knows are NOT part
    of the solution (own hand + cards shown to it + cards it showed others).
    It uses this to:

    1. **Move** toward rooms it hasn't eliminated yet.
    2. **Suggest** unknown suspects/weapons in the current room to gather info.
    3. **Accuse** only when it has narrowed each category to exactly one
       remaining candidate.
    4. **Show cards** strategically (prefer showing a card already seen by the
       requester, otherwise pick randomly from matching cards).

    ``decide_action`` and ``decide_show_card`` are the two entry points called
    by the game loop.
    """

    def __init__(self):
        self.seen_cards: set[str] = set()
        # Track which cards have been shown to whom, for smarter show_card choices
        self.shown_to: dict[str, set[str]] = {}  # player_id -> set of cards they've seen
        # Track rooms we've already visited/suggested in (lower priority targets)
        self.rooms_suggested_in: set[str] = set()
        # Track suggestions where no one could show a card
        self.unrefuted_suggestions: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe_own_cards(self, cards: list[str]):
        """Called once at game start with the agent's dealt hand."""
        self.seen_cards.update(cards)

    def observe_shown_card(self, card: str, shown_by: str | None = None):
        """Called when another player shows us a card."""
        self.seen_cards.add(card)

    def observe_suggestion_no_show(self, suspect: str, weapon: str, room: str):
        """Called when a suggestion gets no card shown by anyone.

        This means no other player holds any of those three cards.  If we
        hold some of them ourselves, the ones we *don't* hold could be part
        of the solution.
        """
        self.unrefuted_suggestions.append({
            "suspect": suspect, "weapon": weapon, "room": room,
        })

    def observe_card_shown_to_other(self, shown_by: str, shown_to: str):
        """Called when we see that player A showed a card to player B.

        We don't know which card, but this is noted for future logic.
        """
        pass  # Could be used for advanced inference

    def decide_action(self, game_state: dict, player_state: dict) -> dict:
        """Return an action dict for the current turn phase."""
        player_id = player_state.get("your_player_id")
        known_cards: list[str] = player_state.get("your_cards", [])
        current_room: dict = game_state.get("current_room", {})
        dice_rolled: bool = game_state.get("dice_rolled", False)
        available: list[str] = player_state.get("available_actions", [])

        # Make sure own cards are tracked
        self.seen_cards.update(known_cards)

        # Compute unknown cards per category
        unknown_suspects = [s for s in SUSPECTS if s not in self.seen_cards]
        unknown_weapons = [w for w in WEAPONS if w not in self.seen_cards]
        unknown_rooms = [r for r in ROOMS if r not in self.seen_cards]

        # If we've narrowed each category to exactly one, accuse!
        if (len(unknown_suspects) == 1 and len(unknown_weapons) == 1
                and len(unknown_rooms) == 1 and "accuse" in available):
            return {
                "type": "accuse",
                "suspect": unknown_suspects[0],
                "weapon": unknown_weapons[0],
                "room": unknown_rooms[0],
            }

        # Phase 1: move (dice not rolled yet)
        if not dice_rolled and "move" in available:
            target_room = self._pick_target_room(unknown_rooms, current_room.get(player_id))
            return {"type": "move", "room": target_room}

        # Phase 2: suggest if in a room and suggestion is available
        room = current_room.get(player_id)
        if room and "suggest" in available:
            suspect = self._pick_unknown_or_random(unknown_suspects, SUSPECTS)
            weapon = self._pick_unknown_or_random(unknown_weapons, WEAPONS)
            self.rooms_suggested_in.add(room)
            return {
                "type": "suggest",
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
            }

        # Phase 3: end turn
        if "end_turn" in available:
            return {"type": "end_turn"}

        # Fallback (shouldn't happen)
        return {"type": "end_turn"}

    def decide_show_card(self, matching_cards: list[str],
                         suggesting_player_id: str) -> str:
        """Pick which card to reveal when we must show one.

        Strategy: prefer showing a card the requester has already seen
        (so we don't give away new information).  If none qualify, show a
        card we've already shown to anyone, then fall back to random.
        """
        # Prefer a card the suggesting player already knows about
        already_known = self.shown_to.get(suggesting_player_id, set())
        for card in matching_cards:
            if card in already_known:
                return card

        # Otherwise pick any card and record it
        card = random.choice(matching_cards)
        self.shown_to.setdefault(suggesting_player_id, set()).add(card)
        return card

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick_target_room(self, unknown_rooms: list[str],
                          current_room: str | None) -> str:
        """Pick the best room to move toward.

        Priority:
        1. Unknown rooms we haven't suggested in yet
        2. Unknown rooms (even if suggested in before — maybe we'll learn more)
        3. Any room we haven't suggested in
        4. Random room
        """
        # Rooms we don't know about AND haven't visited
        fresh_unknown = [r for r in unknown_rooms
                         if r not in self.rooms_suggested_in and r != current_room]
        if fresh_unknown:
            return random.choice(fresh_unknown)

        # Unknown rooms we may have visited
        other_unknown = [r for r in unknown_rooms if r != current_room]
        if other_unknown:
            return random.choice(other_unknown)

        # Rooms not yet suggested in
        unseen = [r for r in ROOMS
                  if r not in self.rooms_suggested_in and r != current_room]
        if unseen:
            return random.choice(unseen)

        # Fallback: random room
        choices = [r for r in ROOMS if r != current_room]
        return random.choice(choices) if choices else random.choice(ROOMS)

    @staticmethod
    def _pick_unknown_or_random(unknown: list[str], full_list: list[str]) -> str:
        """Pick a random unknown card, or any card if all are known."""
        if unknown:
            return random.choice(unknown)
        return random.choice(full_list)
