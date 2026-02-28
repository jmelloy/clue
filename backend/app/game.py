import json
import random
import string
import datetime as dt

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

    async def _save_state(self, state: dict):
        await self.redis.set(self._state_key, json.dumps(state), ex=EXPIRY)

    async def _load_state(self) -> dict | None:
        raw = await self.redis.get(self._state_key)
        if raw is None:
            return None
        return json.loads(raw)

    async def _save_solution(self, solution: dict):
        await self.redis.set(self._solution_key, json.dumps(solution), ex=EXPIRY)

    async def _load_solution(self) -> dict:
        raw = await self.redis.get(self._solution_key)
        return json.loads(raw)

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

    async def add_chat_message(self, message: dict):
        await self.redis.rpush(self._chat_key, json.dumps(message))
        await self.redis.expire(self._chat_key, EXPIRY)

    async def get_chat_messages(self) -> list[dict]:
        entries = await self.redis.lrange(self._chat_key, 0, -1)
        return [json.loads(e) for e in entries]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(self) -> dict:
        """Initialize a new game in Redis and create the solution."""
        solution = {
            "suspect": random.choice(SUSPECTS),
            "weapon": random.choice(WEAPONS),
            "room": random.choice(ROOMS),
        }
        await self._save_solution(solution)

        state = {
            "game_id": self.game_id,
            "status": "waiting",
            "players": [],
            "whose_turn": None,
            "turn_number": 0,
            "current_room": {},
            "suggestions_this_turn": [],
            "winner": None,
            "dice_rolled": False,
            "last_roll": None,
        }
        await self._save_state(state)
        return state

    async def get_state(self) -> dict | None:
        return await self._load_state()

    async def get_player_state(self, player_id: str) -> dict | None:
        state = await self._load_state()
        if state is None:
            return None
        cards = await self._load_player_cards(player_id)
        player_state = dict(state)
        player_state["your_cards"] = cards
        player_state["your_player_id"] = player_id
        return player_state

    async def add_player(
        self, player_id: str, player_name: str, player_type: str
    ) -> dict:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state["status"] != "waiting":
            raise ValueError("Game already started")
        if len(state["players"]) >= 6:
            raise ValueError("Game is full")

        # Assign a character not yet taken
        taken = {p["character"] for p in state["players"]}
        available = [s for s in SUSPECTS if s not in taken]
        character = available[0]

        player = {
            "id": player_id,
            "name": player_name,
            "type": player_type,
            "character": character,
            "active": True,
        }
        state["players"].append(player)
        await self._save_state(state)
        return player

    async def start(self) -> dict:
        state = await self._load_state()
        if state is None:
            raise ValueError("Game not found")
        if state["status"] != "waiting":
            raise ValueError("Game already started")
        if len(state["players"]) < 2:
            raise ValueError("Need at least 2 players to start")

        solution = await self._load_solution()

        # Build deck of remaining cards (exclude solution cards)
        deck = [
            c
            for c in ALL_CARDS
            if c not in (solution["suspect"], solution["weapon"], solution["room"])
        ]
        random.shuffle(deck)

        # Deal cards round-robin
        players = state["players"]
        num_players = len(players)
        dealt: dict[str, list[str]] = {p["id"]: [] for p in players}
        for i, card in enumerate(deck):
            pid = players[i % num_players]["id"]
            dealt[pid].append(card)

        for pid, cards in dealt.items():
            await self._save_player_cards(pid, cards)

        state["status"] = "playing"
        state["whose_turn"] = players[0]["id"]
        state["turn_number"] = 1
        state["dice_rolled"] = False
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
        if state["status"] != "playing":
            raise ValueError("Game is not in progress")
        if state["whose_turn"] != player_id:
            raise ValueError("It is not your turn")

        action_type = action.get("type")
        result: dict = {"type": action_type, "player_id": player_id}

        if action_type == "move":
            result = await self._handle_move(state, player_id, action, result)
        elif action_type == "suggest":
            result = await self._handle_suggest(state, player_id, action, result)
        elif action_type == "accuse":
            result = await self._handle_accuse(state, player_id, action, result)
        elif action_type == "end_turn":
            result = await self._handle_end_turn(state, player_id, result)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

        return result

    async def _handle_move(
        self, state: dict, player_id: str, action: dict, result: dict
    ) -> dict:
        if state.get("dice_rolled"):
            raise ValueError("You already rolled this turn")

        total = self.roll_dice()
        state["last_roll"] = [total]
        state["dice_rolled"] = True

        room = action.get("room")
        if room and room not in ROOMS:
            raise ValueError(f"Invalid room: {room}")

        if room:
            if "current_room" not in state:
                state["current_room"] = {}
            state["current_room"][player_id] = room
            result["room"] = room

        result["dice"] = total
        result["total"] = total

        await self._save_state(state)
        await self._append_log(
            {
                "type": "move",
                "player_id": player_id,
                "dice": total,
                "room": room,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        return result

    async def _handle_suggest(
        self, state: dict, player_id: str, action: dict, result: dict
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

        players = state["players"]
        # Find who shows a card (ask players in turn, starting after suggesting player)
        idx = next(i for i, p in enumerate(players) if p["id"] == player_id)
        order = players[idx + 1 :] + players[:idx]

        shown_card = None
        shown_by = None
        for other_player in order:
            other_id = other_player["id"]
            cards = await self._load_player_cards(other_id)
            matching = [c for c in cards if c in (suspect, weapon, room)]
            if matching:
                shown_card = random.choice(matching)
                shown_by = other_id
                break

        suggestion_entry = {
            "suspect": suspect,
            "weapon": weapon,
            "room": room,
            "shown_by": shown_by,
            "shown_card": shown_card,
        }
        state.setdefault("suggestions_this_turn", []).append(suggestion_entry)
        await self._save_state(state)

        await self._append_log(
            {
                "type": "suggestion",
                "player_id": player_id,
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
                "shown_by": shown_by,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        result.update(
            {
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
                "shown_by": shown_by,
                "shown_card": shown_card,  # Only the suggesting player should see this
            }
        )
        return result

    async def _handle_accuse(
        self, state: dict, player_id: str, action: dict, result: dict
    ) -> dict:
        suspect = action.get("suspect")
        weapon = action.get("weapon")
        room = action.get("room")

        solution = await self._load_solution()
        correct = (
            suspect == solution["suspect"]
            and weapon == solution["weapon"]
            and room == solution["room"]
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
            state["status"] = "finished"
            state["winner"] = player_id
            await self._save_state(state)
            result.update(
                {
                    "correct": True,
                    "winner": player_id,
                    "solution": solution,
                }
            )
        else:
            # Player is eliminated but game continues
            for p in state["players"]:
                if p["id"] == player_id:
                    p["active"] = False
                    break

            # Check if only one player left
            active = [p for p in state["players"] if p.get("active", True)]
            if len(active) == 1:
                state["status"] = "finished"
                state["winner"] = active[0]["id"]

            await self._save_state(state)
            result.update(
                {
                    "correct": False,
                    "solution": solution if state["status"] == "finished" else None,
                }
            )

        return result

    async def _handle_end_turn(self, state: dict, player_id: str, result: dict) -> dict:
        players = state["players"]
        active = [p for p in players if p.get("active", True)]
        idx = next((i for i, p in enumerate(active) if p["id"] == player_id), None)
        if idx is None:
            raise ValueError("Player not found")

        next_player = active[(idx + 1) % len(active)]
        state["whose_turn"] = next_player["id"]
        state["turn_number"] = state.get("turn_number", 0) + 1
        state["dice_rolled"] = False
        state["last_roll"] = None
        state["suggestions_this_turn"] = []
        await self._save_state(state)

        await self._append_log(
            {
                "type": "end_turn",
                "player_id": player_id,
                "next_player_id": next_player["id"],
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )

        result["next_player_id"] = next_player["id"]
        return result

    async def get_log(self) -> list[dict]:
        entries = await self.redis.lrange(self._log_key, 0, -1)
        return [json.loads(e) for e in entries]
