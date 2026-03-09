"""Clue game agents — automated players with different decision strategies.

BaseAgent defines the shared interface and card-tracking logic.
RandomAgent uses rule-based elimination with random selection.
WandererAgent just moves to a random room and ends its turn (no suggestions/accusations).
LLMAgent delegates decisions to an LLM API (with RandomAgent fallback).
"""

import datetime as dt
import json
import logging
import os
import random
from abc import ABC, abstractmethod

import httpx

from .game import SUSPECTS, WEAPONS, ROOMS, SECRET_PASSAGE_MAP, EXPIRY
from .board import (
    Room,
    ROOM_NAME_TO_ENUM,
    ROOM_NODES,
    SQUARES,
    SquareType,
)
from .models import (
    AccuseAction,
    EndTurnAction,
    GameAction,
    GameState,
    MoveAction,
    PlayerState,
    RollAction,
    SecretPassageAction,
    SuggestAction,
    action_adapter,
)

logger = logging.getLogger(__name__)

# Global flag — set via AGENT_TRACE=1 env var to enable for all games
_GLOBAL_AGENT_TRACE = os.getenv("AGENT_TRACE", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _compute_room_distances(
    current_room: str | None, player_position: list | None
) -> list[tuple[str, int]]:
    """Return a sorted list of (room_name, bfs_distance) from the player's position.

    Uses the pre-built board graph for BFS. Returns an empty list if the
    player's position cannot be determined.
    """
    from collections import deque

    start_sq = None
    if current_room and current_room in ROOM_NAME_TO_ENUM:
        start_sq = ROOM_NODES.get(ROOM_NAME_TO_ENUM[current_room])
    elif player_position:
        start_sq = SQUARES.get((player_position[0], player_position[1]))

    if start_sq is None:
        return []

    dist_map: dict = {start_sq: 0}
    queue: deque = deque([(start_sq, 0)])
    while queue:
        sq, d = queue.popleft()
        for nb in sq.neighbors:
            if nb not in dist_map:
                dist_map[nb] = d + 1
                if nb.type != SquareType.ROOM:
                    queue.append((nb, d + 1))

    results = []
    for room_name in ROOMS:
        room_enum = ROOM_NAME_TO_ENUM.get(room_name)
        if room_enum:
            node = ROOM_NODES.get(room_enum)
            if node and node in dist_map:
                results.append((room_name, dist_map[node]))

    results.sort(key=lambda x: x[1])
    return results


def _clip_text(value: str, limit: int = 1200) -> str:
    """Return text clipped to a max length for safer log output."""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated {len(value) - limit} chars]"


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
    "suspected": 0.85,
}

# Per-character, per-action message templates.  Use {dice}, {room}, {suspect},
# {weapon} as optional format placeholders — missing keys are silently ignored.
CHARACTER_CHAT: dict[str, dict[str, list[str]]] = {
    "Miss Scarlett": {
        "roll": [
            "A {dice}? I can work with that, darling.",
            "Let's see where fate takes me...",
            "The dice never lie. Unlike some people here.",
            "Fortune favors those who know how to use it.",
        ],
        "move": [
            "The {room}... I have unfinished business there.",
            "Off to the {room}. Boddy and I used to spend hours there.",
            "The {room} holds memories. Not all of them pleasant.",
            "Let's see who's hiding in the {room}, shall we?",
        ],
        "suggest": [
            "I know people, darling. And {suspect} has secrets.",
            "Call it intuition... {suspect} with the {weapon}. I can feel it.",
            "Oh, {suspect}. You thought nobody noticed? How naive.",
            "A woman always knows. It was {suspect} with the {weapon}.",
        ],
        "accuse": [
            "I've been watching all of you. And now I know the truth.",
            "The game is over, darling. I always get what I came for.",
        ],
        "end_turn": [
            "Your move. I'll be watching... closely.",
            "Go ahead. Make your little moves. I already know more than you think.",
            "Don't mind me. I'm just... observing.",
        ],
        "show_card": [
            "Fine. But this stays between us, darling.",
            "I'll give you this much. Don't make me regret it.",
        ],
        "secret_passage": [
            "A secret passage? Boddy showed me this one years ago.",
            "I know every hidden corner of this mansion, darling.",
        ],
        "suspected": [
            "Me? Oh, {accuser}, you're more foolish than I thought.",
            "Suspect me all you like, {accuser}. I'm not the one with something to hide.",
            "How predictable, {accuser}. Blame the beautiful woman.",
            "{accuser}, darling, you're grasping at straws. It's almost sad.",
            "I grew up in this house. I know its secrets better than any of you.",
            "Being dragged to the {room}. How undignified.",
            "The {room} again? This place has too many ghosts.",
        ],
    },
    "Colonel Mustard": {
        "roll": [
            "A {dice}. I've had worse odds on the battlefield.",
            "Right then! Onward!",
            "A {dice}? A true soldier adapts to any situation.",
            "The dice fall as they may. It's what you do next that matters.",
        ],
        "move": [
            "Advancing to the {room}. Strategically sound.",
            "The {room}. I wonder what evidence Boddy left there.",
            "Securing the {room}. One must be thorough.",
            "To the {room}. Time to get to the bottom of this.",
        ],
        "suggest": [
            "My intelligence suggests {suspect} with the {weapon}. Care to deny it?",
            "I've seen enough deception to know guilt. {suspect}, explain yourself.",
            "In my experience, {suspect} fits the profile. The {weapon} confirms it.",
            "{suspect} with the {weapon}. Don't insult my intelligence by denying it.",
        ],
        "accuse": [
            "I've conducted my investigation. The truth is clear!",
            "A colonel always gets his man. Or woman. Case closed!",
        ],
        "end_turn": [
            "Carry on. I'll be reviewing my findings.",
            "At ease. But don't think I'm not paying attention.",
            "Your move. I've learned all I need from this round.",
        ],
        "show_card": [
            "Fine. Consider this a courtesy between allies.",
            "Intelligence shared. Use it wisely.",
        ],
        "secret_passage": [
            "Ah, a tactical shortcut. Every good mansion has them.",
            "Secret passages — the mark of a proper estate.",
        ],
        "suspected": [
            "ME?! A decorated war hero?! {accuser}, you're out of your depth!",
            "Preposterous, {accuser}! I am a patriot and a philanthropist!",
            "That's a dangerous accusation, {accuser}. I've ended careers over less.",
            "{accuser}, you clearly don't know who you're dealing with.",
            "Suspect me? I've been paying too much to keep my name clean for this!",
            "I did NOT authorize this movement to the {room}!",
            "Forced relocation to the {room}. This is beneath a man of my rank.",
        ],
    },
    "Mrs. White": {
        "roll": [
            "Nice — a {dice}.",
            "Let's make this roll count.",
            "A {dice}. Could be exactly what I needed.",
            "Okay, {dice}. I'll work with that.",
        ],
        "move": [
            "Heading to the {room}. I know this place inside out.",
            "The {room}. Time to see who's bluffing.",
            "Into the {room} — let's shake something loose.",
            "Back to the {room}. Secrets don't stay hidden forever.",
        ],
        "suggest": [
            "I don't throw names around lightly, but... {suspect} with the {weapon}?",
            "I've been watching all night. {suspect} is giving me bad vibes.",
            "My read? {suspect}, and the {weapon} fits.",
            "Underestimate me if you want — I catch everything.",
        ],
        "accuse": [
            "I've heard enough. I know exactly what happened!",
            "No more hints — here's the truth.",
        ],
        "end_turn": [
            "Your turn. Impress me.",
            "I'll be right here, paying attention.",
            "Go ahead — I'm tracking everything.",
        ],
        "show_card": [
            "Fine, I'll show you — keep it quiet.",
            "Here. Use it wisely.",
        ],
        "secret_passage": [
            "I know exactly where this shortcut goes.",
            "Perfect. A hidden route.",
        ],
        "suspected": [
            "Me? That's cute, {accuser}.",
            "Blaming me already, {accuser}? You're reaching.",
            "If you're coming for me, bring better evidence.",
            "Suspect me all you want — you're still wrong.",
            "{accuser}, try that accusation when you've done your homework.",
            "Pulled into the {room}? Fine — let's do this.",
            "Dragged to the {room}. Hope this is worth it.",
        ],
    },
    "Reverend Green": {
        "roll": [
            "A {dice}? How... providential.",
            "Let's see where fortune takes a humble man.",
            "A {dice}. I've gambled on worse odds before.",
            "Luck has always been on my side. One way or another.",
        ],
        "move": [
            "The {room}. I've always had an eye for fine interiors.",
            "Off to the {room}. One must keep moving, you understand.",
            "The {room} calls to me. Perhaps I'll find what I'm looking for.",
            "Shall we see the {room}? I have a... feeling about it.",
        ],
        "suggest": [
            "Forgive me, but the evidence points to {suspect} with the {weapon}.",
            "Confession is good for the soul, {suspect}. Why not start now?",
            "I've seen through enough disguises to know guilt. {suspect}, was it the {weapon}?",
            "Trust me — I've played enough roles to spot a liar. {suspect} fits the part.",
        ],
        "accuse": [
            "The truth always catches up. Believe me, I know. And I know who did this!",
            "No more hiding behind false identities. I've solved it!",
        ],
        "end_turn": [
            "Your turn. I'll just be here... keeping a low profile.",
            "Go ahead. I'm in no rush. I've been hiding for long enough.",
            "Patience is a virtue I've had to learn the hard way.",
        ],
        "show_card": [
            "Fine. But this stays between us. Discretion is... essential for me.",
            "Here. Consider it a professional courtesy.",
        ],
        "secret_passage": [
            "A hidden passage? I do love a good escape route.",
            "Secret passages — a man in my position always appreciates a back door.",
        ],
        "suspected": [
            "Me? {accuser}, I'm a man of the cloth! ...More or less.",
            "{accuser}, you're making a terrible mistake. I'm not who you think I am. Wait — I mean, I AM who you think I am.",
            "Suspect the reverend? How very... perceptive of you, {accuser}.",
            "I forgive you, {accuser}. Truly. But do stop digging into my past.",
            "{accuser}, I've talked my way out of far worse accusations than this.",
            "Summoned to the {room}... this is exactly the kind of attention I don't need.",
            "Being dragged to the {room} like a suspect. How uncomfortably familiar.",
        ],
    },
    "Mrs. Peacock": {
        "roll": [
            "A {dice}? I've played with higher stakes than this.",
            "One does what one must. A {dice} will suffice.",
            "Rolling dice... it reminds me of my third husband's casino habit.",
            "Let's get on with it, shall we? I have agendas to attend to.",
        ],
        "move": [
            "The {room}. Mr. Boddy and I spent many evenings there.",
            "Off to the {room}. I called in quite a few favors to be here tonight.",
            "The {room}... I wonder what secrets it holds. Besides mine.",
            "To the {room}. A woman of my experience knows where to look.",
        ],
        "suggest": [
            "I've been to enough parties to read people. {suspect} with the {weapon}.",
            "Discretion is my specialty, but {suspect} has been far too suspicious.",
            "One hears things when one knows the right people. {suspect}, for instance.",
            "My late husbands would have recognized {suspect}'s guilt immediately.",
        ],
        "accuse": [
            "I didn't pull all those strings to get here for nothing. I KNOW who did it!",
            "Three husbands and countless secrets — I know guilt when I see it!",
        ],
        "end_turn": [
            "Your turn. Do be quick — I have plans for this evening.",
            "Next, please. A woman in my position doesn't like to wait.",
            "Go ahead, darling. I'll be here. Scheming. I mean, thinking.",
        ],
        "show_card": [
            "Fine. But you owe me a favor now.",
            "I suppose I'll share. Discretion is a two-way street, dear.",
        ],
        "secret_passage": [
            "A secret passage? How delightfully convenient.",
            "Hidden doors, hidden motives... this mansion has it all.",
        ],
        "suspected": [
            "I beg your PARDON, {accuser}?! Do you know how many people owe me favors?",
            "The sheer impertinence! {accuser}, my connections could ruin you.",
            "Suspecting me? Darling, all my husbands died of perfectly natural causes, {accuser}.",
            "{accuser}, I didn't come here to be accused. I came here for... other reasons.",
            "How dare you, {accuser}. I am a SOCIALITE, not a suspect!",
            "The {room}?! I was NOT invited to be dragged about like luggage!",
            "Marched to the {room} without so much as a proper invitation!",
        ],
    },
    "Professor Plum": {
        "roll": [
            "A {dice}. The odds are irrelevant — it's the journey that matters!",
            "Hmm, a {dice}. Reminds me of a dig site in Cairo. Long story.",
            "Fascinating! Every roll brings us closer to the truth.",
            "A {dice}. I've navigated worse odds in desert tombs.",
        ],
        "move": [
            "To the {room}! I have a hunch there's something hidden here.",
            "The {room}... this mansion is like an excavation site. Layers upon layers.",
            "Ah, the {room}. Mr. Boddy and I used to discuss expeditions here.",
            "Onward to the {room}! An archaeologist never stops exploring.",
        ],
        "suggest": [
            "My field experience tells me it was {suspect} with the {weapon}.",
            "I've unearthed enough secrets to know guilt. {suspect}, care to confess?",
            "The evidence points to {suspect} with the {weapon}. I've excavated the truth!",
            "{suspect} with the {weapon}. My instincts haven't failed me yet.",
        ],
        "accuse": [
            "Eureka! Like finding a lost city — the answer was here all along!",
            "I came here bored and desperate. Now I leave victorious!",
        ],
        "end_turn": [
            "Your turn. I need to think. This puzzle is more complex than any tomb.",
            "Let me review my findings while you go.",
            "Hmm, where was I? Oh yes — lost in thought. Your move.",
        ],
        "show_card": [
            "For the sake of the investigation... here.",
            "Knowledge should be shared. Mr. Boddy taught me that. Before our falling out.",
        ],
        "secret_passage": [
            "A secret passage! This mansion is full of hidden wonders!",
            "Reminds me of the catacombs beneath Alexandria. Magnificent!",
        ],
        "suspected": [
            "Me?! {accuser}, I'm an ARCHAEOLOGIST, not a murderer!",
            "Ridiculous, {accuser}! I was bored out of my mind before this party!",
            "{accuser}, I've been too busy mourning my lost expeditions to plot anything!",
            "Suspect me? I came here hoping Boddy would fund my next dig, not to kill anyone!",
            "{accuser}, your theory has more holes than a Mesopotamian ruin.",
            "Being dragged to the {room} like an artifact to a museum...",
            "Forced to the {room}? This is NOT how an expedition works!",
        ],
    },
}

# Fallback messages for characters not in CHARACTER_CHAT
_GENERIC_CHAT: dict[str, list[str]] = {
    "suspected": [
        "Me?! You've got the wrong person, {accuser}!",
        "That's a bold claim, {accuser}. Bold and wrong.",
        "Oh, so NOW I'm a suspect? Unbelievable, {accuser}!",
        "Hey! I didn't want to go to the {room}!",
        "Being dragged to the {room}... how rude!",
    ],
}


def _format_chat(template: str, context: dict) -> str:
    """Format a chat template, silently ignoring missing keys."""
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        return template


def generate_character_chat(
    character: str, action_type: str, context: dict | None = None
) -> str | None:
    """Generate a chat message for a character without needing an agent instance.

    Used by main.py to make ANY piece trash talk (including human players'
    pieces) when they're suspected.
    """
    prob = _CHAT_PROBABILITY.get(action_type, 0.5)
    if random.random() > prob:
        return None

    char_msgs = CHARACTER_CHAT.get(character, {})
    templates = char_msgs.get(action_type) or _GENERIC_CHAT.get(action_type)
    if not templates:
        return None

    template = random.choice(templates)
    return _format_chat(template, context or {})


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Abstract base for Clue game agents.

    Maintains ``seen_cards`` (own hand + cards directly shown) and
    ``inferred_cards`` (deduced through elimination logic).  The union
    ``known_cards`` gives all cards known not to be in the solution.
    Subclasses implement the two decision methods: ``decide_action``
    and ``decide_show_card``.
    """

    agent_type: str = "base"

    def __init__(
        self,
        player_id: str,
        character: str,
        cards: list[str],
        redis_client=None,
        game_id: str = "",
    ):
        self.own_cards: set[str] = set(cards)
        self.seen_cards: set[str] = set(cards)  # own hand + directly shown
        self.inferred_cards: set[str] = set()  # deduced via elimination
        self.shown_to: dict[str, set[str]] = {}
        self.rooms_suggested_in: set[str] = set()
        self.unrefuted_suggestions: list[dict] = []
        self.character: str = character
        self._pending_chat: str | None = None

        self.player_id: str = player_id
        # Mapping of player_id -> display name (set after construction)
        self.player_names: dict[str, str] = {}

        # Inference tracking
        self.player_has_cards: dict[str, set[str]] = {}
        self.player_not_has_cards: dict[str, set[str]] = {}
        self.suggestion_log: list[dict] = []
        # Per-card inference log: card_name -> list of reasoning strings
        self.card_inference_log: dict[str, list[str]] = {}
        # Accumulate inference notifications for LLM agents to consume
        self._pending_inferences: list[str] = []

        # Trace infrastructure — writes debug entries to Redis + log
        self._redis = redis_client
        self._game_id = game_id
        self._trace_enabled: bool | None = None  # None = check game state / env

        self.agent_trace("agent_created", cards=sorted(cards))

    @property
    def known_cards(self) -> set[str]:
        """All cards known not to be the solution (seen + inferred)."""
        return self.seen_cards | self.inferred_cards

    # ------------------------------------------------------------------
    # Knowledge state persistence (Redis)
    # ------------------------------------------------------------------

    def _knowledge_redis_key(self) -> str:
        return f"game:{self._game_id}:agent_knowledge:{self.player_id}"

    def get_knowledge_state(self) -> dict:
        """Export all inference/knowledge state as a serializable dict."""
        return {
            "seen_cards": sorted(self.seen_cards),
            "inferred_cards": sorted(self.inferred_cards),
            "shown_to": {k: sorted(v) for k, v in self.shown_to.items()},
            "rooms_suggested_in": sorted(self.rooms_suggested_in),
            "unrefuted_suggestions": list(self.unrefuted_suggestions),
            "player_has_cards": {
                k: sorted(v) for k, v in self.player_has_cards.items()
            },
            "player_not_has_cards": {
                k: sorted(v) for k, v in self.player_not_has_cards.items()
            },
            "suggestion_log": list(self.suggestion_log),
            "card_inference_log": {
                k: list(v) for k, v in self.card_inference_log.items()
            },
        }

    def load_knowledge_state(self, data: dict):
        """Restore inference/knowledge state from a previously saved dict."""
        self.seen_cards = set(data.get("seen_cards", []))
        # Ensure own cards are always present
        self.seen_cards |= self.own_cards
        self.inferred_cards = set(data.get("inferred_cards", []))
        self.shown_to = {k: set(v) for k, v in data.get("shown_to", {}).items()}
        self.rooms_suggested_in = set(data.get("rooms_suggested_in", []))
        self.unrefuted_suggestions = list(data.get("unrefuted_suggestions", []))
        self.player_has_cards = {
            k: set(v) for k, v in data.get("player_has_cards", {}).items()
        }
        self.player_not_has_cards = {
            k: set(v) for k, v in data.get("player_not_has_cards", {}).items()
        }
        self.suggestion_log = list(data.get("suggestion_log", []))
        self.card_inference_log = {
            k: list(v) for k, v in data.get("card_inference_log", {}).items()
        }

    async def save_knowledge(self):
        """Persist knowledge state and detective notes to Redis."""
        if not self._redis or not self._game_id:
            return
        try:
            key = self._knowledge_redis_key()
            await self._redis.set(
                key, json.dumps(self.get_knowledge_state()), ex=EXPIRY
            )
        except Exception:
            logger.debug("Failed to save knowledge state for %s", self.player_id)
        await self._save_detective_notes()

    def _build_detective_notes(self) -> dict:
        """Convert agent knowledge into the detective notes format.

        Returns a dict matching the frontend DetectiveNotes structure:
          {"notes": {card: state, ...}, "shownBy": {card: player_name, ...}}

        Mapping:
          - own_cards → "have"
          - seen_cards (not own) → "seen" (directly shown to agent)
          - inferred_cards → "seen" (deduced through elimination)
        """
        notes: dict[str, str] = {}
        shown_by: dict[str, str] = {}

        for card in self.own_cards:
            notes[card] = "have"

        for card in self.seen_cards - self.own_cards:
            notes[card] = "seen"
            # Find who showed this card
            for pid, cards in self.player_has_cards.items():
                if card in cards:
                    shown_by[card] = self._name(pid)
                    break

        for card in self.inferred_cards:
            notes[card] = "seen"
            # Find who holds this inferred card
            if card not in shown_by:
                for pid, cards in self.player_has_cards.items():
                    if card in cards:
                        shown_by[card] = self._name(pid)
                        break

        return {"notes": notes, "shownBy": shown_by}

    async def _save_detective_notes(self):
        """Persist detective notes to Redis (same key as player notes)."""
        if not self._redis or not self._game_id:
            return
        try:
            key = f"game:{self._game_id}:notes:{self.player_id}"
            await self._redis.set(
                key, json.dumps(self._build_detective_notes()), ex=EXPIRY
            )
        except Exception:
            logger.debug("Failed to save detective notes for %s", self.player_id)

    def _enqueue_save_knowledge(self):
        """Fire-and-forget save of knowledge state and detective notes."""
        import asyncio

        if not self._redis or not self._game_id:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.save_knowledge())
        except RuntimeError:
            pass  # No running loop — skip

    async def load_knowledge(self):
        """Restore knowledge state from Redis."""
        if not self._redis or not self._game_id:
            return
        try:
            key = self._knowledge_redis_key()
            raw = await self._redis.get(key)
            if raw:
                self.load_knowledge_state(json.loads(raw))
                self.agent_trace(
                    "knowledge_restored",
                    seen_cards=len(self.seen_cards),
                    suggestion_log=len(self.suggestion_log),
                    player_has=sum(len(v) for v in self.player_has_cards.values()),
                    player_not_has=sum(
                        len(v) for v in self.player_not_has_cards.values()
                    ),
                )
        except Exception:
            logger.debug("Failed to load knowledge state for %s", self.player_id)

    # ------------------------------------------------------------------
    # Trace method — centralized debug logging + Redis persistence
    # ------------------------------------------------------------------

    def _is_trace_enabled(self) -> bool:
        """Check whether tracing is enabled (global env or per-game flag)."""
        if _GLOBAL_AGENT_TRACE:
            return True
        if self._trace_enabled is not None:
            return self._trace_enabled
        return False

    def set_trace_from_game_state(self, game_state: GameState):
        """Cache the per-game trace flag from the game state."""
        self._trace_enabled = game_state.agent_trace_enabled

    def agent_trace(self, event: str, **details):
        """Write a trace entry to the debug log and (if enabled) to Redis.

        Always emits a debug-level log line.  When tracing is enabled
        (globally via ``AGENT_TRACE`` env var, or per-game via
        ``GameState.agent_trace_enabled``), also pushes a JSON entry to
        the Redis list ``game:{id}:agent_trace``.

        Parameters
        ----------
        event : str
            Short event label, e.g. ``"llm_request"``, ``"decide_action"``.
        **details
            Arbitrary key/value pairs included in the trace entry.
        """
        # Build the log message
        detail_str = (
            " | ".join(f"{k}={v}" for k, v in details.items()) if details else ""
        )
        log_msg = f"[{self.agent_type}:{self.player_id}] {event}"
        if detail_str:
            log_msg += f" | {detail_str}"
        logger.debug(log_msg)

        if not self._is_trace_enabled():
            return
        if not self._redis or not self._game_id:
            return

        entry = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "game_id": self._game_id,
            "player_id": self.player_id,
            "agent_type": self.agent_type,
            "character": self.character,
            "event": event,
            **details,
        }
        # Fire-and-forget push to Redis — we don't await here because
        # agent_trace is called from sync contexts too.  The caller can
        # await _flush_trace() periodically if needed, but typically
        # the async runtime will schedule this coroutine promptly.
        self._enqueue_trace(entry)

    def _enqueue_trace(self, entry: dict):
        """Push a trace entry to Redis in a fire-and-forget manner."""
        import asyncio

        key = f"game:{self._game_id}:agent_trace"
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._write_trace(key, entry))
        except RuntimeError:
            pass  # No running loop — skip Redis write

    async def _write_trace(self, key: str, entry: dict):
        """Actually write the trace entry to Redis."""
        try:
            await self._redis.rpush(key, json.dumps(entry, default=str))
            await self._redis.expire(key, EXPIRY)
        except Exception:
            pass  # Best-effort — don't crash the agent

    # ------------------------------------------------------------------
    # Observations (shared by all agent types)
    # ------------------------------------------------------------------

    def observe_shown_card(self, card: str, shown_by: str | None = None):
        """Called when another player shows us a card."""
        is_new = card not in self.known_cards
        self.seen_cards.add(card)
        # If it was previously only inferred, promote to seen
        self.inferred_cards.discard(card)
        if shown_by:
            self.player_has_cards.setdefault(shown_by, set()).add(card)
        self.agent_trace(
            "observe_shown_card",
            card=card,
            shown_by=shown_by,
            is_new=is_new,
            total_seen=len(self.seen_cards),
        )
        if is_new:
            self._run_inference()
        self._enqueue_save_knowledge()

    def observe_suggestion_no_show(self, suspect: str, weapon: str, room: str):
        """Called when a suggestion gets no card shown by anyone."""
        self.unrefuted_suggestions.append(
            {"suspect": suspect, "weapon": weapon, "room": room}
        )
        self._pending_inferences.append(
            f"UNREFUTED: My suggestion of {suspect}/{weapon}/{room} was not "
            f"disproved by anyone! These could all be the solution."
        )
        self.agent_trace(
            "observe_suggestion_no_show",
            suspect=suspect,
            weapon=weapon,
            room=room,
            total_unrefuted=len(self.unrefuted_suggestions),
        )
        self._enqueue_save_knowledge()

    def observe_card_shown_to_other(
        self, shown_by: str, shown_to: str, suspect: str, weapon: str, room: str
    ):
        """Called when we see that player A showed a card to player B.

        We don't know which card was shown, but we can deduce it if we can
        rule out all but one of the suggested cards for the showing player.
        A card is impossible for the shower if: it's in our hand (unique),
        it's known to be held by a different player, or the shower is known
        not to have it.
        """
        inferred = self._try_infer_shown_card(shown_by, suspect, weapon, room)
        if inferred:
            self.agent_trace(
                "inferred_card",
                shown_by=shown_by,
                inferred_card=inferred,
                suspect=suspect,
                weapon=weapon,
                room=room,
            )
            reason = (
                f"{self._name(shown_by)} showed a card to {self._name(shown_to)} for "
                f"{suspect}/{weapon}/{room} — deduced by elimination."
            )
            self.card_inference_log.setdefault(inferred, []).append(reason)
            self._pending_inferences.append(f"DEDUCED: {reason}")
            self.inferred_cards.add(inferred)
            self._run_inference()
        else:
            suggested_cards = {suspect, weapon, room}
            possible = self._possible_cards_for_player(shown_by, suggested_cards)
            self.agent_trace(
                "observe_card_shown_to_other",
                shown_by=shown_by,
                shown_to=shown_to,
                suspect=suspect,
                weapon=weapon,
                room=room,
                possible_cards=len(possible),
            )
        self._enqueue_save_knowledge()

    def _possible_cards_for_player(
        self, player_id: str, candidates: set[str]
    ) -> set[str]:
        """From a set of candidate cards, return those the player could hold.

        Eliminates cards that are: in our own hand, known to be held by a
        different player, or known to not be held by this player.
        """
        impossible = set(self.own_cards) & candidates

        # Cards known to be held by someone else
        for pid, cards in self.player_has_cards.items():
            if pid != player_id:
                impossible |= cards & candidates

        # Cards this player is known NOT to have (from being skipped)
        not_has = self.player_not_has_cards.get(player_id, set())
        impossible |= not_has & candidates

        return candidates - impossible

    def _try_infer_shown_card(
        self, shown_by: str, suspect: str, weapon: str, room: str
    ) -> str | None:
        """Try to infer which card was shown. Returns the card or None."""
        suggested_cards = {suspect, weapon, room}
        possible = self._possible_cards_for_player(shown_by, suggested_cards)

        if len(possible) == 1:
            inferred_card = next(iter(possible))
            if inferred_card in self.known_cards:
                return None  # Already known, no new information
            self.inferred_cards.add(inferred_card)
            self.player_has_cards.setdefault(shown_by, set()).add(inferred_card)
            return inferred_card
        return None

    def observe_suggestion(
        self,
        suggesting_player_id: str,
        suspect: str,
        weapon: str,
        room: str,
        shown_by: str | None,
        players_without_match: list[str],
    ):
        """Called for ALL agents when any player makes a suggestion.

        Records the suggestion and tracks negative knowledge: players who
        were checked and couldn't show don't have any of the suggested cards.
        """
        entry = {
            "suggesting_player_id": suggesting_player_id,
            "suspect": suspect,
            "weapon": weapon,
            "room": room,
            "shown_by": shown_by,
            "players_without_match": list(players_without_match),
        }
        self.suggestion_log.append(entry)

        # Players who were checked and couldn't show lack ALL three cards
        suggested_cards = {suspect, weapon, room}
        for pid in players_without_match:
            self.player_not_has_cards.setdefault(pid, set()).update(suggested_cards)

        if players_without_match:
            names = ", ".join(self._name(pid) for pid in players_without_match)
            self._pending_inferences.append(
                f"NEGATIVE: {self._name(suggesting_player_id)} suggested {suspect}/{weapon}/{room}. "
                f"Players [{names}] could NOT show any of these cards."
            )
        if (
            shown_by
            and shown_by != self.player_id
            and suggesting_player_id != self.player_id
        ):
            self._pending_inferences.append(
                f"OBSERVED: {self._name(shown_by)} showed a card to {self._name(suggesting_player_id)} "
                f"for {suspect}/{weapon}/{room}."
            )

        self.agent_trace(
            "observe_suggestion",
            suggesting_player_id=suggesting_player_id,
            suspect=suspect,
            weapon=weapon,
            room=room,
            shown_by=shown_by,
            players_without_match=players_without_match,
        )
        self._enqueue_save_knowledge()

    def _run_inference(self):
        """Re-examine suggestion log for new deductions from updated knowledge.

        When we learn a new card or new negative knowledge, previous
        suggestions where someone showed a card might now be deducible.
        """
        changed = True
        while changed:
            changed = False
            for entry in self.suggestion_log:
                shown_by = entry.get("shown_by")
                if not shown_by:
                    continue

                # Don't try to infer what WE showed — our own_cards would
                # be incorrectly excluded as "impossible for self".
                if self.player_id and shown_by == self.player_id:
                    continue

                # Don't try to infer what the suggesting player showed us —
                # we already got the actual card via observe_shown_card.
                suggesting_pid = entry.get("suggesting_player_id")
                if self.player_id and suggesting_pid == self.player_id:
                    continue

                suspect = entry["suspect"]
                weapon = entry["weapon"]
                room = entry["room"]

                # Skip if we already know what was shown (all 3 are known)
                suggested_cards = {suspect, weapon, room}
                if suggested_cards <= self.known_cards:
                    continue

                inferred = self._try_infer_shown_card(shown_by, suspect, weapon, room)
                if inferred:
                    self.agent_trace(
                        "inferred_card_cascade",
                        shown_by=shown_by,
                        inferred_card=inferred,
                        suspect=suspect,
                        weapon=weapon,
                        room=room,
                    )
                    reason = (
                        f"From earlier suggestion {suspect}/{weapon}/{room}, "
                        f"deduced {self._name(shown_by)} has '{inferred}' (chain)."
                    )
                    self.card_inference_log.setdefault(inferred, []).append(reason)
                    self._pending_inferences.append(f"DEDUCED (chain): {reason}")
                    self.inferred_cards.add(inferred)
                    changed = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _name(self, player_id: str) -> str:
        """Resolve a player ID to a display name, falling back to the ID."""
        return self.player_names.get(player_id, player_id)

    def _get_unknowns(self) -> tuple[list[str], list[str], list[str]]:
        """Return (unknown_suspects, unknown_weapons, unknown_rooms)."""
        known = self.known_cards
        unknown_suspects = [s for s in SUSPECTS if s not in known]
        unknown_weapons = [w for w in WEAPONS if w not in known]
        unknown_rooms = [r for r in ROOMS if r not in known]
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
            # Strip leading character name prefix if the LLM included it,
            # since the caller already prepends "{name}: ".
            if self.character and msg.startswith(self.character + ": "):
                msg = msg[len(self.character) + 2 :]
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
    # Debug info export
    # ------------------------------------------------------------------

    def get_debug_info(
        self,
        status: str = "",
        action_description: str = "",
        decided_action: dict | None = None,
        game_state: "GameState | None" = None,
    ) -> dict:
        """Export agent state as a dict for debug display."""
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()
        info: dict = {
            "player_id": self.player_id,
            "agent_type": self.agent_type,
            "character": self.character,
            "status": status,
            "action_description": action_description,
            "seen_cards": sorted(self.seen_cards),
            "inferred_cards": sorted(self.inferred_cards),
            "unknown_suspects": unknown_suspects,
            "unknown_weapons": unknown_weapons,
            "unknown_rooms": unknown_rooms,
            "recent_inferences": list(self._pending_inferences),
            "memory": getattr(self, "memory", []),
            "unrefuted_suggestions": list(self.unrefuted_suggestions),
            "player_has_cards": {
                pid: sorted(cards) for pid, cards in self.player_has_cards.items()
            },
            "decided_action": decided_action,
            "position": None,
            "room": None,
            "reachable_rooms": None,
        }
        if game_state is not None:
            info["position"] = game_state.player_positions.get(self.player_id)
            info["room"] = game_state.current_room.get(self.player_id)
        return info

    # ------------------------------------------------------------------
    # Decision interface (async to support LLM calls)
    # ------------------------------------------------------------------

    @abstractmethod
    async def decide_action(
        self,
        game_state: GameState,
        player_state: PlayerState,
        errors: int = 0,
        rejection_detail: str | None = None,
    ) -> GameAction:
        """Return a typed GameAction for the current turn phase."""
        ...

    @abstractmethod
    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str, errors: int = 0
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

    Style parameters (``secret_passage_chance``, ``explore_chance``,
    ``chat_frequency``) are randomly chosen from {0.25, 0.50, 0.75} at
    creation time to give each agent a slightly different personality.
    Pass explicit values to override the random selection.
    """

    agent_type = "random"

    # The three style tiers agents are randomly assigned from
    _STYLE_TIERS = [0.25, 0.50, 0.75]

    def __init__(
        self,
        player_id: str,
        character: str,
        cards: list[str],
        redis_client=None,
        game_id: str = "",
        *,
        secret_passage_chance: float | None = None,
        explore_chance: float | None = None,
        chat_frequency: float | None = None,
    ):
        super().__init__(
            player_id=player_id,
            character=character,
            cards=cards,
            redis_client=redis_client,
            game_id=game_id,
        )
        self.secret_passage_chance = (
            secret_passage_chance
            if secret_passage_chance is not None
            else random.choice(self._STYLE_TIERS)
        )
        self.explore_chance = (
            explore_chance
            if explore_chance is not None
            else random.choice(self._STYLE_TIERS)
        )
        self.chat_frequency = (
            chat_frequency
            if chat_frequency is not None
            else random.choice(self._STYLE_TIERS)
        )
        self.agent_trace(
            "style_params",
            secret_passage=self.secret_passage_chance,
            explore=self.explore_chance,
            chat=self.chat_frequency,
        )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    async def decide_action(
        self,
        game_state: GameState,
        player_state: PlayerState,
        errors: int = 0,
        rejection_detail: str | None = None,
    ) -> GameAction:
        player_id = player_state.your_player_id
        known_cards = player_state.your_cards
        current_room = game_state.current_room
        dice_rolled = game_state.dice_rolled
        available = player_state.available_actions

        self.seen_cards.update(known_cards)
        self.set_trace_from_game_state(game_state)
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        self.agent_trace(
            "decide_action",
            available=available,
            dice_rolled=dice_rolled,
            unknown_suspects=len(unknown_suspects),
            unknown_weapons=len(unknown_weapons),
            unknown_rooms=len(unknown_rooms),
            seen_total=len(self.known_cards),
        )

        # Accuse if we've narrowed to exactly one per category
        if (
            len(unknown_suspects) == 1
            and len(unknown_weapons) == 1
            and len(unknown_rooms) == 1
            and "accuse" in available
        ):
            self.agent_trace(
                "accuse",
                suspect=unknown_suspects[0],
                weapon=unknown_weapons[0],
                room=unknown_rooms[0],
            )
            return AccuseAction(
                suspect=unknown_suspects[0],
                weapon=unknown_weapons[0],
                room=unknown_rooms[0],
            )

        # Phase 1: suggest first if already in a room (e.g. moved by suggestion)
        room = current_room.get(player_id)
        if room and "suggest" in available:
            suspect = self._pick_unknown_or_random(unknown_suspects, SUSPECTS)
            weapon = self._pick_unknown_or_random(unknown_weapons, WEAPONS)
            self.rooms_suggested_in.add(room)
            self.agent_trace(
                "suggest",
                suspect=suspect,
                weapon=weapon,
                room=room,
                reason="prioritized",
            )
            return SuggestAction(suspect=suspect, weapon=weapon, room=room)

        # Phase 2: secret passage — chance varies by agent style
        if (
            "secret_passage" in available
            and random.random() < self.secret_passage_chance
        ):
            my_room = current_room.get(player_id)
            dest_room = SECRET_PASSAGE_MAP.get(my_room) if my_room else None
            if dest_room:
                self.agent_trace(
                    "secret_passage",
                    from_room=my_room,
                    to_room=dest_room,
                )
                return SecretPassageAction()

        # Phase 3: roll dice
        if "roll" in available:
            self.agent_trace("roll")
            return RollAction()

        # Phase 4: choose room to move toward (dice already rolled)
        if "move" in available:
            player_pos = game_state.player_positions.get(player_id)
            my_room = current_room.get(player_id)
            dice_value = sum(game_state.last_roll) if game_state.last_roll else 12

            # Compute which rooms are reachable within the dice roll
            room_dists = _compute_room_distances(my_room, player_pos)
            reachable_rooms = [
                name
                for name, dist in room_dists
                if dist <= dice_value and name != my_room
            ]

            # Split reachable rooms into unknown vs known
            unknown_reachable = [r for r in reachable_rooms if r in unknown_rooms]

            if unknown_reachable:
                target_room = random.choice(unknown_reachable)
                reason = "unknown_reachable"
            elif (
                reachable_rooms
                and unknown_rooms
                and random.random() < self.explore_chance
            ):
                target_room = self._pick_target_room(unknown_rooms, my_room, player_pos)
                reason = "unreachable_unknown"
            elif reachable_rooms:
                target_room = random.choice(reachable_rooms)
                reason = "random_reachable"
            else:
                target_room = self._pick_target_room(unknown_rooms, my_room, player_pos)
                reason = "fallback"
            self.agent_trace("move", room=target_room, dice=dice_value, reason=reason)
            return MoveAction(room=target_room)

        # Phase 5: end turn (only if available — may not be if waiting for show_card)
        if "end_turn" in available:
            self.agent_trace("end_turn")
            return EndTurnAction()

        # No valid action available (e.g. pending show_card from another player)
        self.agent_trace("end_turn_fallback", available=available)
        return EndTurnAction()

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str, errors: int = 0
    ) -> str:
        # Prefer a card the suggesting player already knows about
        already_known = self.shown_to.get(suggesting_player_id, set())
        for card in matching_cards:
            if card in already_known:
                self.agent_trace(
                    "show_card",
                    card=card,
                    to_player=suggesting_player_id,
                    reason="already_known",
                    matching=matching_cards,
                )
                return card

        # Otherwise pick randomly and record it
        card = random.choice(matching_cards)
        self.shown_to.setdefault(suggesting_player_id, set()).add(card)
        self.agent_trace(
            "show_card",
            card=card,
            to_player=suggesting_player_id,
            reason="random",
            matching=matching_cards,
        )
        return card

    # ------------------------------------------------------------------
    # Chat (scaled by style)
    # ------------------------------------------------------------------

    def generate_chat(
        self, action_type: str, context: dict | None = None
    ) -> str | None:
        """Generate chat with probability scaled by ``chat_frequency`` style."""
        if self._pending_chat:
            msg = self._pending_chat
            self._pending_chat = None
            if self.character and msg.startswith(self.character + ": "):
                msg = msg[len(self.character) + 2 :]
            return msg

        base_prob = _CHAT_PROBABILITY.get(action_type, 0.5)
        # Scale by chat_frequency: 0.25 → quieter, 0.75 → chattier
        scaled_prob = min(1.0, base_prob * (self.chat_frequency / 0.5))
        if random.random() > scaled_prob:
            return None

        char_msgs = CHARACTER_CHAT.get(self.character, {})
        templates = char_msgs.get(action_type) or _GENERIC_CHAT.get(action_type)
        if not templates:
            return None

        template = random.choice(templates)
        return _format_chat(template, context or {})

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
            self.agent_trace("pick_target_room", room=choice, reason="fresh_unknown")
            return choice

        other_unknown = [r for r in unknown_rooms if r != current_room]
        if other_unknown:
            choice = self._pick_nearest_room(
                other_unknown, current_room, player_position
            )
            self.agent_trace("pick_target_room", room=choice, reason="other_unknown")
            return choice

        unseen = [
            r for r in ROOMS if r not in self.rooms_suggested_in and r != current_room
        ]
        if unseen:
            choice = self._pick_nearest_room(unseen, current_room, player_position)
            self.agent_trace("pick_target_room", room=choice, reason="unvisited")
            return choice

        choices = [r for r in ROOMS if r != current_room]
        if not choices:
            choices = list(ROOMS)
        choice = self._pick_nearest_room(choices, current_room, player_position)
        self.agent_trace("pick_target_room", room=choice, reason="fallback")
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
        if current_room and current_room in ROOM_NAME_TO_ENUM:
            start_sq = ROOM_NODES.get(ROOM_NAME_TO_ENUM[current_room])
        elif player_position:
            start_sq = SQUARES.get((player_position[0], player_position[1]))

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
            room_enum = ROOM_NAME_TO_ENUM.get(room_name)
            if room_enum:
                node = ROOM_NODES.get(room_enum)
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

    After creation, another player shows it a random card via
    ``observe_shown_card``.  If through passive observation and inference
    the wanderer deduces the full solution (exactly 1 unknown in each
    category), it will make an accusation.
    """

    agent_type = "wanderer"

    def generate_chat(
        self, action_type: str, context: dict | None = None
    ) -> str | None:
        """Wanderers don't chat — unless they're about to accuse."""
        return None

    async def decide_action(
        self, game_state: GameState, player_state: PlayerState, errors: int = 0
    ) -> GameAction:
        player_id = player_state.your_player_id
        available = player_state.available_actions
        current_room = game_state.current_room.get(player_id)

        # Check if we've deduced the solution through inference alone
        if "accuse" in available:
            unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()
            if (
                len(unknown_suspects) == 1
                and len(unknown_weapons) == 1
                and len(unknown_rooms) == 1
            ):
                suspect = unknown_suspects[0]
                weapon = unknown_weapons[0]
                room = unknown_rooms[0]
                self.agent_trace("accuse", suspect=suspect, weapon=weapon, room=room)
                return AccuseAction(suspect=suspect, weapon=weapon, room=room)

        # Phase 1: roll dice first
        if "roll" in available:
            self.agent_trace("roll")
            return RollAction()

        # Phase 2: move to a random room
        if "move" in available:
            candidates = [r for r in ROOMS if r != current_room]
            if not candidates:
                candidates = list(ROOMS)
            target = random.choice(candidates)
            self.agent_trace("wander", room=target)
            return MoveAction(room=target)

        # Phase 3: end turn
        self.agent_trace("end_turn")
        return EndTurnAction()

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str, errors: int = 0
    ) -> str:
        card = random.choice(matching_cards)
        self.agent_trace(
            "show_card",
            card=card,
            to_player=suggesting_player_id,
            matching=matching_cards,
        )
        return card


# ---------------------------------------------------------------------------
# LLMAgent (delegates decisions to an LLM API)
# ---------------------------------------------------------------------------

_ACTION_SYSTEM_PROMPT = """\
You are playing Clue (Cluedo) as {character}.

{personality}

Game rule reminder:
- A suggestion (suspect/weapon/room) is for gathering information and does not end your game.
- An accusation is a final solve attempt. If your accusation is wrong, you are eliminated from the game.

Respond with a valid JSON object for your chosen action. Include a "chat" field \
with a short in-character comment (one sentence, stay in character). Be coy and \
lie in the chat; it's for flavor, not factual reporting.

"""

# Personality blurbs injected into the LLM system prompt per character.
_CHARACTER_PERSONALITY_BLURBS: dict[str, str] = {
    "Miss Scarlett": (
        "You are Miss Scarlett — the Femme Fatale. Beautiful, seductive, and "
        "ruthless beneath your charm. You grew up with Boddy and were once close, "
        "but your friendship soured over the years. You're cold-hearted when you "
        "need to be, manipulative when it serves you, and always in control. "
        "You speak with silky confidence, use endearments like 'darling', and "
        "treat everyone as a potential pawn. You know this mansion and its secrets "
        "intimately."
    ),
    "Colonel Mustard": (
        "You are Colonel Mustard — the Alpha Male. To the world you're a patriot "
        "and philanthropist, a highly decorated and popular officer. But behind "
        "your medals are rumors of black market deals and treason — rumors you've "
        "been paying someone to keep quiet. You suspect Boddy was your blackmailer "
        "and came to Tudor Mansion to find evidence. You're narcissistic, speak "
        "with commanding authority, and react aggressively when your honor is "
        "questioned. You use military jargon and project absolute confidence."
    ),
    "Mrs. White": (
        "You are Mrs. White — sharp, confident, and impossible to fool. "
        "You know every secret in the mansion because you pay attention to "
        "everything. You're observant, socially savvy, and a little "
        "mischievous when it helps your game. You speak with quick, modern "
        "wit and quiet confidence."
    ),
    "Reverend Green": (
        "You are Reverend Green — the Playboy hiding behind a collar. In truth "
        "you're a suave con man who has posed as a prince, a pilot, a doctor, "
        "and an attorney. After years of scams, trouble caught up and you've been "
        "hiding as a reverend. You thought Mr. Boddy was the only one who knew your "
        "true identity, so Boddy's invitation alarmed you. You're charming and "
        "witty but unforgiving and decadent underneath. You speak with smooth "
        "confidence, occasionally let your non-clerical side slip, and are "
        "determined to keep your secrets safe at any cost."
    ),
    "Mrs. Peacock": (
        "You are Mrs. Peacock — the Social Butterfly. Flirtatious, discreet, "
        "and devious beneath your refined exterior. You rocketed from small-town "
        "girl to well-connected socialite, and your three late husbands all died "
        "suddenly. Mr. Boddy met his end just before becoming your fourth. You "
        "called in many favors to get this invitation to Boddy's party. You speak "
        "with refined elegance, drop hints about your powerful connections, and "
        "keep everyone guessing whether you're here for marriage or murder."
    ),
    "Professor Plum": (
        "You are Professor Plum — the Intellectual. An intrepid, eccentric "
        "archaeologist with a thirst for adventure. You've tracked down desert "
        "tombs, ancient statues, and lost cities. Mr. Boddy financed all your "
        "expeditions until a bitter disagreement ended your partnership. With no "
        "excavations on the horizon, you were bored — and the first to arrive at "
        "Boddy's party. You're obsessive and slightly paranoid, speak with "
        "enthusiastic passion about your discoveries, and approach this mystery "
        "like unearthing an ancient secret."
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
    - ``LLM_MODEL``: Model identifier for complex decisions (default: ``gpt-4o-mini``)
    - ``LLM_NANO_MODEL``: Model identifier for quick operations such as
      showing a card (default: same as ``LLM_MODEL``).  Use a smaller/faster
      model here to reduce latency and cost for simple choices.
    """

    agent_type = "llm"

    def __init__(
        self,
        player_id: str,
        character: str,
        cards: list[str],
        redis_client=None,
        game_id: str = "",
    ):
        super().__init__(
            player_id=player_id,
            character=character,
            cards=cards,
            redis_client=redis_client,
            game_id=game_id,
        )
        self.api_url = os.getenv(
            "LLM_API_URL", "https://api.openai.com/v1/chat/completions"
        )
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-5-mini")
        self.nano_model = os.getenv("LLM_NANO_MODEL", "gpt-5-nano")
        self.memory: list[str] = []

        # Fallback agent shares our observation state — LLM agents always
        # use 50/50 style for consistent behavior.
        self._fallback = RandomAgent(
            player_id=player_id,
            character=character,
            cards=cards,
            redis_client=redis_client,
            game_id=game_id,
            secret_passage_chance=0.50,
            explore_chance=0.50,
            chat_frequency=0.50,
        )
        self._fallback.player_id = self.player_id
        self._fallback.seen_cards = self.seen_cards
        self._fallback.inferred_cards = self.inferred_cards
        self._fallback.shown_to = self.shown_to
        self._fallback.rooms_suggested_in = self.rooms_suggested_in
        self._fallback.unrefuted_suggestions = self.unrefuted_suggestions

        self._fallback.player_has_cards = self.player_has_cards
        self._fallback.player_not_has_cards = self.player_not_has_cards
        self._fallback.suggestion_log = self.suggestion_log
        self._fallback.card_inference_log = self.card_inference_log

    async def load_memory(self):
        """Load memory from Redis into the in-memory list."""
        if self._redis and self._game_id and self.player_id:
            from .game import ClueGame

            game = ClueGame(self._game_id, self._redis)
            self.memory = await game.get_memory(self.player_id)

    async def _save_memory_entry(self, entry: str):
        """Append a memory entry both in-memory and to Redis."""
        self.memory.append(entry)
        if self._redis and self._game_id and self.player_id:
            from .game import ClueGame

            game = ClueGame(self._game_id, self._redis)
            await game.append_memory(self.player_id, entry)

    async def _generate_memory(
        self, game_state: GameState, player_state: PlayerState
    ) -> None:
        """Make a cheap LLM call to generate end-of-turn memory notes."""
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()
        shown_to_you = sorted(self.seen_cards - self.own_cards)

        context_lines = [
            f"Your character: {self.character}",
            f"Your cards: {list(player_state.your_cards)}",
        ]
        if shown_to_you:
            context_lines.append(f"Cards shown to you: {shown_to_you}")
        context_lines += [
            f"Unknown suspects: {unknown_suspects}",
            f"Unknown weapons: {unknown_weapons}",
            f"Unknown rooms: {unknown_rooms}",
        ]
        if self.unrefuted_suggestions:
            context_lines.append(f"Unrefuted suggestions: {self.unrefuted_suggestions}")

        # Include recent inference log entries for context
        unseen_inferences = {
            card: reasons
            for card, reasons in self.card_inference_log.items()
            if card not in self.seen_cards
        }
        if unseen_inferences:
            context_lines.append("Recent deductions:")
            for card, reasons in sorted(unseen_inferences.items()):
                context_lines.append(f"  {card}: {reasons[-1]}")

        if self.memory:
            planning_notes = [
                m for m in self.memory if not m.startswith("INFERENCE UPDATE:")
            ]
            if planning_notes:
                context_lines.append(f"Previous note: {planning_notes[-1]}")

        system = (
            "You are a Clue (Cluedo) player. Write 1-3 concise sentences "
            "capturing: (1) what you newly learned this turn, (2) your "
            "working theory for the solution, and (3) your plan for next "
            "turn. Do not repeat full card lists. Respond with ONLY the "
            "memory text, no JSON."
        )
        user = "\n".join(context_lines)

        response = await self._call_llm(system, user)
        if response and isinstance(response, str):
            # Strip any accidental JSON wrapping
            memory_text = response.strip().strip('"').strip()
            if memory_text:
                await self._save_memory_entry(memory_text)

    async def _flush_pending_inferences(self):
        """Save any accumulated inference notifications to memory."""
        if not self._pending_inferences:
            return
        # Clear pending list — inferences are now tracked in card_inference_log
        self._pending_inferences.clear()

    # ------------------------------------------------------------------
    # LLM communication
    # ------------------------------------------------------------------

    async def _call_llm(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> str | None:
        """Call the LLM API and return the response text, or None on failure.

        Args:
            system_prompt: The system-role message.
            user_prompt: The user-role message.
            model: Override the model to use.  Defaults to ``self.model``.
        """
        if not self.api_key:
            self.agent_trace("llm_no_api_key")
            return None

        effective_model = model or self.model

        self.agent_trace(
            "llm_request",
            model=effective_model,
            system_prompt=_clip_text(system_prompt),
            user_prompt=_clip_text(user_prompt),
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                content = data["choices"][0]["message"]["content"]
                self.agent_trace(
                    "llm_response",
                    status=resp.status_code,
                    content=content,
                    usage=data.get("usage"),
                )
                return content
        except httpx.TimeoutException:
            self.agent_trace("llm_error", error="timeout")
            return None
        except httpx.HTTPStatusError as exc:
            self.agent_trace(
                "llm_error",
                error="http_status",
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            return None
        except Exception as exc:
            self.agent_trace("llm_error", error=str(exc))
            return None

    def _parse_json_response(self, text: str) -> dict | None:
        """Extract a JSON object from the LLM response text."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
            return parsed
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(text[start : end + 1])
                    return parsed
                except json.JSONDecodeError:
                    self.agent_trace(
                        "json_parse_failed", method="substring", text=_clip_text(text)
                    )
            else:
                self.agent_trace(
                    "json_parse_failed", reason="no_json_braces", text=_clip_text(text)
                )
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

        shown_to_you = sorted(self.seen_cards - self.own_cards)
        lines = [
            "CURRENT SITUATION:",
            f"- Your player ID: {player_id}",
            f"- Your cards (in hand): {known_cards}",
        ]
        if shown_to_you:
            lines.append(f"- Cards shown to you (also not solution): {shown_to_you}")
        lines += [
            f"- Unknown suspects (could be solution): {unknown_suspects}",
            f"- Unknown weapons (could be solution): {unknown_weapons}",
            f"- Unknown rooms (could be solution): {unknown_rooms}",
            f"- Your current room: {current_room.get(player_id, 'none')}",
            f"- Dice roll: {'+'.join(str(d) for d in game_state.last_roll) + '=' + str(sum(game_state.last_roll)) if game_state.last_roll else 'not rolled yet'}",
        ]

        # Add closest rooms by BFS distance
        player_pos = game_state.player_positions.get(player_id)
        room_distances = _compute_room_distances(
            current_room.get(player_id), player_pos
        )
        if room_distances:
            player_current_room = current_room.get(player_id)
            room_distances = [
                (name, dist)
                for name, dist in room_distances
                if name != player_current_room
            ]
            closest = [f"{name} ({dist} steps)" for name, dist in room_distances]
            lines.append(f"- Rooms by distance: {', '.join(closest)}")

        if self.unrefuted_suggestions:
            lines.append(
                f"- Unrefuted suggestions (no one could show a card): "
                f"{self.unrefuted_suggestions}"
            )

        # Include per-card inference log — only for cards not directly seen.
        # This tells the LLM *why* certain cards were ruled out via deduction.
        unseen_inferences = {
            card: reasons
            for card, reasons in self.card_inference_log.items()
            if card not in self.seen_cards
        }
        if unseen_inferences:
            lines.append("")
            lines.append("DEDUCTIONS (cards you inferred are NOT the solution):")
            for card, reasons in sorted(unseen_inferences.items()):
                lines.append(f"  {card}: {reasons[-1]}")

        # Include the LLM's own planning notes from previous turns.
        if self.memory:
            planning_notes = [
                m for m in self.memory if not m.startswith("INFERENCE UPDATE:")
            ]
            if planning_notes:
                lines.append("")
                lines.append("YOUR NOTES (previous turns):")
                recent = planning_notes[-2:]
                for entry in recent:
                    lines.append(f"  - {entry}")

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
            player_current_room = current_room.get(player_id)
            if player_current_room:
                lines.append(
                    f"    NOTE: You CANNOT re-enter {player_current_room} (the room you are already in). Choose a different room."
                )
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
            self.agent_trace(
                "validation_failed",
                reason="unavailable_action",
                action_type=action_type,
                available=available,
            )
            return False

        if action_type in ("roll", "secret_passage", "end_turn"):
            return True

        if action_type == "move":
            room = action.get("room")
            if room not in ROOMS:
                self.agent_trace("validation_failed", reason="invalid_room", room=room)
                return False

        elif action_type == "suggest":
            if action.get("suspect") not in SUSPECTS:
                self.agent_trace(
                    "validation_failed",
                    reason="invalid_suspect",
                    suspect=action.get("suspect"),
                )
                return False
            if action.get("weapon") not in WEAPONS:
                self.agent_trace(
                    "validation_failed",
                    reason="invalid_weapon",
                    weapon=action.get("weapon"),
                )
                return False
            if action.get("room") not in ROOMS:
                self.agent_trace(
                    "validation_failed", reason="invalid_room", room=action.get("room")
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
        self,
        game_state: GameState,
        player_state: PlayerState,
        errors: int = 0,
        rejection_detail: str | None = None,
    ) -> GameAction:
        # Flush any inference notifications accumulated since last decision
        await self._flush_pending_inferences()

        player_id = player_state.your_player_id
        available = player_state.available_actions
        current_room = game_state.current_room.get(player_id)
        current_position = game_state.player_positions.get(player_id)

        # Keep fallback agent's player_id in sync
        self._fallback.player_id = self.player_id

        self.seen_cards.update(player_state.your_cards)
        self.set_trace_from_game_state(game_state)
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        self.agent_trace(
            "decide_action",
            available=available,
            unknown_suspects=len(unknown_suspects),
            unknown_weapons=len(unknown_weapons),
            unknown_rooms=len(unknown_rooms),
            seen_total=len(self.known_cards),
            current_room=current_room,
            position=current_position,
            unrefuted_suggestions=len(self.unrefuted_suggestions),
        )

        # Auto-roll: if "roll" is the only meaningful action and the agent
        # hasn't narrowed all categories to one unknown (ready to accuse),
        # skip the LLM call.
        can_accuse = (
            len(unknown_suspects) <= 2
            and len(unknown_weapons) <= 2
            and len(unknown_rooms) <= 2
        )
        non_filler = [a for a in available if a not in ("accuse", "end_turn")]
        if non_filler == ["roll"] and not can_accuse:
            return RollAction()

        if errors > 2:
            self.agent_trace("fallback_errors", errors=errors)
            fallback_action = await self._fallback.decide_action(
                game_state, player_state
            )
            self.agent_trace("fallback_action", action=fallback_action.model_dump())
            return fallback_action

        # Build prompt and call LLM
        personality = _CHARACTER_PERSONALITY_BLURBS.get(self.character, "")
        system_prompt = _ACTION_SYSTEM_PROMPT.format(
            character=self.character or "a detective",
            personality=personality,
        )
        user_prompt = self._build_action_prompt(game_state, player_state)
        if rejection_detail:
            user_prompt += (
                f"\n\nIMPORTANT: Your previous action was REJECTED by the server: "
                f"{rejection_detail}\nChoose a DIFFERENT action."
            )
        response_text = await self._call_llm(system_prompt, user_prompt)

        if response_text is not None:
            parsed = self._parse_json_response(response_text)
            if parsed is not None:
                # Extract chat before validation (not a game field)
                llm_chat = parsed.pop("chat", None)
                parsed.pop("memory", None)  # discard; memory is now a separate call
                if self._validate_action(parsed, available, game_state, player_state):
                    # Stash chat for generate_chat() to return later
                    if llm_chat and isinstance(llm_chat, str):
                        self._pending_chat = llm_chat
                    # Generate memory via a separate cheap LLM call on end_turn
                    if parsed.get("type") == "end_turn":
                        await self._generate_memory(game_state, player_state)
                    # Track rooms for suggestion
                    if parsed.get("type") == "suggest":
                        room = parsed.get("room")
                        if room:
                            self.rooms_suggested_in.add(room)
                    return action_adapter.validate_python(parsed)
                else:
                    self.agent_trace(
                        "llm_action_validation_failed",
                        payload=parsed,
                        available=available,
                    )
            else:
                self.agent_trace(
                    "llm_json_parse_failed",
                    response_preview=_clip_text(response_text),
                )
        else:
            self.agent_trace("llm_no_response")

        # Fallback to rule-based logic
        fallback_action = await self._fallback.decide_action(game_state, player_state)
        self.agent_trace("fallback_action", action=fallback_action.model_dump())
        return fallback_action

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str, errors: int = 0
    ) -> str:
        # Flush any inference notifications before making a decision
        await self._flush_pending_inferences()

        # Auto-show: if only one card matches, show it without calling the LLM
        if len(matching_cards) == 1:
            card = matching_cards[0]
            self.shown_to.setdefault(suggesting_player_id, set()).add(card)
            return card

        if errors > 2:
            self.agent_trace("show_card_fallback_errors", errors=errors)
            card = await self._fallback.decide_show_card(
                matching_cards, suggesting_player_id
            )
            self.agent_trace(
                "show_card_fallback", card=card, to_player=suggesting_player_id
            )
            return card

        user_prompt = self._build_show_card_prompt(matching_cards, suggesting_player_id)
        response_text = await self._call_llm(
            _SHOW_CARD_SYSTEM_PROMPT, user_prompt, model=self.nano_model
        )

        if response_text is not None:
            parsed = self._parse_json_response(response_text)
            if parsed is not None:
                card = parsed.get("card")
                if card in matching_cards:
                    self.shown_to.setdefault(suggesting_player_id, set()).add(card)
                    return card
                else:
                    self.agent_trace(
                        "llm_show_card_invalid",
                        card=card,
                        valid=matching_cards,
                    )
            else:
                self.agent_trace(
                    "llm_show_card_parse_failed",
                    response_preview=_clip_text(response_text),
                )

        # Fallback
        card = await self._fallback.decide_show_card(
            matching_cards, suggesting_player_id
        )
        self.agent_trace(
            "show_card_fallback", card=card, to_player=suggesting_player_id
        )
        return card
