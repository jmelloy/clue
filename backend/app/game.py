import json
import random
import string
import datetime as dt

from .board import (
    START_POSITIONS,
    ROOM_CENTERS,
    Room,
    build_grid,
    build_graph,
    reachable,
    move_towards,
)
from .models import (
    ChatMessage,
    GameState,
    PendingShowCard,
    Player,
    PlayerState,
    Solution,
    Suggestion,
)

# Pre-build the board graph for pathfinding
_GRID = build_grid()
_SQUARES, _ROOM_NODES = build_graph(_GRID)

# Map room name strings to Room enum values
_ROOM_NAME_TO_ENUM = {r.value: r for r in Room}

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

    # ------------------------------------------------------------------
    # Internal Redis helpers
    # ------------------------------------------------------------------

    async def _save_state(self, state: GameState):
        await self.redis.set(self._state_key, state.model_dump_json(), ex=EXPIRY)

    async def _load_state(self) -> GameState | None:
        raw = await self.redis.get(self._state_key)
        if raw is None:
            return None
        return GameState.model_validate_json(raw)

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

    async def _append_log(self, entry: dict):
        await self.redis.rpush(self._log_key, json.dumps(entry))
        await self.redis.expire(self._log_key, EXPIRY)

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

    async def get_state(self) -> GameState | None:
        return await self._load_state()

    def get_available_actions(self, player_id: str, state: GameState) -> list[str]:
        """Return the list of actions available to a player given the current game state."""
        actions = ["chat"]

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

        if not state.dice_rolled:
            actions.append("move")
        elif current_room and not suggestions_made:
            actions.append("suggest")

        actions.append("accuse")
        actions.append("end_turn")

        return actions

    async def get_player_state(self, player_id: str) -> PlayerState | None:
        state = await self._load_state()
        if state is None:
            return None
        cards = await self._load_player_cards(player_id)
        return PlayerState(
            **state.model_dump(),
            your_cards=cards,
            your_player_id=player_id,
            available_actions=self.get_available_actions(player_id, state),
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

        # Assign a character not yet taken
        taken = {p.character for p in state.players}
        available = [s for s in SUSPECTS if s not in taken]
        character = available[0]

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
            {
                "type": "game_started",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        return state

    def roll_dice(self) -> int:
        return random.randint(1, 6)

    async def process_action(self, player_id: str, action: dict) -> dict:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state.status != "playing":
            raise ValueError("Game is not in progress")

        action_type = action.get("type")

        if action_type != "show_card" and state.whose_turn != player_id:
            raise ValueError("It is not your turn")

        available = self.get_available_actions(player_id, state)
        if action_type not in available:
            raise ValueError(f"Action '{action_type}' is not available at this time")

        result: dict = {"type": action_type, "player_id": player_id}

        if action_type == "move":
            result = await self._handle_move(state, player_id, action, result)
        elif action_type == "suggest":
            result = await self._handle_suggest(state, player_id, action, result)
        elif action_type == "accuse":
            result = await self._handle_accuse(state, player_id, action, result)
        elif action_type == "end_turn":
            result = await self._handle_end_turn(state, player_id, result)
        elif action_type == "show_card":
            result = await self._handle_show_card(state, player_id, action, result)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

        return result

    async def _handle_move(
        self, state: GameState, player_id: str, action: dict, result: dict
    ) -> dict:
        if state.dice_rolled:
            raise ValueError("You already rolled this turn")

        total = self.roll_dice()
        state.last_roll = [total]
        state.dice_rolled = True

        room = action.get("room")
        if room and room not in ROOMS:
            raise ValueError(f"Invalid room: {room}")

        if room:
            # Determine the player's current position on the board graph
            current_room_name = state.current_room.get(player_id)
            pos = state.player_positions.get(player_id)

            if current_room_name and current_room_name in _ROOM_NAME_TO_ENUM:
                start_sq = _ROOM_NODES[_ROOM_NAME_TO_ENUM[current_room_name]]
            elif pos:
                start_sq = _SQUARES.get((pos[0], pos[1]))
            else:
                start_sq = None

            target_room_enum = _ROOM_NAME_TO_ENUM.get(room)

            if start_sq and target_room_enum:
                dest, reached = move_towards(
                    start_sq, target_room_enum, total, _SQUARES, _ROOM_NODES
                )
                if reached:
                    # Player reaches the room
                    state.current_room[player_id] = room
                    result["room"] = room
                    center = ROOM_CENTERS.get(room)
                    if center:
                        state.player_positions[player_id] = list(center)
                        result["position"] = list(center)
                else:
                    # Player ends up in the hallway partway there
                    result["room"] = None
                    state.current_room.pop(player_id, None)
                    state.player_positions[player_id] = [dest.row, dest.col]
                    result["position"] = [dest.row, dest.col]
            else:
                # Fallback: no position info yet — place directly in room
                state.current_room[player_id] = room
                result["room"] = room
                center = ROOM_CENTERS.get(room)
                if center:
                    state.player_positions[player_id] = list(center)
                    result["position"] = list(center)

        result["dice"] = total
        result["total"] = total

        await self._save_state(state)
        await self._append_log(
            {
                "type": "move",
                "player_id": player_id,
                "dice": total,
                "room": result.get("room"),
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        return result

    async def _handle_suggest(
        self, state: GameState, player_id: str, action: dict, result: dict
    ) -> dict:
        suspect = action.get("suspect")
        weapon = action.get("weapon")
        room = action.get("room")

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
        for other_player in order:
            other_id = other_player.id
            cards = await self._load_player_cards(other_id)
            matching = [c for c in cards if c in (suspect, weapon, room)]
            if matching:
                pending_player_id = other_id
                matching_cards = matching
                break

        # Move the suggested suspect's player to the suggestion room
        moved_suspect_player = None
        for p in players:
            if p.character == suspect and p.id != player_id:
                moved_suspect_player = p.id
                state.current_room[moved_suspect_player] = room
                center = ROOM_CENTERS.get(room)
                if center:
                    state.player_positions[moved_suspect_player] = list(center)
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
            {
                "type": "suggestion",
                "player_id": player_id,
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
                "pending_show_by": pending_player_id,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        result.update(
            {
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
                "pending_show_by": pending_player_id,
                "moved_suspect_player": moved_suspect_player,
            }
        )
        return result

    async def _handle_show_card(
        self, state: GameState, player_id: str, action: dict, result: dict
    ) -> dict:
        pending = state.pending_show_card
        if not pending:
            raise ValueError("No pending show card request")
        if pending.player_id != player_id:
            raise ValueError("You are not the player who must show a card")

        card = action.get("card")
        if card not in pending.matching_cards:
            raise ValueError(f"Card '{card}' is not valid to show for this suggestion")

        suggesting_player_id = pending.suggesting_player_id
        state.pending_show_card = None
        await self._save_state(state)

        await self._append_log(
            {
                "type": "card_shown",
                "player_id": player_id,
                "to_player_id": suggesting_player_id,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        result.update(
            {
                "card": card,
                "suggesting_player_id": suggesting_player_id,
            }
        )
        return result

    async def _handle_accuse(
        self, state: GameState, player_id: str, action: dict, result: dict
    ) -> dict:
        suspect = action.get("suspect")
        weapon = action.get("weapon")
        room = action.get("room")

        solution = await self._load_solution()
        correct = (
            suspect == solution.suspect
            and weapon == solution.weapon
            and room == solution.room
        )

        await self._append_log(
            {
                "type": "accusation",
                "player_id": player_id,
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
                "correct": correct,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        if correct:
            state.status = "finished"
            state.winner = player_id
            await self._save_state(state)
            result.update(
                {
                    "correct": True,
                    "winner": player_id,
                    "solution": solution.model_dump(),
                }
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
            result.update(
                {
                    "correct": False,
                    "solution": (
                        solution.model_dump() if state.status == "finished" else None
                    ),
                }
            )

        return result

    async def _handle_end_turn(
        self, state: GameState, player_id: str, result: dict
    ) -> dict:
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
        state.last_roll = None
        state.suggestions_this_turn = []
        await self._save_state(state)

        await self._append_log(
            {
                "type": "end_turn",
                "player_id": player_id,
                "next_player_id": next_player.id,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        result["next_player_id"] = next_player.id
        return result

    async def get_log(self) -> list[dict]:
        entries = await self.redis.lrange(self._log_key, 0, -1)
        return [json.loads(e) for e in entries]
