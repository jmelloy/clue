<template>
  <div class="poker-game">
    <!-- Header -->
    <header class="poker-header">
      <div class="header-left">
        <h1>TEXAS HOLD'EM</h1>
        <span class="game-id">{{ gameId }}</span>
        <span v-if="isObserver" class="observer-badge">Observer</span>
      </div>
      <div class="header-right">
        <span class="hand-info">Hand #{{ gameState?.hand_number ?? 0 }}</span>
        <span class="blind-info">Blinds {{ gameState?.small_blind ?? 10 }}/{{ gameState?.big_blind ?? 20 }}</span>
      </div>
    </header>

    <!-- Status Banner -->
    <div class="status-banner" :class="statusClass">
      <template v-if="gameState?.status === 'finished'">
        Game Over! {{ winnerName }} wins the tournament!
      </template>
      <template v-else-if="isMyTurn">
        Your turn — {{ bettingRoundLabel }}
      </template>
      <template v-else-if="gameState?.whose_turn">
        {{ currentTurnName }}'s turn — {{ bettingRoundLabel }}
      </template>
      <template v-else>
        Waiting...
      </template>
    </div>

    <!-- Showdown overlay -->
    <div v-if="showdownData" class="showdown-overlay" @click="dismissShowdown">
      <div class="showdown-card" @click.stop>
        <h2>Showdown</h2>
        <div class="showdown-winners">
          <span v-for="wid in showdownData.winners" :key="wid" class="winner-name">
            {{ playerName(wid) }}
          </span>
          wins with <strong>{{ showdownData.winning_hand }}</strong>
        </div>
        <div class="showdown-pot">Pot: {{ showdownData.pot }}</div>
        <div class="showdown-hands">
          <div v-for="(cards, pid) in showdownData.player_hands" :key="pid" class="showdown-hand">
            <span class="hand-player">{{ playerName(pid) }}:</span>
            <span class="hand-cards">
              <span
                v-for="(c, i) in cards"
                :key="i"
                class="card"
                :class="suitClass(c.suit)"
              >{{ c.rank }}{{ suitSymbol(c.suit) }}</span>
            </span>
          </div>
        </div>
        <button class="dismiss-btn" @click="dismissShowdown">OK</button>
      </div>
    </div>

    <!-- Table Area -->
    <div class="table-area">
      <div class="felt">
        <!-- Pot -->
        <div class="pot-display">
          <span class="pot-label">Pot</span>
          <span class="pot-amount">{{ gameState?.pot ?? 0 }}</span>
        </div>

        <!-- Community Cards -->
        <div class="community-cards">
          <div
            v-for="i in 5"
            :key="i"
            class="card-slot"
            :class="{ dealt: communityCards[i - 1] }"
          >
            <template v-if="communityCards[i - 1]">
              <span
                class="card"
                :class="suitClass(communityCards[i - 1].suit)"
              >{{ communityCards[i - 1].rank }}{{ suitSymbol(communityCards[i - 1].suit) }}</span>
            </template>
            <template v-else>
              <span class="card card-back"></span>
            </template>
          </div>
        </div>

        <!-- Player Seats -->
        <div class="seats">
          <div
            v-for="(p, idx) in activePlayers"
            :key="p.id"
            class="seat"
            :class="{
              'is-turn': p.id === gameState?.whose_turn,
              'is-folded': p.folded,
              'is-all-in': p.all_in,
              'is-you': p.id === playerId,
            }"
            :style="seatPosition(idx, activePlayers.length)"
          >
            <div class="seat-token" :style="{ backgroundColor: seatColor(idx) }">
              {{ p.name.charAt(0).toUpperCase() }}
            </div>
            <div class="seat-info">
              <div class="seat-name">
                {{ p.name }}
                <span v-if="idx === gameState?.dealer_index" class="dealer-chip">D</span>
              </div>
              <div class="seat-chips">{{ p.chips }}</div>
              <div v-if="p.folded" class="seat-status folded">Folded</div>
              <div v-else-if="p.all_in" class="seat-status all-in">All In</div>
              <div v-else-if="p.current_bet > 0" class="seat-bet">Bet: {{ p.current_bet }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Section: Your Cards + Actions + Chat -->
    <div class="bottom-section">
      <!-- Your Hole Cards -->
      <div class="hole-cards-section" v-if="!isObserver">
        <h3>Your Cards</h3>
        <div class="hole-cards">
          <template v-if="yourCards.length">
            <span
              v-for="(c, i) in yourCards"
              :key="i"
              class="card hole-card"
              :class="suitClass(c.suit)"
            >{{ c.rank }}{{ suitSymbol(c.suit) }}</span>
          </template>
          <template v-else>
            <span class="card card-back hole-card"></span>
            <span class="card card-back hole-card"></span>
          </template>
        </div>
      </div>

      <!-- Action Panel -->
      <div class="action-panel" v-if="!isObserver && gameState?.status === 'playing'">
        <template v-if="isMyTurn && availableActions.length">
          <div class="action-buttons">
            <button
              v-if="canFold"
              class="action-btn fold-btn"
              @click="doAction({ type: 'fold' })"
            >Fold</button>

            <button
              v-if="canCheck"
              class="action-btn check-btn"
              @click="doAction({ type: 'check' })"
            >Check</button>

            <button
              v-if="canCall"
              class="action-btn call-btn"
              @click="doAction({ type: 'call' })"
            >Call {{ amountToCall }}</button>

            <button
              v-if="canBet"
              class="action-btn bet-btn"
              @click="showBetInput = !showBetInput; showRaiseInput = false"
            >Bet</button>

            <button
              v-if="canRaise"
              class="action-btn raise-btn"
              @click="showRaiseInput = !showRaiseInput; showBetInput = false"
            >Raise</button>

            <button
              v-if="canAllIn"
              class="action-btn allin-btn"
              @click="doAction({ type: 'all_in' })"
            >All In ({{ myPlayer?.chips ?? 0 }})</button>
          </div>

          <!-- Bet Amount Input -->
          <div v-if="showBetInput" class="amount-input">
            <input
              type="range"
              :min="gameState?.big_blind ?? 20"
              :max="myPlayer?.chips ?? 0"
              :step="gameState?.big_blind ?? 20"
              v-model.number="betAmount"
            />
            <div class="amount-row">
              <input type="number" v-model.number="betAmount" :min="gameState?.big_blind ?? 20" :max="myPlayer?.chips ?? 0" />
              <button class="confirm-btn" @click="submitBet">Bet {{ betAmount }}</button>
            </div>
            <div class="preset-buttons">
              <button @click="betAmount = gameState?.big_blind ?? 20">Min</button>
              <button @click="betAmount = Math.floor((myPlayer?.chips ?? 0) / 3)">1/3</button>
              <button @click="betAmount = Math.floor((myPlayer?.chips ?? 0) / 2)">1/2</button>
              <button @click="betAmount = myPlayer?.chips ?? 0">Max</button>
            </div>
          </div>

          <!-- Raise Amount Input -->
          <div v-if="showRaiseInput" class="amount-input">
            <input
              type="range"
              :min="minRaise"
              :max="myPlayer?.chips ?? 0"
              :step="gameState?.big_blind ?? 20"
              v-model.number="raiseAmount"
            />
            <div class="amount-row">
              <input type="number" v-model.number="raiseAmount" :min="minRaise" :max="myPlayer?.chips ?? 0" />
              <button class="confirm-btn" @click="submitRaise">Raise to {{ raiseAmount }}</button>
            </div>
            <div class="preset-buttons">
              <button @click="raiseAmount = minRaise">Min</button>
              <button @click="raiseAmount = Math.floor((myPlayer?.chips ?? 0) / 2)">1/2</button>
              <button @click="raiseAmount = Math.floor((myPlayer?.chips ?? 0) * 3 / 4)">3/4</button>
              <button @click="raiseAmount = myPlayer?.chips ?? 0">Max</button>
            </div>
          </div>
        </template>
        <div v-else-if="gameState?.status === 'playing'" class="waiting-msg">
          {{ gameState?.whose_turn ? `Waiting for ${currentTurnName}...` : 'Waiting...' }}
        </div>
      </div>

      <!-- Chat Panel -->
      <div class="chat-section">
        <h3>Game Log</h3>
        <ul class="chat-messages" ref="chatContainer">
          <li
            v-for="(msg, i) in chatMessages"
            :key="i"
            class="chat-msg"
            :class="{ system: !msg.player_id }"
          >
            <span class="chat-text">{{ msg.text }}</span>
            <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
          </li>
          <li v-if="!chatMessages.length" class="chat-empty">No messages yet.</li>
        </ul>
        <div class="chat-input">
          <input
            v-model="chatInput"
            placeholder="Type a message..."
            maxlength="300"
            @keyup.enter="sendChatMessage"
          />
          <button :disabled="!chatInput.trim()" @click="sendChatMessage">Send</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const SEAT_COLORS = [
  '#e74c3c', '#f39c12', '#27ae60', '#2980b9', '#8e44ad',
  '#e67e22', '#1abc9c', '#e84393', '#00b894', '#6c5ce7',
]

const SUIT_SYMBOLS = { hearts: '\u2665', diamonds: '\u2666', clubs: '\u2663', spades: '\u2660' }

const props = defineProps({
  gameId: String,
  playerId: String,
  gameState: Object,
  yourCards: { type: Array, default: () => [] },
  availableActions: { type: Array, default: () => [] },
  chatMessages: { type: Array, default: () => [] },
  isObserver: { type: Boolean, default: false },
})
const emit = defineEmits(['action', 'send-chat'])

const showBetInput = ref(false)
const showRaiseInput = ref(false)
const betAmount = ref(20)
const raiseAmount = ref(40)
const chatInput = ref('')
const chatContainer = ref(null)
const showdownData = ref(null)

const communityCards = computed(() => props.gameState?.community_cards ?? [])
const activePlayers = computed(() => props.gameState?.players ?? [])

const myPlayer = computed(() =>
  activePlayers.value.find(p => p.id === props.playerId)
)

const isMyTurn = computed(() =>
  props.gameState?.whose_turn === props.playerId
)

const amountToCall = computed(() => {
  if (!myPlayer.value || !props.gameState) return 0
  return Math.max(0, props.gameState.current_bet - myPlayer.value.current_bet)
})

const minRaise = computed(() => {
  const call = amountToCall.value
  const bb = props.gameState?.big_blind ?? 20
  return call + bb
})

const canFold = computed(() => props.availableActions.includes('fold'))
const canCheck = computed(() => props.availableActions.includes('check'))
const canCall = computed(() => props.availableActions.includes('call'))
const canBet = computed(() => props.availableActions.includes('bet'))
const canRaise = computed(() => props.availableActions.includes('raise'))
const canAllIn = computed(() => props.availableActions.includes('all_in'))

const bettingRoundLabel = computed(() => {
  const round = props.gameState?.betting_round
  if (round === 'preflop') return 'Pre-Flop'
  if (round === 'flop') return 'Flop'
  if (round === 'turn') return 'Turn'
  if (round === 'river') return 'River'
  if (round === 'showdown') return 'Showdown'
  return ''
})

const statusClass = computed(() => {
  if (props.gameState?.status === 'finished') return 'finished'
  if (isMyTurn.value) return 'your-turn'
  return ''
})

const winnerName = computed(() => {
  if (!props.gameState?.winner) return '?'
  return playerName(props.gameState.winner)
})

const currentTurnName = computed(() => {
  if (!props.gameState?.whose_turn) return '?'
  return playerName(props.gameState.whose_turn)
})

function playerName(pid) {
  const p = activePlayers.value.find(p => p.id === pid)
  return p?.name ?? pid
}

function seatColor(idx) {
  return SEAT_COLORS[idx % SEAT_COLORS.length]
}

function seatPosition(idx, total) {
  // Distribute seats in an oval around the table
  const angle = (idx / total) * 2 * Math.PI - Math.PI / 2
  const rx = 42 // % horizontal radius
  const ry = 36 // % vertical radius
  const cx = 50
  const cy = 50
  const x = cx + rx * Math.cos(angle)
  const y = cy + ry * Math.sin(angle)
  return { left: `${x}%`, top: `${y}%` }
}

function suitSymbol(suit) {
  return SUIT_SYMBOLS[suit] ?? suit?.[0]?.toUpperCase() ?? ''
}

function suitClass(suit) {
  return `suit-${suit}`
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function doAction(action) {
  showBetInput.value = false
  showRaiseInput.value = false
  emit('action', action)
}

function submitBet() {
  doAction({ type: 'bet', amount: betAmount.value })
}

function submitRaise() {
  doAction({ type: 'raise', amount: raiseAmount.value })
}

function sendChatMessage() {
  const text = chatInput.value.trim()
  if (!text) return
  emit('send-chat', text)
  chatInput.value = ''
}

function dismissShowdown() {
  showdownData.value = null
}

// Reset bet/raise inputs when turn changes
watch(() => props.gameState?.whose_turn, () => {
  showBetInput.value = false
  showRaiseInput.value = false
})

// Initialize bet amounts when it's our turn
watch(isMyTurn, (isTurn) => {
  if (isTurn) {
    betAmount.value = props.gameState?.big_blind ?? 20
    raiseAmount.value = minRaise.value
  }
})

// Auto-scroll chat
watch(
  () => props.chatMessages.length,
  async () => {
    await nextTick()
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  }
)

// Expose showdown handler so parent can call it
defineExpose({
  onShowdown(data) {
    showdownData.value = data
  }
})
</script>

<style scoped>
.poker-game {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 1000px;
  margin: 0 auto;
}

/* Header */
.poker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.poker-header h1 {
  font-size: 1.4rem;
  color: #27ae60;
  letter-spacing: 0.1em;
  margin: 0;
}

.game-id {
  color: #667;
  font-family: monospace;
  font-size: 0.8rem;
  margin-left: 0.75rem;
}

.observer-badge {
  background: #e67e22;
  color: #fff;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  margin-left: 0.5rem;
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  gap: 1rem;
  color: #8899aa;
  font-size: 0.85rem;
}

/* Status Banner */
.status-banner {
  text-align: center;
  padding: 0.5rem;
  border-radius: 6px;
  background: #16213e;
  color: #aab;
  font-size: 0.9rem;
}

.status-banner.your-turn {
  background: #27ae60;
  color: #fff;
  font-weight: bold;
}

.status-banner.finished {
  background: #c9a84c;
  color: #1a1a2e;
  font-weight: bold;
}

/* Showdown Overlay */
.showdown-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.showdown-card {
  background: #16213e;
  border: 2px solid #c9a84c;
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  max-width: 500px;
  width: 90%;
}

.showdown-card h2 {
  color: #c9a84c;
  margin-bottom: 1rem;
  font-size: 1.5rem;
}

.showdown-winners {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
}

.winner-name {
  color: #27ae60;
  font-weight: bold;
}

.showdown-pot {
  color: #c9a84c;
  font-size: 1rem;
  margin-bottom: 1rem;
}

.showdown-hands {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}

.showdown-hand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.hand-player {
  color: #aab;
  min-width: 80px;
  text-align: right;
}

.hand-cards {
  display: flex;
  gap: 0.25rem;
}

.dismiss-btn {
  background: #27ae60;
  color: #fff;
  border: none;
  padding: 0.5rem 2rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
}

.dismiss-btn:hover {
  background: #229954;
}

/* Table Area */
.table-area {
  display: flex;
  justify-content: center;
  padding: 0.5rem 0;
}

.felt {
  position: relative;
  width: 100%;
  max-width: 700px;
  aspect-ratio: 16 / 9;
  background: radial-gradient(ellipse at center, #1a6b3c 0%, #0d4a27 60%, #0a3a1e 100%);
  border-radius: 120px;
  border: 6px solid #5a3e1b;
  box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.4), 0 4px 20px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
}

/* Pot */
.pot-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
}

.pot-label {
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.pot-amount {
  color: #c9a84c;
  font-size: 1.4rem;
  font-weight: bold;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

/* Community Cards */
.community-cards {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
}

.card-slot {
  width: 52px;
  height: 72px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s ease;
}

.card-slot.dealt {
  transform: scale(1);
}

.card {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 72px;
  background: #fff;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: bold;
  border: 1px solid #ccc;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.card-back {
  background: linear-gradient(135deg, #2c3e50, #34495e);
  border: 2px solid #1a252f;
  color: transparent;
}

.card-back::after {
  content: '\2660';
  color: rgba(255, 255, 255, 0.15);
  font-size: 1.5rem;
}

.suit-hearts, .suit-diamonds {
  color: #e74c3c;
}

.suit-clubs, .suit-spades {
  color: #2c3e50;
}

/* Player Seats */
.seats {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

.seat {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  min-width: 70px;
  transition: all 0.3s ease;
}

.seat.is-turn {
  filter: drop-shadow(0 0 8px rgba(39, 174, 96, 0.6));
}

.seat.is-folded {
  opacity: 0.4;
}

.seat.is-you .seat-token {
  box-shadow: 0 0 0 3px #c9a84c;
}

.seat-token {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 0.9rem;
  color: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

.seat-info {
  background: rgba(0, 0, 0, 0.6);
  border-radius: 6px;
  padding: 0.2rem 0.5rem;
  text-align: center;
  min-width: 60px;
}

.seat-name {
  font-size: 0.7rem;
  color: #eee;
  font-weight: bold;
  white-space: nowrap;
}

.dealer-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #c9a84c;
  color: #1a1a2e;
  font-size: 0.55rem;
  font-weight: bold;
  margin-left: 0.2rem;
  vertical-align: middle;
}

.seat-chips {
  font-size: 0.65rem;
  color: #c9a84c;
}

.seat-status {
  font-size: 0.6rem;
  font-weight: bold;
  text-transform: uppercase;
}

.seat-status.folded { color: #e74c3c; }
.seat-status.all-in { color: #e67e22; }

.seat-bet {
  font-size: 0.6rem;
  color: #3498db;
}

/* Bottom Section */
.bottom-section {
  display: grid;
  grid-template-columns: 180px 1fr 280px;
  gap: 0.75rem;
  align-items: start;
}

/* Hole Cards */
.hole-cards-section {
  background: #16213e;
  border-radius: 8px;
  padding: 0.75rem;
}

.hole-cards-section h3 {
  color: #c9a84c;
  font-size: 0.8rem;
  margin-bottom: 0.5rem;
}

.hole-cards {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
}

.hole-card {
  width: 60px;
  height: 84px;
  font-size: 1.1rem;
}

/* Action Panel */
.action-panel {
  background: #16213e;
  border-radius: 8px;
  padding: 0.75rem;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  justify-content: center;
}

.action-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.85rem;
  transition: all 0.15s;
}

.fold-btn { background: #555; color: #eee; }
.fold-btn:hover { background: #666; }

.check-btn { background: #3498db; color: #fff; }
.check-btn:hover { background: #2980b9; }

.call-btn { background: #27ae60; color: #fff; }
.call-btn:hover { background: #229954; }

.bet-btn { background: #e67e22; color: #fff; }
.bet-btn:hover { background: #d35400; }

.raise-btn { background: #e74c3c; color: #fff; }
.raise-btn:hover { background: #c0392b; }

.allin-btn { background: #8e44ad; color: #fff; }
.allin-btn:hover { background: #7d3c98; }

.amount-input {
  margin-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.amount-input input[type="range"] {
  width: 100%;
  accent-color: #27ae60;
}

.amount-row {
  display: flex;
  gap: 0.4rem;
}

.amount-row input[type="number"] {
  flex: 1;
  padding: 0.35rem 0.5rem;
  border-radius: 5px;
  border: 1px solid #334;
  background: #0f3460;
  color: #eee;
  font-size: 0.9rem;
}

.confirm-btn {
  background: #27ae60;
  color: #fff;
  border: none;
  padding: 0.35rem 0.8rem;
  border-radius: 5px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.85rem;
  white-space: nowrap;
}

.confirm-btn:hover { background: #229954; }

.preset-buttons {
  display: flex;
  gap: 0.3rem;
}

.preset-buttons button {
  flex: 1;
  background: #0f3460;
  color: #aab;
  border: 1px solid #334;
  padding: 0.25rem 0.3rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
  transition: all 0.15s;
}

.preset-buttons button:hover {
  border-color: #27ae60;
  color: #27ae60;
}

.waiting-msg {
  color: #667;
  text-align: center;
  font-style: italic;
  padding: 0.5rem;
}

/* Chat Section */
.chat-section {
  background: #16213e;
  border-radius: 8px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  max-height: 250px;
}

.chat-section h3 {
  color: #c9a84c;
  font-size: 0.8rem;
  margin-bottom: 0.4rem;
}

.chat-messages {
  list-style: none;
  flex: 1;
  overflow-y: auto;
  margin-bottom: 0.4rem;
  max-height: 160px;
}

.chat-msg {
  padding: 0.15rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  font-size: 0.75rem;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.chat-msg.system {
  color: #8899aa;
  font-style: italic;
}

.chat-text {
  flex: 1;
  word-break: break-word;
}

.chat-time {
  color: #556;
  font-size: 0.65rem;
  white-space: nowrap;
}

.chat-empty {
  color: #556;
  font-style: italic;
  font-size: 0.75rem;
  padding: 0.5rem 0;
}

.chat-input {
  display: flex;
  gap: 0.3rem;
}

.chat-input input {
  flex: 1;
  padding: 0.3rem 0.5rem;
  border-radius: 5px;
  border: 1px solid #334;
  background: #0f3460;
  color: #eee;
  font-size: 0.8rem;
}

.chat-input input::placeholder { color: #557; }

.chat-input button {
  background: #c9a84c;
  color: #1a1a2e;
  border: none;
  padding: 0.3rem 0.6rem;
  border-radius: 5px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.8rem;
}

.chat-input button:hover:not(:disabled) { background: #d4b85c; }
.chat-input button:disabled { opacity: 0.4; cursor: not-allowed; }

/* Responsive */
@media (max-width: 768px) {
  .bottom-section {
    grid-template-columns: 1fr;
  }

  .hole-cards-section {
    order: -1;
  }

  .felt {
    border-radius: 60px;
  }
}
</style>
