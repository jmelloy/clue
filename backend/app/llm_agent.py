import random
from .game import SUSPECTS, WEAPONS, ROOMS


class LLMAgent:
    """Simple rule-based agent that mimics an LLM player.

    The ``decide_action`` method can be replaced with a real LLM API call.

    Expected ``game_state`` keys: status, players, whose_turn, turn_number,
    current_room (dict of player_id→room), dice_rolled (bool), winner.

    Expected ``player_state`` keys: your_player_id, your_cards (list of card
    names), game_id, status, players, whose_turn, current_room.

    Returns an action dict with a ``type`` key and relevant fields:
      - ``{"type": "move", "room": <str>}``
      - ``{"type": "suggest", "suspect": <str>, "weapon": <str>, "room": <str>}``
      - ``{"type": "accuse", "suspect": <str>, "weapon": <str>, "room": <str>}``
      - ``{"type": "end_turn"}``
    """

    def decide_action(self, game_state: dict, player_state: dict) -> dict:
        """Return an action dict for the current turn phase."""
        player_id = player_state.get("your_player_id")
        known_cards: list[str] = player_state.get("your_cards", [])
        current_room: dict = game_state.get("current_room", {})
        dice_rolled: bool = game_state.get("dice_rolled", False)

        # Phase 1: roll dice / move
        if not dice_rolled:
            target_room = random.choice(ROOMS)
            return {"type": "move", "room": target_room}

        # Phase 2: if in a room, maybe suggest
        room = current_room.get(player_id)
        if room:
            # Pick a random suspect/weapon the agent doesn't hold
            unknown_suspects = [s for s in SUSPECTS if s not in known_cards]
            unknown_weapons = [w for w in WEAPONS if w not in known_cards]

            suspect = random.choice(unknown_suspects) if unknown_suspects else random.choice(SUSPECTS)
            weapon = random.choice(unknown_weapons) if unknown_weapons else random.choice(WEAPONS)

            # Occasionally make an accusation (10% chance)
            if random.random() < 0.10:
                unknown_rooms = [r for r in ROOMS if r not in known_cards]
                acc_room = random.choice(unknown_rooms) if unknown_rooms else random.choice(ROOMS)
                return {
                    "type": "accuse",
                    "suspect": suspect,
                    "weapon": weapon,
                    "room": acc_room,
                }

            return {
                "type": "suggest",
                "suspect": suspect,
                "weapon": weapon,
                "room": room,
            }

        # Phase 3: end turn
        return {"type": "end_turn"}
