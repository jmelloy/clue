"""Clue game agents — automated players with different decision strategies.

BaseAgent defines the shared interface and card-tracking logic.
RandomAgent uses rule-based elimination with random selection.
WandererAgent just moves to a random room and ends its turn (no suggestions/accusations).
LLMAgent delegates decisions to an LLM API (with RandomAgent fallback).
"""

import json
import logging
import os
import random
from abc import ABC, abstractmethod

import httpx

from .game import SUSPECTS, WEAPONS, ROOMS, SECRET_PASSAGE_MAP
from .board import (
    Room,
    build_grid,
    build_graph,
    reachable as bfs_reachable,
    SquareType,
)

# Pre-build the board graph for agent pathfinding
_GRID = build_grid()
_SQUARES, _ROOM_NODES = build_graph(_GRID)
_ROOM_NAME_TO_ENUM = {r.value: r for r in Room}
from .models import GameState, PlayerState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Character personality chat templates
# ---------------------------------------------------------------------------

# Probability that an agent sends a chat message after each action type.
_CHAT_PROBABILITY: dict[str, float] = {
    "roll": 0.7,
    "move": 0.7,
    "suggest": 1.0,
    "accuse": 1.0,
    "end_turn": 0.3,
    "show_card": 0.5,
    "secret_passage": 0.9,
}

# Per-character, per-action message templates.  Use {dice}, {room}, {suspect},
# {weapon} as optional format placeholders — missing keys are silently ignored.
CHARACTER_CHAT: dict[str, dict[str, list[str]]] = {
    "Miss Scarlett": {
        "roll": [
            "Come on, lucky number!",
            "A {dice}? I suppose that'll do.",
            "The suspense is simply killing me!",
            "Fortune favors the bold, darling.",
        ],
        "move": [
            "Off to the {room}. Try to keep up, everyone!",
            "The {room}... how intriguing.",
            "I always look good arriving somewhere new.",
            "Let's see what secrets the {room} holds.",
        ],
        "suggest": [
            "I have a hunch... call it feminine intuition.",
            "Something tells me it was {suspect} with the {weapon}.",
            "Trust me, darlings. I know what happened here.",
            "A little birdie told me about {suspect}...",
        ],
        "accuse": [
            "I've figured it all out. Prepare to be dazzled!",
            "The truth always comes out, darling. And here it is!",
        ],
        "end_turn": [
            "Your move. Don't bore me.",
            "I'll be watching closely...",
            "Fine, I'll wait. But not patiently.",
        ],
        "show_card": [
            "Oh, if I must... you're welcome for the peek.",
            "Don't get too excited, dear.",
        ],
        "secret_passage": [
            "A secret passage? How absolutely thrilling!",
            "Ooh, sneaky sneaky. I love it!",
        ],
    },
    "Colonel Mustard": {
        "roll": [
            "Right then, let's see what we've got!",
            "A {dice}! Onward!",
            "Steady as she goes.",
            "In my army days, we made do with worse odds.",
        ],
        "move": [
            "Advancing to the {room}. Good tactical position.",
            "The {room} it is. I have a feeling about this one.",
            "Strategic repositioning to the {room}.",
            "Forward march to the {room}!",
        ],
        "suggest": [
            "Based on my analysis, I suspect {suspect} with the {weapon}.",
            "Military intelligence suggests {suspect} is our culprit.",
            "I've been watching everyone. {suspect} looks guilty to me.",
            "Time to interrogate. {suspect}, you have some explaining to do!",
        ],
        "accuse": [
            "Case closed! Years of tactical training pay off!",
            "I'm making my accusation. A colonel is never wrong!",
        ],
        "end_turn": [
            "Carry on, next player.",
            "At ease. Your turn.",
            "Standing by for the next move.",
        ],
        "show_card": [
            "Very well. Intelligence shared.",
            "Here you go. Use it wisely.",
        ],
        "secret_passage": [
            "Excellent! A tactical shortcut!",
            "Secret passages — every good estate has them.",
        ],
    },
    "Mrs. White": {
        "roll": [
            "Oh my... a {dice}.",
            "Let's see now... oh dear.",
            "I've been rolling dice since before you were born.",
            "Hmm, a {dice}. I've seen better, I've seen worse.",
        ],
        "move": [
            "Off to the {room}. I know this house like the back of my hand.",
            "The {room}? I just cleaned in there!",
            "I've dusted every corner of the {room}.",
            "Back to the {room} again. There's always something to find.",
        ],
        "suggest": [
            "Now, I don't like to gossip, but... {suspect} with the {weapon}?",
            "I've seen things in this house. {suspect} has been acting suspicious.",
            "Between you and me, I think {suspect} did it.",
            "I may just be the housekeeper, but I notice everything.",
        ],
        "accuse": [
            "I've kept quiet long enough. I KNOW what happened!",
            "After all these years of service, I finally have the answer!",
        ],
        "end_turn": [
            "Right then. Who's next?",
            "I'll just be over here. Watching.",
            "Don't mind me.",
        ],
        "show_card": [
            "Oh, very well. But you didn't hear it from me.",
            "I suppose you should see this. Discreetly, please.",
        ],
        "secret_passage": [
            "I know every hidden nook in this house!",
            "These old walls have more secrets than you'd think.",
        ],
    },
    "Reverend Green": {
        "roll": [
            "The Lord provides... a {dice}.",
            "Let us see what fortune delivers.",
            "Providence smiles upon us... or perhaps not.",
            "A {dice}? Everything happens for a reason.",
        ],
        "move": [
            "I shall make my way to the {room}. Peacefully.",
            "The {room} calls to me. Perhaps the truth awaits there.",
            "Onward to the {room}, with a clear conscience.",
            "Let me visit the {room}. For... spiritual reasons.",
        ],
        "suggest": [
            "Forgive me, but I must suggest... {suspect} with the {weapon}.",
            "Confession is good for the soul, {suspect}.",
            "Let us seek the truth. Was it {suspect} with the {weapon}?",
            "I hate to cast suspicion, but someone must.",
        ],
        "accuse": [
            "The truth shall set us free! I know who did it!",
            "By all that is holy, I have solved this mystery!",
        ],
        "end_turn": [
            "Patience is a virtue. Next player, please.",
            "I shall reflect quietly while you take your turn.",
            "Go in peace. And suspicion.",
        ],
        "show_card": [
            "In the spirit of honesty...",
            "The truth must be shared, even reluctantly.",
        ],
        "secret_passage": [
            "Even a man of the cloth knows a shortcut or two.",
            "The Lord works in mysterious passages.",
        ],
    },
    "Mrs. Peacock": {
        "roll": [
            "A {dice}? How perfectly adequate.",
            "One does what one can with a {dice}.",
            "Rolling dice... how undignified. But necessary.",
            "Let's get on with it, shall we?",
        ],
        "move": [
            "I shall retire to the {room}.",
            "The {room}? I suppose it will have to do.",
            "To the {room}. I expect it to be properly maintained.",
            "Moving to the {room}. Do try to keep things orderly.",
        ],
        "suggest": [
            "If I may be so bold — {suspect} with the {weapon}.",
            "I have my suspicions about {suspect}. Quite serious ones.",
            "Good breeding aside, {suspect} seems rather guilty.",
            "One hears things at parties. {suspect}, for instance.",
        ],
        "accuse": [
            "I am quite certain of this. My reputation depends on it!",
            "Mark my words — I know exactly who is responsible!",
        ],
        "end_turn": [
            "Your turn. Do be quick about it.",
            "I believe it's someone else's turn now.",
            "Next, please. Time is of the essence.",
        ],
        "show_card": [
            "I suppose you need to see this. How tiresome.",
            "Very well. But do keep this between us.",
        ],
        "secret_passage": [
            "How convenient. Even I can appreciate a shortcut.",
            "Secret passages are terribly gauche, but useful.",
        ],
    },
    "Professor Plum": {
        "roll": [
            "Statistically speaking, a {dice} is... interesting.",
            "Hmm, a {dice}. Let me think about what that means.",
            "Fascinating! The probability of rolling that was exactly 1 in 6.",
            "A {dice}. Yes, yes, I can work with that.",
        ],
        "move": [
            "To the {room}! I believe I left my notes there.",
            "The {room}... now what was I going there for again?",
            "Ah yes, the {room}. Excellent for contemplation.",
            "I have a hypothesis about the {room}.",
        ],
        "suggest": [
            "My research indicates {suspect} with the {weapon}. Probably.",
            "According to my deductions — and I do have a PhD — {suspect} is suspicious.",
            "Elementary deduction points to {suspect} with the {weapon}.",
            "I've been running the numbers. {suspect} is statistically likely.",
        ],
        "accuse": [
            "Eureka! The solution is clear as day! Well, to me at least.",
            "After careful academic analysis, I've solved it!",
        ],
        "end_turn": [
            "I need time to think. Your turn.",
            "Let me consult my notes while you go.",
            "Hmm, where was I? Oh yes, your turn.",
        ],
        "show_card": [
            "For the sake of scientific transparency...",
            "Here, take a look. Knowledge should be shared. Usually.",
        ],
        "secret_passage": [
            "Ah, a secret passage! Architecturally fascinating!",
            "I wrote a paper on secret passages once. Or was it bridges?",
        ],
    },
}

# Fallback messages for characters not in CHARACTER_CHAT
_GENERIC_CHAT: dict[str, list[str]] = {
    "roll": ["Let's see...", "Here goes nothing."],
    "move": ["Heading to the {room}.", "On my way."],
    "suggest": ["I think it was {suspect} with the {weapon}.", "Interesting theory..."],
    "accuse": ["I've solved it!", "This is it!"],
    "end_turn": ["Next player.", "Your turn."],
    "show_card": ["Take a look.", "Here you go."],
    "secret_passage": ["A shortcut!", "Through the passage!"],
}


def _format_chat(template: str, context: dict) -> str:
    """Format a chat template, silently ignoring missing keys."""
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        return template


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Abstract base for Clue game agents.

    Maintains a ``seen_cards`` set of all cards known not to be in the
    solution (own hand + shown cards).  Subclasses implement the two
    decision methods: ``decide_action`` and ``decide_show_card``.
    """

    agent_type: str = "base"

    def __init__(self):
        self.seen_cards: set[str] = set()
        self.shown_to: dict[str, set[str]] = {}
        self.rooms_suggested_in: set[str] = set()
        self.unrefuted_suggestions: list[dict] = []
        self.character: str = ""
        self._pending_chat: str | None = None
        logger.info("[%s] Agent instance created", self.agent_type)

    # ------------------------------------------------------------------
    # Observations (shared by all agent types)
    # ------------------------------------------------------------------

    def observe_own_cards(self, cards: list[str]):
        """Called once at game start with the agent's dealt hand."""
        self.seen_cards.update(cards)
        logger.info(
            "[%s] Received hand: %s (%d cards)", self.agent_type, cards, len(cards)
        )

    def observe_shown_card(self, card: str, shown_by: str | None = None):
        """Called when another player shows us a card."""
        is_new = card not in self.seen_cards
        self.seen_cards.add(card)
        logger.info(
            "[%s] Card shown by %s: '%s' (new_info=%s, total_seen=%d)",
            self.agent_type,
            shown_by,
            card,
            is_new,
            len(self.seen_cards),
        )

    def observe_suggestion_no_show(self, suspect: str, weapon: str, room: str):
        """Called when a suggestion gets no card shown by anyone."""
        self.unrefuted_suggestions.append(
            {"suspect": suspect, "weapon": weapon, "room": room}
        )
        logger.info(
            "[%s] Unrefuted suggestion: %s / %s / %s (total_unrefuted=%d)",
            self.agent_type,
            suspect,
            weapon,
            room,
            len(self.unrefuted_suggestions),
        )

    def observe_card_shown_to_other(self, shown_by: str, shown_to: str):
        """Called when we see that player A showed a card to player B."""
        logger.debug(
            "[%s] Observed: %s showed a card to %s",
            self.agent_type,
            shown_by,
            shown_to,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_unknowns(self) -> tuple[list[str], list[str], list[str]]:
        """Return (unknown_suspects, unknown_weapons, unknown_rooms)."""
        unknown_suspects = [s for s in SUSPECTS if s not in self.seen_cards]
        unknown_weapons = [w for w in WEAPONS if w not in self.seen_cards]
        unknown_rooms = [r for r in ROOMS if r not in self.seen_cards]
        return unknown_suspects, unknown_weapons, unknown_rooms

    # ------------------------------------------------------------------
    # Chat generation
    # ------------------------------------------------------------------

    def generate_chat(
        self, action_type: str, context: dict | None = None
    ) -> str | None:
        """Return an in-character chat message after an action, or None.

        Checks a per-action probability, then picks a random template from
        the character's personality set and formats it with the given context.
        """
        # If the subclass stashed a message (e.g. from an LLM), use it
        if self._pending_chat:
            msg = self._pending_chat
            self._pending_chat = None
            return msg

        prob = _CHAT_PROBABILITY.get(action_type, 0.5)
        if random.random() > prob:
            return None

        char_msgs = CHARACTER_CHAT.get(self.character, {})
        templates = char_msgs.get(action_type) or _GENERIC_CHAT.get(action_type)
        if not templates:
            return None

        template = random.choice(templates)
        return _format_chat(template, context or {})

    # ------------------------------------------------------------------
    # Decision interface (async to support LLM calls)
    # ------------------------------------------------------------------

    @abstractmethod
    async def decide_action(
        self, game_state: GameState, player_state: PlayerState
    ) -> dict:
        """Return an action dict for the current turn phase."""
        ...

    @abstractmethod
    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        """Pick which card to reveal when we must show one."""
        ...


# ---------------------------------------------------------------------------
# RandomAgent (formerly LLMAgent — rule-based elimination + random choices)
# ---------------------------------------------------------------------------


class RandomAgent(BaseAgent):
    """Rule-based Clue agent that tracks seen cards and uses elimination logic.

    The agent maintains a ``seen_cards`` set of all cards it knows are NOT
    part of the solution (own hand + cards shown to it + cards it showed
    others).  It uses this to:

    1. **Move** toward rooms it hasn't eliminated yet.
    2. **Suggest** unknown suspects/weapons in the current room.
    3. **Accuse** only when it has narrowed each category to exactly one
       remaining candidate.
    4. **Show cards** strategically (prefer cards the requester already knows).
    """

    agent_type = "random"

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    async def decide_action(
        self, game_state: GameState, player_state: PlayerState
    ) -> dict:
        player_id = player_state.your_player_id
        known_cards = player_state.your_cards
        current_room = game_state.current_room
        dice_rolled = game_state.dice_rolled
        available = player_state.available_actions

        self.seen_cards.update(known_cards)
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        logger.info(
            "[%s:%s] Deciding action | available=%s | dice_rolled=%s | "
            "unknown: suspects=%d weapons=%d rooms=%d | seen_total=%d",
            self.agent_type,
            player_id,
            available,
            dice_rolled,
            len(unknown_suspects),
            len(unknown_weapons),
            len(unknown_rooms),
            len(self.seen_cards),
        )

        # Accuse if we've narrowed to exactly one per category
        if (
            len(unknown_suspects) == 1
            and len(unknown_weapons) == 1
            and len(unknown_rooms) == 1
            and "accuse" in available
        ):
            action = {
                "type": "accuse",
                "suspect": unknown_suspects[0],
                "weapon": unknown_weapons[0],
                "room": unknown_rooms[0],
            }
            logger.info(
                "[%s:%s] ACCUSING — narrowed to: %s / %s / %s",
                self.agent_type,
                player_id,
                unknown_suspects[0],
                unknown_weapons[0],
                unknown_rooms[0],
            )
            return action

        # Phase 1a: use secret passage if available and destination is useful
        if "secret_passage" in available:
            my_room = current_room.get(player_id)
            dest_room = SECRET_PASSAGE_MAP.get(my_room) if my_room else None
            if dest_room and dest_room in unknown_rooms:
                logger.info(
                    "[%s:%s] Using secret passage from %s to %s",
                    self.agent_type,
                    player_id,
                    my_room,
                    dest_room,
                )
                return {"type": "secret_passage"}

        # Phase 1b: roll dice
        if "roll" in available:
            logger.info("[%s:%s] Rolling dice", self.agent_type, player_id)
            return {"type": "roll"}

        # Phase 2: choose room to move toward (dice already rolled)
        if "move" in available:
            player_pos = game_state.player_positions.get(player_id)
            target_room = self._pick_target_room(
                unknown_rooms, current_room.get(player_id), player_pos
            )
            logger.info(
                "[%s:%s] Moving to '%s' (current=%s, unknown_rooms=%s)",
                self.agent_type,
                player_id,
                target_room,
                current_room.get(player_id),
                unknown_rooms,
            )
            return {"type": "move", "room": target_room}

        # Phase 3: suggest if in a room
        room = current_room.get(player_id)
        if room and "suggest" in available:
            suspect = self._pick_unknown_or_random(unknown_suspects, SUSPECTS)
            weapon = self._pick_unknown_or_random(unknown_weapons, WEAPONS)
            self.rooms_suggested_in.add(room)
            logger.info(
                "[%s:%s] Suggesting %s / %s / %s",
                self.agent_type,
                player_id,
                suspect,
                weapon,
                room,
            )
            return {
                "type": "suggest",
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
            }

        # Phase 4: end turn
        logger.info("[%s:%s] Ending turn", self.agent_type, player_id)
        return {"type": "end_turn"}

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        logger.info(
            "[%s] Deciding which card to show to %s from %s",
            self.agent_type,
            suggesting_player_id,
            matching_cards,
        )

        # Prefer a card the suggesting player already knows about
        already_known = self.shown_to.get(suggesting_player_id, set())
        for card in matching_cards:
            if card in already_known:
                logger.info(
                    "[%s] Showing '%s' (already known to %s)",
                    self.agent_type,
                    card,
                    suggesting_player_id,
                )
                return card

        # Otherwise pick randomly and record it
        card = random.choice(matching_cards)
        self.shown_to.setdefault(suggesting_player_id, set()).add(card)
        logger.info(
            "[%s] Showing '%s' (random choice, new info for %s)",
            self.agent_type,
            card,
            suggesting_player_id,
        )
        return card

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick_target_room(
        self,
        unknown_rooms: list[str],
        current_room: str | None,
        player_position: list | None = None,
    ) -> str:
        """Pick the best room to move toward, preferring closer rooms.

        Priority:
        1. Unknown rooms we haven't suggested in yet (weighted by proximity)
        2. Unknown rooms (even if suggested in before, weighted by proximity)
        3. Any room we haven't suggested in (weighted by proximity)
        4. Random room (weighted by proximity)
        """
        fresh_unknown = [
            r
            for r in unknown_rooms
            if r not in self.rooms_suggested_in and r != current_room
        ]
        if fresh_unknown:
            choice = self._pick_nearest_room(
                fresh_unknown, current_room, player_position
            )
            logger.debug(
                "[%s] Target room '%s' (fresh unknown, proximity-weighted)",
                self.agent_type,
                choice,
            )
            return choice

        other_unknown = [r for r in unknown_rooms if r != current_room]
        if other_unknown:
            choice = self._pick_nearest_room(
                other_unknown, current_room, player_position
            )
            logger.debug(
                "[%s] Target room '%s' (other unknown, proximity-weighted)",
                self.agent_type,
                choice,
            )
            return choice

        unseen = [
            r for r in ROOMS if r not in self.rooms_suggested_in and r != current_room
        ]
        if unseen:
            choice = self._pick_nearest_room(unseen, current_room, player_position)
            logger.debug(
                "[%s] Target room '%s' (unvisited, proximity-weighted)",
                self.agent_type,
                choice,
            )
            return choice

        choices = [r for r in ROOMS if r != current_room]
        if not choices:
            choices = list(ROOMS)
        choice = self._pick_nearest_room(choices, current_room, player_position)
        logger.debug(
            "[%s] Target room '%s' (fallback, proximity-weighted)",
            self.agent_type,
            choice,
        )
        return choice

    @staticmethod
    def _pick_nearest_room(
        candidates: list[str],
        current_room: str | None,
        player_position: list | None,
    ) -> str:
        """Pick a room from candidates, biased toward nearer rooms.

        Uses BFS distance on the board graph.  Closer rooms get higher
        weight so the agent doesn't waste turns crossing the entire board.
        Falls back to random choice if position data is unavailable.
        """
        from collections import deque

        if len(candidates) == 1:
            return candidates[0]

        # Determine the starting square for distance calculation
        start_sq = None
        if current_room and current_room in _ROOM_NAME_TO_ENUM:
            start_sq = _ROOM_NODES.get(_ROOM_NAME_TO_ENUM[current_room])
        elif player_position:
            start_sq = _SQUARES.get((player_position[0], player_position[1]))

        if start_sq is None:
            return random.choice(candidates)

        # BFS from start to get distance to every room node
        dist_map: dict = {start_sq: 0}
        queue: deque = deque([(start_sq, 0)])
        while queue:
            sq, d = queue.popleft()
            for nb in sq.neighbors:
                if nb not in dist_map:
                    dist_map[nb] = d + 1
                    if nb.type != SquareType.ROOM:
                        queue.append((nb, d + 1))

        # Compute distances to each candidate room
        room_dists = {}
        for room_name in candidates:
            room_enum = _ROOM_NAME_TO_ENUM.get(room_name)
            if room_enum:
                node = _ROOM_NODES.get(room_enum)
                if node and node in dist_map:
                    room_dists[room_name] = dist_map[node]

        if not room_dists:
            return random.choice(candidates)

        # Weight inversely proportional to distance (closer = higher weight)
        # Use 1/(dist+1) so that rooms at distance 0 still get finite weight
        weights = []
        rooms_list = list(room_dists.keys())
        for r in rooms_list:
            weights.append(1.0 / (room_dists[r] + 1))

        return random.choices(rooms_list, weights=weights, k=1)[0]

    @staticmethod
    def _pick_unknown_or_random(unknown: list[str], full_list: list[str]) -> str:
        """Pick a random unknown card, or any card if all are known."""
        if unknown:
            return random.choice(unknown)
        return random.choice(full_list)


# ---------------------------------------------------------------------------
# WandererAgent (ambient suspect that just moves around)
# ---------------------------------------------------------------------------


class WandererAgent(BaseAgent):
    """Agent that wanders randomly — moves to a random room and ends its turn.

    Never makes suggestions or accusations. Used for unplayed suspect
    characters so they still appear on the board and move around.
    """

    agent_type = "wanderer"

    async def decide_action(
        self, game_state: GameState, player_state: PlayerState
    ) -> dict:
        player_id = player_state.your_player_id
        available = player_state.available_actions
        current_room = game_state.current_room.get(player_id)

        if not game_state.dice_rolled and "move" in available:
            # Pick a random room different from the current one
            candidates = [r for r in ROOMS if r != current_room]
            if not candidates:
                candidates = list(ROOMS)
            target = random.choice(candidates)
            logger.info(
                "[%s:%s] Wandering to '%s'", self.agent_type, player_id, target
            )
            return {"type": "move", "room": target}

        logger.info("[%s:%s] Ending turn", self.agent_type, player_id)
        return {"type": "end_turn"}

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        # Just pick a random card to show
        card = random.choice(matching_cards)
        logger.info(
            "[%s] Showing '%s' to %s",
            self.agent_type, card, suggesting_player_id,
        )
        return card


# ---------------------------------------------------------------------------
# LLMAgent (delegates decisions to an LLM API)
# ---------------------------------------------------------------------------

_ACTION_SYSTEM_PROMPT = """\
You are playing the board game Clue (Cluedo). You are playing as {character}.

{personality}

GAME ELEMENTS:
- Suspects: Miss Scarlett, Colonel Mustard, Mrs. White, Reverend Green, Mrs. Peacock, Professor Plum
- Weapons: Candlestick, Knife, Lead Pipe, Revolver, Rope, Wrench
- Rooms: Kitchen, Ballroom, Conservatory, Billiard Room, Library, Study, Hall, Lounge, Dining Room
- Secret passages: Study<->Kitchen, Lounge<->Conservatory

RULES:
- One suspect, one weapon, and one room form the secret solution.
- Cards you hold or have been shown are NOT the solution.
- On your turn: if in a corner room, you may use a secret passage; otherwise roll dice, then choose a room to move toward. After moving, optionally suggest or accuse.
- Suggestions must use the room you are currently in.
- Accuse ONLY when you are certain of all three solution cards.
- A wrong accusation eliminates you from the game.

Respond with a valid JSON object for your chosen action. Include a "chat" field \
with a short in-character comment about what you're doing (one sentence, stay in \
character as {character}). Example: {{"type": "roll", "chat": "Let's see what fate has in store!"}}\
"""

# Personality blurbs injected into the LLM system prompt per character.
_CHARACTER_PERSONALITY_BLURBS: dict[str, str] = {
    "Miss Scarlett": (
        "You are Miss Scarlett — dramatic, flirtatious, and supremely confident. "
        "You speak with flair, use endearments like 'darling', and treat the "
        "investigation like a glamorous adventure."
    ),
    "Colonel Mustard": (
        "You are Colonel Mustard — a retired military officer who is gruff, "
        "proper, and tactical. You use military jargon, speak decisively, "
        "and approach the mystery like a battlefield operation."
    ),
    "Mrs. White": (
        "You are Mrs. White — the long-serving housekeeper who knows every "
        "secret of the mansion. You're observant, a bit gossipy, and "
        "occasionally nervous. You speak plainly with dry wit."
    ),
    "Reverend Green": (
        "You are Reverend Green — pious, thoughtful, and slightly sanctimonious. "
        "You sprinkle in religious references, speak gently, and treat the "
        "investigation as a moral duty."
    ),
    "Mrs. Peacock": (
        "You are Mrs. Peacock — an aristocrat who is dignified, slightly "
        "snobbish, and proper to a fault. You speak with refined vocabulary "
        "and mild disdain for anything beneath your station."
    ),
    "Professor Plum": (
        "You are Professor Plum — an absent-minded academic who is brilliant "
        "but scatterbrained. You reference statistics and research, sometimes "
        "lose your train of thought, and approach the mystery like a thesis."
    ),
}


_SHOW_CARD_SYSTEM_PROMPT = """\
You are playing Clue. Another player made a suggestion and you hold matching cards.
You must choose ONE card to show them. Strategic considerations:
- Prefer showing a card the requester might already know about.
- Avoid revealing cards that give away unique information.

Respond with ONLY a valid JSON object: {"card": "<card name>"}. No explanation.\
"""


class LLMAgent(BaseAgent):
    """Agent that delegates decisions to an LLM API.

    Builds a prompt describing the game state and available actions, sends
    it to an OpenAI-compatible chat completions endpoint, and parses the
    JSON response into a game action.

    Falls back to ``RandomAgent`` logic if the LLM call fails or returns
    an unparseable response.

    Configuration via environment variables:
    - ``LLM_API_URL``: Chat completions endpoint (default: OpenAI)
    - ``LLM_API_KEY``: Bearer token for the API
    - ``LLM_MODEL``: Model identifier (default: ``gpt-4o-mini``)
    """

    agent_type = "llm"

    def __init__(self):
        super().__init__()
        self.api_url = os.getenv(
            "LLM_API_URL", "https://api.openai.com/v1/chat/completions"
        )
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # Fallback agent shares our observation state
        self._fallback = RandomAgent()
        self._fallback.seen_cards = self.seen_cards
        self._fallback.shown_to = self.shown_to
        self._fallback.rooms_suggested_in = self.rooms_suggested_in
        self._fallback.unrefuted_suggestions = self.unrefuted_suggestions

        logger.info(
            "[%s] Configured | api_url=%s | model=%s | api_key_set=%s",
            self.agent_type,
            self.api_url,
            self.model,
            bool(self.api_key),
        )

    # ------------------------------------------------------------------
    # LLM communication
    # ------------------------------------------------------------------

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str | None:
        """Call the LLM API and return the response text, or None on failure."""
        if not self.api_key:
            logger.warning(
                "[%s] No LLM_API_KEY set — falling back to random agent",
                self.agent_type,
            )
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        }

        logger.info(
            "[%s] Sending LLM request | model=%s | prompt_length=%d",
            self.agent_type,
            self.model,
            len(user_prompt),
        )
        logger.debug("[%s] LLM user prompt:\n%s", self.agent_type, user_prompt)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(
                    "[%s] LLM response received | length=%d",
                    self.agent_type,
                    len(content),
                )
                logger.debug("[%s] LLM raw response: %s", self.agent_type, content)
                return content
        except httpx.TimeoutException:
            logger.error("[%s] LLM API call timed out", self.agent_type)
            return None
        except httpx.HTTPStatusError as exc:
            logger.error(
                "[%s] LLM API HTTP error: %s %s",
                self.agent_type,
                exc.response.status_code,
                exc.response.text[:200],
            )
            return None
        except Exception as exc:
            logger.error("[%s] LLM API call failed: %s", self.agent_type, exc)
            return None

    @staticmethod
    def _parse_json_response(text: str) -> dict | None:
        """Extract a JSON object from the LLM response text."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON within the text
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return None

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_action_prompt(
        self, game_state: GameState, player_state: PlayerState
    ) -> str:
        """Build a user prompt describing the current situation."""
        player_id = player_state.your_player_id
        known_cards = player_state.your_cards
        current_room = game_state.current_room
        dice_rolled = game_state.dice_rolled
        available = player_state.available_actions

        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        lines = [
            "CURRENT SITUATION:",
            f"- Your player ID: {player_id}",
            f"- Your cards (in hand): {known_cards}",
            f"- All cards you've seen (not in solution): {sorted(self.seen_cards)}",
            f"- Unknown suspects (could be solution): {unknown_suspects}",
            f"- Unknown weapons (could be solution): {unknown_weapons}",
            f"- Unknown rooms (could be solution): {unknown_rooms}",
            f"- Your current room: {current_room.get(player_id, 'none')}",
            f"- Dice rolled this turn: {dice_rolled}",
            f"- Available actions: {available}",
        ]

        if self.unrefuted_suggestions:
            lines.append(
                f"- Unrefuted suggestions (no one could show a card): "
                f"{self.unrefuted_suggestions}"
            )

        lines.append("")
        lines.append("Choose your action. Valid action formats:")

        if "secret_passage" in available:
            passage_dest = SECRET_PASSAGE_MAP.get(current_room.get(player_id, ""), "?")
            lines.append(
                f'  Secret passage (to {passage_dest}): {{"type": "secret_passage"}}'
            )
        if "roll" in available:
            lines.append('  Roll dice: {"type": "roll"}')
        if "move" in available:
            lines.append('  Move: {"type": "move", "room": "<room name>"}')
        if "suggest" in available:
            room = current_room.get(player_id, "")
            lines.append(
                f'  Suggest: {{"type": "suggest", "suspect": "<name>", '
                f'"weapon": "<weapon>", "room": "{room}"}}'
            )
        if "accuse" in available:
            lines.append(
                '  Accuse: {"type": "accuse", "suspect": "<name>", '
                '"weapon": "<weapon>", "room": "<room>"}'
            )
        if "end_turn" in available:
            lines.append('  End turn: {"type": "end_turn"}')

        return "\n".join(lines)

    def _build_show_card_prompt(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        """Build a user prompt for the show-card decision."""
        already_shown = self.shown_to.get(suggesting_player_id, set())
        lines = [
            "You must show ONE card to the suggesting player.",
            f"- Suggesting player: {suggesting_player_id}",
            f"- Matching cards you can show: {matching_cards}",
            f"- Cards you've previously shown to this player: {sorted(already_shown)}",
            "",
            'Respond with: {"card": "<card name>"}',
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Action validation
    # ------------------------------------------------------------------

    def _validate_action(
        self,
        action: dict,
        available: list[str],
        game_state: GameState,
        player_state: PlayerState,
    ) -> bool:
        """Check that a parsed LLM action is structurally valid."""
        action_type = action.get("type")
        if action_type not in available:
            logger.warning(
                "[%s] LLM chose unavailable action '%s' (available: %s)",
                self.agent_type,
                action_type,
                available,
            )
            return False

        if action_type in ("roll", "secret_passage", "end_turn"):
            # No additional validation needed for these action types
            return True

        if action_type == "move":
            room = action.get("room")
            if room not in ROOMS:
                logger.warning(
                    "[%s] LLM chose invalid room '%s'", self.agent_type, room
                )
                return False

        elif action_type == "suggest":
            if action.get("suspect") not in SUSPECTS:
                logger.warning(
                    "[%s] LLM chose invalid suspect '%s'",
                    self.agent_type,
                    action.get("suspect"),
                )
                return False
            if action.get("weapon") not in WEAPONS:
                logger.warning(
                    "[%s] LLM chose invalid weapon '%s'",
                    self.agent_type,
                    action.get("weapon"),
                )
                return False
            if action.get("room") not in ROOMS:
                logger.warning(
                    "[%s] LLM chose invalid room '%s'",
                    self.agent_type,
                    action.get("room"),
                )
                return False

        elif action_type == "accuse":
            if action.get("suspect") not in SUSPECTS:
                return False
            if action.get("weapon") not in WEAPONS:
                return False
            if action.get("room") not in ROOMS:
                return False

        return True

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    async def decide_action(
        self, game_state: GameState, player_state: PlayerState
    ) -> dict:
        player_id = player_state.your_player_id
        available = player_state.available_actions

        self.seen_cards.update(player_state.your_cards)
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        logger.info(
            "[%s:%s] Deciding action | available=%s | "
            "unknown: suspects=%d weapons=%d rooms=%d | seen_total=%d",
            self.agent_type,
            player_id,
            available,
            len(unknown_suspects),
            len(unknown_weapons),
            len(unknown_rooms),
            len(self.seen_cards),
        )

        # Build prompt and call LLM
        personality = _CHARACTER_PERSONALITY_BLURBS.get(self.character, "")
        system_prompt = _ACTION_SYSTEM_PROMPT.format(
            character=self.character or "a detective",
            personality=personality,
        )
        user_prompt = self._build_action_prompt(game_state, player_state)
        response_text = await self._call_llm(system_prompt, user_prompt)

        if response_text is not None:
            parsed = self._parse_json_response(response_text)
            if parsed is not None:
                # Extract chat message before validation (it's not a game field)
                llm_chat = parsed.pop("chat", None)
                logger.info(
                    "[%s:%s] LLM proposed action: %s",
                    self.agent_type,
                    player_id,
                    parsed,
                )
                if self._validate_action(parsed, available, game_state, player_state):
                    logger.info(
                        "[%s:%s] Using LLM action: %s",
                        self.agent_type,
                        player_id,
                        parsed.get("type"),
                    )
                    # Stash chat for generate_chat() to return later
                    if llm_chat and isinstance(llm_chat, str):
                        self._pending_chat = llm_chat
                    # Track rooms for suggestion
                    if parsed.get("type") == "suggest":
                        room = parsed.get("room")
                        if room:
                            self.rooms_suggested_in.add(room)
                    return parsed
                else:
                    logger.warning(
                        "[%s:%s] LLM action failed validation — falling back",
                        self.agent_type,
                        player_id,
                    )
            else:
                logger.warning(
                    "[%s:%s] Failed to parse LLM response as JSON — falling back",
                    self.agent_type,
                    player_id,
                )
        else:
            logger.info(
                "[%s:%s] No LLM response — falling back to random agent",
                self.agent_type,
                player_id,
            )

        # Fallback to rule-based logic
        fallback_action = await self._fallback.decide_action(game_state, player_state)
        logger.info(
            "[%s:%s] Fallback action: %s",
            self.agent_type,
            player_id,
            fallback_action,
        )
        return fallback_action

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        logger.info(
            "[%s] Deciding which card to show to %s from %s",
            self.agent_type,
            suggesting_player_id,
            matching_cards,
        )

        user_prompt = self._build_show_card_prompt(matching_cards, suggesting_player_id)
        response_text = await self._call_llm(_SHOW_CARD_SYSTEM_PROMPT, user_prompt)

        if response_text is not None:
            parsed = self._parse_json_response(response_text)
            if parsed is not None:
                card = parsed.get("card")
                if card in matching_cards:
                    self.shown_to.setdefault(suggesting_player_id, set()).add(card)
                    logger.info(
                        "[%s] LLM chose to show '%s' to %s",
                        self.agent_type,
                        card,
                        suggesting_player_id,
                    )
                    return card
                else:
                    logger.warning(
                        "[%s] LLM chose invalid card '%s' (valid: %s) — falling back",
                        self.agent_type,
                        card,
                        matching_cards,
                    )
            else:
                logger.warning(
                    "[%s] Failed to parse LLM show_card response — falling back",
                    self.agent_type,
                )

        # Fallback
        card = await self._fallback.decide_show_card(
            matching_cards, suggesting_player_id
        )
        logger.info(
            "[%s] Fallback: showing '%s' to %s",
            self.agent_type,
            card,
            suggesting_player_id,
        )
        return card
