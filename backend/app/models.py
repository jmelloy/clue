"""Pydantic models for Clue game state and API requests."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class Player(BaseModel):
    id: str
    name: str
    type: str  # "human" | "agent" | "llm_agent" | "wanderer"
    character: str
    active: bool = True


class Solution(BaseModel):
    suspect: str
    weapon: str
    room: str


class Suggestion(BaseModel):
    suspect: str
    weapon: str
    room: str
    suggested_by: str
    pending_show_by: Optional[str] = None


class PendingShowCard(BaseModel):
    player_id: str
    suggesting_player_id: str
    suspect: str
    weapon: str
    room: str
    matching_cards: list[str]


class GameState(BaseModel):
    game_id: str
    status: str  # "waiting" | "playing" | "finished"
    players: list[Player] = Field(default_factory=list)
    whose_turn: Optional[str] = None
    turn_number: int = 0
    current_room: dict[str, str] = Field(default_factory=dict)
    player_positions: dict[str, list[int]] = Field(default_factory=dict)
    suggestions_this_turn: list[Suggestion] = Field(default_factory=list)
    winner: Optional[str] = None
    dice_rolled: bool = False
    moved: bool = False
    last_roll: Optional[list[int]] = None
    pending_show_card: Optional[PendingShowCard] = None
    was_moved_by_suggestion: dict[str, bool] = Field(default_factory=dict)


class PlayerState(GameState):
    your_cards: list[str] = Field(default_factory=list)
    your_player_id: str = ""
    available_actions: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    player_id: Optional[str] = None
    text: str
    timestamp: str


# ---------------------------------------------------------------------------
# Game action types (inputs to process_action)
# ---------------------------------------------------------------------------


class RollAction(BaseModel):
    type: Literal["roll"] = "roll"


class SecretPassageAction(BaseModel):
    type: Literal["secret_passage"] = "secret_passage"


class MoveAction(BaseModel):
    type: Literal["move"] = "move"
    room: Optional[str] = None
    position: Optional[list[int]] = None


class SuggestAction(BaseModel):
    type: Literal["suggest"] = "suggest"
    suspect: str
    weapon: str
    room: str


class AccuseAction(BaseModel):
    type: Literal["accuse"] = "accuse"
    suspect: str
    weapon: str
    room: str


class EndTurnAction(BaseModel):
    type: Literal["end_turn"] = "end_turn"


class ShowCardAction(BaseModel):
    type: Literal["show_card"] = "show_card"
    card: str


GameAction = Annotated[
    Union[
        RollAction,
        SecretPassageAction,
        MoveAction,
        SuggestAction,
        AccuseAction,
        EndTurnAction,
        ShowCardAction,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Action result types (outputs from process_action)
# ---------------------------------------------------------------------------


class ActionResultBase(BaseModel):
    """Base for all action results."""

    type: str
    player_id: str


class RollResult(ActionResultBase):
    type: Literal["roll"] = "roll"
    dice: int
    total: int


class SecretPassageResult(ActionResultBase):
    type: Literal["secret_passage"] = "secret_passage"
    from_room: str
    room: str
    position: Optional[list[int]] = None


class MoveResult(ActionResultBase):
    type: Literal["move"] = "move"
    room: Optional[str] = None
    position: Optional[list[int]] = None
    dice: int = 0
    total: int = 0


class SuggestResult(ActionResultBase):
    type: Literal["suggest"] = "suggest"
    suspect: str
    weapon: str
    room: str
    pending_show_by: Optional[str] = None
    moved_suspect_player: Optional[str] = None
    players_without_match: list[str] = Field(default_factory=list)


class ShowCardResult(ActionResultBase):
    type: Literal["show_card"] = "show_card"
    card: str
    suggesting_player_id: str
    suspect: str
    weapon: str
    room: str


class AccuseResult(ActionResultBase):
    type: Literal["accuse"] = "accuse"
    correct: bool
    winner: Optional[str] = None
    solution: Optional[dict] = None


class EndTurnResult(ActionResultBase):
    type: Literal["end_turn"] = "end_turn"
    next_player_id: str


ActionResult = Annotated[
    Union[
        RollResult,
        SecretPassageResult,
        MoveResult,
        SuggestResult,
        ShowCardResult,
        AccuseResult,
        EndTurnResult,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# WebSocket message types
# ---------------------------------------------------------------------------


class WSMessage(BaseModel):
    """Base class for all WebSocket messages."""

    type: str


class DiceRolledMessage(WSMessage):
    type: Literal["dice_rolled"] = "dice_rolled"
    player_id: str
    dice: int
    last_roll: Optional[list[int]] = None
    reachable_rooms: list[str] = Field(default_factory=list)


class YourTurnMessage(WSMessage):
    type: Literal["your_turn"] = "your_turn"
    available_actions: list[str] = Field(default_factory=list)
    reachable_rooms: Optional[list[str]] = None
    reachable_positions: Optional[list[list[int]]] = None


class PlayerMovedMessage(WSMessage):
    type: Literal["player_moved"] = "player_moved"
    player_id: str
    position: Optional[list[int]] = None
    room: Optional[str] = None
    from_room: Optional[str] = None
    dice: Optional[int] = None
    secret_passage: Optional[bool] = None


class SuggestionMadeMessage(WSMessage):
    type: Literal["suggestion_made"] = "suggestion_made"
    player_id: str
    suspect: str
    weapon: str
    room: str
    pending_show_by: Optional[str] = None
    moved_suspect_player: Optional[str] = None
    player_positions: Optional[dict[str, list[int]]] = None


class ShowCardRequestMessage(WSMessage):
    type: Literal["show_card_request"] = "show_card_request"
    suggesting_player_id: str
    suspect: str
    weapon: str
    room: str
    available_actions: list[str] = Field(default_factory=list)


class CardShownMessage(WSMessage):
    type: Literal["card_shown"] = "card_shown"
    shown_by: str
    card: str
    available_actions: list[str] = Field(default_factory=list)


class CardShownPublicMessage(WSMessage):
    type: Literal["card_shown_public"] = "card_shown_public"
    shown_by: str
    shown_to: str


class AccusationMadeMessage(WSMessage):
    type: Literal["accusation_made"] = "accusation_made"
    player_id: str
    correct: bool


class GameOverMessage(WSMessage):
    type: Literal["game_over"] = "game_over"
    player_id: str
    correct: bool
    winner: Optional[str] = None
    solution: Optional[dict] = None


class GameStateUpdateMessage(WSMessage):
    type: Literal["game_state"] = "game_state"
    whose_turn: Optional[str] = None
    turn_number: Optional[int] = None
    dice_rolled: Optional[bool] = None
    moved: Optional[bool] = None
    last_roll: Optional[list[int]] = None
    suggestions_this_turn: Optional[list[dict]] = None
    pending_show_card: Optional[dict] = None
    player_positions: Optional[dict[str, list[int]]] = None
    state: Optional[dict] = None


class AutoEndTimerMessage(WSMessage):
    type: Literal["auto_end_timer"] = "auto_end_timer"
    player_id: str
    seconds: int


class PlayerJoinedMessage(WSMessage):
    type: Literal["player_joined"] = "player_joined"
    player: Player
    players: list[Player]


class GameStartedMessage(WSMessage):
    type: Literal["game_started"] = "game_started"
    your_cards: Optional[list[str]] = None
    whose_turn: Optional[str] = None
    available_actions: Optional[list[str]] = None
    state: Optional[GameState] = None


class ChatBroadcastMessage(WSMessage):
    type: Literal["chat_message"] = "chat_message"
    player_id: Optional[str] = None
    text: str
    timestamp: str


class PongMessage(WSMessage):
    type: Literal["pong"] = "pong"


# ---------------------------------------------------------------------------
# Agent event types (published to Redis for external agent runners)
# ---------------------------------------------------------------------------


class AgentEvent(BaseModel):
    type: str


class ShowCardAgentEvent(AgentEvent):
    type: Literal["show_card"] = "show_card"
    shown_by: str
    shown_to: Optional[str] = None
    card: Optional[str] = None
    suspect: str = ""
    weapon: str = ""
    room: str = ""


class SuggestAgentEvent(AgentEvent):
    type: Literal["suggest"] = "suggest"
    suggesting_player_id: str
    suspect: str
    weapon: str
    room: str
    shown_by: Optional[str] = None
    players_without_match: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request models
# ---------------------------------------------------------------------------


class JoinRequest(BaseModel):
    player_name: str
    player_type: str = "human"


class AddAgentRequest(BaseModel):
    agent_type: str = "agent"  # "agent" or "llm_agent"


class ActionRequest(BaseModel):
    player_id: str
    action: GameAction


class ChatRequest(BaseModel):
    player_id: str
    text: str
