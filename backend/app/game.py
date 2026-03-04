"""Backward-compat shim — game logic now lives in app.games.clue.game."""

from app.games.clue.game import *  # noqa: F401,F403
from app.games.clue.game import (  # explicit re-exports for type checkers
    ALL_CARDS,
    CHARACTER_START_KEY,
    ClueGame,
    EXPIRY,
    ROOM_CENTERS,
    ROOMS,
    SECRET_PASSAGE_MAP,
    SUSPECTS,
    WEAPONS,
)
