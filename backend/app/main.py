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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter

from .agents import (
    BaseAgent,
    LLMAgent,
    RandomAgent,
    WandererAgent,
    generate_character_chat,
)
from .game import ClueGame
from .models import (
    AccusationMadeMessage,
    AccuseAction,
    AccuseResult,
    ActionRequest,
    ActionResult,
    AddAgentRequest,
    AutoEndTimerMessage,
    CardShownMessage,
    CardShownPublicMessage,
    ChatBroadcastMessage,
    ChatMessage,
    ChatRequest,
    DiceRolledMessage,
    EndTurnAction,
    EndTurnResult,
    GameAction,
    GameOverMessage,
    GameStartedMessage,
    GameState,
    GameStateUpdateMessage,
    JoinRequest,
    MoveResult,
    Player,
    PlayerJoinedMessage,
    PlayerMovedMessage,
    PlayerState,
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
    YourTurnMessage,
)
from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

# TypeAdapter for parsing agent action dicts into typed GameAction models
_action_adapter: TypeAdapter[GameAction] = TypeAdapter(GameAction)

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
    for task in _agent_tasks.values():
        task.cancel()
    _agent_tasks.clear()
    _game_agents.clear()
    # Cancel any auto-end timers
    for task in _auto_end_timers.values():
        task.cancel()
    _auto_end_timers.clear()
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
_game_agents: dict[str, dict[str, BaseAgent]] = {}
_agent_tasks: dict[str, asyncio.Task] = {}

# Auto-end-turn timers: game_id -> asyncio.Task
_auto_end_timers: dict[str, asyncio.Task] = {}
AUTO_END_TURN_SECONDS = 7

# Player types that trigger the automated agent loop
_AGENT_PLAYER_TYPES = {"agent", "llm_agent", "wanderer"}

# Agent mode: "inline" runs agents in-process (legacy), "external" relies on agent_runner
_AGENT_MODE = os.getenv("AGENT_MODE", "inline")

# Accumulate wanderer turn info so we can emit one collapsed chat line
# Key: (game_id, player_id) -> {"dice": int, "room": str|None}
_wanderer_turn_info: dict[tuple[str, str], dict] = {}


def _new_id(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _new_player_id() -> str:
    return _new_id(8)


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
    logger.info(f"Broadcasting chat in game {game_id} from player {player_id}: {text}")
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
# Action execution (shared by HTTP endpoint and agent loop)
# ---------------------------------------------------------------------------


async def _execute_action(
    game_id: str, player_id: str, action: GameAction
) -> ActionResult:
    """Process a game action and broadcast WebSocket messages.

    Returns the typed action result. Raises ValueError on invalid actions.
    """
    # Cancel any pending auto-end timer when a player takes an action
    _cancel_auto_end_timer(game_id)

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
                reachable_rooms=reachable_targets["reachable_rooms"],
            ),
        )
        if wanderer:
            _wanderer_turn_info[(game_id, player_id)] = {
                "dice": result.dice,
                "room": None,
            }
        else:
            await _broadcast_chat(
                game_id,
                f"{actor_name} rolled {result.dice}.",
                player_id,
            )
        await manager.send_to_player(
            game_id,
            player_id,
            YourTurnMessage(
                available_actions=game.get_available_actions(player_id, state),
                reachable_rooms=reachable_targets["reachable_rooms"],
                reachable_positions=reachable_targets["reachable_positions"],
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
            ),
        )
        if wanderer:
            info = _wanderer_turn_info.get((game_id, player_id))
            if info is not None:
                info["room"] = result.room
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
            ),
        )
        if pending_show_by:
            pending_by_name = _player_name(state, pending_show_by)
            await manager.send_to_player(
                game_id,
                pending_show_by,
                ShowCardRequestMessage(
                    suggesting_player_id=player_id,
                    suspect=result.suspect,
                    weapon=result.weapon,
                    room=result.room,
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
            chat_text = (
                f"{actor_name} suggests {result.suspect} with the {result.weapon}"
                f" in the {result.room}. {pending_by_name} must show a card."
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

        # "dragged_to_room" reaction — if the piece was physically moved
        if moved_suspect_player:
            dragged_msg = generate_character_chat(
                suspect_character,
                "dragged_to_room",
                {"room": result.room, "accuser": accuser_name},
            )
            if dragged_msg:
                await _broadcast_chat(
                    game_id,
                    f"{suspect_character}: {dragged_msg}",
                    moved_suspect_player,
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
            ),
        )
        await _broadcast_chat(
            game_id,
            f"{shown_by_name} showed a card to {shown_to_name}.",
            player_id,
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
            await manager.broadcast(
                game_id,
                AccusationMadeMessage(
                    player_id=player_id,
                    correct=False,
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
                suggestions_this_turn=[
                    s.model_dump() for s in state.suggestions_this_turn
                ],
                pending_show_card=(
                    state.pending_show_card.model_dump()
                    if state.pending_show_card
                    else None
                ),
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
            dice = info["dice"] if info else "?"
            room = info["room"] if info else None
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

    # Check if the current player should get an auto-end-turn timer
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
# Agent background loop
# ---------------------------------------------------------------------------


async def _run_agent_loop(game_id: str):
    """Background task that drives agent players in a game."""
    agents = _game_agents.get(game_id)
    if not agents:
        return

    logger.info("Agent loop started for game %s with %d agent(s)", game_id, len(agents))

    try:
        while True:
            game = ClueGame(game_id, redis_client)
            state = await game.get_state()
            if state is None or state.status != "playing":
                break

            pending = state.pending_show_card
            if pending and pending.player_id in agents:
                # An agent needs to show a card
                await asyncio.sleep(1)
                # Re-check state (may have changed during sleep)
                state = await game.get_state()
                if not state or state.status != "playing":
                    break
                pending = state.pending_show_card
                if not pending or pending.player_id not in agents:
                    continue

                pid = pending.player_id
                agent = agents[pid]
                matching = pending.matching_cards
                suggesting_pid = pending.suggesting_player_id
                card = await agent.decide_show_card(matching, suggesting_pid)

                logger.info("Agent %s showing card in game %s", pid, game_id)
                await _execute_action(game_id, pid, ShowCardAction(card=card))
                # Broadcast personality chat for show_card
                chat_msg = agent.generate_chat("show_card")
                if chat_msg:
                    s = await game.get_state()
                    name = _player_name(s, pid) if s else pid
                    await _broadcast_chat(game_id, f"{name}: {chat_msg}", pid)

            elif pending:
                # A non-agent (human) player must show a card — wait for them
                await asyncio.sleep(0.5)

            elif state.whose_turn in agents:
                # It's an agent's turn — pace actions for human observers
                agent = agents[state.whose_turn]
                if agent.agent_type != "llm":
                    await asyncio.sleep(1.35)
                # Re-check state
                state = await game.get_state()
                if not state or state.status != "playing":
                    break
                pid = state.whose_turn
                if pid not in agents:
                    continue

                agent = agents[pid]
                player_state = await game.get_player_state(pid)
                action_dict = await agent.decide_action(state, player_state)

                # Parse agent's dict action into a typed GameAction
                action = _action_adapter.validate_python(action_dict)

                logger.info(
                    "Agent %s taking action %s in game %s",
                    pid,
                    action.type,
                    game_id,
                )
                result = await _execute_action(game_id, pid, action)
                # Broadcast personality chat after the action
                result_d = result.model_dump()
                action_d = action.model_dump()
                chat_context = {
                    "dice": result_d.get("dice", ""),
                    "room": result_d.get("room") or action_d.get("room") or "",
                    "suspect": action_d.get("suspect", ""),
                    "weapon": action_d.get("weapon", ""),
                }
                chat_msg = agent.generate_chat(action.type, chat_context)
                if chat_msg:
                    s = await game.get_state()
                    name = _player_name(s, pid) if s else pid
                    await _broadcast_chat(game_id, f"{name}: {chat_msg}", pid)

            else:
                # Human player's turn — poll periodically
                await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("Agent loop cancelled for game %s", game_id)
    except Exception:
        logger.exception("Agent loop error in game %s", game_id)
    finally:
        _game_agents.pop(game_id, None)
        _agent_tasks.pop(game_id, None)
        logger.info("Agent loop ended for game %s", game_id)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/games", status_code=201)
async def create_game():
    game_id = _new_id(6)
    game = ClueGame(game_id, redis_client)
    state = await game.create()
    return {"game_id": game_id, "status": state.status}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/games/{game_id}")
async def get_game(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return state.model_dump()


@app.post("/games/{game_id}/join")
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
    return {"player_id": player_id, "player": player.model_dump()}


_AGENT_NAMES = [
    "Bot Alice",
    "Bot Bob",
    "Bot Carol",
    "Bot Dave",
    "Bot Eve",
    "Bot Frank",
]


@app.post("/games/{game_id}/add_agent")
async def add_agent(game_id: str, req: AddAgentRequest | None = None):
    """Add an AI agent to a game in the waiting room."""
    agent_type = req.agent_type if req else "agent"
    if agent_type not in _AGENT_PLAYER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid agent type")

    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")

    player_id = _new_player_id()

    # Use a placeholder name; we'll rename to the assigned character below
    taken_names = {p.name for p in state.players}
    placeholder = None
    for name in _AGENT_NAMES:
        if name not in taken_names:
            placeholder = name
            break
    if placeholder is None:
        placeholder = f"Bot {len(state.players) + 1}"

    try:
        player = await game.add_player(player_id, placeholder, agent_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Use the character name as the display name for more personality
    state = await game.get_state()
    if player.character:
        player.name = player.character
        for p in state.players:
            if p.id == player_id:
                p.name = player.character
                break
        await game._save_state(state)
    await manager.broadcast(
        game_id,
        PlayerJoinedMessage(player=player, players=list(state.players)),
    )
    await _broadcast_chat(game_id, f"{player.name} joined the game.")
    return {"player_id": player_id, "player": player.model_dump()}


@app.post("/games/{game_id}/start")
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
        # Always store agent config in Redis so external runners can pick it up
        agent_config = {}
        for player in agent_players:
            pid = player.id
            cards = await game._load_player_cards(pid)
            agent_config[pid] = {
                "type": player.type,
                "character": player.character,
                "cards": cards,
            }
        await redis_client.set(
            f"game:{game_id}:agent_config",
            json.dumps(agent_config),
            ex=86400,
        )

        if _AGENT_MODE == "inline":
            # Run agents in-process (original behavior)
            agents: dict[str, BaseAgent] = {}
            for player in agent_players:
                pid = player.id
                ptype = player.type
                if ptype == "llm_agent":
                    agent: BaseAgent = LLMAgent(
                        redis_client=redis_client, game_id=game_id
                    )
                elif ptype == "wanderer":
                    agent = WandererAgent()
                else:
                    agent = RandomAgent()
                agent.character = player.character
                agent.player_id = pid
                cards = await game._load_player_cards(pid)
                agent.observe_own_cards(cards)
                if ptype == "llm_agent":
                    await agent.load_memory()
                agents[pid] = agent
                logger.info(
                    "Created %s agent for player %s (%s) in game %s",
                    ptype,
                    pid,
                    player.character,
                    game_id,
                )
            _game_agents[game_id] = agents
            _agent_tasks[game_id] = asyncio.create_task(_run_agent_loop(game_id))
        else:
            logger.info(
                "Agent mode is '%s' — %d agent(s) in game %s will be managed externally",
                _AGENT_MODE,
                len(agent_players),
                game_id,
            )

    return state.model_dump()


@app.post("/games/{game_id}/action")
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


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    await manager.connect(game_id, player_id, websocket)
    game = ClueGame(game_id, redis_client)
    try:
        player_state = await game.get_player_state(player_id)
        if player_state:
            await manager.send_to_player(
                game_id,
                player_id,
                GameStateUpdateMessage(state=player_state.model_dump()),
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
        manager.disconnect(game_id, player_id)


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.get("/games/{game_id}/chat")
async def get_chat(game_id: str):
    game = ClueGame(game_id, redis_client)
    state = await game.get_state()
    if state is None:
        raise HTTPException(status_code=404, detail="Game not found")
    messages = await game.get_chat_messages()
    return {"messages": [m.model_dump() for m in messages]}


@app.post("/games/{game_id}/chat")
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
    return {"ok": True}


# ---------------------------------------------------------------------------
# SPA fallback for /game/{id} routes
# ---------------------------------------------------------------------------

_static_dir = Path(__file__).parent.parent / "static"


@app.get("/game/{game_id}")
async def spa_game_route(game_id: str):
    """Serve index.html for /game/{id} so the Vue SPA can handle routing."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    # In dev mode (no static build), return a minimal redirect
    return FileResponse(str(index)) if index.exists() else {"detail": "Not found"}


# ---------------------------------------------------------------------------
# Static files (Vue build output)
# ---------------------------------------------------------------------------

# NOTE: Static files must be mounted LAST — it acts as a catch-all and would
# shadow any API routes defined after this point.
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
