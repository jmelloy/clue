"""Base AgentRunner class for driving automated game agents.

Provides the common polling loop, error handling, cleanup, and watchdog
restart logic shared by all game types.  Game-specific subclasses override
a small set of hooks to supply turn-handling behaviour.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class AgentRunner(ABC):
    """Manages agent background loops for a single game instance.

    Subclasses must implement:
    - ``game_label``      – short string for log messages (e.g. ``"Clue"``).
    - ``is_game_active``  – check whether the game is still running.
    - ``tick``            – perform one iteration of the agent loop. Return
      ``True`` to keep looping, ``False`` to stop.

    Optional overrides:
    - ``on_start``        – called once when the loop begins.
    - ``on_stop``         – called in the ``finally`` block.
    - ``create_agents_from_config`` – rebuild agent instances for watchdog
      restart.
    """

    def __init__(
        self,
        game_id: str,
        agents: dict[str, Any],
        *,
        registry: _LoopRegistry | None = None,
    ) -> None:
        self.game_id = game_id
        self.agents = agents
        self._registry = registry

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def game_label(self) -> str:
        """Human-readable game type label for logging."""
        ...

    @abstractmethod
    async def is_game_active(self) -> bool:
        """Return True when the game is still in a playable state."""
        ...

    @abstractmethod
    async def tick(self) -> bool:
        """Execute one iteration of the agent loop.

        Return ``True`` to continue the loop, ``False`` to stop.
        Implementations should include their own ``asyncio.sleep`` calls
        as needed to pace actions.
        """
        ...

    async def on_start(self) -> None:
        """Called once when the loop is about to begin.  Override as needed."""

    async def on_stop(self) -> None:
        """Called in the finally block when the loop ends.  Override as needed."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the agent polling loop until the game ends or an error occurs.

        This is the method you pass to ``asyncio.create_task()``.
        """
        if not self.agents:
            return

        logger.info(
            "%s agent loop started for game %s with %d agent(s)",
            self.game_label,
            self.game_id,
            len(self.agents),
        )

        try:
            await self.on_start()

            while True:
                if not await self.is_game_active():
                    break
                keep_going = await self.tick()
                if not keep_going:
                    break

        except asyncio.CancelledError:
            logger.info(
                "%s agent loop cancelled for game %s",
                self.game_label,
                self.game_id,
            )
        except Exception:
            logger.exception(
                "%s agent loop error in game %s",
                self.game_label,
                self.game_id,
            )
        finally:
            await self.on_stop()
            if self._registry:
                self._registry.remove(self.game_id)
            logger.info(
                "%s agent loop ended for game %s",
                self.game_label,
                self.game_id,
            )

    # ------------------------------------------------------------------
    # Task management helpers
    # ------------------------------------------------------------------

    def make_done_callback(self) -> "callable":
        """Return a done-callback that triggers the watchdog on unexpected exit."""
        registry = self._registry

        def _cb(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            if registry and registry.watchdog:
                task.get_loop().create_task(
                    registry.watchdog(self.game_id)
                )

        return _cb


class _LoopRegistry:
    """Tracks running agent tasks and their agent dicts for a single game type.

    This replaces the module-level ``_game_agents`` / ``_agent_tasks`` dicts
    that were previously scattered across ``main.py``.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.agents: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.watchdog: "callable | None" = None

    # -- mutators -------------------------------------------------------

    def register(
        self,
        game_id: str,
        agents: dict[str, Any],
        task: asyncio.Task,
    ) -> None:
        self.agents[game_id] = agents
        self.tasks[game_id] = task

    def remove(self, game_id: str) -> None:
        self.agents.pop(game_id, None)
        self.tasks.pop(game_id, None)

    def cancel_all(self) -> None:
        """Cancel every running task and clear state.  Used during shutdown."""
        for task in list(self.tasks.values()):
            task.cancel()
        self.tasks.clear()
        self.agents.clear()

    # -- queries --------------------------------------------------------

    def is_running(self, game_id: str) -> bool:
        return game_id in self.tasks and not self.tasks[game_id].done()

    def get_agents(self, game_id: str) -> dict[str, Any] | None:
        return self.agents.get(game_id)
