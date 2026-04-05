"""Clue-specific AgentRunner — drives Clue agent players in a background loop."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from ..agent_loop import AgentRunner
from .agents import BaseAgent
from .models import (
    ChatContext,
    GameState,
    ShowCardAction,
)

logger = logging.getLogger(__name__)


class ClueAgentRunner(AgentRunner):
    """Inline agent loop for Clue games.

    Constructor parameters beyond the base class:

    - ``get_state``           – async () -> GameState | None
    - ``get_player_state``    – async (player_id) -> PlayerState
    - ``execute_action``      – async (game_id, player_id, action) -> ActionResult
    - ``broadcast_agent_debug`` – async (game_id, agent, status, desc, ...) -> None
    - ``broadcast_chat``      – async (game_id, text, player_id=None) -> None
    - ``player_name``         – (state, player_id) -> str
    """

    game_label = "Clue"

    def __init__(
        self,
        game_id: str,
        agents: dict[str, BaseAgent],
        *,
        get_state: Callable[[], Awaitable[GameState | None]],
        get_player_state: Callable[[str], Awaitable[Any]],
        execute_action: Callable[..., Awaitable[Any]],
        broadcast_agent_debug: Callable[..., Awaitable[None]],
        broadcast_chat: Callable[..., Awaitable[None]],
        player_name: Callable[[GameState, str], str],
        registry=None,
    ) -> None:
        super().__init__(game_id, agents, registry=registry)
        self._get_state = get_state
        self._get_player_state = get_player_state
        self._execute_action = execute_action
        self._broadcast_agent_debug = broadcast_agent_debug
        self._broadcast_chat = broadcast_chat
        self._player_name = player_name

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

        pending = state.pending_show_card
        if pending and pending.player_id in self.agents:
            await self._handle_show_card(state, pending)
        elif pending:
            # A human must show a card — wait for them
            await asyncio.sleep(0.5)
        elif state.whose_turn in self.agents:
            await self._handle_agent_turn(state)
        else:
            # Human player's turn — poll periodically
            await asyncio.sleep(0.5)

        return True

    # ------------------------------------------------------------------
    # Show-card handling
    # ------------------------------------------------------------------

    async def _handle_show_card(self, state: GameState, pending: Any) -> None:
        # Pace for human observers
        await asyncio.sleep(1)

        # Re-check state (may have changed during sleep)
        state = await self._get_state()
        if not state or state.status != "playing":
            return
        pending = state.pending_show_card
        if not pending or pending.player_id not in self.agents:
            return

        pid = pending.player_id
        agent = self.agents[pid]
        matching = pending.matching_cards
        suggesting_pid = pending.suggesting_player_id

        await self._broadcast_agent_debug(
            self.game_id,
            agent,
            "thinking",
            f"Deciding which card to show from {matching}",
            game_state=state,
        )

        card = await agent.decide_show_card(matching, suggesting_pid)

        await self._broadcast_agent_debug(
            self.game_id,
            agent,
            "decided",
            "Showing card to disprove suggestion",
            decided_action={"type": "show_card", "card": card},
            game_state=state,
        )

        logger.info("Agent %s showing card in game %s", pid, self.game_id)
        await self._execute_action(self.game_id, pid, ShowCardAction(card=card))
        await agent.save_knowledge()

        # Broadcast personality chat for show_card
        chat_msg = await agent.generate_chat("show_card")
        if chat_msg:
            s = await self._get_state()
            name = self._player_name(s, pid) if s else pid
            await self._broadcast_chat(self.game_id, f"{name}: {chat_msg}", pid)

    # ------------------------------------------------------------------
    # Agent turn handling
    # ------------------------------------------------------------------

    async def _handle_agent_turn(self, state: GameState) -> None:
        agent = self.agents[state.whose_turn]

        # Pace non-LLM agents for human observers
        if agent.agent_type != "llm":
            await asyncio.sleep(1.35)

        # Re-check state
        state = await self._get_state()
        if not state or state.status != "playing":
            return
        pid = state.whose_turn
        if pid not in self.agents:
            return

        agent = self.agents[pid]
        player_state = await self._get_player_state(pid)

        await self._broadcast_agent_debug(
            self.game_id,
            agent,
            "thinking",
            f"Deciding next action (available: {', '.join(player_state.available_actions)})",
            game_state=state,
        )

        action = await agent.decide_action(state, player_state)
        action_d = action.model_dump()
        action_desc = _describe_action(action)

        await self._broadcast_agent_debug(
            self.game_id,
            agent,
            "decided",
            action_desc,
            decided_action=action_d,
            game_state=state,
        )

        logger.info(
            "Agent %s taking action %s in game %s",
            pid,
            action.type,
            self.game_id,
        )

        # For suggestions, broadcast personality chat BEFORE the action
        action_d = action.model_dump()
        if action.type == "suggest":
            chat_context = ChatContext(
                room=action_d.get("room", ""),
                suspect=action_d.get("suspect", ""),
                weapon=action_d.get("weapon", ""),
            )
            chat_msg = await agent.generate_chat(action.type, chat_context.model_dump())
            if chat_msg:
                name = self._player_name(state, pid) if state else pid
                await self._broadcast_chat(self.game_id, f"{name}: {chat_msg}", pid)

        # Execute the action with retry/fallback on rejection
        result = await self._execute_with_retry(
            agent, pid, action, action_d, state, player_state
        )
        if result is None:
            return  # action failed irrecoverably — skip rest of turn

        action = result[0]
        action_result = result[1]
        action_d = action.model_dump()

        await agent.save_knowledge()

        # Broadcast personality chat after the action (non-suggest)
        if action.type != "suggest":
            result_d = action_result.model_dump()
            chat_context = ChatContext(
                dice=result_d.get("dice", ""),
                room=result_d.get("room") or action_d.get("room") or "",
                suspect=action_d.get("suspect", ""),
                weapon=action_d.get("weapon", ""),
            )
            chat_msg = await agent.generate_chat(action.type, chat_context.model_dump())
            if chat_msg:
                s = await self._get_state()
                name = self._player_name(s, pid) if s else pid
                await self._broadcast_chat(self.game_id, f"{name}: {chat_msg}", pid)

    async def _execute_with_retry(
        self,
        agent: BaseAgent,
        pid: str,
        action: Any,
        action_d: dict,
        state: GameState,
        player_state: Any,
    ) -> tuple[Any, Any] | None:
        """Try to execute an action.  On rejection, retry for LLM agents and
        fall back to the RandomAgent fallback.

        Returns ``(final_action, result)`` on success, or ``None`` if every
        attempt failed.
        """
        try:
            result = await self._execute_action(self.game_id, pid, action)
            return (action, result)
        except ValueError as exc:
            detail = str(exc)
            agent.agent_trace(
                "action_rejected",
                status=400,
                detail=detail,
                action=action_d,
            )

            # Retry once with rejection detail for LLM agents
            if agent.agent_type == "llm":
                logger.info(
                    "Retrying action for %s in game %s after rejection: %s",
                    pid,
                    self.game_id,
                    detail,
                )
                try:
                    action = await agent.decide_action(
                        state, player_state, rejection_detail=detail
                    )
                    action_d = action.model_dump()
                    result = await self._execute_action(self.game_id, pid, action)
                    return (action, result)
                except Exception as retry_exc:
                    agent.agent_trace(
                        "action_rejected_retry_failed",
                        detail=str(retry_exc),
                        action=action_d,
                    )
                    logger.warning(
                        "Retry also failed for %s in game %s, using fallback",
                        pid,
                        self.game_id,
                    )
                    return await self._try_fallback(agent, pid, state, player_state)
            else:
                logger.warning(
                    "Action rejected for non-LLM agent %s in game %s: %s",
                    pid,
                    self.game_id,
                    detail,
                )
                return None

    async def _try_fallback(
        self,
        agent: BaseAgent,
        pid: str,
        state: GameState,
        player_state: Any,
    ) -> tuple[Any, Any] | None:
        """Attempt the RandomAgent fallback after primary + retry both failed."""
        try:
            fallback_action = await agent._fallback.decide_action(state, player_state)
            agent.agent_trace(
                "fallback_after_rejection",
                action=fallback_action.model_dump(),
            )
            result = await self._execute_action(self.game_id, pid, fallback_action)
            return (fallback_action, result)
        except Exception:
            logger.exception(
                "Fallback also failed for %s in game %s",
                pid,
                self.game_id,
            )
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _describe_action(action: Any) -> str:
    """Produce a human-readable description of a Clue action."""
    d = action.model_dump()
    t = action.type
    if t == "move":
        return f"Moving to {d.get('room', '?')}"
    if t == "suggest":
        return f"Suggesting {d.get('suspect', '?')} with {d.get('weapon', '?')}"
    if t == "accuse":
        return f"Accusing {d.get('suspect', '?')} with {d.get('weapon', '?')} in {d.get('room', '?')}"
    if t == "roll":
        return "Rolling dice"
    if t == "end_turn":
        return "Ending turn"
    if t == "secret_passage":
        return "Using secret passage"
    return t
