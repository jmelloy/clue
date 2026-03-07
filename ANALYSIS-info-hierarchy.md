# Information Hierarchy Analysis — Discrepancies & Issues

Analysis of data flow between backend models, Redis storage, WebSocket broadcasts, HTTP APIs, frontend components, and agent subsystems.

---

## Critical: Information Leakage

### 1. `PendingShowCard.matching_cards` broadcast to all players
- **Backend**: `models.py:33-39` — `PendingShowCard` contains `matching_cards: list[str]`
- **Broadcast at**: `main.py:714-725` — `GameStateUpdateMessage` includes `pending_show_card`
- **Impact**: All connected players can see which cards the showing player holds that match a suggestion. This breaks the core Clue deduction mechanic.

### 2. Player cards endpoint has no authorization
- **Endpoint**: `GET /games/{game_id}/player/{player_id}` (`main.py:1462-1468`)
- **Impact**: Any client can request any player's `your_cards`, `detective_notes`, and `available_actions` by substituting a different `player_id`. No check that the requester is the player.

### 3. Agent debug info broadcast to all players
- **Broadcast at**: `main.py:894-910` via `_broadcast_agent_debug()`
- **Exposed data** (from `AgentDebugMessage`, `models.py:359-379`): `seen_cards`, `inferred_cards`, `player_has_cards`, `unrefuted_suggestions`, `memory`
- **Impact**: Human players can see exactly what each AI agent has deduced, including which cards other players hold.

### 4. Debug endpoint publicly accessible
- **Endpoint**: `GET /games/{game_id}/debug` (`main.py:1368-1459`)
- **Exposes**: Solution, all player cards, LLM memory, full game log
- **Impact**: Anyone who knows a game ID can retrieve the complete hidden state, including the solution.

---

## Medium: Frontend ↔ Backend Mismatches

### 5. Missing `game_type` field in GameState
- **Frontend**: `Lobby.vue:354` checks `state.game_type === 'holdem'`
- **Backend**: `GameState` model (`models.py:49-65`) has no `game_type` field
- **Impact**: Game type detection on rejoin/URL navigation may fail silently, defaulting to Clue.

### 6. `detective_notes` accessed on wrong model level
- **Frontend**: `App.vue:222` reads `msg.state.detective_notes`
- **Backend**: `detective_notes` exists on `PlayerState` (`models.py:68-72`) but not `GameState` (`models.py:49-65`). The `game_state` WebSocket message sends a `GameState`, not `PlayerState`.
- **Impact**: Detective notes may not restore correctly after reconnection via WebSocket state updates.

### 7. `/board` endpoint fetched but data never used
- **Frontend**: `App.vue:163` fetches `/board` and stores result in `boardData`
- **Frontend**: `BoardMap.vue:55-81` uses hardcoded `BOARD_ROWS` layout — never references `boardData`
- **Impact**: Wasted HTTP request on every game load. If the board layout changes in `board.py`, `BoardMap.vue` won't reflect it.

### 8. `GameState` broadcasts internal-only fields
- **Fields**: `was_moved_by_suggestion` (line 63), `agent_trace_enabled` (line 65)
- **Impact**: Internal state leaked to all clients. `was_moved_by_suggestion` reveals game mechanics that should be server-side only.

---

## Low: Structural / Maintenance Issues

### 9. Chat message categorization is fragile
- **Frontend**: `ChatPanel.vue:91-104` categorizes messages by substring matching ("suggests it was", "showed a card to", etc.)
- **Backend**: Message text is generated in `game.py` with no structured type field
- **Impact**: If backend message format changes, chat filtering breaks silently. A structured message type would be more robust.

### 10. `agent_trace_enabled` is dead code
- **Defined**: `GameState` (`models.py:65`) — `agent_trace_enabled: bool = False`
- **Never set to `True`** anywhere in the codebase
- **Impact**: Misleading field; clutters the model.

### 11. `solution` not guaranteed in `GameOverMessage`
- **Backend**: `GameOverMessage` (`models.py:301-306`) has `solution: Optional[Solution] = None`
- **Frontend**: `App.vue:435`, `GameBoard.vue:12` expect `solution` with `.suspect`, `.weapon`, `.room`
- **Impact**: If solution is not populated, the game-over screen may show incomplete information.

### 12. Hold'em vs Clue information architecture inconsistency
- **Hold'em**: Uses `HoldemPlayerState(HoldemGameState)` inheritance to properly extend game state with private fields
- **Clue**: Uses separate `GameState` and `PlayerState` models with no inheritance relationship
- **Impact**: Different patterns for the same concept; Clue's approach makes it easier to accidentally send the wrong model type.

---

## Summary Table

| # | Severity | Category | Location |
|---|----------|----------|----------|
| 1 | Critical | Info leak | `PendingShowCard.matching_cards` broadcast |
| 2 | Critical | Auth | `/player/{player_id}` no authz |
| 3 | Critical | Info leak | Agent debug broadcast to all |
| 4 | Critical | Auth | `/debug` endpoint public |
| 5 | Medium | Mismatch | Missing `game_type` in GameState |
| 6 | Medium | Mismatch | `detective_notes` on wrong model |
| 7 | Medium | Dead code | `/board` fetched but unused |
| 8 | Medium | Info leak | Internal fields in GameState |
| 9 | Low | Fragile | Chat categorization by substring |
| 10 | Low | Dead code | `agent_trace_enabled` never used |
| 11 | Low | Mismatch | `solution` optional in GameOver |
| 12 | Low | Inconsistency | Clue vs Hold'em model patterns |
