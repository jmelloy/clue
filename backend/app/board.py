"""Backward-compat shim — board logic now lives in app.games.clue.board."""

from app.games.clue.board import *  # noqa: F401,F403
from app.games.clue.board import (  # explicit re-exports for type checkers
    BOARD,
    COLS,
    DOORS,
    ROOM_BOUNDS,
    ROOM_CENTERS,
    ROWS,
    Room,
    SECRET_PASSAGES,
    START_POSITIONS,
    Square,
    SquareType,
    build_graph,
    build_grid,
    move_towards,
    reachable,
    validate_grid,
)
