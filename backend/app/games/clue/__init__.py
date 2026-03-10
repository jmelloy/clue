"""Clue (Cluedo) game package — detective board game."""

from .game import ClueGame
from .board import (
    DOORS,
    ROOM_BOUNDS,
    ROOM_CENTERS,
    SECRET_PASSAGES,
    START_POSITIONS,
    Room,
)
from .agents import (
    BaseAgent,
    LLMAgent,
    RandomAgent,
    WandererAgent,
    generate_character_chat,
    INFERENCE_NONE,
    INFERENCE_BASIC,
    INFERENCE_STANDARD,
    INFERENCE_ADVANCED,
    INFERENCE_LEVELS,
)

__all__ = [
    "ClueGame",
    "DOORS",
    "ROOM_BOUNDS",
    "ROOM_CENTERS",
    "SECRET_PASSAGES",
    "START_POSITIONS",
    "Room",
    "BaseAgent",
    "LLMAgent",
    "RandomAgent",
    "WandererAgent",
    "generate_character_chat",
    "INFERENCE_NONE",
    "INFERENCE_BASIC",
    "INFERENCE_STANDARD",
    "INFERENCE_ADVANCED",
    "INFERENCE_LEVELS",
]
