"""Clue game agents — automated players with different decision strategies.

BaseAgent defines the shared interface and card-tracking logic.
RandomAgent uses rule-based elimination with random selection.
LLMAgent delegates decisions to an LLM API (with RandomAgent fallback).
"""

import json
import logging
import os
import random
from abc import ABC, abstractmethod

import httpx

from .game import SUSPECTS, WEAPONS, ROOMS
from .models import GameState, PlayerState

logger = logging.getLogger(__name__)


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
            self.agent_type, shown_by, card, is_new, len(self.seen_cards),
        )

    def observe_suggestion_no_show(self, suspect: str, weapon: str, room: str):
        """Called when a suggestion gets no card shown by anyone."""
        self.unrefuted_suggestions.append(
            {"suspect": suspect, "weapon": weapon, "room": room}
        )
        logger.info(
            "[%s] Unrefuted suggestion: %s / %s / %s (total_unrefuted=%d)",
            self.agent_type, suspect, weapon, room,
            len(self.unrefuted_suggestions),
        )

    def observe_card_shown_to_other(self, shown_by: str, shown_to: str):
        """Called when we see that player A showed a card to player B."""
        logger.debug(
            "[%s] Observed: %s showed a card to %s",
            self.agent_type, shown_by, shown_to,
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
    # Decision interface (async to support LLM calls)
    # ------------------------------------------------------------------

    @abstractmethod
    async def decide_action(self, game_state: GameState, player_state: PlayerState) -> dict:
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

    async def decide_action(self, game_state: GameState, player_state: PlayerState) -> dict:
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
            self.agent_type, player_id, available, dice_rolled,
            len(unknown_suspects), len(unknown_weapons), len(unknown_rooms),
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
                self.agent_type, player_id,
                unknown_suspects[0], unknown_weapons[0], unknown_rooms[0],
            )
            return action

        # Phase 1: move (dice not rolled yet)
        if not dice_rolled and "move" in available:
            target_room = self._pick_target_room(
                unknown_rooms, current_room.get(player_id)
            )
            logger.info(
                "[%s:%s] Moving to '%s' (current=%s, unknown_rooms=%s)",
                self.agent_type, player_id, target_room,
                current_room.get(player_id), unknown_rooms,
            )
            return {"type": "move", "room": target_room}

        # Phase 2: suggest if in a room
        room = current_room.get(player_id)
        if room and "suggest" in available:
            suspect = self._pick_unknown_or_random(unknown_suspects, SUSPECTS)
            weapon = self._pick_unknown_or_random(unknown_weapons, WEAPONS)
            self.rooms_suggested_in.add(room)
            logger.info(
                "[%s:%s] Suggesting %s / %s / %s",
                self.agent_type, player_id, suspect, weapon, room,
            )
            return {
                "type": "suggest",
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
            }

        # Phase 3: end turn
        logger.info("[%s:%s] Ending turn", self.agent_type, player_id)
        return {"type": "end_turn"}

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        logger.info(
            "[%s] Deciding which card to show to %s from %s",
            self.agent_type, suggesting_player_id, matching_cards,
        )

        # Prefer a card the suggesting player already knows about
        already_known = self.shown_to.get(suggesting_player_id, set())
        for card in matching_cards:
            if card in already_known:
                logger.info(
                    "[%s] Showing '%s' (already known to %s)",
                    self.agent_type, card, suggesting_player_id,
                )
                return card

        # Otherwise pick randomly and record it
        card = random.choice(matching_cards)
        self.shown_to.setdefault(suggesting_player_id, set()).add(card)
        logger.info(
            "[%s] Showing '%s' (random choice, new info for %s)",
            self.agent_type, card, suggesting_player_id,
        )
        return card

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick_target_room(
        self, unknown_rooms: list[str], current_room: str | None
    ) -> str:
        """Pick the best room to move toward.

        Priority:
        1. Unknown rooms we haven't suggested in yet
        2. Unknown rooms (even if suggested in before)
        3. Any room we haven't suggested in
        4. Random room
        """
        fresh_unknown = [
            r for r in unknown_rooms
            if r not in self.rooms_suggested_in and r != current_room
        ]
        if fresh_unknown:
            choice = random.choice(fresh_unknown)
            logger.debug("[%s] Target room '%s' (fresh unknown)", self.agent_type, choice)
            return choice

        other_unknown = [r for r in unknown_rooms if r != current_room]
        if other_unknown:
            choice = random.choice(other_unknown)
            logger.debug("[%s] Target room '%s' (other unknown)", self.agent_type, choice)
            return choice

        unseen = [
            r for r in ROOMS
            if r not in self.rooms_suggested_in and r != current_room
        ]
        if unseen:
            choice = random.choice(unseen)
            logger.debug("[%s] Target room '%s' (unvisited)", self.agent_type, choice)
            return choice

        choices = [r for r in ROOMS if r != current_room]
        choice = random.choice(choices) if choices else random.choice(ROOMS)
        logger.debug("[%s] Target room '%s' (fallback random)", self.agent_type, choice)
        return choice

    @staticmethod
    def _pick_unknown_or_random(unknown: list[str], full_list: list[str]) -> str:
        """Pick a random unknown card, or any card if all are known."""
        if unknown:
            return random.choice(unknown)
        return random.choice(full_list)


# ---------------------------------------------------------------------------
# LLMAgent (delegates decisions to an LLM API)
# ---------------------------------------------------------------------------

_ACTION_SYSTEM_PROMPT = """\
You are playing the board game Clue (Cluedo) as an expert detective.

GAME ELEMENTS:
- Suspects: Miss Scarlett, Colonel Mustard, Mrs. White, Reverend Green, Mrs. Peacock, Professor Plum
- Weapons: Candlestick, Knife, Lead Pipe, Revolver, Rope, Wrench
- Rooms: Kitchen, Ballroom, Conservatory, Billiard Room, Library, Study, Hall, Lounge, Dining Room

RULES:
- One suspect, one weapon, and one room form the secret solution.
- Cards you hold or have been shown are NOT the solution.
- On your turn: roll dice and move to a room, then optionally suggest or accuse.
- Suggestions must use the room you are currently in.
- Accuse ONLY when you are certain of all three solution cards.
- A wrong accusation eliminates you from the game.

Respond with ONLY a valid JSON object for your chosen action. No explanation.\
"""

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
            self.agent_type, self.api_url, self.model, bool(self.api_key),
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
            self.agent_type, self.model, len(user_prompt),
        )
        logger.debug("[%s] LLM user prompt:\n%s", self.agent_type, user_prompt)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.api_url, json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(
                    "[%s] LLM response received | length=%d",
                    self.agent_type, len(content),
                )
                logger.debug("[%s] LLM raw response: %s", self.agent_type, content)
                return content
        except httpx.TimeoutException:
            logger.error("[%s] LLM API call timed out", self.agent_type)
            return None
        except httpx.HTTPStatusError as exc:
            logger.error(
                "[%s] LLM API HTTP error: %s %s",
                self.agent_type, exc.response.status_code, exc.response.text[:200],
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

    def _validate_action(self, action: dict, available: list[str],
                         game_state: GameState, player_state: PlayerState) -> bool:
        """Check that a parsed LLM action is structurally valid."""
        action_type = action.get("type")
        if action_type not in available:
            logger.warning(
                "[%s] LLM chose unavailable action '%s' (available: %s)",
                self.agent_type, action_type, available,
            )
            return False

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
                    self.agent_type, action.get("suspect"),
                )
                return False
            if action.get("weapon") not in WEAPONS:
                logger.warning(
                    "[%s] LLM chose invalid weapon '%s'",
                    self.agent_type, action.get("weapon"),
                )
                return False
            if action.get("room") not in ROOMS:
                logger.warning(
                    "[%s] LLM chose invalid room '%s'",
                    self.agent_type, action.get("room"),
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

    async def decide_action(self, game_state: GameState, player_state: PlayerState) -> dict:
        player_id = player_state.your_player_id
        available = player_state.available_actions

        self.seen_cards.update(player_state.your_cards)
        unknown_suspects, unknown_weapons, unknown_rooms = self._get_unknowns()

        logger.info(
            "[%s:%s] Deciding action | available=%s | "
            "unknown: suspects=%d weapons=%d rooms=%d | seen_total=%d",
            self.agent_type, player_id, available,
            len(unknown_suspects), len(unknown_weapons), len(unknown_rooms),
            len(self.seen_cards),
        )

        # Build prompt and call LLM
        user_prompt = self._build_action_prompt(game_state, player_state)
        response_text = await self._call_llm(_ACTION_SYSTEM_PROMPT, user_prompt)

        if response_text is not None:
            parsed = self._parse_json_response(response_text)
            if parsed is not None:
                logger.info(
                    "[%s:%s] LLM proposed action: %s",
                    self.agent_type, player_id, parsed,
                )
                if self._validate_action(parsed, available, game_state, player_state):
                    logger.info(
                        "[%s:%s] Using LLM action: %s",
                        self.agent_type, player_id, parsed.get("type"),
                    )
                    # Track rooms for suggestion
                    if parsed.get("type") == "suggest":
                        room = parsed.get("room")
                        if room:
                            self.rooms_suggested_in.add(room)
                    return parsed
                else:
                    logger.warning(
                        "[%s:%s] LLM action failed validation — falling back",
                        self.agent_type, player_id,
                    )
            else:
                logger.warning(
                    "[%s:%s] Failed to parse LLM response as JSON — falling back",
                    self.agent_type, player_id,
                )
        else:
            logger.info(
                "[%s:%s] No LLM response — falling back to random agent",
                self.agent_type, player_id,
            )

        # Fallback to rule-based logic
        fallback_action = await self._fallback.decide_action(game_state, player_state)
        logger.info(
            "[%s:%s] Fallback action: %s",
            self.agent_type, player_id, fallback_action,
        )
        return fallback_action

    async def decide_show_card(
        self, matching_cards: list[str], suggesting_player_id: str
    ) -> str:
        logger.info(
            "[%s] Deciding which card to show to %s from %s",
            self.agent_type, suggesting_player_id, matching_cards,
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
                        self.agent_type, card, suggesting_player_id,
                    )
                    return card
                else:
                    logger.warning(
                        "[%s] LLM chose invalid card '%s' (valid: %s) — falling back",
                        self.agent_type, card, matching_cards,
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
            self.agent_type, card, suggesting_player_id,
        )
        return card
