"""Pydantic models for Texas Hold'em game state and API."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Card representation
# ---------------------------------------------------------------------------

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["hearts", "diamonds", "clubs", "spades"]

RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}


class Card(BaseModel):
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit[0].upper()}"

    def __hash__(self) -> int:
        return hash((self.rank, self.suit))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self.rank == other.rank and self.suit == other.suit


# ---------------------------------------------------------------------------
# Player & game state
# ---------------------------------------------------------------------------


class HoldemPlayer(BaseModel):
    id: str
    name: str
    chips: int = 1000
    active: bool = True  # still in the tournament
    folded: bool = False  # folded this hand
    current_bet: int = 0  # amount bet this round
    all_in: bool = False


class HoldemGameState(BaseModel):
    game_id: str
    game_type: str = "holdem"
    status: str = "waiting"  # "waiting" | "playing" | "finished"
    players: list[HoldemPlayer] = Field(default_factory=list)

    # Hand state
    community_cards: list[Card] = Field(default_factory=list)
    pot: int = 0
    current_bet: int = 0  # highest bet this round
    whose_turn: Optional[str] = None
    dealer_index: int = 0
    small_blind: int = 10
    big_blind: int = 20
    hand_number: int = 0

    # Betting round: "preflop" | "flop" | "turn" | "river" | "showdown"
    betting_round: str = "preflop"

    winner: Optional[str] = None
    winning_hand: Optional[str] = None

    # Track who has acted this betting round
    last_raiser: Optional[str] = None
    actions_this_round: int = 0


class HoldemPlayerState(HoldemGameState):
    """Player-specific view including hole cards and available actions."""
    your_cards: list[Card] = Field(default_factory=list)
    your_player_id: str = ""
    available_actions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class FoldAction(BaseModel):
    type: Literal["fold"] = "fold"


class CheckAction(BaseModel):
    type: Literal["check"] = "check"


class CallAction(BaseModel):
    type: Literal["call"] = "call"


class BetAction(BaseModel):
    type: Literal["bet"] = "bet"
    amount: int


class RaiseAction(BaseModel):
    type: Literal["raise"] = "raise"
    amount: int


class AllInAction(BaseModel):
    type: Literal["all_in"] = "all_in"


HoldemAction = Annotated[
    Union[FoldAction, CheckAction, CallAction, BetAction, RaiseAction, AllInAction],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Action results
# ---------------------------------------------------------------------------


class HoldemActionResultBase(BaseModel):
    type: str
    player_id: str


class FoldResult(HoldemActionResultBase):
    type: Literal["fold"] = "fold"


class CheckResult(HoldemActionResultBase):
    type: Literal["check"] = "check"


class CallResult(HoldemActionResultBase):
    type: Literal["call"] = "call"
    amount: int = 0


class BetResult(HoldemActionResultBase):
    type: Literal["bet"] = "bet"
    amount: int = 0


class RaiseResult(HoldemActionResultBase):
    type: Literal["raise"] = "raise"
    amount: int = 0


class AllInResult(HoldemActionResultBase):
    type: Literal["all_in"] = "all_in"
    amount: int = 0


class NewHandResult(HoldemActionResultBase):
    type: Literal["new_hand"] = "new_hand"
    hand_number: int = 0


class ShowdownResult(HoldemActionResultBase):
    type: Literal["showdown"] = "showdown"
    winners: list[str] = Field(default_factory=list)
    winning_hand: str = ""
    pot: int = 0
    player_hands: dict[str, list[Card]] = Field(default_factory=dict)


HoldemActionResult = Annotated[
    Union[
        FoldResult, CheckResult, CallResult, BetResult,
        RaiseResult, AllInResult, NewHandResult, ShowdownResult,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# WebSocket messages
# ---------------------------------------------------------------------------


class HoldemWSMessage(BaseModel):
    type: str


class HoldemGameStateMessage(HoldemWSMessage):
    type: Literal["game_state"] = "game_state"
    state: Optional[HoldemPlayerState] = None


class HoldemPlayerJoinedMessage(HoldemWSMessage):
    type: Literal["player_joined"] = "player_joined"
    player: HoldemPlayer
    players: list[HoldemPlayer] = Field(default_factory=list)


class HoldemGameStartedMessage(HoldemWSMessage):
    type: Literal["game_started"] = "game_started"
    your_cards: Optional[list[Card]] = None
    whose_turn: Optional[str] = None
    available_actions: Optional[list[str]] = None
    state: Optional[HoldemGameState] = None


class HoldemYourTurnMessage(HoldemWSMessage):
    type: Literal["your_turn"] = "your_turn"
    available_actions: list[str] = Field(default_factory=list)


class HoldemActionMessage(HoldemWSMessage):
    type: Literal["player_action"] = "player_action"
    player_id: str
    action: str
    amount: int = 0


class HoldemCommunityCardsMessage(HoldemWSMessage):
    type: Literal["community_cards"] = "community_cards"
    cards: list[Card] = Field(default_factory=list)
    betting_round: str = ""


class HoldemShowdownMessage(HoldemWSMessage):
    type: Literal["showdown"] = "showdown"
    winners: list[str] = Field(default_factory=list)
    winning_hand: str = ""
    pot: int = 0
    player_hands: dict[str, list[Card]] = Field(default_factory=dict)


class HoldemNewHandMessage(HoldemWSMessage):
    type: Literal["new_hand"] = "new_hand"
    hand_number: int = 0
    dealer: str = ""


class HoldemGameOverMessage(HoldemWSMessage):
    type: Literal["game_over"] = "game_over"
    winner: str = ""


class HoldemPongMessage(HoldemWSMessage):
    type: Literal["pong"] = "pong"


# ---------------------------------------------------------------------------
# Log entries
# ---------------------------------------------------------------------------


class HoldemLogEntryBase(BaseModel):
    type: str
    timestamp: str = ""


class HandStartedLogEntry(HoldemLogEntryBase):
    type: Literal["hand_started"] = "hand_started"
    hand_number: int = 0
    dealer: str = ""


class PlayerActionLogEntry(HoldemLogEntryBase):
    type: Literal["player_action"] = "player_action"
    player_id: str
    action: str
    amount: int = 0


class CommunityCardsLogEntry(HoldemLogEntryBase):
    type: Literal["community_cards"] = "community_cards"
    cards: list[Card] = Field(default_factory=list)
    betting_round: str = ""


class ShowdownLogEntry(HoldemLogEntryBase):
    type: Literal["showdown_log"] = "showdown_log"
    winners: list[str] = Field(default_factory=list)
    winning_hand: str = ""
    pot: int = 0


HoldemLogEntry = Annotated[
    Union[
        HandStartedLogEntry,
        PlayerActionLogEntry,
        CommunityCardsLogEntry,
        ShowdownLogEntry,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------


class HoldemJoinRequest(BaseModel):
    player_name: str
    buy_in: int = 1000


class HoldemActionRequest(BaseModel):
    player_id: str
    action: HoldemAction


class HoldemCreateGameResponse(BaseModel):
    game_id: str
    game_type: str = "holdem"
    status: str


class HoldemJoinGameResponse(BaseModel):
    player_id: str
    player: HoldemPlayer


class HoldemChatMessage(BaseModel):
    player_id: Optional[str] = None
    text: str
    timestamp: str


class HoldemChatBroadcastMessage(HoldemWSMessage):
    type: Literal["chat_message"] = "chat_message"
    player_id: Optional[str] = None
    text: str
    timestamp: str


class HoldemChatRequest(BaseModel):
    player_id: str
    text: str


class HoldemChatMessagesResponse(BaseModel):
    messages: list[HoldemChatMessage]


class OkResponse(BaseModel):
    ok: bool = True
