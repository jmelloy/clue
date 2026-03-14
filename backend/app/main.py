import asyncio
import json
import logging
import os
import random
import string
import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .games.agent_loop import _LoopRegistry
from .games.clue.agent_loop import ClueAgentRunner
from .games.clue.agents import (
    BaseAgent,
    LLMAgent,
    RandomAgent,
    WandererAgent,
    generate_character_chat,
)
from .games.clue.board import (
    DOORS,
    ROOM_BOUNDS,
    ROOM_CENTERS,
    SECRET_PASSAGES,
    START_POSITIONS,
    Room,
)
from .games.clue.game import ClueGame
from .games.clue.models import (
    AccusationMadeMessage,
    AccuseAction,
    AccuseResult,
    ActionRequest,
    ActionResult,
    AddAgentRequest,
    AgentDebugMessage,
    AgentPlayerConfig,
    AutoEndTimerMessage,
    AutoShowCardTimerMessage,
    CardShownMessage,
    CardShownPublicMessage,
    ChatBroadcastMessage,
    ChatContext,
    WandererSeed,
    ChatMessage,
    ChatMessagesResponse,
    ChatRequest,
    CreateGameResponse,
    DiceRolledMessage,
    EndTurnAction,
    EndTurnResult,
    GameAction,
    GameOverMessage,
    GameStartedMessage,
    GameState,
    GameStateUpdateMessage,
    JoinGameResponse,
    JoinRequest,
    MoveResult,
    OkResponse,
    Player,
    PlayerJoinedMessage,
    PlayerMovedMessage,
    PlayerState,
    SaveNotesRequest,
    PongMessage,
    RollResult,
    SecretPassageResult,
    ShowCardAction,
    ShowCardAgentEvent,
    ShowCardRequestMessage,
    ShowCardResult,
    SuggestAgentEvent,
    SuggestAction,
    SuggestResult,
    SuggestionMadeMessage,
    WandererTurnInfo,
    YourTurnMessage,
)
from .ws_manager import ConnectionManager
from .games.holdem.agent_loop import HoldemAgentRunner
from .games.holdem.agents import HoldemAgent, get_personality
from .games.holdem.game import HoldemGame
from .games.holdem.models import (
    HoldemActionMessage,
    HoldemActionRequest,
    HoldemAddAgentRequest,
    HoldemChatBroadcastMessage,
    HoldemChatMessage,
    HoldemChatMessagesResponse,
    HoldemChatRequest,
    HoldemCommunityCardsMessage,
    HoldemCreateGameRequest,
    HoldemCreateGameResponse,
    HoldemGameOverMessage,
    HoldemGameStartedMessage,
    HoldemGameState,
    HoldemGameStateMessage,
    HoldemJoinGameResponse,
    HoldemJoinRequest,
    HoldemNewHandMessage,
    HoldemPlayerJoinedMessage,
    HoldemPlayerEliminatedMessage,
    HoldemPongMessage,
    HoldemRebuyMessage,
    HoldemRebuyPromptMessage,
    HoldemRebuyRequest,
    HoldemShowdownMessage,
    HoldemYourTurnMessage,
    AllInResult,
    BetResult,
    CallResult,
    CheckResult,
    FoldResult,
    RaiseResult,
    ShowdownResult,
    OkResponse as HoldemOkResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    yield
    # Cancel any running agent loops
    _clue_registry.cancel_all()
    # Cancel any auto-end timers
    for task in _auto_end_timers.values():
        task.cancel()
    _auto_end_timers.clear()
    # Cancel any auto-show-card timers
    for task in _auto_show_card_timers.values():
        task.cancel()
    _auto_show_card_timers.clear()
    # Cancel any holdem agent loops
    _holdem_registry.cancel_all()
    await redis_client.aclose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Clue Game Server", lifespan=lifespan)

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

# Track agent instances and background tasks per game
_clue_registry = _LoopRegistry("Clue")
# Aliases for backward-compat within this module
_game_agents = _clue_registry.agents
_agent_tasks = _clue_registry.tasks

# Auto-end-turn timers: game_id -> asyncio.Task
_auto_end_timers: dict[str, asyncio.Task] = {}
AUTO_END_TURN_SECONDS = 7

# Auto-show-card timers: game_id -> asyncio.Task
_auto_show_card_timers: dict[str, asyncio.Task] = {}
AUTO_SHOW_CARD_SECONDS = 7

# Player types that trigger the automated agent loop
_AGENT_PLAYER_TYPES = {"agent", "llm_agent", "wanderer"}

# Agent mode: "inline" runs agents in-process (legacy), "external" relies on agent_runner
_AGENT_MODE = os.getenv("AGENT_MODE", "inline")

# Accumulate wanderer turn info so we can emit one collapsed chat line
_wanderer_turn_info: dict[tuple[str, str], WandererTurnInfo] = {}

# Track holdem agent instances and background tasks per game
_holdem_registry = _LoopRegistry("Holdem")
_holdem_agents = _holdem_registry.agents
_holdem_agent_tasks = _holdem_registry.tasks

_HOLDEM_AGENT_NAMES = [
    "Ace Ventura",
    "Bluff Daddy",
    "Chip Hazard",
    "The Dealer of Doom",
    "Lady Luck",
    "Floppy McFlopface",
    "Gambit the Unreadable",
    "High Card Houdini",
    "Jackpot Jenkins",
    "Kicker? I Hardly Know Her",
    "All-In Alan",
    "Fold McFoldington",
    "River Rat Rick",
    "Pocket Rocket Pete",
    "The Velvet Hammer",
    "Sir Bets-a-Lot",
    "Check Norris",
    "Phil Hellmouth",
    "Tilt McGee",
    "Raise the Roof Reggie",
    "No Limit Nancy",
    "Fishy McFishface",
    "The Gutshot Kid",
    "Bad Beat Barbara",
    "Stone Cold Bluffer",
]


def _new_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


_AGENT_TYPE_PREFIX = {"agent": "R_", "llm_agent": "L_", "wanderer": "W_"}


def _new_player_id(agent_type: str | None = None) -> str:
    prefix = _AGENT_TYPE_PREFIX.get(agent_type, "") if agent_type else ""
    return f"{prefix}{_new_id(8)}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player_name(state: GameState, player_id: str) -> str:
    player = next((p for p in state.players if p.id == player_id), None)
    return player.name if player else player_id


def _is_wanderer(state: GameState, player_id: str) -> bool:
    player = next((p for p in state.players if p.id == player_id), None)
    return player.type == "wanderer" if player else False


async def _broadcast_chat(game_id: str, text: str, player_id: str | None = None):
    """Broadcast a chat message to all connected players and persist it."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    message = ChatMessage(
        player_id=player_id,
        text=text,
        timestamp=timestamp,
    )
    game = ClueGame(game_id, redis_client)
    await game.add_chat_message(message)
    await manager.broadcast(
        game_id,
        ChatBroadcastMessage(player_id=player_id, text=text, timestamp=timestamp),
    )


# ---------------------------------------------------------------------------
# Auto-end-turn timer helpers
# ---------------------------------------------------------------------------


def _cancel_auto_end_timer(game_id: str):
    """Cancel any pending auto-end-turn timer for a game."""
    task = _auto_end_timers.pop(game_id, None)
    if task and not task.done():
        task.cancel()


async def _auto_end_turn_task(game_id: str, player_id: str, turn_number: int):
    """Wait AUTO_END_TURN_SECONDS then auto-end the player's turn if still valid."""
    try:
        await asyncio.sleep(AUTO_END_TURN_SECONDS)
        # Remove ourselves from the timer dict BEFORE calling _execute_action,
        # otherwise _execute_action -> _cancel_auto_end_timer will cancel this
        # running task, causing CancelledError before the end_turn completes.
        _auto_end_timers.pop(game_id, None)
        game = ClueGame(game_id, redis_client)
        state = await game.get_state()
        if (
            state
            and state.status == "playing"
            and state.whose_turn == player_id
            and state.turn_number == turn_number
        ):
            logger.info(
                "Auto-ending turn for player %s in game %s (turn %d)",
                player_id,
                game_id,
                turn_number,
            )
            await _execute_action(game_id, player_id, EndTurnAction())
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Auto-end-turn error in game %s", game_id)
    finally:
        _auto_end_timers.pop(game_id, None)


async def _maybe_start_auto_end_timer(game_id: str):
    """Check if the current player should get an auto-end-turn timer.

    Starts a timer if the player is human and their only actions are accuse + end_turn.
    """
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if not state or state.status != "playing":
        return

    pid = state.whose_turn
    # Only apply to human players
    player = next((p for p in state.players if p.id == pid), None)
    if not player or player.type in _AGENT_PLAYER_TYPES:
        return

    actions = set(game.get_available_actions(pid, state))
    if actions == {"accuse", "end_turn"}:
        _cancel_auto_end_timer(game_id)
        task = asyncio.create_task(_auto_end_turn_task(game_id, pid, state.turn_number))
        _auto_end_timers[game_id] = task
        # Notify all players about the timer
        await manager.broadcast(
            game_id,
            AutoEndTimerMessage(player_id=pid, seconds=AUTO_END_TURN_SECONDS),
        )


# ---------------------------------------------------------------------------
# Auto-show-card timer helpers
# ---------------------------------------------------------------------------


def _cancel_auto_show_card_timer(game_id: str):
    """Cancel any pending auto-show-card timer for a game."""
    task = _auto_show_card_timers.pop(game_id, None)
    if task and not task.done():
        task.cancel()


async def _auto_show_card_task(
    game_id: str, player_id: str, card: str, turn_number: int
):
    """Wait AUTO_SHOW_CARD_SECONDS then auto-show the only matching card."""
    try:
        await asyncio.sleep(AUTO_SHOW_CARD_SECONDS)
        _auto_show_card_timers.pop(game_id, None)
        game = ClueGame(game_id, redis_client)
        state = await game.get_state()
        if (
            state
            and state.status == "playing"
            and state.pending_show_card
            and state.pending_show_card.player_id == player_id
            and state.turn_number == turn_number
        ):
            logger.info(
                "Auto-showing card for player %s in game %s (turn %d)",
                player_id,
                game_id,
                turn_number,
            )
            await _execute_action(game_id, player_id, ShowCardAction(card=card))
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Auto-show-card error in game %s", game_id)
    finally:
        _auto_show_card_timers.pop(game_id, None)


async def _maybe_start_auto_show_card_timer(game_id: str):
    """Start an auto-show timer if a human player has exactly one matching card."""
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if not state or state.status != "playing":
        return
    pending = state.pending_show_card
    if not pending:
        return
    # Only apply to human players
    player = next((p for p in state.players if p.id == pending.player_id), None)
    if not player or player.type in _AGENT_PLAYER_TYPES:
        return
    if len(pending.matching_cards) == 1:
        _cancel_auto_show_card_timer(game_id)
        task = asyncio.create_task(
            _auto_show_card_task(
                game_id, pending.player_id, pending.matching_cards[0], state.turn_number
            )
        )
        _auto_show_card_timers[game_id] = task
        await manager.send_to_player(
            game_id,
            pending.player_id,
            AutoShowCardTimerMessage(
                player_id=pending.player_id, seconds=AUTO_SHOW_CARD_SECONDS
            ),
        )


# ---------------------------------------------------------------------------
# Action execution (shared by HTTP endpoint and agent loop)
# ---------------------------------------------------------------------------


async def _execute_action(
    game_id: str, player_id: str, action: GameAction
) -> ActionResult:
    """Process a game action and broadcast WebSocket messages.

    Returns the typed action result. Raises ValueError on invalid actions.
    """
    # Cancel any pending auto-end / auto-show-card timer when a player takes an action
    _cancel_auto_end_timer(game_id)
    _cancel_auto_show_card_timer(game_id)

    game = ClueGame(game_id, redis_client)
    result = await game.process_action(player_id, action)
    state = await game.get_state()

    wanderer = _is_wanderer(state, player_id)

    if isinstance(result, RollResult):
        actor_name = _player_name(state, player_id)
        reachable_targets = game.get_reachable_targets(player_id, state, result.dice)
        await manager.broadcast(
            game_id,
            DiceRolledMessage(
                player_id=player_id,
                dice=result.dice,
                last_roll=state.last_roll,
                reachable_rooms=reachable_targets.reachable_rooms,
            ),
        )
        if wanderer:
            _wanderer_turn_info[(game_id, player_id)] = WandererTurnInfo(
                dice=result.dice,
            )
        else:
            roll_parts = state.last_roll or []
            roll_text = (
                f"{result.dice} ({'+'.join(str(d) for d in roll_parts)})"
                if len(roll_parts) > 1
                else str(result.dice)
            )
            await _broadcast_chat(
                game_id,
                f"{actor_name} rolled {roll_text}.",
                player_id,
            )
        await manager.send_to_player(
            game_id,
            player_id,
            YourTurnMessage(
                available_actions=game.get_available_actions(player_id, state),
                reachable_rooms=reachable_targets.reachable_rooms,
                reachable_positions=reachable_targets.reachable_positions,
            ),
        )

    elif isinstance(result, SecretPassageResult):
        actor_name = _player_name(state, player_id)
        await manager.broadcast(
            game_id,
            PlayerMovedMessage(
                player_id=player_id,
                room=result.room,
                from_room=result.from_room,
                position=result.position,
                secret_passage=True,
            ),
        )
        await _broadcast_chat(
            game_id,
            f"{actor_name} used the secret passage from {result.from_room} to {result.room}.",
            player_id,
        )
        await manager.send_to_player(
            game_id,
            player_id,
            YourTurnMessage(
                available_actions=game.get_available_actions(player_id, state),
            ),
        )

    elif isinstance(result, MoveResult):
        actor_name = _player_name(state, player_id)
        await manager.broadcast(
            game_id,
            PlayerMovedMessage(
                player_id=player_id,
                dice=result.dice,
                room=result.room,
                position=result.position,
                path=result.path,
            ),
        )
        if wanderer:
            info = _wanderer_turn_info.get((game_id, player_id))
            if info is not None:
                info.room = result.room
        else:
            room_text = f" to {result.room}" if result.room else ""
            await _broadcast_chat(
                game_id,
                f"{actor_name} moved{room_text}.",
                player_id,
            )
        await manager.send_to_player(
            game_id,
            player_id,
            YourTurnMessage(
                available_actions=game.get_available_actions(player_id, state),
            ),
        )

    elif isinstance(result, SuggestResult):
        pending_show_by = result.pending_show_by
        moved_suspect_player = result.moved_suspect_player
        actor_name = _player_name(state, player_id)
        await manager.broadcast(
            game_id,
            SuggestionMadeMessage(
                player_id=player_id,
                suspect=result.suspect,
                weapon=result.weapon,
                room=result.room,
                pending_show_by=pending_show_by,
                moved_suspect_player=moved_suspect_player,
                player_positions=(
                    dict(state.player_positions) if moved_suspect_player else None
                ),
                weapon_positions=dict(state.weapon_positions),
                current_room=(
                    dict(state.current_room) if moved_suspect_player else None
                ),
                players_without_match=result.players_without_match,
            ),
        )
        if pending_show_by:
            pending_by_name = _player_name(state, pending_show_by)
            pending_matching = (
                state.pending_show_card.matching_cards
                if state.pending_show_card
                else []
            )
            await manager.send_to_player(
                game_id,
                pending_show_by,
                ShowCardRequestMessage(
                    suggesting_player_id=player_id,
                    suspect=result.suspect,
                    weapon=result.weapon,
                    room=result.room,
                    matching_cards=pending_matching,
                    available_actions=game.get_available_actions(
                        pending_show_by, state
                    ),
                ),
            )
            # Update suggesting player's actions (they must wait for card to be shown)
            await manager.send_to_player(
                game_id,
                player_id,
                YourTurnMessage(
                    available_actions=game.get_available_actions(player_id, state),
                ),
            )
            # Auto-show if the player has exactly one matching card
            await _maybe_start_auto_show_card_timer(game_id)
            skipped_names = [
                _player_name(state, pid)
                for pid in result.players_without_match
                if not _is_wanderer(state, pid)
            ]
            skipped_text = ""
            if skipped_names:
                skipped_text = (
                    f" {', '.join(skipped_names)} couldn't help."
                )
            chat_text = (
                f"{actor_name} suggests {result.suspect} with the {result.weapon}"
                f" in the {result.room}.{skipped_text}"
                f" {pending_by_name} must show a card."
            )
        else:
            chat_text = (
                f"{actor_name} suggests {result.suspect} with the {result.weapon}"
                f" in the {result.room}. No one could show a card."
            )
            await manager.send_to_player(
                game_id,
                player_id,
                YourTurnMessage(
                    available_actions=game.get_available_actions(player_id, state),
                ),
            )
        await _broadcast_chat(game_id, chat_text, player_id)

        # --- Piece trash talk: the suspected character reacts! ---
        suspect_character = result.suspect
        accuser_name = actor_name
        # Find the player whose character was suspected
        suspect_pid = None
        for p in state.players:
            if p.character == suspect_character:
                suspect_pid = p.id
                break

        # "suspected" reaction — the named character claps back
        suspected_msg = generate_character_chat(
            suspect_character,
            "suspected",
            {
                "accuser": accuser_name,
                "weapon": result.weapon,
                "room": result.room,
            },
        )
        if suspected_msg:
            await _broadcast_chat(
                game_id,
                f"{suspect_character}: {suspected_msg}",
                suspect_pid,
            )

    elif isinstance(result, ShowCardResult):
        shown_by_name = _player_name(state, player_id)
        shown_to_name = _player_name(state, result.suggesting_player_id)
        await manager.send_to_player(
            game_id,
            result.suggesting_player_id,
            CardShownMessage(
                shown_by=player_id,
                card=result.card,
                suspect=result.suspect,
                weapon=result.weapon,
                room=result.room,
                available_actions=game.get_available_actions(
                    result.suggesting_player_id, state
                ),
            ),
        )
        await manager.broadcast(
            game_id,
            CardShownPublicMessage(
                shown_by=player_id,
                shown_to=result.suggesting_player_id,
                suspect=result.suspect,
                weapon=result.weapon,
                room=result.room,
            ),
        )
        await _broadcast_chat(
            game_id,
            f"{shown_by_name} showed a card to {shown_to_name}.",
            player_id,
        )
        # Send a private chat message to the recipient with the actual card name
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        await manager.send_to_player(
            game_id,
            result.suggesting_player_id,
            ChatBroadcastMessage(
                player_id=player_id,
                text=f"{shown_by_name} showed you: {result.card}",
                timestamp=timestamp,
            ),
        )
        # Notify the suggesting player it's still their turn so external
        # agents (WebSocket-driven) know to take their next action.
        suggesting_pid = result.suggesting_player_id
        await manager.send_to_player(
            game_id,
            suggesting_pid,
            YourTurnMessage(
                available_actions=game.get_available_actions(suggesting_pid, state),
            ),
        )

    elif isinstance(result, AccuseResult):
        actor_name = _player_name(state, player_id)
        assert isinstance(action, AccuseAction)
        if result.correct:
            await manager.broadcast(
                game_id,
                GameOverMessage(
                    player_id=player_id,
                    correct=True,
                    winner=result.winner,
                    solution=result.solution,
                ),
            )
            chat_text = (
                f"{actor_name} accuses {action.suspect} with the"
                f" {action.weapon} in the {action.room}."
                f" Correct! {actor_name} wins!"
            )
        else:
            # Re-fetch state — _handle_accuse advanced the turn and may
            # have moved the eliminated player off a door square.
            state = await game.get_state()
            if state.status == "finished":
                await manager.broadcast(
                    game_id,
                    GameOverMessage(
                        player_id=player_id,
                        correct=False,
                        winner=state.winner,
                        solution=result.solution,
                    ),
                )
            else:
                await manager.broadcast(
                    game_id,
                    AccusationMadeMessage(
                        player_id=player_id,
                        correct=False,
                    ),
                )
                # Broadcast the turn change so all clients update
                await manager.broadcast(
                    game_id,
                    GameStateUpdateMessage(
                        whose_turn=state.whose_turn,
                        turn_number=state.turn_number,
                        dice_rolled=state.dice_rolled,
                        moved=state.moved,
                        last_roll=state.last_roll,
                        suggestions_this_turn=list(state.suggestions_this_turn),
                        pending_show_card=state.pending_show_card,
                        player_positions=state.player_positions,
                    ),
                )
                # Notify the next player it's their turn
                next_pid = result.next_player_id
                if next_pid:
                    await manager.send_to_player(
                        game_id,
                        next_pid,
                        YourTurnMessage(
                            available_actions=game.get_available_actions(
                                next_pid, state
                            ),
                        ),
                    )
            chat_text = (
                f"{actor_name} accuses {action.suspect} with the"
                f" {action.weapon} in the {action.room}."
                f" Wrong! {actor_name} is eliminated."
            )
        await _broadcast_chat(game_id, chat_text, player_id)

    elif isinstance(result, EndTurnResult):
        next_pid = result.next_player_id
        actor_name = _player_name(state, player_id)
        next_name = _player_name(state, next_pid)
        await manager.broadcast(
            game_id,
            GameStateUpdateMessage(
                whose_turn=state.whose_turn,
                turn_number=state.turn_number,
                dice_rolled=state.dice_rolled,
                moved=state.moved,
                last_roll=state.last_roll,
                suggestions_this_turn=list(state.suggestions_this_turn),
                pending_show_card=state.pending_show_card,
                player_positions=state.player_positions,
            ),
        )
        await manager.send_to_player(
            game_id,
            next_pid,
            YourTurnMessage(
                available_actions=game.get_available_actions(next_pid, state),
            ),
        )
        if wanderer:
            # Emit one collapsed line for the wanderer's entire turn
            info = _wanderer_turn_info.pop((game_id, player_id), None)
            dice = info.dice if info else "?"
            room = info.room if info else None
            room_text = f" to the {room}" if room else ""
            await _broadcast_chat(
                game_id,
                f"{actor_name} rolled a {dice} and moved{room_text}.",
                player_id,
            )
        else:
            await _broadcast_chat(
                game_id,
                f"{actor_name} ended their turn. It is now {next_name}'s turn.",
                player_id,
            )

    # Update agent observations for any active agents in this game
    _update_agent_observations(game_id, player_id, action, result)

    # Publish observation events to Redis for external agent runners
    await _publish_agent_event(game_id, player_id, action, result)

    # Check if the current player should get an auto-end-turn timer.
    # Skip when the card-shown banner will be visible to the player — the
    # frontend will call /ack_card_shown after the player dismisses it.
    _banner_visible = isinstance(result, ShowCardResult) or (
        isinstance(result, SuggestResult) and result.pending_show_by is None
    )
    if not _banner_visible:
        await _maybe_start_auto_end_timer(game_id)

    return result


def _update_agent_observations(
    game_id: str, player_id: str, action: GameAction, result: ActionResult
):
    """Update agent observations based on action results."""
    agents = _game_agents.get(game_id)
    if not agents:
        return

    if isinstance(result, ShowCardResult):
        # The suggesting player learns which card was shown
        suggesting_pid = result.suggesting_player_id
        card = result.card
        if suggesting_pid and suggesting_pid in agents and card:
            agents[suggesting_pid].observe_shown_card(card, shown_by=player_id)

        # All OTHER agents observe that a card was shown (they don't see which)
        # and can try to infer it from their own knowledge.
        for aid, agent in agents.items():
            if aid not in (suggesting_pid, player_id):
                agent.observe_card_shown_to_other(
                    shown_by=player_id,
                    shown_to=suggesting_pid,
                    suspect=result.suspect,
                    weapon=result.weapon,
                    room=result.room,
                )

    elif isinstance(result, SuggestResult) and isinstance(action, SuggestAction):
        # Notify ALL agents about the suggestion (for inference tracking)
        shown_by = result.pending_show_by
        players_without = result.players_without_match
        for aid, agent in agents.items():
            agent.observe_suggestion(
                suggesting_player_id=player_id,
                suspect=action.suspect,
                weapon=action.weapon,
                room=action.room,
                shown_by=shown_by,
                players_without_match=players_without,
            )

        # If no one could show a card, the suggesting agent also notes this
        if shown_by is None and player_id in agents:
            agents[player_id].observe_suggestion_no_show(
                action.suspect,
                action.weapon,
                action.room,
            )


# ---------------------------------------------------------------------------
# Agent observation events (Redis-backed for external agent runner)
# ---------------------------------------------------------------------------


async def _publish_agent_event(
    game_id: str, player_id: str, action: GameAction, result: ActionResult
):
    """Publish observation events to Redis for external agent runners."""
    if not redis_client:
        return

    event = None

    if isinstance(result, ShowCardResult):
        event = ShowCardAgentEvent(
            shown_by=player_id,
            shown_to=result.suggesting_player_id,
            card=result.card,
            suspect=result.suspect,
            weapon=result.weapon,
            room=result.room,
        )
    elif isinstance(result, SuggestResult) and isinstance(action, SuggestAction):
        event = SuggestAgentEvent(
            suggesting_player_id=player_id,
            suspect=action.suspect,
            weapon=action.weapon,
            room=action.room,
            shown_by=result.pending_show_by,
            players_without_match=result.players_without_match,
        )

    if event:
        key = f"game:{game_id}:agent_events"
        await redis_client.rpush(key, event.model_dump_json())
        await redis_client.expire(key, 86400)


# ---------------------------------------------------------------------------
# Agent debug broadcast
# ---------------------------------------------------------------------------


async def _broadcast_agent_debug(
    game_id: str,
    agent: "BaseAgent",
    status: str,
    action_description: str = "",
    decided_action: dict | None = None,
    game_state=None,
):
    """Broadcast agent debug info to all WebSocket clients (visible to observers/agents)."""
    debug_info = agent.get_debug_info(
        status=status,
        action_description=action_description,
        decided_action=decided_action,
        game_state=game_state,
    )
    debug_info = await _attach_llm_memory(game_id, debug_info)
    await manager.broadcast(game_id, AgentDebugMessage(**debug_info))


async def _get_llm_memory_by_player(
    game_id: str, player_ids: set[str]
) -> dict[str, list[str]]:
    """Load persisted LLM memory entries for the given players."""
    out: dict[str, list[str]] = {}
    for player_id in sorted(player_ids):
        key = f"game:{game_id}:memory:{player_id}"
        out[player_id] = await redis_client.lrange(key, 0, -1)
    return out


async def _attach_llm_memory(
    game_id: str,
    debug_info: dict,
    memory_by_player: dict[str, list[str]] | None = None,
) -> dict:
    """Ensure LLM debug payload includes persisted memory entries."""
    player_id = debug_info.get("player_id")
    if not player_id:
        return debug_info

    if memory_by_player is not None and player_id in memory_by_player:
        debug_info["memory"] = memory_by_player[player_id]
        return debug_info

    if debug_info.get("agent_type") == "llm":
        key = f"game:{game_id}:memory:{player_id}"
        debug_info["memory"] = await redis_client.lrange(key, 0, -1)

    return debug_info


# ---------------------------------------------------------------------------
# Agent background loop (inline mode)
# ---------------------------------------------------------------------------


def _on_agent_loop_done(game_id: str, task: asyncio.Task) -> None:
    """Callback invoked when an inline agent-loop task finishes.

    If the task ended for any reason other than explicit cancellation,
    schedule a watchdog check so the loop can be restarted when the
    game is still active.
    """
    if task.cancelled():
        return
    task.get_loop().create_task(_agent_loop_watchdog(game_id))


# Wire up the registry watchdog so AgentRunner.make_done_callback() works
_clue_registry.watchdog = lambda game_id: _agent_loop_watchdog(game_id)


async def _agent_loop_watchdog(game_id: str) -> None:
    """Restart the inline agent loop for *game_id* if the game is still active.

    Called automatically via :func:`_on_agent_loop_done` whenever an agent
    task exits.  Does nothing if the game has already ended or if a fresh
    task is already running.
    """
    # Bail out if a fresh task was already started (race guard).
    if _clue_registry.is_running(game_id):
        return

    try:
        game = ClueGame(game_id, redis_client)
        state = await game.get_state()
        if not state or state.status != "playing":
            return

        config_raw = await redis_client.get(f"game:{game_id}:agent_config")
        if not config_raw:
            return

        config = json.loads(config_raw)
        agents: dict[str, BaseAgent] = {}
        for pid, info in config.items():
            ptype = info.get("type", "agent")
            character = info.get("character", "")
            cards = info.get("cards", [])

            if ptype == "llm_agent":
                agent: BaseAgent = LLMAgent(
                    player_id=pid,
                    character=character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                )
                await agent.load_memory()
            elif ptype == "wanderer":
                agent = WandererAgent(
                    player_id=pid,
                    character=character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                )
            else:
                agent = RandomAgent(
                    player_id=pid,
                    character=character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                )

            # Restore accumulated knowledge (seen cards, inferences, etc.)
            await agent.load_knowledge()

            # Replay the wanderer seed so the restarted agent has the same
            # initial card knowledge as when it was first created (only if
            # no persisted knowledge was loaded).
            seed = info.get("wanderer_seed")
            if seed and ptype == "wanderer" and len(agent.seen_cards) <= len(cards):
                agent.observe_shown_card(seed["card"], shown_by=seed["shown_by"])

            agents[pid] = agent

        if not agents:
            return

        player_names = {p.id: p.name for p in state.players}
        for a in agents.values():
            a.player_names = player_names

        logger.warning(
            "Restarting agent loop for game %s with %d agent(s) after unexpected exit",
            game_id,
            len(agents),
        )
        runner = _make_clue_runner(game_id, agents)
        task = asyncio.create_task(runner.run())
        task.add_done_callback(runner.make_done_callback())
        _clue_registry.register(game_id, agents, task)
    except Exception:
        logger.exception("Error in agent loop watchdog for game %s", game_id)


def _make_clue_runner(game_id: str, agents: dict[str, BaseAgent]) -> ClueAgentRunner:
    """Create a ClueAgentRunner wired to this module's helpers."""
    game = ClueGame(game_id, redis_client)
    return ClueAgentRunner(
        game_id,
        agents,
        get_state=game.get_state,
        get_player_state=game.get_player_state,
        execute_action=_execute_action,
        broadcast_agent_debug=_broadcast_agent_debug,
        broadcast_chat=_broadcast_chat,
        player_name=_player_name,
        registry=_clue_registry,
    )


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/api/clue/games", status_code=201, response_model=CreateGameResponse)
async def create_game():
    game_id = _new_id(6)
    game = ClueGame(game_id, redis_client)
    state = await game.create()
    return CreateGameResponse(game_id=game_id, status=state.status)


@app.get("/api/healthz")
async def healthz():
    return OkResponse()


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@app.get("/api/admin/games")
async def admin_list_games():
    """Return summary info for every active game (Clue + Hold'em)."""
    games: list[dict] = []

    # Scan for Clue games (keys like "game:{id}")
    async for key in redis_client.scan_iter(match="game:*", count=200):
        key_str = key if isinstance(key, str) else key.decode()
        # Skip sub-keys (game:{id}:solution, etc.)
        parts = key_str.split(":")
        if len(parts) != 2:
            continue
        game_id = parts[1]
        raw = await redis_client.get(key_str)
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        games.append(
            {
                "game_id": game_id,
                "game_type": "clue",
                "status": state.get("status", "unknown"),
                "players": [
                    {
                        "name": p.get("name", "?"),
                        "type": p.get("type", "human"),
                        "character": p.get("character"),
                    }
                    for p in state.get("players", [])
                ],
                "turn_number": state.get("turn_number", 0),
                "whose_turn": state.get("whose_turn"),
                "winner": state.get("winner"),
            }
        )

    # Scan for Hold'em games (keys like "holdem:{id}")
    async for key in redis_client.scan_iter(match="holdem:*", count=200):
        key_str = key if isinstance(key, str) else key.decode()
        parts = key_str.split(":")
        if len(parts) != 2:
            continue
        game_id = parts[1]
        raw = await redis_client.get(key_str)
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        games.append(
            {
                "game_id": game_id,
                "game_type": "holdem",
                "status": state.get("status", "unknown"),
                "players": [
                    {
                        "name": p.get("name", "?"),
                        "type": p.get("type", "human"),
                        "chips": p.get("chips"),
                    }
                    for p in state.get("players", [])
                ],
                "hand_number": state.get("hand_number", 0),
                "pot": state.get("pot", 0),
                "whose_turn": state.get("whose_turn"),
                "winner": state.get("winner"),
            }
        )

    # Sort: playing first, then waiting, then finished
    status_order = {"playing": 0, "waiting": 1, "finished": 2}
    games.sort(key=lambda g: (status_order.get(g["status"], 3), g["game_id"]))
    return {"games": games}


@app.get("/api/admin/games/{game_id}")
async def admin_get_game(game_id: str):
    """Return full raw state for a specific game (admin view)."""
    # Try Clue first
    raw = await redis_client.get(f"game:{game_id}")
    if raw:
        state = json.loads(raw)
        # Fetch the log
        log_entries = await redis_client.lrange(f"game:{game_id}:log", 0, -1)
        log = [json.loads(e) for e in log_entries] if log_entries else []
        return {"game_type": "clue", "state": state, "log": log}

    # Try Hold'em
    raw = await redis_client.get(f"holdem:{game_id}")
    if raw:
        state = json.loads(raw)
        log_entries = await redis_client.lrange(f"holdem:{game_id}:log", 0, -1)
        log = [json.loads(e) for e in log_entries] if log_entries else []
        return {"game_type": "holdem", "state": state, "log": log}

    raise HTTPException(status_code=404, detail="Game not found")


@app.get("/api/clue/board")
async def get_board():
    """Return static board layout data (doors, rooms, starts, passages)."""
    return {
        "doors": {
            f"{r},{c}": {"room": room.value, "direction": direction}
            for (r, c), (room, direction) in DOORS.items()
        },
        "rooms": {
            room.value: {
                "bounds": {"c1": c1, "r1": r1, "c2": c2, "r2": r2},
                "center": ROOM_CENTERS[room.value],
            }
            for room, (c1, r1, c2, r2) in ROOM_BOUNDS.items()
        },
        "starts": {f"{r},{c}": name for name, (r, c) in START_POSITIONS.items()},
        "secret_passages": {
            src.value: dst.value for src, dst in SECRET_PASSAGES.items()
        },
    }


@app.get("/api/clue/games/{game_id}")
async def get_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state.model_dump()


@app.get("/api/clue/games/{game_id}/debug")
async def get_game_debug(
    game_id: str,
    trace_limit: int = 500,
    log_offset: int = 0,
    chat_offset: int = 0,
    trace_offset: int = 0,
    events_offset: int = 0,
):
    """Return comprehensive debug data: game state, log, chat, agent debug,
    agent trace, LLM memory, solution, and cards for every player.

    Offset params let clients fetch only new entries since their last request.
    """
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Gather all data concurrently
    log_key = f"game:{game_id}:log"
    chat_key = f"game:{game_id}:chat"
    trace_key = f"game:{game_id}:agent_trace"
    events_key = f"game:{game_id}:agent_events"
    solution_key = f"game:{game_id}:solution"

    (
        log_raw,
        chat_raw,
        trace_raw,
        trace_total,
        events_raw,
        solution_raw,
    ) = await asyncio.gather(
        redis_client.lrange(log_key, log_offset, -1),
        redis_client.lrange(chat_key, chat_offset, -1),
        redis_client.lrange(trace_key, trace_offset, trace_offset + trace_limit - 1),
        redis_client.llen(trace_key),
        redis_client.lrange(events_key, events_offset, -1),
        redis_client.get(solution_key),
    )

    # Parse all JSON entries
    game_log = [json.loads(e) for e in log_raw]
    chat = [json.loads(e) for e in chat_raw]
    trace_entries = [json.loads(e) for e in trace_raw]
    agent_events = [json.loads(e) for e in events_raw]
    solution = json.loads(solution_raw) if solution_raw else None

    # Collect player cards
    player_ids = [p.id for p in state.players if p.id]
    card_keys = [f"game:{game_id}:cards:{pid}" for pid in player_ids]
    card_raws = await asyncio.gather(*[redis_client.get(k) for k in card_keys])
    player_cards = {}
    for pid, raw in zip(player_ids, card_raws):
        player_cards[pid] = json.loads(raw) if raw else []

    # Collect LLM memory for all players
    memory_keys = [f"game:{game_id}:memory:{pid}" for pid in player_ids]
    memory_raws = await asyncio.gather(
        *[redis_client.lrange(k, 0, -1) for k in memory_keys]
    )
    player_memory = {}
    for pid, entries in zip(player_ids, memory_raws):
        if entries:
            player_memory[pid] = [
                e.decode() if isinstance(e, bytes) else e for e in entries
            ]

    # Get agent debug info (reuse existing logic)
    agent_debug_resp = await get_agent_debug(game_id)

    # Group trace entries by player_id
    trace_by_player: dict[str, list] = {}
    for entry in trace_entries:
        pid = entry.get("player_id", "_unknown")
        trace_by_player.setdefault(pid, []).append(entry)

    return {
        "game_id": game_id,
        "state": state.model_dump(),
        "solution": solution,
        "player_cards": player_cards,
        "game_log": game_log,
        "chat": chat,
        "agent_debug": agent_debug_resp.get("agents", []),
        "agent_events": agent_events,
        "agent_trace": {
            "total": trace_total,
            "entries": trace_entries,
            "by_player": trace_by_player,
        },
        "player_memory": player_memory,
    }


@app.get("/api/clue/games/{game_id}/player/{player_id}")
async def get_player_state(game_id: str, player_id: str):
    game = ClueGame(game_id, redis_client)
    player_state = await game.get_player_state(player_id)
    if player_state is None:
        raise HTTPException(status_code=404, detail="Game or player not found")
    return player_state.model_dump()


@app.get("/api/clue/games/{game_id}/agent_debug")
async def get_agent_debug(game_id: str):
    """Return current debug info for all players (agents and humans) in a game."""
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()

    result = []
    llm_player_ids: set[str] = set()
    if state:
        llm_player_ids = {p.id for p in state.players if p.type == "llm_agent" and p.id}
    memory_by_player = await _get_llm_memory_by_player(game_id, llm_player_ids)

    # Include in-memory agents with game state
    agents = _game_agents.get(game_id, {})
    if agents:
        for pid, agent in agents.items():
            info = agent.get_debug_info(status="idle", game_state=state)
            result.append(await _attach_llm_memory(game_id, info, memory_by_player))

    # Fall back to Redis-stored debug data (external mode) if no in-memory agents
    if not agents:
        raw = await redis_client.get(f"game:{game_id}:agent_debug")
        if raw:
            import json as _json

            debug_map = _json.loads(raw)
            for info in debug_map.values():
                result.append(await _attach_llm_memory(game_id, info, memory_by_player))

    # Ensure non-human players appear even before first debug event (external mode)
    if state:
        agent_pids = {r["player_id"] for r in result}
        for player in state.players:
            if player.id in agent_pids:
                continue

            if player.type in {"agent", "llm_agent", "wanderer"}:
                agent_type = {
                    "agent": "random",
                    "llm_agent": "llm",
                    "wanderer": "wanderer",
                }.get(player.type, player.type)
                result.append(
                    {
                        "player_id": player.id,
                        "agent_type": agent_type,
                        "character": player.character,
                        "status": "idle",
                        "memory": memory_by_player.get(player.id, []),
                        "position": state.player_positions.get(player.id),
                        "room": state.current_room.get(player.id),
                        "reachable_rooms": None,
                    }
                )
                continue

            result.append(
                {
                    "player_id": player.id,
                    "agent_type": "human",
                    "character": player.character,
                    "status": "idle",
                    "position": state.player_positions.get(player.id),
                    "room": state.current_room.get(player.id),
                    "reachable_rooms": None,
                }
            )

    return {"agents": result}


@app.post("/api/clue/games/{game_id}/agent_debug")
async def post_agent_debug(game_id: str, request: Request):
    """Receive agent debug info from external agent runner, store and broadcast."""
    data = await request.json()
    player_id = data.get("player_id")
    if not player_id:
        raise HTTPException(status_code=400, detail="player_id required")

    data = await _attach_llm_memory(game_id, data)

    # Store in Redis (merge into per-game debug map)
    import json as _json

    key = f"game:{game_id}:agent_debug"
    raw = await redis_client.get(key)
    debug_map = _json.loads(raw) if raw else {}
    debug_map[player_id] = data
    await redis_client.set(key, _json.dumps(debug_map), ex=86400)

    # Broadcast to WebSocket clients
    await manager.broadcast(game_id, AgentDebugMessage(**data))


@app.get("/api/clue/games/{game_id}/agent_trace")
async def get_agent_trace(game_id: str, limit: int = 200, offset: int = 0):
    """Return agent trace entries from Redis for debugging."""
    key = f"game:{game_id}:agent_trace"
    entries = await redis_client.lrange(key, offset, offset + limit - 1)
    total = await redis_client.llen(key)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [json.loads(e) for e in entries],
    }


@app.put("/api/clue/games/{game_id}/agent_trace")
async def toggle_agent_trace(game_id: str, request: Request):
    """Enable or disable agent tracing for a specific game."""
    data = await request.json()
    enabled = bool(data.get("enabled", False))
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    state.agent_trace_enabled = enabled
    await game._save_state(state)
    return {"agent_trace_enabled": enabled}


@app.post("/api/clue/games/{game_id}/join")
async def join_game(game_id: str, req: JoinRequest):
    game = ClueGame(game_id, redis_client)
    player_id = _new_player_id()
    try:
        player = await game.add_player(player_id, req.player_name, req.player_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = await game.get_state()
    await manager.broadcast(
        game_id,
        PlayerJoinedMessage(player=player, players=list(state.players)),
    )
    await _broadcast_chat(game_id, f"{player.name} joined the game.")
    return JoinGameResponse(player_id=player_id, player=player)


@app.post("/api/clue/games/{game_id}/add_agent")
async def add_agent(game_id: str, req: AddAgentRequest | None = None):
    """Add an AI agent to a game in the waiting room."""
    agent_type = req.agent_type if req else "agent"
    inference_level = req.inference_level if req else "standard"
    if agent_type not in _AGENT_PLAYER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid agent type")
    from app.games.clue.agents import INFERENCE_LEVELS
    if inference_level not in INFERENCE_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid inference_level. Must be one of: {INFERENCE_LEVELS}")

    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    player_id = _new_player_id(agent_type=agent_type)

    try:
        # Pass None as the name; add_player assigns the character name for non-human types
        player = await game.add_player(player_id, None, agent_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Store inference_level preference for this agent (read at game start)
    await redis_client.set(
        f"game:{game_id}:agent_inference:{player_id}",
        inference_level,
        ex=86400,
    )

    state = await game.get_state()
    await manager.broadcast(
        game_id,
        PlayerJoinedMessage(player=player, players=list(state.players)),
    )
    await _broadcast_chat(game_id, f"{player.name} joined the game.")
    return JoinGameResponse(player_id=player_id, player=player)


@app.post("/api/clue/games/{game_id}/start")
async def start_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    try:
        state = await game.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Notify all players
    for player in state.players:
        pid = player.id
        cards = await game._load_player_cards(pid)
        await manager.send_to_player(
            game_id,
            pid,
            GameStartedMessage(
                your_cards=cards,
                whose_turn=state.whose_turn,
                available_actions=game.get_available_actions(pid, state),
            ),
        )

    await manager.broadcast(game_id, GameStartedMessage(state=state))
    first_player_name = _player_name(state, state.whose_turn)
    await _broadcast_chat(game_id, f"Game started! {first_player_name} goes first.")

    # Start background agent loop for any agent players (including wanderers)
    agent_players = [p for p in state.players if p.type in _AGENT_PLAYER_TYPES]
    if agent_players:
        # Build agent instances first so we can do wanderer seeding before
        # persisting the config (the seed must be stored alongside the config
        # so watchdog restarts reproduce the same starting knowledge).
        agents: dict[str, BaseAgent] = {}
        agent_cards: dict[str, list[str]] = {}
        agent_inference_levels: dict[str, str] = {}
        for player in agent_players:
            pid = player.id
            ptype = player.type
            cards = await game._load_player_cards(pid)
            agent_cards[pid] = cards
            # Read per-agent inference level (default: standard)
            inference_raw = await redis_client.get(
                f"game:{game_id}:agent_inference:{pid}"
            )
            inf_level = inference_raw if inference_raw else "standard"
            agent_inference_levels[pid] = inf_level
            if ptype == "llm_agent":
                agent: BaseAgent = LLMAgent(
                    player_id=pid,
                    character=player.character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                    inference_level=inf_level,
                )
                await agent.load_memory()
            elif ptype == "wanderer":
                agent = WandererAgent(
                    player_id=pid,
                    character=player.character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                    inference_level=inf_level,
                )
            else:
                agent = RandomAgent(
                    player_id=pid,
                    character=player.character,
                    cards=cards,
                    redis_client=redis_client,
                    game_id=game_id,
                    inference_level=inf_level,
                )
            agents[pid] = agent
            logger.info(
                "Created %s agent for player %s (%s) in game %s",
                ptype,
                pid,
                player.character,
                game_id,
            )

        # Show one random card from a real player's hand to each wanderer.
        # Record the seed so the config can reproduce this on restart.
        wanderer_seeds: dict[str, WandererSeed] = {}
        real_agents = {
            pid: a
            for pid, a in agents.items()
            if a.agent_type != "wanderer" and a.own_cards
        }
        if real_agents:
            for pid, a in agents.items():
                if a.agent_type == "wanderer":
                    donor_pid, donor = random.choice(list(real_agents.items()))
                    card = random.choice(list(donor.own_cards))
                    a.observe_shown_card(card, shown_by=donor_pid)
                    wanderer_seeds[pid] = WandererSeed(card=card, shown_by=donor_pid)

        # Persist agent config (with wanderer seeds) so external runners and
        # the inline watchdog can reconstruct agents faithfully on restart.
        agent_config: dict[str, AgentPlayerConfig] = {}
        for player in agent_players:
            pid = player.id
            agent_config[pid] = AgentPlayerConfig(
                type=player.type,
                character=player.character,
                cards=agent_cards[pid],
                wanderer_seed=wanderer_seeds.get(pid),
                inference_level=agent_inference_levels.get(pid, "standard"),
            )
        await redis_client.set(
            f"game:{game_id}:agent_config",
            json.dumps({k: v.model_dump() for k, v in agent_config.items()}),
            ex=86400,
        )

        if _AGENT_MODE == "inline":
            # Build player name map and share with all agents
            player_names = {p.id: p.name for p in state.players}
            for a in agents.values():
                a.player_names = player_names

            runner = _make_clue_runner(game_id, agents)
            task = asyncio.create_task(runner.run())
            task.add_done_callback(runner.make_done_callback())
            _clue_registry.register(game_id, agents, task)
        else:
            logger.info(
                "Agent mode is '%s' — %d agent(s) in game %s will be managed externally",
                _AGENT_MODE,
                len(agent_players),
                game_id,
            )

    return state.model_dump()


@app.post("/api/clue/games/{game_id}/action")
async def submit_action(game_id: str, req: ActionRequest):
    try:
        result = await _execute_action(game_id, req.player_id, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Include current available actions so the frontend can stay in sync
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    response = result.model_dump()
    if state:
        response["available_actions"] = game.get_available_actions(req.player_id, state)
    return response


@app.post("/api/clue/games/{game_id}/ack_card_shown")
async def ack_card_shown(game_id: str, req: dict):
    """Called when a player dismisses the card-shown banner.

    Starts the auto-end-turn timer now that the player can see their actions.
    """
    player_id = req.get("player_id")
    if not player_id:
        raise HTTPException(status_code=400, detail="player_id required")
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if not state or state.status != "playing":
        return OkResponse()
    # Only start the timer if it's actually this player's turn
    if state.whose_turn == player_id:
        await _maybe_start_auto_end_timer(game_id)
    return OkResponse()


# ---------------------------------------------------------------------------
# Detective notes
# ---------------------------------------------------------------------------


@app.put("/api/clue/games/{game_id}/notes")
async def save_notes(game_id: str, req: SaveNotesRequest):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    await game.save_detective_notes(req.player_id, req.notes)
    return OkResponse()


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/api/ws/clue/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    await manager.connect(game_id, player_id, websocket)
    game = ClueGame(game_id, redis_client)
    try:
        player_state = await game.get_player_state(player_id)
        if player_state:
            await manager.send_to_player(
                game_id,
                player_id,
                GameStateUpdateMessage(state=player_state),
            )
            # Resend show_card_request if there's a pending one for this player
            pending = player_state.pending_show_card
            if pending and pending.player_id == player_id:
                await manager.send_to_player(
                    game_id,
                    player_id,
                    ShowCardRequestMessage(
                        suggesting_player_id=pending.suggesting_player_id,
                        suspect=pending.suspect,
                        weapon=pending.weapon,
                        room=pending.room,
                        matching_cards=pending.matching_cards,
                        available_actions=player_state.available_actions,
                    ),
                )
            # Notify the player if it's their turn (helps agents and reconnecting humans)
            if (
                player_state.whose_turn == player_id
                and player_state.available_actions
                and not (pending and pending.player_id == player_id)
            ):
                await manager.send_to_player(
                    game_id,
                    player_id,
                    YourTurnMessage(
                        available_actions=player_state.available_actions,
                    ),
                )
        while True:
            data = await websocket.receive_text()
            # Clients can send ping/keep-alive or chat messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_to_player(game_id, player_id, PongMessage())
                elif msg.get("type") == "chat":
                    text = str(msg.get("text", "")).strip()
                    if text:
                        g = ClueGame(game_id, redis_client)
                        s = await g.get_state()
                        name = _player_name(s, player_id) if s else player_id
                        await _broadcast_chat(game_id, f"{name}: {text}", player_id)
            except Exception:
                logger.debug(
                    "Ignoring non-JSON WebSocket message from %s/%s", game_id, player_id
                )
    except WebSocketDisconnect:
        manager.disconnect(game_id, player_id, websocket)


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.get("/api/clue/games/{game_id}/chat")
async def get_chat(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    messages = await game.get_chat_messages()
    return ChatMessagesResponse(messages=messages)


@app.post("/api/clue/games/{game_id}/chat")
async def send_chat(game_id: str, req: ChatRequest):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    text = str(req.text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty")
    name = _player_name(state, req.player_id)
    await _broadcast_chat(game_id, f"{name}: {text}", req.player_id)
    return OkResponse()


# ===========================================================================
# TEXAS HOLD'EM ENDPOINTS
# ===========================================================================


def _holdem_player_name(state, player_id: str) -> str:
    player = next((p for p in state.players if p.id == player_id), None)
    return player.name if player else player_id


def _format_currency(amount: int | float) -> str:
    """Format a chip amount (in cents) as dollars and cents (e.g. $1,000.00)."""
    return f"${amount / 100:,.2f}"


async def _holdem_broadcast_chat(game_id: str, text: str, player_id: str | None = None):
    """Broadcast a chat message for a Hold'em game."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    message = HoldemChatMessage(player_id=player_id, text=text, timestamp=timestamp)
    game = HoldemGame(game_id, redis_client)
    await game.add_chat_message(message)
    await manager.broadcast(
        game_id,
        HoldemChatBroadcastMessage(player_id=player_id, text=text, timestamp=timestamp),
    )


@app.post("/api/holdem/games", status_code=201, response_model=HoldemCreateGameResponse)
async def holdem_create_game(req: HoldemCreateGameRequest | None = None):
    game_id = _new_id(6)
    game = HoldemGame(game_id, redis_client)
    buy_in = req.buy_in if req else 2000
    allow_rebuys = req.allow_rebuys if req else False
    state = await game.create(buy_in=buy_in, allow_rebuys=allow_rebuys)
    return HoldemCreateGameResponse(
        game_id=game_id,
        status=state.status,
        buy_in=state.buy_in,
        allow_rebuys=state.allow_rebuys,
    )


@app.get("/api/holdem/games/{game_id}")
async def holdem_get_game(game_id: str):
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state.model_dump()


@app.get("/api/holdem/games/{game_id}/player/{player_id}")
async def holdem_get_player_state(game_id: str, player_id: str):
    game = HoldemGame(game_id, redis_client)
    ps = await game.get_player_state(player_id)
    if ps is None:
        raise HTTPException(status_code=404, detail="Game or player not found")
    return ps.model_dump()


@app.post("/api/holdem/games/{game_id}/join")
async def holdem_join_game(game_id: str, req: HoldemJoinRequest):
    game = HoldemGame(game_id, redis_client)
    player_id = _new_player_id()
    try:
        player = await game.add_player(player_id, req.player_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    state = await game.get_state()
    await manager.broadcast(
        game_id,
        HoldemPlayerJoinedMessage(player=player, players=list(state.players)),
    )
    await _holdem_broadcast_chat(game_id, f"{player.name} joined the table.")
    return HoldemJoinGameResponse(player_id=player_id, player=player)


@app.post("/api/holdem/games/{game_id}/start")
async def holdem_start_game(game_id: str):
    game = HoldemGame(game_id, redis_client)
    try:
        state = await game.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Notify all players
    for player in state.players:
        pid = player.id
        cards = await game._load_player_cards(pid)
        await manager.send_to_player(
            game_id,
            pid,
            HoldemGameStartedMessage(
                your_cards=cards,
                whose_turn=state.whose_turn,
                available_actions=game.get_available_actions(pid, state),
            ),
        )

    await manager.broadcast(game_id, HoldemGameStartedMessage(state=state))
    await _holdem_broadcast_chat(game_id, "Game started! Shuffling and dealing...")

    # Notify first player it's their turn
    if state.whose_turn:
        await manager.send_to_player(
            game_id,
            state.whose_turn,
            HoldemYourTurnMessage(
                available_actions=game.get_available_actions(state.whose_turn, state),
            ),
        )

    # Create agent instances and launch loop for agent players
    agent_players = [p for p in state.players if p.player_type == "holdem_agent"]
    if agent_players:
        import json as _json

        agents: dict[str, HoldemAgent] = {}
        for player in agent_players:
            # Load per-agent config from Redis (set during add_agent)
            config_raw = await redis_client.get(
                f"holdem:{game_id}:agent_config:{player.id}"
            )
            config = _json.loads(config_raw) if config_raw else {}
            agents[player.id] = HoldemAgent(
                player_id=player.id,
                name=player.name,
                aggression=config.get("aggression", 0.5),
                tightness=config.get("tightness", 0.5),
                bluff_frequency=config.get("bluff_frequency", 0.15),
                slowplay_frequency=config.get("slowplay_frequency", 0.1),
                chat_frequency=config.get("chat_frequency", 0.3),
                personality=config.get("personality"),
            )
            logger.info(
                "Created holdem agent for player %s (%s) in game %s",
                player.id,
                player.name,
                game_id,
            )
        runner = _make_holdem_runner(game_id, agents)
        task = asyncio.create_task(runner.run())
        _holdem_registry.register(game_id, agents, task)

    return state.model_dump()


async def _holdem_execute_action(game_id: str, player_id: str, action):
    """Process a Hold'em action and broadcast results."""
    game = HoldemGame(game_id, redis_client)
    result = await game.process_action(player_id, action)
    state = await game.get_state()

    actor_name = _holdem_player_name(state, player_id)

    # Broadcast the action to all players
    amount = getattr(result, "amount", 0)
    await manager.broadcast(
        game_id,
        HoldemActionMessage(
            player_id=player_id,
            action=result.type,
            amount=amount,
        ),
    )

    # Chat narration
    if isinstance(result, FoldResult):
        await _holdem_broadcast_chat(game_id, f"{actor_name} folds.", player_id)
    elif isinstance(result, CheckResult):
        await _holdem_broadcast_chat(game_id, f"{actor_name} checks.", player_id)
    elif isinstance(result, CallResult):
        await _holdem_broadcast_chat(
            game_id, f"{actor_name} calls {_format_currency(result.amount)}.", player_id
        )
    elif isinstance(result, BetResult):
        await _holdem_broadcast_chat(
            game_id, f"{actor_name} bets {_format_currency(result.amount)}.", player_id
        )
    elif isinstance(result, RaiseResult):
        await _holdem_broadcast_chat(
            game_id,
            f"{actor_name} raises to {_format_currency(result.amount)}.",
            player_id,
        )
    elif isinstance(result, AllInResult):
        await _holdem_broadcast_chat(
            game_id,
            f"{actor_name} goes all-in for {_format_currency(result.amount)}!",
            player_id,
        )

    # Broadcast updated state and community cards if they changed
    if state.community_cards:
        await manager.broadcast(
            game_id,
            HoldemCommunityCardsMessage(
                cards=state.community_cards,
                betting_round=state.betting_round,
            ),
        )

    # Broadcast showdown/hand result if a hand just completed
    hand_result = state.last_hand_result
    if hand_result:
        await manager.broadcast(
            game_id,
            HoldemShowdownMessage(
                winners=hand_result.winners,
                winning_hand=hand_result.winning_hand,
                pot=hand_result.pot,
                player_hands=hand_result.player_hands,
                community_cards=hand_result.community_cards,
            ),
        )
        winner_names = ", ".join(
            _holdem_player_name(state, w) for w in hand_result.winners
        )
        if hand_result.winning_hand:
            await _holdem_broadcast_chat(
                game_id,
                f"{winner_names} wins the pot ({_format_currency(hand_result.pot)}) with {hand_result.winning_hand}!",
            )
        else:
            await _holdem_broadcast_chat(
                game_id,
                f"{winner_names} takes the pot ({_format_currency(hand_result.pot)}).",
            )

    if state.status == "finished":
        winner_name = _holdem_player_name(state, state.winner) if state.winner else "?"
        await manager.broadcast(
            game_id,
            HoldemGameOverMessage(winner=state.winner or ""),
        )
        await _holdem_broadcast_chat(
            game_id, f"Game over! {winner_name} wins the tournament!"
        )
    elif state.status == "playing" and state.whose_turn:
        # Notify next player
        await manager.send_to_player(
            game_id,
            state.whose_turn,
            HoldemYourTurnMessage(
                available_actions=game.get_available_actions(state.whose_turn, state),
            ),
        )

    # Send rebuy prompts to busted players (when allow_rebuys is on)
    # Re-load state since _end_hand may have modified it
    state = await game.get_state()
    if state and state.allow_rebuys:
        rebuy_pending = [p for p in state.players if p.rebuy_pending]
        for p in rebuy_pending:
            name = _holdem_player_name(state, p.id)
            await manager.send_to_player(
                game_id,
                p.id,
                HoldemRebuyPromptMessage(player_id=p.id, buy_in=state.buy_in),
            )
            await _holdem_broadcast_chat(
                game_id,
                f"{name} is out of chips! Rebuy for {_format_currency(state.buy_in)}?",
            )

    return result


@app.post("/api/holdem/games/{game_id}/action")
async def holdem_submit_action(game_id: str, req: HoldemActionRequest):
    try:
        result = await _holdem_execute_action(game_id, req.player_id, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    response = result.model_dump()
    if state:
        response["available_actions"] = game.get_available_actions(req.player_id, state)
    return response


@app.websocket("/api/ws/holdem/{game_id}/{player_id}")
async def holdem_websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    await manager.connect(game_id, player_id, websocket)
    game = HoldemGame(game_id, redis_client)
    try:
        ps = await game.get_player_state(player_id)
        if ps:
            await manager.send_to_player(
                game_id, player_id, HoldemGameStateMessage(state=ps)
            )
            if ps.whose_turn == player_id and ps.available_actions:
                await manager.send_to_player(
                    game_id,
                    player_id,
                    HoldemYourTurnMessage(available_actions=ps.available_actions),
                )
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_to_player(
                        game_id, player_id, HoldemPongMessage()
                    )
                elif msg.get("type") == "chat":
                    text = str(msg.get("text", "")).strip()
                    if text:
                        g = HoldemGame(game_id, redis_client)
                        s = await g.get_state()
                        name = _holdem_player_name(s, player_id) if s else player_id
                        await _holdem_broadcast_chat(
                            game_id, f"{name}: {text}", player_id
                        )
            except Exception:
                logger.debug(
                    "Ignoring non-JSON WebSocket message from %s/%s",
                    game_id,
                    player_id,
                )
    except WebSocketDisconnect:
        manager.disconnect(game_id, player_id, websocket)


@app.get("/api/holdem/games/{game_id}/chat")
async def holdem_get_chat(game_id: str):
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    messages = await game.get_chat_messages()
    return HoldemChatMessagesResponse(messages=messages)


@app.post("/api/holdem/games/{game_id}/chat")
async def holdem_send_chat(game_id: str, req: HoldemChatRequest):
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    text = str(req.text).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty")
    name = _holdem_player_name(state, req.player_id)
    await _holdem_broadcast_chat(game_id, f"{name}: {text}", req.player_id)
    return HoldemOkResponse()


@app.post("/api/holdem/games/{game_id}/rebuy")
async def holdem_rebuy(game_id: str, req: HoldemRebuyRequest):
    """Player rebuys after going bust."""
    game = HoldemGame(game_id, redis_client)
    try:
        state = await game.rebuy(req.player_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    player = next((p for p in state.players if p.id == req.player_id), None)
    name = _holdem_player_name(state, req.player_id)
    await manager.broadcast(
        game_id,
        HoldemRebuyMessage(
            player_id=req.player_id, chips=player.chips if player else 0
        ),
    )
    await _holdem_broadcast_chat(
        game_id, f"{name} rebuys for {_format_currency(state.buy_in)}!"
    )

    # If the game advanced to a new hand, notify players
    if state.status == "playing" and state.whose_turn:
        await _holdem_notify_new_hand(game_id, state, game)

    return HoldemOkResponse()


@app.post("/api/holdem/games/{game_id}/decline_rebuy")
async def holdem_decline_rebuy(game_id: str, req: HoldemRebuyRequest):
    """Player declines rebuy and is eliminated."""
    game = HoldemGame(game_id, redis_client)
    try:
        state = await game.decline_rebuy(req.player_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    name = _holdem_player_name(state, req.player_id)
    await manager.broadcast(
        game_id,
        HoldemPlayerEliminatedMessage(player_id=req.player_id),
    )
    await _holdem_broadcast_chat(game_id, f"{name} is eliminated.")

    if state.status == "finished":
        winner_name = _holdem_player_name(state, state.winner) if state.winner else "?"
        await manager.broadcast(
            game_id,
            HoldemGameOverMessage(winner=state.winner or ""),
        )
        await _holdem_broadcast_chat(
            game_id, f"Game over! {winner_name} wins the tournament!"
        )
    elif state.status == "playing" and state.whose_turn:
        await _holdem_notify_new_hand(game_id, state, game)

    return HoldemOkResponse()


async def _holdem_notify_new_hand(
    game_id: str, state: HoldemGameState, game: HoldemGame
):
    """Notify all players about a new hand starting."""
    for player in state.players:
        if player.active:
            cards = await game._load_player_cards(player.id)
            await manager.send_to_player(
                game_id,
                player.id,
                HoldemGameStartedMessage(
                    your_cards=cards,
                    whose_turn=state.whose_turn,
                    available_actions=game.get_available_actions(player.id, state),
                ),
            )
    await manager.broadcast(
        game_id,
        HoldemNewHandMessage(
            hand_number=state.hand_number,
            dealer=state.players[state.dealer_index].id if state.players else "",
        ),
    )
    if state.whose_turn:
        await manager.send_to_player(
            game_id,
            state.whose_turn,
            HoldemYourTurnMessage(
                available_actions=game.get_available_actions(state.whose_turn, state),
            ),
        )


# ---------------------------------------------------------------------------
# Hold'em agent support
# ---------------------------------------------------------------------------


def _make_holdem_runner(game_id: str, agents: dict[str, HoldemAgent]) -> HoldemAgentRunner:
    """Create a HoldemAgentRunner wired to this module's helpers."""
    game = HoldemGame(game_id, redis_client)

    async def _rebuy(player_id: str):
        return await game.rebuy(player_id)

    async def _on_rebuy_success(gid: str, agent_id: str, new_state) -> None:
        name = agents[agent_id].name
        await manager.broadcast(
            gid,
            HoldemRebuyMessage(
                player_id=agent_id,
                chips=new_state.buy_in,
            ),
        )
        await _holdem_broadcast_chat(
            gid,
            f"{name} rebuys for {_format_currency(new_state.buy_in)}!",
        )

    async def _notify_new_hand(gid: str, state) -> None:
        await _holdem_notify_new_hand(gid, state, game)

    return HoldemAgentRunner(
        game_id,
        agents,
        get_state=game.get_state,
        get_player_state=game.get_player_state,
        execute_action=_holdem_execute_action,
        broadcast_chat=_holdem_broadcast_chat,
        rebuy=_rebuy,
        on_rebuy_success=_on_rebuy_success,
        notify_new_hand=_notify_new_hand,
        format_currency=_format_currency,
        registry=_holdem_registry,
    )


@app.get("/api/holdem/games/{game_id}/debug")
async def holdem_get_game_debug(
    game_id: str,
    log_offset: int = 0,
    chat_offset: int = 0,
):
    """Return comprehensive debug data for a Hold'em game: state, player cards,
    agent configs, game log, and chat messages.

    Offset params allow incremental fetching.
    """
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    log_key = f"holdem:{game_id}:log"
    chat_key = f"holdem:{game_id}:chat"

    log_raw, chat_raw = await asyncio.gather(
        redis_client.lrange(log_key, log_offset, -1),
        redis_client.lrange(chat_key, chat_offset, -1),
    )

    game_log = [json.loads(e) for e in log_raw]
    chat = [json.loads(e) for e in chat_raw]

    # Collect player cards (hole cards)
    player_ids = [p.id for p in state.players]
    card_keys = [f"holdem:{game_id}:cards:{pid}" for pid in player_ids]
    card_raws = await asyncio.gather(*[redis_client.get(k) for k in card_keys])
    player_cards = {}
    for pid, raw in zip(player_ids, card_raws):
        if raw:
            cards = json.loads(raw)
            player_cards[pid] = [
                f"{c['rank']}{c['suit'][0].upper()}" if isinstance(c, dict) else str(c)
                for c in cards
            ]
        else:
            player_cards[pid] = []

    # Collect agent configs from Redis
    config_keys = [f"holdem:{game_id}:agent_config:{pid}" for pid in player_ids]
    config_raws = await asyncio.gather(*[redis_client.get(k) for k in config_keys])
    agent_configs = {}
    for pid, raw in zip(player_ids, config_raws):
        if raw:
            agent_configs[pid] = json.loads(raw)

    return {
        "game_id": game_id,
        "state": state.model_dump(),
        "player_cards": player_cards,
        "agent_configs": agent_configs,
        "game_log": game_log,
        "chat": chat,
    }


@app.post("/api/holdem/games/{game_id}/add_agent")
async def holdem_add_agent(game_id: str, req: HoldemAddAgentRequest | None = None):
    """Add an AI agent to a Hold'em game in the waiting room."""
    game = HoldemGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Resolve personality — use requested, or pick a random one
    requested_personality = req.personality if req else ""
    personality_name, personality_defaults = get_personality(
        requested_personality or None
    )

    # Explicit params override personality defaults
    aggression = (
        req.aggression
        if (req and req.aggression is not None)
        else personality_defaults["aggression"]
    )
    tightness = (
        req.tightness
        if (req and req.tightness is not None)
        else personality_defaults["tightness"]
    )
    bluff_frequency = (
        req.bluff_frequency
        if (req and req.bluff_frequency is not None)
        else personality_defaults["bluff_frequency"]
    )
    slowplay_frequency = (
        req.slowplay_frequency
        if (req and req.slowplay_frequency is not None)
        else personality_defaults["slowplay_frequency"]
    )
    chat_frequency = (
        req.chat_frequency
        if (req and req.chat_frequency is not None)
        else personality_defaults["chat_frequency"]
    )

    # Pick a name
    taken_names = {p.name for p in state.players}
    name = req.name if req and req.name else ""
    if not name:
        for candidate in _HOLDEM_AGENT_NAMES:
            if candidate not in taken_names:
                name = candidate
                break
        if not name:
            name = f"Bot {len(state.players) + 1}"

    player_id = _new_player_id()
    try:
        player = await game.add_player(player_id, name, player_type="holdem_agent")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Store agent config in Redis so it can be used at game start
    import json as _json

    agent_config = {
        "personality": personality_name,
        "aggression": aggression,
        "tightness": tightness,
        "bluff_frequency": bluff_frequency,
        "slowplay_frequency": slowplay_frequency,
        "chat_frequency": chat_frequency,
    }
    await redis_client.set(
        f"holdem:{game_id}:agent_config:{player_id}",
        _json.dumps(agent_config),
        ex=86400,
    )

    state = await game.get_state()
    await manager.broadcast(
        game_id,
        HoldemPlayerJoinedMessage(player=player, players=list(state.players)),
    )
    await _holdem_broadcast_chat(
        game_id, f"{name} joined the table. (Style: {personality_name})"
    )

    return HoldemJoinGameResponse(player_id=player_id, player=player)


# ---------------------------------------------------------------------------
# SPA fallback for /{game_type}/{id} routes
# ---------------------------------------------------------------------------

_static_dir = Path(__file__).parent.parent / "static"


@app.get("/clue/{game_id}")
@app.get("/clue/{game_id}/debug")
async def spa_clue_route(game_id: str):
    """Serve index.html for /clue/{id} and /clue/{id}/debug so the Vue SPA can handle routing."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    # In dev mode (no static build), return a minimal redirect
    return FileResponse(str(index)) if index.exists() else {"detail": "Not found"}


@app.get("/holdem/{game_id}")
@app.get("/holdem/{game_id}/debug")
async def spa_holdem_route(game_id: str):
    """Serve index.html for /holdem/{id} and /holdem/{id}/debug so the Vue SPA can handle routing."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"detail": "Not found"}


@app.get("/admin")
async def spa_admin_route():
    """Serve index.html for /admin so the Vue SPA can handle routing."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"detail": "Not found"}


# ---------------------------------------------------------------------------
# Static files (Vue build output)
# ---------------------------------------------------------------------------

# NOTE: Static files must be mounted LAST — it acts as a catch-all and would
# shadow any API routes defined after this point.
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
