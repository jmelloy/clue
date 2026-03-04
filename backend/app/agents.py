"""Backward-compat shim — agents now live in app.games.clue.agents."""

from app.games.clue.agents import *  # noqa: F401,F403
from app.games.clue.agents import (  # explicit re-exports for type checkers
    BaseAgent,
    LLMAgent,
    RandomAgent,
    WandererAgent,
    generate_character_chat,
)
