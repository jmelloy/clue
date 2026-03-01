"""Pydantic models for Clue game state and API requests."""

from __future__ import annotations

from typing import Optional

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
    last_roll: Optional[list[int]] = None
    pending_show_card: Optional[PendingShowCard] = None


class PlayerState(GameState):
    your_cards: list[str] = Field(default_factory=list)
    your_player_id: str = ""
    available_actions: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    player_id: Optional[str] = None
    text: str
    timestamp: str


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
    action: dict


class ChatRequest(BaseModel):
    player_id: str
    text: str
