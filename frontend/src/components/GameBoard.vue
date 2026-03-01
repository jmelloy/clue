<template>
  <div class="game-board">
    <!-- Header -->
    <header class="game-header">
      <div class="header-left">
        <h1>CLUE</h1>
        <span class="game-id-label">Game {{ gameId }}</span>
      </div>
      <div class="header-center">
        <div v-if="gameState?.status === 'finished'" class="status-banner winner">
          Game Over! {{ winnerName }} wins!
          <div v-if="gameState.solution" class="solution-detail">
            {{ gameState.solution.suspect }} with the {{ gameState.solution.weapon }} in the {{ gameState.solution.room }}
          </div>
        </div>
        <div v-else-if="isMyTurn" class="status-banner my-turn">
          Your turn! (Turn {{ gameState?.turn_number }})
        </div>
        <div v-else class="status-banner waiting">
          {{ currentPlayerName }}'s turn (Turn {{ gameState?.turn_number }})
        </div>
      </div>
      <div class="header-right">
        <div v-if="isObserver" class="observer-badge">Observer</div>
        <div v-if="gameState?.last_roll" class="dice-display" title="Last dice roll">
          <span class="dice">{{ gameState.last_roll[0] }}</span>
          <span class="dice-plus">+</span>
          <span class="dice">{{ gameState.last_roll[1] }}</span>
          <span class="dice-eq">=</span>
          <span class="dice-total">{{ gameState.last_roll[0] + gameState.last_roll[1] }}</span>
        </div>
      </div>
    </header>

    <!-- Main content: Board + Sidebar -->
    <div class="main-layout">
      <!-- Left: Board Map + Players -->
      <div class="board-column">
        <BoardMap
          :game-state="gameState"
          :player-id="playerId"
          :selected-room="targetRoom"
          :selectable="canMove"
          @select-room="onRoomSelected"
        />

        <!-- Player Legend -->
        <div class="player-legend">
          <div
            v-for="p in gameState?.players"
            :key="p.id"
            class="legend-item"
            :class="{
              active: gameState?.whose_turn === p.id,
              eliminated: !p.active,
              'is-me': p.id === playerId,
              'wanderer-legend': p.type === 'wanderer',
            }"
          >
            <span class="legend-token" :class="{ 'wanderer-token-legend': p.type === 'wanderer' }" :style="tokenStyle(p)">{{ abbr(p.character) }}</span>
            <span class="legend-name">{{ p.name }}</span>
            <span v-if="p.type !== 'wanderer'" class="legend-character">{{ p.character }}</span>
            <span v-if="gameState?.current_room?.[p.id]" class="legend-room">{{ gameState.current_room[p.id] }}</span>
            <span v-if="!p.active" class="legend-status">eliminated</span>
            <span v-if="p.type === 'wanderer'" class="legend-wanderer-label">wandering</span>
            <span v-else-if="gameState?.whose_turn === p.id" class="legend-turn">turn</span>
          </div>
        </div>
      </div>

      <!-- Right: Sidebar -->
      <div class="sidebar-column">
        <!-- Your Cards -->
        <section v-if="!isObserver" class="sidebar-panel cards-panel">
          <h2>Your Cards</h2>
          <div class="card-hand">
            <div v-for="card in yourCards" :key="card" class="hand-card" :class="cardCategory(card)">
              <span class="card-icon">{{ cardIcon(card) }}</span>
              <span class="card-label">{{ card }}</span>
            </div>
            <div v-if="!yourCards.length" class="no-cards">No cards dealt yet</div>
          </div>
        </section>

        <!-- Card Shown notification -->
        <section v-if="cardShown" class="sidebar-panel shown-card-panel">
          <div class="shown-card-notice">
            <span class="shown-card-icon">&#128065;</span>
            <div>
              <strong>{{ playerName(cardShown.by) }}</strong> showed you:
              <span class="shown-card-name">{{ cardShown.card }}</span>
            </div>
            <button class="dismiss-btn" @click="$emit('dismiss-card-shown')">&times;</button>
          </div>
        </section>

        <!-- Show Card Request (must respond) -->
        <section v-if="showCardRequest" class="sidebar-panel show-card-request-panel">
          <h2>You Must Show a Card</h2>
          <p class="show-card-desc">
            <strong>{{ playerName(showCardRequest.suggestingPlayerId) }}</strong> suggested:
            <em>{{ showCardRequest.suspect }}</em> with the
            <em>{{ showCardRequest.weapon }}</em> in the
            <em>{{ showCardRequest.room }}</em>
          </p>
          <p class="show-card-prompt">Choose a card to reveal:</p>
          <div class="show-card-options">
            <button
              v-for="card in matchingCards"
              :key="card"
              class="show-card-btn"
              @click="doShowCard(card)"
            >{{ card }}</button>
          </div>
        </section>

        <!-- Actions -->
        <section v-if="isMyTurn && !showCardRequest && gameState?.status === 'playing' && !isObserver" class="sidebar-panel actions-panel">
          <h2>Actions</h2>

          <!-- Move -->
          <div v-if="canMove" class="action-group">
            <h3>Move</h3>
            <p class="action-hint">Click a room on the board or select below:</p>
            <select v-model="targetRoom" class="action-select">
              <option value="">-- Choose a room --</option>
              <option v-for="room in ROOMS" :key="room" :value="room">{{ room }}</option>
            </select>
            <button class="action-btn move-btn" :disabled="!targetRoom" @click="doMove">
              Roll &amp; Move{{ targetRoom ? ' to ' + targetRoom : '' }}
            </button>
          </div>

          <!-- Suggest -->
          <div v-if="canSuggest" class="action-group">
            <h3>Suggest (in {{ myCurrentRoom }})</h3>
            <select v-model="suggestSuspect" class="action-select">
              <option value="">-- Suspect --</option>
              <option v-for="s in SUSPECTS" :key="s" :value="s">{{ s }}</option>
            </select>
            <select v-model="suggestWeapon" class="action-select">
              <option value="">-- Weapon --</option>
              <option v-for="w in WEAPONS" :key="w" :value="w">{{ w }}</option>
            </select>
            <button
              class="action-btn suggest-btn"
              :disabled="!suggestSuspect || !suggestWeapon"
              @click="doSuggest"
            >Make Suggestion</button>
          </div>

          <!-- Accuse -->
          <div v-if="canAccuse" class="action-group accuse-group">
            <button v-if="!showAccuseForm" class="action-btn toggle-accuse-btn" @click="showAccuseForm = true">
              Make Final Accusation...
            </button>
            <div v-if="showAccuseForm" class="accuse-form">
              <h3>Final Accusation</h3>
              <p class="action-warning">Warning: A wrong accusation eliminates you from the game!</p>
              <select v-model="accuseSuspect" class="action-select">
                <option value="">-- Suspect --</option>
                <option v-for="s in SUSPECTS" :key="s" :value="s">{{ s }}</option>
              </select>
              <select v-model="accuseWeapon" class="action-select">
                <option value="">-- Weapon --</option>
                <option v-for="w in WEAPONS" :key="w" :value="w">{{ w }}</option>
              </select>
              <select v-model="accuseRoom" class="action-select">
                <option value="">-- Room --</option>
                <option v-for="r in ROOMS" :key="r" :value="r">{{ r }}</option>
              </select>
              <div class="accuse-buttons">
                <button
                  class="action-btn accuse-btn"
                  :disabled="!accuseSuspect || !accuseWeapon || !accuseRoom"
                  @click="doAccuse"
                >Accuse!</button>
                <button class="action-btn cancel-btn" @click="showAccuseForm = false">Cancel</button>
              </div>
            </div>
          </div>

          <!-- End Turn -->
          <div v-if="canEndTurn" class="action-group">
            <button class="action-btn end-turn-btn" @click="doEndTurn">End Turn</button>
          </div>
        </section>

        <!-- Waiting message when not your turn -->
        <section v-if="!isMyTurn && !showCardRequest && gameState?.status === 'playing' && !isObserver" class="sidebar-panel waiting-panel">
          <div class="waiting-message">
            Waiting for <strong>{{ currentPlayerName }}</strong>'s turn...
          </div>
        </section>

        <!-- Detective Notes -->
        <section v-if="!isObserver" class="sidebar-panel notes-panel">
          <DetectiveNotes ref="notesRef" :your-cards="yourCards" />
        </section>
      </div>
    </div>

    <!-- Bottom: Chat -->
    <div class="chat-row">
      <section class="chat-panel-wrapper">
        <ChatPanel
          :messages="chatMessages"
          :players="gameState?.players"
          @send-message="$emit('send-chat', $event)"
        />
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import BoardMap from './BoardMap.vue'
import ChatPanel from './ChatPanel.vue'
import DetectiveNotes from './DetectiveNotes.vue'

const SUSPECTS = ['Miss Scarlett', 'Colonel Mustard', 'Mrs. White', 'Reverend Green', 'Mrs. Peacock', 'Professor Plum']
const WEAPONS = ['Candlestick', 'Knife', 'Lead Pipe', 'Revolver', 'Rope', 'Wrench']
const ROOMS = ['Kitchen', 'Ballroom', 'Conservatory', 'Billiard Room', 'Library', 'Study', 'Hall', 'Lounge', 'Dining Room']

const CHARACTER_COLORS = {
  'Miss Scarlett':    { bg: '#e74c3c', text: '#fff' },
  'Colonel Mustard':  { bg: '#f39c12', text: '#1a1a2e' },
  'Mrs. White':       { bg: '#ecf0f1', text: '#1a1a2e' },
  'Reverend Green':   { bg: '#27ae60', text: '#fff' },
  'Mrs. Peacock':     { bg: '#2980b9', text: '#fff' },
  'Professor Plum':   { bg: '#8e44ad', text: '#fff' },
}

const CHARACTER_ABBR = {
  'Miss Scarlett': 'Sc',
  'Colonel Mustard': 'Mu',
  'Mrs. White': 'Wh',
  'Reverend Green': 'Gr',
  'Mrs. Peacock': 'Pe',
  'Professor Plum': 'Pl',
}

const props = defineProps({
  gameId: String,
  playerId: String,
  gameState: Object,
  yourCards: { type: Array, default: () => [] },
  availableActions: { type: Array, default: () => [] },
  showCardRequest: Object,
  cardShown: Object,
  chatMessages: { type: Array, default: () => [] },
  isObserver: { type: Boolean, default: false },
})

const emit = defineEmits(['action', 'send-chat', 'dismiss-card-shown'])

const notesRef = ref(null)

// Form state
const targetRoom = ref('')
const suggestSuspect = ref('')
const suggestWeapon = ref('')
const accuseSuspect = ref('')
const accuseWeapon = ref('')
const accuseRoom = ref('')
const showAccuseForm = ref(false)

// Computed
const isMyTurn = computed(() => props.gameState?.whose_turn === props.playerId)
const myCurrentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const canMove = computed(() => props.availableActions.includes('move'))
const canSuggest = computed(() => props.availableActions.includes('suggest'))
const canAccuse = computed(() => props.availableActions.includes('accuse'))
const canEndTurn = computed(() => props.availableActions.includes('end_turn'))

const currentPlayerName = computed(() => {
  return playerName(props.gameState?.whose_turn)
})

const winnerName = computed(() => {
  return playerName(props.gameState?.winner)
})

const matchingCards = computed(() => {
  if (!props.showCardRequest) return []
  const suggestion = [props.showCardRequest.suspect, props.showCardRequest.weapon, props.showCardRequest.room]
  return props.yourCards.filter(c => suggestion.includes(c))
})

function playerName(pid) {
  if (!pid) return '?'
  const p = props.gameState?.players?.find(pl => pl.id === pid)
  return p ? p.name : pid
}

function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

function tokenStyle(player) {
  const colors = CHARACTER_COLORS[player.character] ?? { bg: '#666', text: '#fff' }
  const style = { backgroundColor: colors.bg, color: colors.text }
  if (player.type === 'wanderer') style.opacity = 0.5
  return style
}

function cardCategory(card) {
  if (SUSPECTS.includes(card)) return 'card-suspect'
  if (WEAPONS.includes(card)) return 'card-weapon'
  if (ROOMS.includes(card)) return 'card-room'
  return ''
}

function cardIcon(card) {
  if (SUSPECTS.includes(card)) return '\u{1F464}'
  if (WEAPONS.includes(card)) return '\u{1F52A}'
  if (ROOMS.includes(card)) return '\u{1F3E0}'
  return '\u{1F0CF}'
}

// Actions
function onRoomSelected(room) {
  if (canMove.value) {
    targetRoom.value = room
  }
}

function doMove() {
  emit('action', { type: 'move', room: targetRoom.value })
  targetRoom.value = ''
}

function doSuggest() {
  emit('action', { type: 'suggest', suspect: suggestSuspect.value, weapon: suggestWeapon.value, room: myCurrentRoom.value })
  suggestSuspect.value = ''
  suggestWeapon.value = ''
}

function doShowCard(card) {
  emit('action', { type: 'show_card', card })
}

function doAccuse() {
  emit('action', { type: 'accuse', suspect: accuseSuspect.value, weapon: accuseWeapon.value, room: accuseRoom.value })
  showAccuseForm.value = false
}

function doEndTurn() {
  emit('action', { type: 'end_turn' })
}

// Auto-mark shown cards in detective notes
watch(
  () => props.cardShown,
  (shown) => {
    if (shown?.card && notesRef.value) {
      notesRef.value.markCard(shown.card, 'seen')
    }
  }
)

// Reset accuse form on turn change
watch(
  () => props.gameState?.whose_turn,
  () => {
    showAccuseForm.value = false
  }
)
</script>

<style scoped>
.game-board {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

/* Header */
.game-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #16213e;
  border-radius: 10px;
  padding: 0.6rem 1.2rem;
  gap: 1rem;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.header-left h1 {
  font-size: 1.6rem;
  color: #c9a84c;
  letter-spacing: 0.15em;
  margin: 0;
}

.game-id-label {
  font-size: 0.75rem;
  color: #667;
  font-family: monospace;
}

.header-center {
  flex: 1;
  text-align: center;
}

.status-banner {
  font-size: 1rem;
  font-weight: bold;
  padding: 0.3rem 1rem;
  border-radius: 20px;
  display: inline-block;
}

.status-banner.my-turn {
  background: rgba(241, 196, 15, 0.2);
  color: #f1c40f;
  border: 1px solid rgba(241, 196, 15, 0.3);
}

.status-banner.waiting {
  color: #8899aa;
}

.status-banner.winner {
  background: rgba(46, 204, 113, 0.2);
  color: #2ecc71;
  border: 1px solid rgba(46, 204, 113, 0.3);
}

.solution-detail {
  font-size: 0.85rem;
  font-weight: normal;
  margin-top: 0.2rem;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.observer-badge {
  background: #3498db;
  color: #fff;
  font-size: 0.7rem;
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.dice-display {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.9rem;
}

.dice {
  background: #fff;
  color: #1a1a2e;
  width: 28px;
  height: 28px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 0.95rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}

.dice-plus, .dice-eq {
  color: #667;
  font-size: 0.8rem;
}

.dice-total {
  color: #f1c40f;
  font-weight: bold;
  font-size: 1.1rem;
}

/* Main layout */
.main-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 0.75rem;
  min-height: 400px;
}

/* Board column */
.board-column {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/* Player legend */
.player-legend {
  background: #16213e;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-size: 0.75rem;
  background: rgba(255,255,255,0.03);
  border: 1px solid transparent;
}

.legend-item.active {
  border-color: rgba(241, 196, 15, 0.4);
  background: rgba(241, 196, 15, 0.1);
}

.legend-item.eliminated {
  opacity: 0.4;
}

.legend-item.is-me {
  border-color: rgba(52, 152, 219, 0.4);
}

.legend-token {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 0.55rem;
  font-weight: bold;
  flex-shrink: 0;
  box-shadow: 0 1px 2px rgba(0,0,0,0.3);
}

.legend-name {
  font-weight: bold;
  color: #ddd;
}

.legend-character {
  color: #778;
  font-style: italic;
}

.legend-room {
  color: #c9a84c;
  font-size: 0.7rem;
}

.legend-status {
  color: #e74c3c;
  font-size: 0.65rem;
  text-transform: uppercase;
}

.legend-turn {
  background: #f1c40f;
  color: #1a1a2e;
  font-size: 0.6rem;
  padding: 0.05rem 0.3rem;
  border-radius: 6px;
  font-weight: bold;
  text-transform: uppercase;
}

.wanderer-legend {
  opacity: 0.6;
}

.wanderer-token-legend {
  border: 1.5px dashed rgba(255, 255, 255, 0.4);
}

.legend-wanderer-label {
  color: #667;
  font-size: 0.6rem;
  font-style: italic;
}

/* Sidebar */
.sidebar-column {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  overflow-y: auto;
  max-height: calc(100vh - 180px);
}

.sidebar-panel {
  background: #16213e;
  border-radius: 8px;
  padding: 0.8rem;
}

.sidebar-panel h2 {
  color: #c9a84c;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

/* Cards */
.card-hand {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.hand-card {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.55rem;
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 500;
  border: 1px solid;
}

.card-suspect {
  background: rgba(231, 76, 60, 0.15);
  border-color: rgba(231, 76, 60, 0.3);
  color: #e8a49c;
}

.card-weapon {
  background: rgba(52, 152, 219, 0.15);
  border-color: rgba(52, 152, 219, 0.3);
  color: #94c6e8;
}

.card-room {
  background: rgba(46, 204, 113, 0.15);
  border-color: rgba(46, 204, 113, 0.3);
  color: #8ed8ad;
}

.card-icon {
  font-size: 0.85rem;
}

.card-label {
  white-space: nowrap;
}

.no-cards {
  color: #556;
  font-style: italic;
  font-size: 0.85rem;
}

/* Card shown notification */
.shown-card-panel {
  border: 1px solid rgba(52, 152, 219, 0.4);
  background: rgba(52, 152, 219, 0.1);
}

.shown-card-notice {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
}

.shown-card-icon {
  font-size: 1.3rem;
  flex-shrink: 0;
}

.shown-card-name {
  color: #3498db;
  font-weight: bold;
}

.dismiss-btn {
  background: none;
  border: none;
  color: #888;
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0;
  margin-left: auto;
}

.dismiss-btn:hover {
  color: #fff;
}

/* Show card request */
.show-card-request-panel {
  border: 2px solid #e74c3c;
  background: rgba(231, 76, 60, 0.1);
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% { border-color: #e74c3c; }
  50% { border-color: #c0392b; box-shadow: 0 0 12px rgba(231, 76, 60, 0.3); }
}

.show-card-desc {
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

.show-card-desc em {
  color: #c9a84c;
}

.show-card-prompt {
  font-size: 0.8rem;
  color: #aaa;
  margin-bottom: 0.4rem;
}

.show-card-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.show-card-btn {
  background: #e74c3c;
  color: #fff;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.85rem;
  transition: background 0.2s;
}

.show-card-btn:hover {
  background: #c0392b;
}

/* Actions */
.action-group {
  margin-bottom: 0.75rem;
}

.action-group h3 {
  font-size: 0.8rem;
  color: #8899aa;
  margin-bottom: 0.3rem;
}

.action-hint {
  font-size: 0.75rem;
  color: #667;
  margin-bottom: 0.3rem;
}

.action-select {
  display: block;
  width: 100%;
  margin-bottom: 0.35rem;
  padding: 0.4rem 0.5rem;
  border-radius: 5px;
  border: 1px solid #334;
  background: #0f3460;
  color: #eee;
  font-size: 0.85rem;
}

.action-btn {
  display: block;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.85rem;
  transition: all 0.2s;
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.move-btn {
  background: #c9a84c;
  color: #1a1a2e;
}

.move-btn:not(:disabled):hover {
  background: #d4b85c;
}

.suggest-btn {
  background: #3498db;
  color: #fff;
}

.suggest-btn:not(:disabled):hover {
  background: #2980b9;
}

.toggle-accuse-btn {
  background: transparent;
  border: 1px solid #555;
  color: #888;
  font-weight: normal;
}

.toggle-accuse-btn:hover {
  border-color: #e74c3c;
  color: #e74c3c;
}

.action-warning {
  font-size: 0.75rem;
  color: #e74c3c;
  margin-bottom: 0.4rem;
  font-style: italic;
}

.accuse-buttons {
  display: flex;
  gap: 0.4rem;
}

.accuse-btn {
  background: #e74c3c;
  color: #fff;
  flex: 1;
}

.accuse-btn:not(:disabled):hover {
  background: #c0392b;
}

.cancel-btn {
  background: #444;
  color: #ccc;
  flex: 0;
  white-space: nowrap;
}

.cancel-btn:hover {
  background: #555;
}

.end-turn-btn {
  background: #27ae60;
  color: #fff;
}

.end-turn-btn:hover {
  background: #229954;
}

/* Waiting message */
.waiting-panel {
  text-align: center;
}

.waiting-message {
  padding: 0.5rem;
  color: #8899aa;
  font-size: 0.9rem;
}

/* Notes panel */
.notes-panel {
  max-height: 300px;
  overflow-y: auto;
}

/* Chat row */
.chat-row {
  display: flex;
  gap: 0.75rem;
}

.chat-panel-wrapper {
  flex: 1;
  background: #16213e;
  border-radius: 8px;
  padding: 0.8rem;
}

/* Responsive */
@media (max-width: 900px) {
  .main-layout {
    grid-template-columns: 1fr;
  }

  .sidebar-column {
    max-height: none;
  }
}
</style>
