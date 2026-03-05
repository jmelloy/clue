import json
import random
import string
import datetime as dt
import logging

from pydantic import TypeAdapter, ValidationError

from .board import (
    START_POSITIONS,
    ROOM_CENTERS,
    ROOM_NAME_TO_ENUM,
    ROOM_NODES,
    SECRET_PASSAGES,
    SQUARES,
    Room,
    SquareType,
    reachable,
    move_towards,
)
from .models import (
    AccuseAction,
    AccuseResult,
    AccusationLogEntry,
    ActionResult,
    CardShownLogEntry,
    ChatMessage,
    EndTurnAction,
    EndTurnLogEntry,
    EndTurnResult,
    GameAction,
    GameStartedLogEntry,
    GameState,
    LogEntry,
    LogEntryBase,
    MoveAction,
    MoveLogEntry,
    MoveResult,
    PendingShowCard,
    Player,
    PlayerState,
    ReachableTargets,
    RollAction,
    RollLogEntry,
    RollResult,
    SecretPassageAction,
    SecretPassageLogEntry,
    SecretPassageResult,
    ShowCardAction,
    ShowCardResult,
    Solution,
    SuggestAction,
    SuggestResult,
    Suggestion,
    SuggestionLogEntry,
    action_adapter,
)

logger = logging.getLogger(__name__)

CHARACTER_START_KEY = {
    "Miss Scarlett": "Scarlet",
    "Colonel Mustard": "Mustard",
    "Mrs. White": "White",
    "Reverend Green": "Green",
    "Mrs. Peacock": "Peacock",
    "Professor Plum": "Plum",
}

SUSPECTS = [
    "Miss Scarlett",
    "Colonel Mustard",
    "Mrs. White",
    "Reverend Green",
    "Mrs. Peacock",
    "Professor Plum",
]

WEAPONS = [
    "Candlestick",
    "Knife",
    "Lead Pipe",
    "Revolver",
    "Rope",
    "Wrench",
]

ROOMS = [
    "Kitchen",
    "Ballroom",
    "Conservatory",
    "Billiard Room",
    "Library",
    "Study",
    "Hall",
    "Lounge",
    "Dining Room",
]

ALL_CARDS = SUSPECTS + WEAPONS + ROOMS
EXPIRY = 24 * 60 * 60  # 24 hours in seconds

# Rooms with secret passages, keyed by room name string
SECRET_PASSAGE_MAP = {src.value: dst.value for src, dst in SECRET_PASSAGES.items()}


class ClueGame:
    def __init__(self, game_id: str, redis_client):
        self.game_id = game_id
        self.redis = redis_client
        self._state_key = f"game:{game_id}"
        self._solution_key = f"game:{game_id}:solution"
        self._log_key = f"game:{game_id}:log"
        self._chat_key = f"game:{game_id}:chat"

    def _cards_key(self, player_id: str) -> str:
        return f"game:{self.game_id}:cards:{player_id}"

    def _memory_key(self, player_id: str) -> str:
        return f"game:{self.game_id}:memory:{player_id}"

    def _notes_key(self, player_id: str) -> str:
        return f"game:{self.game_id}:notes:{player_id}"

    # ------------------------------------------------------------------
    # Internal Redis helpers
    # ------------------------------------------------------------------

    async def _save_state(self, state: GameState):
        await self.redis.set(self._state_key, state.model_dump_json(), ex=EXPIRY)

    async def _load_state(self) -> "GameState | None":
        raw = await self.redis.get(self._state_key)
        if raw is None:
            return None
        try:
            return GameState.model_validate_json(raw)
        except ValidationError as e:
            logger.error(f"Error loading game state from Redis: {e}")
            raise ValueError("Failed to load game state")

    async def _save_solution(self, solution: Solution):
        await self.redis.set(self._solution_key, solution.model_dump_json(), ex=EXPIRY)

    async def _load_solution(self) -> Solution:
        raw = await self.redis.get(self._solution_key)
        return Solution.model_validate_json(raw)

    async def _save_player_cards(self, player_id: str, cards: list[str]):
        await self.redis.set(self._cards_key(player_id), json.dumps(cards), ex=EXPIRY)

    async def _load_player_cards(self, player_id: str) -> list[str]:
        raw = await self.redis.get(self._cards_key(player_id))
        if raw is None:
            return []
        return json.loads(raw)

    async def _append_log(self, entry: LogEntryBase):
        await self.redis.rpush(self._log_key, entry.model_dump_json())
        await self.redis.expire(self._log_key, EXPIRY)

    async def append_memory(self, player_id: str, entry: str):
        """Append a memory entry for an LLM agent."""
        await self.redis.rpush(self._memory_key(player_id), entry)
        await self.redis.expire(self._memory_key(player_id), EXPIRY)

    async def get_memory(self, player_id: str) -> list[str]:
        """Retrieve all memory entries for an LLM agent."""
        entries = await self.redis.lrange(self._memory_key(player_id), 0, -1)
        return [e if isinstance(e, str) else e.decode() for e in entries]

    async def save_detective_notes(self, player_id: str, notes: dict):
        """Save a player's detective notes to Redis."""
        await self.redis.set(self._notes_key(player_id), json.dumps(notes), ex=EXPIRY)

    async def load_detective_notes(self, player_id: str) -> dict | None:
        """Load a player's detective notes from Redis."""
        raw = await self.redis.get(self._notes_key(player_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def add_chat_message(self, message: ChatMessage):
        await self.redis.rpush(self._chat_key, message.model_dump_json())
        await self.redis.expire(self._chat_key, EXPIRY)

    async def get_chat_messages(self) -> list[ChatMessage]:
        entries = await self.redis.lrange(self._chat_key, 0, -1)
        return [ChatMessage.model_validate_json(e) for e in entries]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(self) -> GameState:
        """Initialize a new game in Redis and create the solution."""
        solution = Solution(
            suspect=random.choice(SUSPECTS),
            weapon=random.choice(WEAPONS),
            room=random.choice(ROOMS),
        )
        await self._save_solution(solution)

        state = GameState(
            game_id=self.game_id,
            status="waiting",
        )
        await self._save_state(state)
        return state

    async def get_state(self) -> GameState:
        return await self._load_state()

    def get_available_actions(self, player_id: str, state: GameState) -> list[str]:
        """Return the list of actions available to a player given the current game state.

        Turn phases:
        1. Pre-roll: offer secret_passage (if in corner room) and roll
        2. Post-roll: offer move (choose room)
        3. Post-move: offer suggest (if in a room), accuse, end_turn
        """
        actions = []

        if state.status != "playing":
            return actions

        pending = state.pending_show_card
        if pending:
            if pending.player_id == player_id:
                actions.append("show_card")
            return actions

        if state.whose_turn != player_id:
            return actions

        current_room = state.current_room.get(player_id)
        suggestions_made = bool(state.suggestions_this_turn)

        # After making a suggestion, you can only accuse or end turn
        # (no more rolling/moving this turn).
        if suggestions_made:
            actions.append("accuse")
            actions.append("end_turn")
            return actions

        if not state.dice_rolled and not state.moved:
            # Phase 1: before rolling — offer passage (if applicable) and roll
            if current_room and current_room in SECRET_PASSAGE_MAP:
                actions.append("secret_passage")
            actions.append("roll")
            # If pulled into a room by a suggestion, can suggest without rolling
            if (
                current_room
                and state.was_moved_by_suggestion.get(player_id)
            ):
                actions.append("suggest")
        elif state.dice_rolled and not state.moved:
            # Phase 2: dice rolled, choose room to move toward
            actions.append("move")
        elif current_room and not suggestions_made:
            # Phase 3: moved, in a room, can suggest
            actions.append("suggest")

        actions.append("accuse")

        # Only offer end_turn if the player has done something this turn
        has_acted = state.moved or bool(state.suggestions_this_turn)
        if has_acted:
            actions.append("end_turn")

        return actions

    async def get_player_state(self, player_id: str) -> PlayerState | None:
        state = await self._load_state()
        if state is None:
            return None
        cards = await self._load_player_cards(player_id)
        notes = await self.load_detective_notes(player_id)
        return PlayerState(
            **state.model_dump(),
            your_cards=cards,
            your_player_id=player_id,
            available_actions=self.get_available_actions(player_id, state),
            detective_notes=notes,
        )

    async def add_player(
        self, player_id: str, player_name: str, player_type: str
    ) -> Player:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "waiting":
            raise ValueError("Game already started")
        if len(state.players) >= 6:
            raise ValueError("Game is full")

        # Assign a random character not yet taken
        taken = {p.character for p in state.players}
        available = [s for s in SUSPECTS if s not in taken]
        character = random.choice(available)

        player = Player(
            id=player_id,
            name=player_name,
            type=player_type,
            character=character,
        )
        state.players.append(player)
        await self._save_state(state)
        return player

    async def start(self) -> GameState:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "waiting":
            raise ValueError("Game already started")
        if len(state.players) < 2:
            raise ValueError("Need at least 2 players to start")

        # Auto-add wanderer players for unplayed suspects
        taken_characters = {p.character for p in state.players}
        for suspect in SUSPECTS:
            if suspect not in taken_characters:
                wanderer_id = "W_" + "".join(
                    random.choices(string.ascii_uppercase + string.digits, k=6)
                )
                wanderer = Player(
                    id=wanderer_id,
                    name=suspect,
                    type="wanderer",
                    character=suspect,
                )
                state.players.append(wanderer)

        solution = await self._load_solution()

        # Build deck of remaining cards (exclude solution cards)
        deck = [
            c
            for c in ALL_CARDS
            if c not in (solution.suspect, solution.weapon, solution.room)
        ]
        random.shuffle(deck)

        # Deal cards round-robin to real players only (wanderers get none)
        players = state.players
        real_players = [p for p in players if p.type != "wanderer"]
        num_real = len(real_players)
        dealt: dict[str, list[str]] = {p.id: [] for p in real_players}
        for i, card in enumerate(deck):
            pid = real_players[i % num_real].id
            dealt[pid].append(card)

        for pid, cards in dealt.items():
            await self._save_player_cards(pid, cards)

        state.status = "playing"
        state.whose_turn = players[0].id
        state.turn_number = 1
        state.dice_rolled = False

        # Initialize player positions at starting squares
        state.player_positions = {}
        for player in players:
            start_key = CHARACTER_START_KEY.get(player.character)
            if start_key and start_key in START_POSITIONS:
                row, col = START_POSITIONS[start_key]
                state.player_positions[player.id] = [row, col]

        await self._save_state(state)

        await self._append_log(
            GameStartedLogEntry(
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return state

    def roll_dice(self) -> tuple[int, int]:
        return (random.randint(1, 6), random.randint(1, 6))

    @staticmethod
    def _get_start_square(player_id: str, state: "GameState"):
        """Return the board Square for the given player's current location."""
        current_room_name = state.current_room.get(player_id)
        pos = state.player_positions.get(player_id)
        if current_room_name and current_room_name in ROOM_NAME_TO_ENUM:
            return ROOM_NODES[ROOM_NAME_TO_ENUM[current_room_name]]
        elif pos:
            return SQUARES.get((pos[0], pos[1]))
        return None

    @staticmethod
    def _get_occupied_positions(
        state: "GameState", exclude_player_id: str
    ) -> set[tuple[int, int]]:
        """Return hallway positions occupied by other pawns.

        Only players who are NOT currently inside a room are counted —
        rooms have infinite capacity.
        """
        occupied: set[tuple[int, int]] = set()
        for pid, pos in state.player_positions.items():
            if pid == exclude_player_id:
                continue
            # Only count players in the hallway (not in a room)
            if pid not in state.current_room:
                occupied.add((pos[0], pos[1]))
        return occupied

    def get_reachable_targets(
        self, player_id: str, state: "GameState", dice: int
    ) -> ReachableTargets:
        """Compute which rooms and hallway squares are reachable with the given dice roll.

        Returns a ReachableTargets with:
          - reachable_rooms: list of room names the player can enter
          - reachable_positions: list of [row, col] hallway positions reachable

        Applies movement constraints:
          - Occupied hallway/door squares are impassable
          - The player's current room is excluded (cannot re-enter same room)
        """
        start_sq = self._get_start_square(player_id, state)
        if not start_sq:
            logger.warning(
                "Could not resolve start square for player %s "
                "(current_room=%s, position=%s)",
                player_id,
                state.current_room.get(player_id),
                state.player_positions.get(player_id),
            )
            return ReachableTargets(reachable_rooms=list(ROOMS))

        occupied = self._get_occupied_positions(state, player_id)
        reached = reachable(
            start_sq, dice, SQUARES, ROOM_NODES, occupied, use_secret_passages=False
        )

        rooms = []
        positions = []
        for sq, dist in reached.items():
            if sq.type == SquareType.ROOM and sq.room and sq != start_sq:
                rooms.append(sq.room.value)
            elif sq != start_sq and sq.type in (
                SquareType.HALLWAY,
                SquareType.DOOR,
                SquareType.START,
            ):
                positions.append([sq.row, sq.col])

        return ReachableTargets(reachable_rooms=rooms, reachable_positions=positions)

    async def process_action(
        self, player_id: str, action: GameAction | dict
    ) -> ActionResult:
        """Process a game action and return a typed result.

        Accepts either a typed GameAction or a plain dict (for backward
        compatibility with agents and tests). Dicts are parsed into the
        appropriate GameAction subclass via the discriminated union.
        """
        # Parse dict actions into typed models
        if isinstance(action, dict):
            action = action_adapter.validate_python(action)

        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "playing":
            raise ValueError("Game is not in progress")

        if not isinstance(action, ShowCardAction) and state.whose_turn != player_id:
            raise ValueError("It is not your turn")

        available = self.get_available_actions(player_id, state)
        if action.type not in available:
            raise ValueError(f"Action '{action.type}' is not available at this time")

        if isinstance(action, RollAction):
            return await self._handle_roll(state, player_id)
        elif isinstance(action, SecretPassageAction):
            return await self._handle_secret_passage(state, player_id)
        elif isinstance(action, MoveAction):
            return await self._handle_move(state, player_id, action)
        elif isinstance(action, SuggestAction):
            return await self._handle_suggest(state, player_id, action)
        elif isinstance(action, AccuseAction):
            return await self._handle_accuse(state, player_id, action)
        elif isinstance(action, EndTurnAction):
            return await self._handle_end_turn(state, player_id)
        elif isinstance(action, ShowCardAction):
            return await self._handle_show_card(state, player_id, action)
        else:
            raise ValueError(f"Unknown action type: {action.type}")

    async def _handle_roll(
        self, state: GameState, player_id: str
    ) -> RollResult:
        """Roll the dice without moving. The player then chooses a room."""
        if state.dice_rolled:
            raise ValueError("You already rolled this turn")

        die1, die2 = self.roll_dice()
        total = die1 + die2
        state.last_roll = [die1, die2]
        state.dice_rolled = True

        await self._save_state(state)
        await self._append_log(
            RollLogEntry(
                player_id=player_id,
                dice=total,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return RollResult(player_id=player_id, dice=total, total=total)

    async def _handle_secret_passage(
        self, state: GameState, player_id: str
    ) -> SecretPassageResult:
        """Use a secret passage to move to the linked corner room."""
        current_room = state.current_room.get(player_id)
        if not current_room or current_room not in SECRET_PASSAGE_MAP:
            raise ValueError("You are not in a room with a secret passage")

        dest_room = SECRET_PASSAGE_MAP[current_room]
        state.current_room[player_id] = dest_room
        state.moved = True
        position: list[int] | None = None
        center = ROOM_CENTERS.get(dest_room)
        if center:
            state.player_positions[player_id] = list(center)
            position = list(center)

        await self._save_state(state)
        await self._append_log(
            SecretPassageLogEntry(
                player_id=player_id,
                from_room=current_room,
                room=dest_room,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return SecretPassageResult(
            player_id=player_id,
            from_room=current_room,
            room=dest_room,
            position=position,
        )

    async def _handle_move(
        self, state: GameState, player_id: str, action: MoveAction
    ) -> MoveResult:
        """Choose a room to move toward using the already-rolled dice."""
        if not state.dice_rolled:
            raise ValueError("You must roll the dice first")
        if state.moved:
            raise ValueError("You already moved this turn")

        total = sum(state.last_roll) if state.last_roll else 0

        room_name = action.room
        target_pos = action.position
        if room_name and room_name not in ROOMS:
            raise ValueError(f"Invalid room: {room_name}")

        # Cannot re-enter the room you are already in
        current_room_name = state.current_room.get(player_id)
        if room_name and room_name == current_room_name:
            raise ValueError("Cannot re-enter the room you are already in")

        occupied = self._get_occupied_positions(state, player_id)
        start_sq = self._get_start_square(player_id, state)

        final_room: str | None = None
        final_position: list[int] | None = None

        if target_pos and not room_name:
            # Position-based move: player clicked a specific hallway cell
            target_row, target_col = int(target_pos[0]), int(target_pos[1])
            target_sq = SQUARES.get((target_row, target_col))
            if not target_sq:
                raise ValueError("Invalid position")

            if start_sq:
                reachable_squares = reachable(
                    start_sq,
                    total,
                    SQUARES,
                    ROOM_NODES,
                    occupied,
                    use_secret_passages=False,
                )
                if target_sq in reachable_squares:
                    state.current_room.pop(player_id, None)
                    state.player_positions[player_id] = [target_row, target_col]
                    final_room = None
                    final_position = [target_row, target_col]
                else:
                    raise ValueError("That position is not reachable with your roll")
            else:
                raise ValueError("Cannot determine current position")

        elif room_name:
            target_room_enum = ROOM_NAME_TO_ENUM.get(room_name)

            if start_sq and target_room_enum:
                dest, reached = move_towards(
                    start_sq,
                    target_room_enum,
                    total,
                    SQUARES,
                    ROOM_NODES,
                    occupied,
                    use_secret_passages=False,
                )
                if reached:
                    # Player reaches the room
                    state.current_room[player_id] = room_name
                    final_room = room_name
                    center = ROOM_CENTERS.get(room_name)
                    if center:
                        state.player_positions[player_id] = list(center)
                        final_position = list(center)
                elif dest == start_sq:
                    # Player couldn't actually move (all paths blocked)
                    final_room = current_room_name
                    final_position = state.player_positions.get(player_id)
                else:
                    # Player ends up in the hallway partway there
                    final_room = None
                    state.current_room.pop(player_id, None)
                    state.player_positions[player_id] = [dest.row, dest.col]
                    final_position = [dest.row, dest.col]
            else:
                # Fallback: no position info yet — place directly in room
                state.current_room[player_id] = room_name
                final_room = room_name
                center = ROOM_CENTERS.get(room_name)
                if center:
                    state.player_positions[player_id] = list(center)
                    final_position = list(center)

        state.moved = True

        await self._save_state(state)
        await self._append_log(
            MoveLogEntry(
                player_id=player_id,
                dice=total,
                room=final_room,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return MoveResult(
            player_id=player_id,
            room=final_room,
            position=final_position,
            dice=total,
            total=total,
        )

    async def _handle_suggest(
        self, state: GameState, player_id: str, action: SuggestAction
    ) -> SuggestResult:
        suspect = action.suspect
        weapon = action.weapon
        room = action.room

        if suspect not in SUSPECTS:
            raise ValueError(f"Invalid suspect: {suspect}")
        if weapon not in WEAPONS:
            raise ValueError(f"Invalid weapon: {weapon}")
        if room not in ROOMS:
            raise ValueError(f"Invalid room: {room}")

        players = state.players
        # Find who shows a card (ask players in turn, starting after suggesting player)
        idx = next(i for i, p in enumerate(players) if p.id == player_id)
        order = players[idx + 1 :] + players[:idx]

        pending_player_id = None
        matching_cards: list[str] = []
        players_without_match: list[str] = []
        for other_player in order:
            other_id = other_player.id
            cards = await self._load_player_cards(other_id)
            matching = [c for c in cards if c in (suspect, weapon, room)]
            if matching:
                pending_player_id = other_id
                matching_cards = matching
                break
            else:
                players_without_match.append(other_id)

        # Move the suggested suspect's player to the suggestion room
        moved_suspect_player = None
        for p in players:
            if p.character == suspect and p.id != player_id:
                moved_suspect_player = p.id
                state.current_room[moved_suspect_player] = room
                center = ROOM_CENTERS.get(room)
                if center:
                    state.player_positions[moved_suspect_player] = list(center)
                # Mark that this player was pulled into a room by a suggestion,
                # so they can suggest from it on their next turn without rolling.
                state.was_moved_by_suggestion[moved_suspect_player] = True
                break

        suggestion_entry = Suggestion(
            suspect=suspect,
            weapon=weapon,
            room=room,
            suggested_by=player_id,
            pending_show_by=pending_player_id,
        )
        state.suggestions_this_turn.append(suggestion_entry)

        if pending_player_id:
            state.pending_show_card = PendingShowCard(
                player_id=pending_player_id,
                suggesting_player_id=player_id,
                suspect=suspect,
                weapon=weapon,
                room=room,
                matching_cards=matching_cards,
            )

        await self._save_state(state)

        await self._append_log(
            SuggestionLogEntry(
                player_id=player_id,
                suspect=suspect,
                weapon=weapon,
                room=room,
                pending_show_by=pending_player_id,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return SuggestResult(
            player_id=player_id,
            suspect=suspect,
            weapon=weapon,
            room=room,
            pending_show_by=pending_player_id,
            moved_suspect_player=moved_suspect_player,
            players_without_match=players_without_match,
        )

    async def _handle_show_card(
        self, state: GameState, player_id: str, action: ShowCardAction
    ) -> ShowCardResult:
        pending = state.pending_show_card
        if not pending:
            raise ValueError("No pending show card request")
        if pending.player_id != player_id:
            raise ValueError("You are not the player who must show a card")

        card = action.card
        if card not in pending.matching_cards:
            raise ValueError(f"Card '{card}' is not valid to show for this suggestion")

        suggesting_player_id = pending.suggesting_player_id
        state.pending_show_card = None
        await self._save_state(state)

        await self._append_log(
            CardShownLogEntry(
                player_id=player_id,
                to_player_id=suggesting_player_id,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return ShowCardResult(
            player_id=player_id,
            card=card,
            suggesting_player_id=suggesting_player_id,
            suspect=pending.suspect,
            weapon=pending.weapon,
            room=pending.room,
        )

    async def _handle_accuse(
        self, state: GameState, player_id: str, action: AccuseAction
    ) -> AccuseResult:
        suspect = action.suspect
        weapon = action.weapon
        room = action.room

        solution = await self._load_solution()
        correct = (
            suspect == solution.suspect
            and weapon == solution.weapon
            and room == solution.room
        )

        await self._append_log(
            AccusationLogEntry(
                player_id=player_id,
                suspect=suspect,
                weapon=weapon,
                room=room,
                correct=correct,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        if correct:
            state.status = "finished"
            state.winner = player_id
            await self._save_state(state)
            return AccuseResult(
                player_id=player_id,
                correct=True,
                winner=player_id,
                solution=solution,
            )
        else:
            # Player is eliminated but game continues
            for p in state.players:
                if p.id == player_id:
                    p.active = False
                    break

            # Check if only one non-wanderer player left
            active_real = [
                p for p in state.players if p.active and p.type != "wanderer"
            ]
            if len(active_real) == 1:
                state.status = "finished"
                state.winner = active_real[0].id

            await self._save_state(state)
            return AccuseResult(
                player_id=player_id,
                correct=False,
                solution=(
                    solution if state.status == "finished" else None
                ),
            )

    async def _handle_end_turn(
        self, state: GameState, player_id: str
    ) -> EndTurnResult:
        if state.pending_show_card:
            raise ValueError(
                "Cannot end turn while waiting for a player to show a card"
            )
        players = state.players
        active = [p for p in players if p.active]
        idx = next((i for i, p in enumerate(active) if p.id == player_id), None)
        if idx is None:
            raise ValueError("Player not found")

        next_player = active[(idx + 1) % len(active)]
        state.whose_turn = next_player.id
        state.turn_number += 1
        state.dice_rolled = False
        state.moved = False
        state.last_roll = None
        state.suggestions_this_turn = []
        state.was_moved_by_suggestion.pop(player_id, None)
        await self._save_state(state)

        await self._append_log(
            EndTurnLogEntry(
                player_id=player_id,
                next_player_id=next_player.id,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )

        return EndTurnResult(player_id=player_id, next_player_id=next_player.id)

    async def get_log(self) -> list[LogEntryBase]:
        _log_adapter: TypeAdapter[LogEntry] = TypeAdapter(LogEntry)
        entries = await self.redis.lrange(self._log_key, 0, -1)
        result = []
        for e in entries:
            try:
                result.append(_log_adapter.validate_json(e))
            except ValidationError:
                # Fallback for entries written before typed log models
                result.append(LogEntryBase.model_validate_json(e))
        return result
