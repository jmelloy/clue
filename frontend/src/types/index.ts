// =============================================================================
// Shared TypeScript types for the Clue + Hold'em frontend.
// Mirrors the backend Pydantic models in backend/app/games/*/models.py.
// =============================================================================

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

export type GameType = 'clue' | 'holdem'
export type GameStatus = 'waiting' | 'playing' | 'finished'
export type PlayerType = 'human' | 'agent' | 'llm_agent' | 'wanderer'
export type Theme = 'dark' | 'light' | 'vintage'
/** Image-based deck style, or 'css' for the built-in CSS/Unicode rendering. */
export type Deck = 'css' | 'classic' | 'modern' | 'vintage' | 'fantasy'

// ---------------------------------------------------------------------------
// Clue types
// ---------------------------------------------------------------------------

export interface CluePlayer {
  id: string
  name: string
  type: PlayerType
  character: string
  active: boolean
}

export interface Solution {
  suspect: string
  weapon: string
  room: string
}

export interface Suggestion {
  suspect: string
  weapon: string
  room: string
  suggested_by: string
  pending_show_by?: string | null
}

export interface PendingShowCard {
  player_id: string
  suggesting_player_id: string
  suspect: string
  weapon: string
  room: string
  matching_cards: string[]
}

/** [row, col] grid position on the 25×24 board. */
export type Position = [number, number]

export interface DetectiveNotes {
  notes: Record<string, string>
  shownBy?: Record<string, string>
}

export interface ClueGameState {
  game_id: string
  status: GameStatus
  players: CluePlayer[]
  whose_turn: string | null
  turn_number: number
  current_room: Record<string, string>
  player_positions: Record<string, Position>
  suggestions_this_turn: Suggestion[]
  winner: string | null
  dice_rolled: boolean
  moved: boolean
  last_roll: number[] | null
  pending_show_card: PendingShowCard | null
  was_moved_by_suggestion: Record<string, boolean>
  weapon_positions: Record<string, string>
  agent_trace_enabled: boolean
  solution?: Solution
}

export interface CluePlayerState extends ClueGameState {
  your_cards: string[]
  your_player_id: string
  available_actions: string[]
  detective_notes: DetectiveNotes | null
}

// -- Clue actions (sent to backend) --

export interface RollAction {
  type: 'roll'
}

export interface SecretPassageAction {
  type: 'secret_passage'
}

export interface MoveAction {
  type: 'move'
  room?: string | null
  position?: Position | null
}

export interface SuggestAction {
  type: 'suggest'
  suspect: string
  weapon: string
  room: string
}

export interface AccuseAction {
  type: 'accuse'
  suspect: string
  weapon: string
  room: string
}

export interface EndTurnAction {
  type: 'end_turn'
}

export interface ShowCardAction {
  type: 'show_card'
  card: string
}

export type ClueAction =
  | RollAction
  | SecretPassageAction
  | MoveAction
  | SuggestAction
  | AccuseAction
  | EndTurnAction
  | ShowCardAction

// -- Clue WebSocket messages (received from backend) --

export interface GameStateMessage {
  type: 'game_state'
  state?: CluePlayerState
  // Partial update fields (when state is absent)
  whose_turn?: string | null
  turn_number?: number
  dice_rolled?: boolean
  moved?: boolean
  last_roll?: number[] | null
  suggestions_this_turn?: Suggestion[]
  pending_show_card?: PendingShowCard | null
  player_positions?: Record<string, Position>
}

export interface PlayerJoinedMessage {
  type: 'player_joined'
  player: CluePlayer
  players: CluePlayer[]
}

export interface GameStartedMessage {
  type: 'game_started'
  your_cards?: string[]
  whose_turn?: string
  available_actions?: string[]
  state?: ClueGameState
}

export interface YourTurnMessage {
  type: 'your_turn'
  available_actions?: string[]
  reachable_rooms?: string[]
  reachable_positions?: Position[]
}

export interface AutoEndTimerMessage {
  type: 'auto_end_timer'
  player_id: string
  seconds: number
}

export interface AutoShowCardTimerMessage {
  type: 'auto_show_card_timer'
  player_id: string
  seconds: number
}

export interface ShowCardRequestMessage {
  type: 'show_card_request'
  suggesting_player_id: string
  suspect: string
  weapon: string
  room: string
  matching_cards?: string[]
  available_actions?: string[]
}

export interface DiceRolledMessage {
  type: 'dice_rolled'
  player_id: string
  dice: number
  last_roll?: number[]
  reachable_rooms?: string[]
}

export interface PlayerMovedMessage {
  type: 'player_moved'
  player_id: string
  position?: Position | null
  path?: Position[] | null
  room?: string | null
  from_room?: string | null
  dice?: number
  secret_passage?: boolean
}

export interface SuggestionMadeMessage {
  type: 'suggestion_made'
  player_id: string
  suspect: string
  weapon: string
  room: string
  pending_show_by?: string | null
  moved_suspect_player?: string | null
  player_positions?: Record<string, Position>
  weapon_positions?: Record<string, string>
  current_room?: Record<string, string>
  players_without_match?: string[]
}

export interface CardShownMessage {
  type: 'card_shown'
  shown_by: string
  card: string
  available_actions?: string[]
}

export interface CardShownPublicMessage {
  type: 'card_shown_public'
  shown_by: string
  shown_to: string
  suspect?: string
  weapon?: string
  room?: string
}

export interface AccusationMadeMessage {
  type: 'accusation_made'
  player_id: string
  correct: boolean
}

export interface GameOverMessage {
  type: 'game_over'
  player_id: string
  correct: boolean
  winner: string | null
  solution: Solution | null
}

export interface ChatMessage {
  type: 'chat_message'
  player_id: string | null
  text: string
  timestamp: string
}

export interface AgentDebugMessage {
  type: 'agent_debug'
  player_id: string
  agent_type?: string
  character?: string
  status?: string
  action_description?: string
  seen_cards?: string[]
  inferred_cards?: string[]
  unknown_suspects?: string[]
  unknown_weapons?: string[]
  unknown_rooms?: string[]
  recent_inferences?: string[]
  memory?: string[]
  unrefuted_suggestions?: Record<string, unknown>[]
  player_has_cards?: Record<string, string[]>
  decided_action?: Record<string, unknown> | null
  position?: Position | null
  room?: string | null
  reachable_rooms?: string[] | null
}

export interface PongMessage {
  type: 'pong'
}

export type ClueWSMessage =
  | GameStateMessage
  | PlayerJoinedMessage
  | GameStartedMessage
  | YourTurnMessage
  | AutoEndTimerMessage
  | AutoShowCardTimerMessage
  | ShowCardRequestMessage
  | DiceRolledMessage
  | PlayerMovedMessage
  | SuggestionMadeMessage
  | CardShownMessage
  | CardShownPublicMessage
  | AccusationMadeMessage
  | GameOverMessage
  | ChatMessage
  | AgentDebugMessage
  | PongMessage

// ---------------------------------------------------------------------------
// Hold'em types
// ---------------------------------------------------------------------------

export interface Card {
  rank: string
  suit: string
}

export interface HoldemPlayer {
  id: string
  name: string
  chips: number
  active: boolean
  folded: boolean
  current_bet: number
  all_in: boolean
  player_type: string
}

export interface HoldemGameState {
  game_id: string
  game_type: 'holdem'
  status: GameStatus
  players: HoldemPlayer[]
  buy_in: number
  allow_rebuys: boolean
  community_cards: Card[]
  pot: number
  current_bet: number
  whose_turn: string | null
  dealer_index: number
  small_blind: number
  big_blind: number
  hand_number: number
  betting_round: 'preflop' | 'flop' | 'turn' | 'river' | 'showdown'
  winner: string | null
  winning_hand: string | null
  last_raiser: string | null
  actions_this_round: number
}

export interface HoldemPlayerState extends HoldemGameState {
  your_cards: Card[]
  your_player_id: string
  available_actions: string[]
}

// -- Hold'em actions --

export interface FoldAction {
  type: 'fold'
}

export interface CheckAction {
  type: 'check'
}

export interface CallAction {
  type: 'call'
}

export interface BetAction {
  type: 'bet'
  amount: number
}

export interface RaiseAction {
  type: 'raise'
  amount: number
}

export interface AllInAction {
  type: 'all_in'
}

export type HoldemAction =
  | FoldAction
  | CheckAction
  | CallAction
  | BetAction
  | RaiseAction
  | AllInAction

// -- Hold'em WebSocket messages --

export interface HoldemGameStateMessage {
  type: 'game_state'
  state?: HoldemPlayerState
}

export interface HoldemPlayerJoinedMessage {
  type: 'player_joined'
  player: HoldemPlayer
  players: HoldemPlayer[]
}

export interface HoldemGameStartedMessage {
  type: 'game_started'
  your_cards?: Card[]
  whose_turn?: string
  available_actions?: string[]
  state?: HoldemGameState
}

export interface HoldemYourTurnMessage {
  type: 'your_turn'
  available_actions: string[]
}

export interface HoldemPlayerActionMessage {
  type: 'player_action'
  player_id: string
  action: string
  amount?: number
}

export interface HoldemCommunityCardsMessage {
  type: 'community_cards'
  cards: Card[]
  betting_round: string
}

export interface HoldemShowdownMessage {
  type: 'showdown'
  winners: string[]
  winning_hand: string
  pot: number
  player_hands: Record<string, Card[]>
}

export interface HoldemNewHandMessage {
  type: 'new_hand'
  hand_number: number
  dealer: string
}

export interface HoldemGameOverMessage {
  type: 'game_over'
  winner: string
}

export type HoldemWSMessage =
  | HoldemGameStateMessage
  | HoldemPlayerJoinedMessage
  | HoldemGameStartedMessage
  | HoldemYourTurnMessage
  | HoldemPlayerActionMessage
  | HoldemCommunityCardsMessage
  | HoldemShowdownMessage
  | HoldemNewHandMessage
  | HoldemGameOverMessage
  | ChatMessage
  | PongMessage

// ---------------------------------------------------------------------------
// Frontend-specific UI types
// ---------------------------------------------------------------------------

/** Show-card request as stored in the frontend (camelCase). */
export interface ShowCardRequestUI {
  suggestingPlayerId: string
  suspect: string
  weapon: string
  room: string
}

/** Card-shown notification as stored in the frontend. */
export interface CardShownUI {
  card: string
  by: string
}

/** Auto-end / auto-show-card timer state. */
export interface TimerState {
  playerId: string
  seconds: number
  startedAt: number
}

/** Agent debug data keyed by player_id. */
export type AgentDebugMap = Record<string, AgentDebugMessage>

/** Observer's view of a selected player's private state. */
export interface ObserverPlayerState {
  playerId: string
  your_cards: string[]
  available_actions: string[]
  detective_notes: DetectiveNotes | null
}

/** Character color pair used for player tokens / badges. */
export interface CharacterColor {
  bg: string
  text: string
  name?: string
}

/** Board data fetched from /api/clue/board endpoint. */
export interface BoardData {
  grid: string[][]
  rooms: Record<string, { name: string; top: number; left: number; width: number; height: number }>
  doors: Array<{ room: string; row: number; col: number }>
  passages: Record<string, string>
  starting_positions: Record<string, Position>
}

// ---------------------------------------------------------------------------
// Lobby / lifecycle events
// ---------------------------------------------------------------------------

export interface GameJoinedEvent {
  gameId: string
  playerId: string
  state: ClueGameState | HoldemGameState
  gameType: GameType
}

export interface ObserveEvent {
  gameId: string
  gameType: GameType
}

export interface RejoinEvent {
  gameId: string
  playerId: string
  gameType: GameType
}
