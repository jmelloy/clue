"""Hold'em-specific AgentRunner — drives poker agent players in a background loop."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from ..agent_loop import AgentRunner
from .agents import HoldemAgent
from .models import CheckAction, FoldAction

logger = logging.getLogger(__name__)


class HoldemAgentRunner(AgentRunner):
    """Inline agent loop for Hold'em games.

    Constructor parameters beyond the base class:

    - ``get_state``             – async () -> HoldemGameState | None
    - ``get_player_state``      – async (player_id) -> HoldemPlayerState
    - ``execute_action``        – async (game_id, player_id, action) -> result
    - ``broadcast_chat``        – async (game_id, text, player_id=None) -> None
    - ``rebuy``                 – async (player_id) -> new_state
    - ``on_rebuy_success``      – async (game_id, agent_id, new_state) -> None
    - ``notify_new_hand``       – async (game_id, state) -> None
    - ``format_currency``       – (amount) -> str
    """

    game_label = "Holdem"

    def __init__(
        self,
        game_id: str,
        agents: dict[str, HoldemAgent],
        *,
        get_state: Callable[[], Awaitable[Any]],
        get_player_state: Callable[[str], Awaitable[Any]],
        execute_action: Callable[..., Awaitable[Any]],
        broadcast_chat: Callable[..., Awaitable[None]],
        rebuy: Callable[[str], Awaitable[Any]],
        on_rebuy_success: Callable[..., Awaitable[None]],
        notify_new_hand: Callable[..., Awaitable[None]],
        format_currency: Callable[[int | float], str],
        registry=None,
    ) -> None:
        super().__init__(game_id, agents, registry=registry)
        self._get_state = get_state
        self._get_player_state = get_player_state
        self._execute_action = execute_action
        self._broadcast_chat = broadcast_chat
        self._rebuy = rebuy
        self._on_rebuy_success = on_rebuy_success
        self._notify_new_hand = notify_new_hand
        self._format_currency = format_currency

    # ------------------------------------------------------------------
    # AgentRunner hooks
    # ------------------------------------------------------------------

    async def is_game_active(self) -> bool:
        state = await self._get_state()
        return state is not None and state.status == "playing"

    async def tick(self) -> bool:
        state = await self._get_state()
        if state is None or state.status != "playing":
            return False

        # Auto-rebuy for agents that are rebuy_pending
        if state.allow_rebuys:
            state = await self._handle_rebuys(state)
            if not state or state.status != "playing":
                return False

        whose_turn = state.whose_turn
        if whose_turn and whose_turn in self.agents:
            await self._handle_agent_turn(state, whose_turn)
        else:
            # Human player's turn or no turn — poll
            await asyncio.sleep(0.5)

        return True

    # ------------------------------------------------------------------
    # Rebuy handling
    # ------------------------------------------------------------------

    async def _handle_rebuys(self, state: Any) -> Any:
        """Process auto-rebuys for agents.  Returns the (possibly refreshed) state."""
        for agent_id in list(self.agents.keys()):
            agent_player = next(
                (p for p in state.players if p.id == agent_id), None
            )
            if agent_player and agent_player.rebuy_pending:
                await asyncio.sleep(1.0)
                try:
                    new_state = await self._rebuy(agent_id)
                    await self._on_rebuy_success(self.game_id, agent_id, new_state)

                    # Refresh state after rebuy
                    state = await self._get_state()
                    if not state or state.status != "playing":
                        return state

                    # If game advanced to new hand, notify
                    if state.whose_turn:
                        await self._notify_new_hand(self.game_id, state)
                except Exception:
                    logger.warning(
                        "Holdem agent %s rebuy failed in game %s",
                        agent_id,
                        self.game_id,
                        exc_info=True,
                    )

        return state

    # ------------------------------------------------------------------
    # Turn handling
    # ------------------------------------------------------------------

    async def _handle_agent_turn(self, state: Any, whose_turn: str) -> None:
        agent = self.agents[whose_turn]

        # Pace actions for human observers
        await asyncio.sleep(1.5)

        # Re-check state after sleep
        state = await self._get_state()
        if not state or state.status != "playing":
            return
        if state.whose_turn != whose_turn:
            return

        player_state = await self._get_player_state(whose_turn)
        if not player_state or not player_state.available_actions:
            await asyncio.sleep(0.5)
            return

        try:
            action = agent.decide_action(state, player_state)
            logger.info(
                "Holdem agent %s taking action %s in game %s",
                whose_turn,
                action.type,
                self.game_id,
            )

            try:
                await self._execute_action(self.game_id, whose_turn, action)
            except ValueError as exc:
                logger.warning(
                    "Holdem agent %s action failed: %s", whose_turn, exc
                )
                # Fallback: check or fold
                await self._agent_fallback(whose_turn, player_state)

            # Chat (non-critical — don't let it kill the loop)
            try:
                chat_msg = await agent.generate_chat(
                    action.type,
                    community_cards=(
                        [str(c) for c in state.community_cards]
                        if state.community_cards
                        else None
                    ),
                    pot=state.pot,
                )
                if chat_msg:
                    await self._broadcast_chat(
                        self.game_id, f"{agent.name}: {chat_msg}", whose_turn
                    )
            except Exception:
                logger.warning(
                    "Holdem agent %s chat failed in game %s",
                    whose_turn,
                    self.game_id,
                    exc_info=True,
                )

        except Exception:
            logger.exception(
                "Holdem agent %s crashed in game %s, attempting fallback",
                whose_turn,
                self.game_id,
            )
            try:
                # Re-fetch state in case it changed
                ps = await self._get_player_state(whose_turn)
                await self._agent_fallback(whose_turn, ps)
            except Exception:
                logger.exception(
                    "Holdem agent %s fallback also failed in game %s",
                    whose_turn,
                    self.game_id,
                )

    async def _agent_fallback(self, player_id: str, player_state: Any) -> None:
        """Try to check or fold for an agent whose action failed."""
        if player_state and player_state.available_actions:
            if "check" in player_state.available_actions:
                await self._execute_action(self.game_id, player_id, CheckAction())
            elif "fold" in player_state.available_actions:
                await self._execute_action(self.game_id, player_id, FoldAction())
