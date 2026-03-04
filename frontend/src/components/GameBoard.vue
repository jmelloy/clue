<template>
  <div class="game-board">
    <!-- Header -->
    <header class="game-header">
      <div class="header-left">
        <h1>CLUE</h1>
        <span class="game-id-label">Case {{ gameId }}</span>
      </div>
      <div class="header-center">
        <div v-if="gameState?.status === 'finished'" class="status-banner winner">
          Case Closed! {{ winnerName }} wins!
          <div v-if="gameState.solution" class="solution-detail">
            <span class="highlight-suspect">{{ gameState.solution.suspect }}</span> with the
            <span class="highlight-weapon">{{ gameState.solution.weapon }}</span> in the
            <span class="highlight-room">{{ gameState.solution.room }}</span>
          </div>
        </div>
        <div v-else-if="isMyTurn" class="status-banner my-turn">
          Your turn! (Turn {{ gameState?.turn_number }})
        </div>
        <div v-else class="status-banner waiting">
          {{ currentPlayerName }}'s turn (Turn {{ gameState?.turn_number }})
          <span v-if="countdown !== null && !timerForMe" class="header-timer">- auto-end in {{ countdown }}s</span>
        </div>
      </div>
      <div class="header-right">
        <div v-if="isObserver" class="observer-badge">Observer</div>
        <div v-if="gameState?.last_roll" class="dice-display" title="Last dice roll">
          <span class="dice" v-for="(die, idx) in gameState.last_roll" :key="idx">{{ die }}</span>
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
          :reachable-rooms="reachableRooms"
          :reachable-positions="reachablePositions"
          @select-room="onRoomSelected"
          @select-position="onPositionSelected"
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
          <h2 class="collapsible-header" @click="cardsCollapsed = !cardsCollapsed">
            <span>Your Cards</span>
            <span class="collapse-indicator" :class="{ collapsed: cardsCollapsed }">&#9660;</span>
          </h2>
          <div v-if="!cardsCollapsed">
            <div v-if="!yourCards.length" class="no-cards">No cards dealt yet</div>
            <template v-else>
              <div v-if="suspectCards.length" class="card-group">
                <h3 class="card-group-label card-group-suspect">Suspects</h3>
                <div class="card-hand">
                  <div v-for="card in suspectCards" :key="card" class="hand-card card-suspect">
                    <span class="card-icon">{{ cardIcon(card) }}</span>
                    <span class="card-label">{{ card }}</span>
                  </div>
                </div>
              </div>
              <div v-if="weaponCards.length" class="card-group">
                <h3 class="card-group-label card-group-weapon">Weapons</h3>
                <div class="card-hand">
                  <div v-for="card in weaponCards" :key="card" class="hand-card card-weapon">
                    <span class="card-icon">{{ cardIcon(card) }}</span>
                    <span class="card-label">{{ card }}</span>
                  </div>
                </div>
              </div>
              <div v-if="roomCards.length" class="card-group">
                <h3 class="card-group-label card-group-room">Rooms</h3>
                <div class="card-hand">
                  <div v-for="card in roomCards" :key="card" class="hand-card card-room">
                    <span class="card-icon">{{ cardIcon(card) }}</span>
                    <span class="card-label">{{ card }}</span>
                  </div>
                </div>
              </div>
            </template>
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
            <span class="highlight-suspect">{{ showCardRequest.suspect }}</span> with the
            <span class="highlight-weapon">{{ showCardRequest.weapon }}</span> in the
            <span class="highlight-room">{{ showCardRequest.room }}</span>
          </p>
          <p class="show-card-prompt">Choose a card to reveal:</p>
          <div class="show-card-options">
            <button
              v-for="card in matchingCards"
              :key="card"
              class="show-card-btn"
              :class="cardCategory(card)"
              @click="doShowCard(card)"
            ><span class="card-icon">{{ cardIcon(card) }}</span> {{ card }}</button>
          </div>
        </section>

        <!-- Actions -->
        <section v-if="isMyTurn && !showCardRequest && gameState?.status === 'playing' && !isObserver" class="sidebar-panel actions-panel">
          <h2>Actions</h2>

          <!-- Secret Passage -->
          <div v-if="canSecretPassage" class="action-group">
            <h3>Secret Passage</h3>
            <p class="action-hint">You're in {{ myCurrentRoom }} — take the secret passage?</p>
            <button class="action-btn passage-btn" @click="doSecretPassage">
              Use Passage to {{ passageDestination }}
            </button>
          </div>

          <!-- Roll Dice -->
          <div v-if="canRoll" class="action-group">
            <h3>Roll Dice</h3>
            <button class="action-btn roll-btn" @click="doRoll">
              Roll Dice
            </button>
          </div>

          <!-- Move (choose room after rolling) -->
          <div v-if="canMove" class="action-group">
            <h3>Move (rolled {{ gameState?.last_roll?.reduce((a, b) => a + b, 0) }})</h3>
            <p class="action-hint">
              Click a highlighted room on the board or select below:
              <span v-if="reachableRooms.length" class="reachable-count">{{ reachableRooms.length }} room{{ reachableRooms.length !== 1 ? 's' : '' }} reachable</span>
            </p>
            <select v-model="targetRoom" class="action-select">
              <option value="">-- Choose a room --</option>
              <option v-for="room in ROOMS" :key="room" :value="room" :class="{ 'reachable-option': reachableRooms.includes(room) }">
                {{ room }}{{ reachableRooms.includes(room) ? ' ✓' : '' }}
              </option>
            </select>
            <button class="action-btn move-btn" :disabled="!targetRoom" @click="doMove">
              Move{{ targetRoom ? ' to ' + targetRoom : '' }}
            </button>
          </div>

          <!-- Suggest -->
          <div v-if="canSuggest" class="action-group">
            <h3>Suggest (in <span class="highlight-room">{{ myCurrentRoom }}</span>)</h3>
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
            <div v-if="timerForMe" class="auto-end-timer">
              <div class="timer-bar">
                <div class="timer-bar-fill" :style="{ width: (countdown / (props.autoEndTimer?.seconds || 15)) * 100 + '%' }"></div>
              </div>
              <span class="timer-text">Auto-ending turn in {{ countdown }}s</span>
            </div>
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
          <DetectiveNotes ref="notesRef" :your-cards="yourCards" :saved-notes="savedNotes" @notes-changed="onNotesChanged" />
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
import { ref, computed, watch, onUnmounted } from 'vue'
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
  autoEndTimer: { type: Object, default: null },
  reachableRooms: { type: Array, default: () => [] },
  reachablePositions: { type: Array, default: () => [] },
  savedNotes: { type: Object, default: null },
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
const cardsCollapsed = ref(false)

// Auto-end timer countdown
const countdown = ref(null)
let countdownInterval = null

function clearCountdown() {
  if (countdownInterval) {
    clearInterval(countdownInterval)
    countdownInterval = null
  }
  countdown.value = null
}

watch(
  () => props.autoEndTimer,
  (timer) => {
    clearCountdown()
    if (timer && timer.seconds > 0) {
      const updateCountdown = () => {
        const elapsed = (Date.now() - timer.startedAt) / 1000
        const remaining = Math.max(0, Math.ceil(timer.seconds - elapsed))
        countdown.value = remaining
        if (remaining <= 0) clearCountdown()
      }
      updateCountdown()
      countdownInterval = setInterval(updateCountdown, 1000)
    }
  },
  { immediate: true }
)

onUnmounted(() => clearCountdown())

const timerForMe = computed(() => countdown.value !== null && props.autoEndTimer?.playerId === props.playerId)

// Computed
const isMyTurn = computed(() => props.gameState?.whose_turn === props.playerId)
const myCurrentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const canSecretPassage = computed(() => props.availableActions.includes('secret_passage'))
const canRoll = computed(() => props.availableActions.includes('roll'))
const canMove = computed(() => props.availableActions.includes('move'))
const canSuggest = computed(() => props.availableActions.includes('suggest'))
const canAccuse = computed(() => props.availableActions.includes('accuse'))
const canEndTurn = computed(() => props.availableActions.includes('end_turn'))

const SECRET_PASSAGES = {
  'Study': 'Kitchen',
  'Kitchen': 'Study',
  'Lounge': 'Conservatory',
  'Conservatory': 'Lounge',
}
const passageDestination = computed(() => SECRET_PASSAGES[myCurrentRoom.value] ?? '?')

const currentPlayerName = computed(() => {
  return playerName(props.gameState?.whose_turn)
})

const winnerName = computed(() => {
  return playerName(props.gameState?.winner)
})

const suspectCards = computed(() => props.yourCards.filter(c => SUSPECTS.includes(c)))
const weaponCards = computed(() => props.yourCards.filter(c => WEAPONS.includes(c)))
const roomCards = computed(() => props.yourCards.filter(c => ROOMS.includes(c)))

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
    emit('action', { type: 'move', room })
    targetRoom.value = ''
  }
}

function onPositionSelected(position) {
  if (canMove.value) {
    emit('action', { type: 'move', position })
  }
}

function doSecretPassage() {
  emit('action', { type: 'secret_passage' })
}

function doRoll() {
  emit('action', { type: 'roll' })
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

// Debounced save of detective notes to backend
let saveNotesTimer = null
function onNotesChanged(notesData) {
  if (saveNotesTimer) clearTimeout(saveNotesTimer)
  saveNotesTimer = setTimeout(() => {
    fetch(`/games/${props.gameId}/notes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: props.playerId, notes: notesData }),
    }).catch(() => {})
  }, 500)
}

onUnmounted(() => {
  if (saveNotesTimer) clearTimeout(saveNotesTimer)
})

// Auto-mark shown cards in detective notes
watch(
  () => props.cardShown,
  (shown) => {
    if (shown?.card && notesRef.value) {
      notesRef.value.markCard(shown.card, 'seen', playerName(shown.by))
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
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.game-board {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  font-family: 'Crimson Text', Georgia, serif;
}

/* Header */
.game-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.95), rgba(18, 14, 10, 0.97));
  border: 1px solid rgba(212, 168, 73, 0.1);
  border-radius: 8px;
  padding: 0.6rem 1.2rem;
  gap: 1rem;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.header-left h1 {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.5rem;
  font-weight: 900;
  color: #d4a849;
  letter-spacing: 0.15em;
  margin: 0;
  text-shadow: 0 0 20px rgba(212, 168, 73, 0.15);
}

.game-id-label {
  font-size: 0.7rem;
  color: #5a5040;
  letter-spacing: 0.08em;
}

.header-center {
  flex: 1;
  text-align: center;
}

.status-banner {
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.3rem 1rem;
  border-radius: 20px;
  display: inline-block;
  letter-spacing: 0.02em;
}

.status-banner.my-turn {
  background: rgba(212, 168, 73, 0.15);
  color: #d4a849;
  border: 1px solid rgba(212, 168, 73, 0.25);
}

.status-banner.waiting {
  color: #6a6050;
}

.status-banner.winner {
  background: rgba(46, 160, 80, 0.15);
  color: #4caf50;
  border: 1px solid rgba(46, 160, 80, 0.25);
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
  background: rgba(212, 168, 73, 0.12);
  color: #d4a849;
  font-size: 0.65rem;
  padding: 0.2rem 0.6rem;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.dice-display {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.dice {
  background: #d4a849;
  color: #1a1008;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.95rem;
  font-family: 'Playfair Display', Georgia, serif;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
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
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.9), rgba(18, 14, 10, 0.95));
  border: 1px solid rgba(212, 168, 73, 0.08);
  border-radius: 6px;
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
  border-radius: 4px;
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  transition: border-color 0.2s;
}

.legend-item.active {
  border-color: rgba(212, 168, 73, 0.3);
  background: rgba(212, 168, 73, 0.06);
}

.legend-item.eliminated {
  opacity: 0.35;
}

.legend-item.is-me {
  border-color: rgba(212, 168, 73, 0.15);
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
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}

.legend-name {
  font-weight: 600;
  color: #e8dcc8;
}

.legend-character {
  color: #5a5040;
  font-style: italic;
}

.legend-room {
  color: #d4a849;
  font-size: 0.7rem;
}

.legend-status {
  color: #c45050;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.legend-turn {
  background: #d4a849;
  color: #1a1008;
  font-size: 0.6rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.wanderer-legend {
  opacity: 0.5;
}

.wanderer-token-legend {
  border: 1.5px dashed rgba(255, 255, 255, 0.3);
}

.legend-wanderer-label {
  color: #4a4030;
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
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.95), rgba(18, 14, 10, 0.97));
  border: 1px solid rgba(212, 168, 73, 0.08);
  border-radius: 6px;
  padding: 0.8rem;
}

.sidebar-panel h2 {
  font-family: 'Playfair Display', Georgia, serif;
  color: #d4a849;
  font-size: 0.9rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
  letter-spacing: 0.03em;
}

/* Collapsible header */
.collapsible-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.collapsible-header:hover {
  opacity: 0.85;
}

.collapse-indicator {
  font-size: 0.6rem;
  transition: transform 0.2s ease;
  color: #5a5040;
}

.collapse-indicator.collapsed {
  transform: rotate(-90deg);
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
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 500;
  border: 1px solid;
}

.card-suspect {
  background: rgba(155, 27, 48, 0.15);
  border-color: rgba(155, 27, 48, 0.3);
  color: #d4888a;
}

.card-weapon {
  background: rgba(26, 58, 107, 0.2);
  border-color: rgba(26, 58, 107, 0.4);
  color: #7aa8d4;
}

.card-room {
  background: rgba(26, 107, 60, 0.15);
  border-color: rgba(26, 107, 60, 0.3);
  color: #7ac89a;
}

.card-group {
  margin-bottom: 0.5rem;
}

.card-group:last-child {
  margin-bottom: 0;
}

.card-group-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.25rem;
  font-weight: 600;
}

.card-group-suspect { color: #d4888a; }
.card-group-weapon { color: #7aa8d4; }
.card-group-room { color: #7ac89a; }

.card-icon {
  font-size: 0.85rem;
}

.card-label {
  white-space: nowrap;
}

.no-cards {
  color: #4a4030;
  font-style: italic;
  font-size: 0.85rem;
}

/* Card shown notification */
.shown-card-panel {
  border-color: rgba(26, 58, 107, 0.4);
  background: linear-gradient(135deg, rgba(26, 58, 107, 0.15), rgba(18, 14, 10, 0.95));
}

.shown-card-notice {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  color: #e8dcc8;
}

.shown-card-icon {
  font-size: 1.3rem;
  flex-shrink: 0;
}

.shown-card-name {
  color: #7aa8d4;
  font-weight: bold;
}

.dismiss-btn {
  background: none;
  border: none;
  color: #5a5040;
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0;
  margin-left: auto;
  transition: color 0.2s;
}

.dismiss-btn:hover {
  color: #e8dcc8;
}

/* Show card request */
.show-card-request-panel {
  border: 1.5px solid rgba(155, 27, 48, 0.6);
  background: linear-gradient(135deg, rgba(155, 27, 48, 0.1), rgba(18, 14, 10, 0.95));
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% { border-color: rgba(155, 27, 48, 0.6); }
  50% { border-color: rgba(155, 27, 48, 0.9); box-shadow: 0 0 12px rgba(155, 27, 48, 0.15); }
}

.show-card-desc {
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
  color: #e8dcc8;
}

/* Card type color highlights */
.highlight-suspect { color: #d4888a; font-weight: bold; }
.highlight-weapon { color: #7aa8d4; font-weight: bold; }
.highlight-room { color: #7ac89a; font-weight: bold; }

.show-card-prompt {
  font-size: 0.8rem;
  color: #6a6050;
  margin-bottom: 0.4rem;
}

.show-card-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.show-card-btn {
  color: #e8dcc8;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: #9b1b30;
}

.show-card-btn:hover {
  filter: brightness(1.15);
  transform: translateY(-1px);
}

.show-card-btn.card-suspect { background: #9b1b30; }
.show-card-btn.card-weapon { background: #1a3a6b; }
.show-card-btn.card-room { background: #1a6b3c; }

/* Actions */
.action-group {
  margin-bottom: 0.75rem;
}

.action-group h3 {
  font-size: 0.8rem;
  color: #8a7e6b;
  margin-bottom: 0.3rem;
  font-weight: 600;
}

.action-hint {
  font-size: 0.75rem;
  color: #5a5040;
  margin-bottom: 0.3rem;
}

.reachable-count {
  display: inline-block;
  color: #4caf50;
  font-weight: bold;
  margin-left: 0.3rem;
}

.action-select {
  display: block;
  width: 100%;
  margin-bottom: 0.35rem;
  padding: 0.45rem 0.6rem;
  border-radius: 4px;
  border: 1px solid rgba(212, 168, 73, 0.12);
  background: rgba(255, 255, 255, 0.03);
  color: #e8dcc8;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  appearance: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

.action-select:focus {
  border-color: rgba(212, 168, 73, 0.3);
  outline: none;
  box-shadow: 0 0 0 2px rgba(212, 168, 73, 0.06);
}

.action-btn {
  display: block;
  width: 100%;
  padding: 0.55rem 0.75rem;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
  transition: all 0.25s;
  letter-spacing: 0.02em;
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.passage-btn {
  background: linear-gradient(135deg, #5c2d82, #4a2268);
  color: #e8dcc8;
}

.passage-btn:hover {
  box-shadow: 0 3px 12px rgba(92, 45, 130, 0.2);
  transform: translateY(-1px);
}

.roll-btn {
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
}

.roll-btn:hover {
  box-shadow: 0 3px 12px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.move-btn {
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
}

.move-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.suggest-btn {
  background: linear-gradient(135deg, #1a3a6b, #153058);
  color: #e8dcc8;
}

.suggest-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(26, 58, 107, 0.3);
  transform: translateY(-1px);
}

.toggle-accuse-btn {
  background: transparent;
  border: 1px solid rgba(155, 27, 48, 0.2);
  color: #6a6050;
  font-weight: normal;
}

.toggle-accuse-btn:hover {
  border-color: rgba(155, 27, 48, 0.5);
  color: #c45050;
}

.action-warning {
  font-size: 0.75rem;
  color: #c45050;
  margin-bottom: 0.4rem;
  font-style: italic;
}

.accuse-buttons {
  display: flex;
  gap: 0.4rem;
}

.accuse-btn {
  background: linear-gradient(135deg, #9b1b30, #7a1525);
  color: #e8dcc8;
  flex: 1;
}

.accuse-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(155, 27, 48, 0.25);
  transform: translateY(-1px);
}

.cancel-btn {
  background: rgba(255, 255, 255, 0.05);
  color: #6a6050;
  flex: 0;
  white-space: nowrap;
}

.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #8a7e6b;
}

.end-turn-btn {
  background: linear-gradient(135deg, #1a6b3c, #14562e);
  color: #e8dcc8;
}

.end-turn-btn:hover {
  box-shadow: 0 3px 12px rgba(26, 107, 60, 0.2);
  transform: translateY(-1px);
}

.auto-end-timer {
  margin-bottom: 0.4rem;
}

.timer-bar {
  height: 3px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.25rem;
}

.timer-bar-fill {
  height: 100%;
  background: #d4a849;
  border-radius: 2px;
  transition: width 1s linear;
}

.timer-text {
  font-size: 0.75rem;
  color: #d4a849;
  font-weight: 600;
}

.header-timer {
  font-size: 0.85rem;
  color: #d4a849;
}

/* Waiting message */
.waiting-panel {
  text-align: center;
}

.waiting-message {
  padding: 0.5rem;
  color: #6a6050;
  font-size: 0.9rem;
  font-style: italic;
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
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.95), rgba(18, 14, 10, 0.97));
  border: 1px solid rgba(212, 168, 73, 0.08);
  border-radius: 6px;
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
