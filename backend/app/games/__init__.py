"""Game registry — maps game type slugs to their game classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Registry: game_type_slug -> module path
GAME_TYPES: dict[str, str] = {
    "clue": "app.games.clue",
    "holdem": "app.games.holdem",
}

# Default game type used when none is specified (backward compat)
DEFAULT_GAME_TYPE = "clue"
