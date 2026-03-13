<template>
  <div class="poker-scene">
    <!-- Top Bar -->
    <header class="top-bar">
      <div class="top-bar-left">
        <span class="logo">Texas Hold'em</span>
        <span class="game-code">{{ gameId }}</span>
        <span v-if="isObserver" class="observer-pill">Spectating</span>
      </div>
      <div class="top-bar-right">
        <span class="meta-item">
          <span class="meta-label">Hand</span>
          <span class="meta-value">#{{ gameState?.hand_number ?? 0 }}</span>
        </span>
        <span class="meta-divider"></span>
        <span class="meta-item">
          <span class="meta-label">Blinds</span>
          <span class="meta-value">{{ formatChips(gameState?.small_blind ?? 10) }}/{{ formatChips(gameState?.big_blind ?? 20) }}</span>
        </span>
        <button class="chat-toggle" @click="chatOpen = !chatOpen" :class="{ active: chatOpen }">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
          <span v-if="unreadChat" class="chat-badge">{{ unreadChat }}</span>
        </button>
      </div>
    </header>

    <!-- Main Table Area -->
    <div class="table-container">
      <!-- Turn/Status indicator -->
      <div class="turn-strip" :class="statusClass">
        <template v-if="gameState?.status === 'finished'"> {{ winnerName }} takes it all </template>
        <template v-else-if="isMyTurn"> Your action &middot; {{ bettingRoundLabel }} </template>
        <template v-else-if="gameState?.whose_turn">
          {{ currentTurnName }} &middot; {{ bettingRoundLabel }}
        </template>
        <template v-else> Waiting for next hand... </template>
      </div>

      <div class="felt-wrapper">
        <div class="felt" ref="feltRef">
          <!-- Felt texture overlay -->
          <div class="felt-texture"></div>

          <!-- Rail -->
          <div class="rail"></div>

          <!-- Player Seats -->
          <div v-for="(p, idx) in activePlayers" :key="p.id" class="seat" :class="{
            'is-turn': p.id === gameState?.whose_turn,
            'is-folded': p.folded,
            'is-all-in': p.all_in,
            'is-you': p.id === playerId,
            'is-dealer': idx === gameState?.dealer_index
          }" :style="getSeatStyle(idx, activePlayers.length)">
            <!-- Dealer Button -->
            <div v-if="idx === gameState?.dealer_index" class="dealer-btn">D</div>

            <!-- Player bet above seat -->
            <div v-if="p.current_bet > 0 && !p.folded" class="bet-above-seat">
              <div class="bet-chip-stacks">
                <div v-for="(chip, ci) in chipStackVisual(p.current_bet, 6)" :key="ci" class="bet-chip"
                  :class="`chip-${chip}`" :style="{ '--bi': ci }"></div>
              </div>
              <span>{{ formatChips(p.current_bet) }}</span>
            </div>

            <!-- Avatar -->
            <div class="avatar" :style="{ '--seat-hue': seatHue(idx) }">
              <span class="avatar-letter">{{ p.name.charAt(0).toUpperCase() }}</span>
              <div v-if="p.id === gameState?.whose_turn" class="turn-ring"></div>
            </div>

            <!-- Info plate -->
            <div class="info-plate">
              <span class="player-name">{{ p.name }}</span>
              <span class="player-chips">
                <span class="chip-dot"
                  :class="`chip-${(chipBreakdown(p.chips)[0] || { color: 'white' }).color}`"></span>
                {{ formatChips(p.chips) }}
              </span>
            </div>

            <!-- Chip stack indicator for active players -->
            <div v-if="!p.folded && p.chips > 0" class="player-chip-stack">
              <div v-for="(stack, si) in chipBreakdown(p.chips).slice(0, 4)" :key="si" class="pcs-stack">
                <div v-for="n in Math.min(stack.count, 5)" :key="n" class="pcs-chip" :class="`chip-${stack.color}`"
                  :style="{ '--si': n - 1 }"></div>
              </div>
            </div>

            <!-- Status badge -->
            <div v-if="p.folded" class="status-badge folded">Fold</div>
            <div v-else-if="p.all_in" class="status-badge all-in">All In</div>
          </div>

          <!-- Sweep animation: chips flying to center -->
          <div v-for="chip in sweepingChips" :key="chip.id"
            class="sweep-chip"
            :style="{ '--from-x': chip.fromX + '%', '--from-y': chip.fromY + '%' }">
            <div class="sweep-chip-stack">
              <div class="sweep-single-chip chip-red"></div>
              <div class="sweep-single-chip chip-blue"></div>
              <div class="sweep-single-chip chip-white"></div>
            </div>
          </div>

          <!-- Center: Pot + Community Cards -->
          <div class="table-center">
            <div class="pot-area" v-if="(gameState?.pot ?? 0) > 0">
              <div class="pot-chips">
                <div v-for="(stack, si) in chipBreakdown(gameState?.pot ?? 0).slice(0, 4)" :key="si" class="chip-stack">
                  <div v-for="n in Math.min(stack.count, 6)" :key="n" class="mini-chip" :class="`chip-${stack.color}`"
                    :style="{ '--i': n }"></div>
                </div>
              </div>
              <div class="pot-amount">
                <span class="pot-number">{{ formatChips(gameState?.pot ?? 0) }}</span>
              </div>
            </div>

            <div class="community-cards">
              <TransitionGroup name="card-deal">
                <div v-for="(card, i) in communityCardSlots" :key="card.key" class="card-slot"
                  :class="{ 'is-dealt': card.dealt }" :style="{ '--deal-delay': `${i * 0.08}s` }">
                  <PlayingCard v-if="card.dealt" :rank="card.rank" :suit="card.suit" size="large" />
                  <PlayingCard v-else :faceDown="true" size="large" :rotation="deckRotation" />
                </div>
              </TransitionGroup>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Winner Banner (persistent, shows after showdown until next hand) -->
    <Transition name="banner-slide">
      <div v-if="winnerBanner" class="winner-banner">
        <div class="winner-banner-glow"></div>
        <div class="winner-banner-content">
          <span class="winner-crown">&#9813;</span>
          <span class="winner-text">
            <strong>{{ winnerBanner.names }}</strong> takes the pot
          </span>
          <span class="winner-pot">
            <svg class="chip-svg" width="14" height="14" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" fill="var(--gold)" stroke="var(--gold-dim)" stroke-width="2" />
            </svg>
            {{ formatChips(winnerBanner.pot) }}
          </span>
          <span v-if="winnerBanner.hand" class="winner-hand-type">{{ winnerBanner.hand }}</span>
        </div>
        <!-- Community cards + revealed hands row -->
        <div v-if="winnerBanner.playerHands && Object.keys(winnerBanner.playerHands).length" class="winner-banner-hands">
          <div v-if="winnerBanner.communityCards && winnerBanner.communityCards.length" class="banner-community-cards">
            <PlayingCard v-for="(c, i) in winnerBanner.communityCards" :key="'cc-' + i"
              :rank="c.rank" :suit="c.suit" size="tiny" class="banner-mini-card" />
          </div>
          <div class="banner-player-hands-row">
            <div v-for="(cards, pid) in winnerBanner.playerHands" :key="pid" class="banner-player-hand"
              :class="{ 'banner-hand-winner': winnerBanner.winnerIds.includes(pid) }">
              <span class="banner-hand-name">{{ playerName(pid) }}</span>
              <div class="banner-hand-cards">
                <PlayingCard v-for="(c, i) in cards" :key="c.rank + '-' + c.suit"
                  :rank="c.rank" :suit="c.suit" size="tiny" class="banner-mini-card" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Bottom Dock: Hole Cards + Actions -->
    <div class="bottom-dock" v-if="!isObserver">
      <!-- Your Hole Cards -->
      <div class="hole-cards-area">
        <div class="hole-cards">
          <template v-if="yourCards.length">
            <PlayingCard v-for="(c, i) in yourCards" :key="i"
              :rank="c.rank" :suit="c.suit" size="medium" class="hole-card"
              :style="{ '--tilt': i === 0 ? '-4deg' : '4deg', '--lift': i === 0 ? '0px' : '2px' }" />
          </template>
          <template v-else>
            <PlayingCard :faceDown="true" size="medium" class="hole-card" :style="{ '--tilt': '-4deg' }" :rotation="deckRotation" />
            <PlayingCard :faceDown="true" size="medium" class="hole-card" :style="{ '--tilt': '4deg' }" :rotation="deckRotation" />
          </template>
        </div>
      </div>

      <!-- Action Panel -->
      <div class="action-dock" v-if="gameState?.status === 'playing'">
        <template v-if="isMyTurn && availableActions.length">
          <div class="action-row">
            <button v-if="canFold" class="action-btn fold" @click="doAction({ type: 'fold' })">
              <span class="btn-label">Fold</span>
            </button>

            <button v-if="canCheck" class="action-btn check" @click="doAction({ type: 'check' })">
              <span class="btn-label">Check</span>
            </button>

            <button v-if="canCall" class="action-btn call" @click="doAction({ type: 'call' })">
              <span class="btn-label">Call</span>
              <span class="btn-amount">{{ formatChips(amountToCall) }}</span>
            </button>

            <button v-if="canBet" class="action-btn bet" @click="showBetInput = !showBetInput; showRaiseInput = false"
              :class="{ active: showBetInput }">
              <span class="btn-label">Bet</span>
            </button>

            <button v-if="canRaise" class="action-btn raise"
              @click="showRaiseInput = !showRaiseInput; showBetInput = false" :class="{ active: showRaiseInput }">
              <span class="btn-label">Raise</span>
            </button>

            <button v-if="canAllIn" class="action-btn allin" @click="doAction({ type: 'all_in' })">
              <span class="btn-label">All In</span>
              <span class="btn-amount">{{ formatChips(myPlayer?.chips ?? 0) }}</span>
            </button>
          </div>

          <!-- Bet Slider -->
          <Transition name="slider-expand">
            <div v-if="showBetInput" class="slider-panel">
              <div class="slider-row">
                <div class="preset-pills">
                  <button @click="betAmount = gameState?.big_blind ?? 20" class="pill">Min</button>
                  <button @click="betAmount = Math.max(gameState?.big_blind ?? 20, roundToChip((gameState?.pot ?? 0) / 3))" class="pill">
                    &frac13; Pot
                  </button>
                  <button @click="betAmount = Math.max(gameState?.big_blind ?? 20, roundToChip((gameState?.pot ?? 0) / 2))" class="pill">
                    &frac12; Pot
                  </button>
                  <button @click="betAmount = roundToChip(gameState?.pot ?? 0)" class="pill">Pot</button>
                </div>
                <div class="range-track">
                  <input type="range" :min="gameState?.big_blind ?? 20" :max="myPlayer?.chips ?? 0"
                    :step="MIN_CHIP" v-model.number="betAmount" class="range-input" />
                </div>
                <div class="slider-confirm">
                  <input type="number" v-model.number="betAmount" :min="gameState?.big_blind ?? 20"
                    :max="myPlayer?.chips ?? 0" :step="MIN_CHIP" class="num-input" />
                  <button class="go-btn" @click="submitBet">
                    Bet {{ formatChips(betAmount) }}
                  </button>
                </div>
              </div>
            </div>
          </Transition>

          <!-- Raise Slider -->
          <Transition name="slider-expand">
            <div v-if="showRaiseInput" class="slider-panel">
              <div class="slider-row">
                <div class="preset-pills">
                  <button @click="raiseAmount = minRaise" class="pill">Min</button>
                  <button @click="raiseAmount = Math.max(minRaise, roundToChip((gameState?.pot ?? 0) / 2))" class="pill">
                    &frac12; Pot
                  </button>
                  <button @click="raiseAmount = Math.max(minRaise, roundToChip(((gameState?.pot ?? 0) * 3) / 4))" class="pill">
                    &frac34; Pot
                  </button>
                  <button @click="raiseAmount = Math.max(minRaise, roundToChip(gameState?.pot ?? 0))" class="pill">Pot</button>
                </div>
                <div class="range-track">
                  <input type="range" :min="minRaise" :max="myPlayer?.chips ?? 0" :step="MIN_CHIP"
                    v-model.number="raiseAmount" class="range-input" />
                </div>
                <div class="slider-confirm">
                  <input type="number" v-model.number="raiseAmount" :min="minRaise" :max="myPlayer?.chips ?? 0"
                    :step="MIN_CHIP" class="num-input" />
                  <button class="go-btn" @click="submitRaise">
                    Raise {{ formatChips(raiseAmount) }}
                  </button>
                </div>
              </div>
            </div>
          </Transition>
        </template>

        <div v-else class="waiting-msg">
          <div class="waiting-dots"><span></span><span></span><span></span></div>
          {{ gameState?.whose_turn ? `${currentTurnName} is thinking...` : 'Waiting...' }}
        </div>
      </div>
    </div>

    <!-- Chat Drawer -->
    <Transition name="drawer">
      <div v-if="chatOpen" class="chat-drawer">
        <div class="chat-header">
          <span>Table Chat</span>
          <button class="chat-close" @click="chatOpen = false">&times;</button>
        </div>
        <ul class="chat-messages" ref="chatContainer">
          <li v-for="(msg, i) in chatMessages" :key="i" class="chat-msg" :class="{ system: !msg.player_id }">
            <span class="chat-text">{{ msg.text }}</span>
            <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
          </li>
          <li v-if="!chatMessages.length" class="chat-empty">No messages yet.</li>
        </ul>
        <div class="chat-input-row">
          <input v-model="chatInput" placeholder="Say something..." maxlength="300" @keyup.enter="sendChatMessage" />
          <button :disabled="!chatInput.trim()" @click="sendChatMessage">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
      </div>
    </Transition>

    <!-- Showdown Overlay -->
    <Transition name="showdown-fade">
      <div v-if="showdownData" class="showdown-backdrop" @click="dismissShowdown">
        <div class="showdown-modal" @click.stop>
          <div class="showdown-glow"></div>
          <div class="showdown-content">
            <div class="showdown-crown">&#9813;</div>
            <h2 class="showdown-title">
              <span v-for="(wid, wi) in showdownData.winners" :key="wid">
                <span v-if="wi > 0"> &amp; </span>
                {{ playerName(wid) }}
              </span>
              wins
            </h2>
            <div class="showdown-hand-type">{{ showdownData.winning_hand }}</div>
            <div class="showdown-pot-line">
              <svg class="chip-svg" width="16" height="16" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" fill="var(--gold)" stroke="var(--gold-dim)" stroke-width="2" />
                <circle cx="12" cy="12" r="6" fill="none" stroke="var(--gold-dim)" stroke-width="1.5" />
              </svg>
              {{ formatChips(showdownData.pot) }}
            </div>
            <div v-if="showdownData.community_cards && showdownData.community_cards.length" class="showdown-community-cards">
              <PlayingCard v-for="(c, i) in showdownData.community_cards" :key="'sc-' + i"
                :rank="c.rank" :suit="c.suit" size="mini" class="mini-card" />
            </div>
            <div class="showdown-divider"></div>
            <div class="showdown-hands">
              <div v-for="(cards, pid) in showdownData.player_hands" :key="pid" class="showdown-player-hand">
                <span class="sh-name">{{ playerName(pid) }}</span>
                <div class="sh-cards">
                  <PlayingCard v-for="(c, i) in cards" :key="i"
                    :rank="c.rank" :suit="c.suit" size="mini" class="mini-card" />
                </div>
              </div>
            </div>
            <button class="showdown-dismiss" @click="dismissShowdown">Continue</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Rebuy Overlay -->
    <Transition name="showdown-fade">
      <div v-if="showRebuyPrompt" class="showdown-backdrop">
        <div class="showdown-modal" @click.stop>
          <div class="showdown-glow"></div>
          <div class="showdown-content">
            <div class="showdown-crown" style="filter: grayscale(1);">&#9760;</div>
            <h2 class="showdown-title">You're out of chips!</h2>
            <div class="showdown-hand-type">Rebuy for {{ formatChips(gameState?.buy_in ?? 0) }}?</div>
            <div class="showdown-divider"></div>
            <div style="display: flex; gap: 12px; justify-content: center;">
              <button class="action-btn call" style="padding: 10px 28px; font-size: 1rem;" @click="doRebuy">
                <span class="btn-label">Rebuy</span>
              </button>
              <button class="action-btn fold" style="padding: 10px 28px; font-size: 1rem;" @click="doDeclineRebuy">
                <span class="btn-label">Leave Game</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import PlayingCard from '../common/PlayingCard.vue'

const props = defineProps({
  gameId: String,
  playerId: String,
  gameState: Object,
  yourCards: { type: Array, default: () => [] },
  availableActions: { type: Array, default: () => [] },
  chatMessages: { type: Array, default: () => [] },
  isObserver: { type: Boolean, default: false }
})
const emit = defineEmits(['action', 'send-chat', 'rebuy', 'decline-rebuy'])

// Chip denominations: value, color name (used as CSS class), and display color
const CHIP_DENOMS = [
  { value: 500, color: 'green' },
  { value: 100, color: 'blue' },
  { value: 25, color: 'red' },
  { value: 10, color: 'white' }
]
// GCD of all denominations — the smallest representable bet increment
function _gcd(a, b) { while (b) { [a, b] = [b, a % b] } return a }
const MIN_CHIP = CHIP_DENOMS.map(d => d.value).reduce(_gcd)  // 5

// Round a bet amount down to the nearest chip denomination multiple
function roundToChip(amount) {
  return Math.floor(amount / MIN_CHIP) * MIN_CHIP
}

// Break an amount into chip denominations, returns array of { color, count }
function chipBreakdown(amount) {
  const result = []
  let remaining = amount
  for (const denom of CHIP_DENOMS) {
    const count = Math.floor(remaining / denom.value)
    if (count > 0) {
      result.push({ color: denom.color, count })
      remaining -= count * denom.value
    }
  }
  // Any remainder goes on white chips
  if (remaining > 0 && result.length === 0) {
    result.push({ color: 'white', count: 1 })
  }
  return result
}

// Build visual chip stacks for display (max chips per stack, returns flat list of chip colors)
function chipStackVisual(amount, maxChips = 10) {
  const breakdown = chipBreakdown(amount)
  const chips = []
  for (const { color, count } of breakdown) {
    for (let i = 0; i < Math.min(count, maxChips); i++) {
      chips.push(color)
      if (chips.length >= maxChips) return chips
    }
  }
  return chips
}

// Seat hue wheel — evenly spaced warm/cool tones
const SEAT_HUES = [0, 35, 120, 210, 270, 330, 55, 170, 300, 85]

const showBetInput = ref(false)
const showRaiseInput = ref(false)
const betAmount = ref(20)
const raiseAmount = ref(40)
const chatInput = ref('')
const chatContainer = ref(null)
const chatOpen = ref(false)
const showdownData = ref(null)
const winnerBanner = ref(null)
const feltRef = ref(null)
const unreadChat = ref(0)
const lastReadChat = ref(0)
const sweepingChips = ref([])   // chips animating to center after a betting round ends
const prevBettingRound = ref(null)
const showRebuyPrompt = ref(false)

const communityCards = computed(() => props.gameState?.community_cards ?? [])
const activePlayers = computed(() => props.gameState?.players ?? [])

// Small rotation for face-down card backs — changes each hand to give the
// "dealt from a shuffled deck" visual. Value cycles gently between -4 and 4 deg.
const deckRotation = computed(() => {
  const h = props.gameState?.hand_number ?? 0
  const rotations = [-4, -2, 0, 2, 4, 3, -3, 1, -1]
  return rotations[h % rotations.length]
})

const communityCardSlots = computed(() => {
  const cards = communityCards.value
  const slots = []
  for (let i = 0; i < 5; i++) {
    if (cards[i]) {
      slots.push({ ...cards[i], dealt: true, key: `card-${i}-${cards[i].rank}-${cards[i].suit}` })
    } else {
      slots.push({ dealt: false, key: `empty-${i}` })
    }
  }
  return slots
})

const myPlayer = computed(() => activePlayers.value.find((p) => p.id === props.playerId))

const isMyTurn = computed(() => props.gameState?.whose_turn === props.playerId)

const amountToCall = computed(() => {
  if (!myPlayer.value || !props.gameState) return 0
  return Math.max(0, props.gameState.current_bet - myPlayer.value.current_bet)
})

const minRaise = computed(() => {
  const call = amountToCall.value
  const bb = props.gameState?.big_blind ?? 20
  const lastRaise = props.gameState?.last_raise_size ?? bb
  return call + Math.max(bb, lastRaise)
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
  const p = activePlayers.value.find((p) => p.id === pid)
  return p?.name ?? pid
}

function seatHue(idx) {
  return SEAT_HUES[idx % SEAT_HUES.length]
}

function formatChips(n) {
  return '$' + (Number(n) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Position seats around an ellipse
// Places the current player ("you") at the bottom center
function getSeatStyle(idx, total) {
  // Seat layout positions (percentage-based)
  // Pre-computed positions for common player counts to get ideal spacing
  const positions = getSeatPositions(total)
  const pos = positions[idx]
  return { left: `${pos.x}%`, top: `${pos.y}%` }
}

function getSeatPositions(total) {
  // Place seats around an oval, with seat 0 at bottom
  // We want the user's seat at bottom-center
  const positions = []
  for (let i = 0; i < total; i++) {
    // Start from bottom (Math.PI/2) and go clockwise
    const angle = Math.PI / 2 + (i / total) * 2 * Math.PI
    const rx = 46 // horizontal radius %
    const ry = 42 // vertical radius %
    const x = 50 + rx * Math.cos(angle)
    const y = 50 + ry * Math.sin(angle)
    positions.push({ x, y })
  }
  return positions
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
  const chips = myPlayer.value?.chips ?? 0
  const amount = betAmount.value >= chips ? chips : roundToChip(betAmount.value)
  doAction({ type: 'bet', amount })
}

function submitRaise() {
  const chips = myPlayer.value?.chips ?? 0
  const amount = raiseAmount.value >= chips ? chips : roundToChip(raiseAmount.value)
  doAction({ type: 'raise', amount })
}

function doRebuy() {
  showRebuyPrompt.value = false
  emit('rebuy')
}

function doDeclineRebuy() {
  showRebuyPrompt.value = false
  emit('decline-rebuy')
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
watch(
  () => props.gameState?.whose_turn,
  () => {
    showBetInput.value = false
    showRaiseInput.value = false
  }
)

// Initialize bet amounts when it's our turn
watch(isMyTurn, (isTurn) => {
  if (isTurn) {
    betAmount.value = props.gameState?.big_blind ?? 20
    raiseAmount.value = minRaise.value
  }
})

// Auto-scroll chat + unread counter
watch(
  () => props.chatMessages.length,
  async (len) => {
    if (!chatOpen.value && len > lastReadChat.value) {
      unreadChat.value = len - lastReadChat.value
    }
    await nextTick()
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  }
)

watch(chatOpen, (open) => {
  if (open) {
    unreadChat.value = 0
    lastReadChat.value = props.chatMessages.length
  }
})

defineExpose({
  onShowdown(data) {
    showdownData.value = data
    // Set persistent banner with player hands
    const names = data.winners.map((wid) => playerName(wid)).join(' & ')
    winnerBanner.value = {
      names,
      pot: data.pot,
      hand: data.winning_hand,
      playerHands: data.player_hands || {},
      winnerIds: data.winners || [],
      communityCards: data.community_cards || []
    }
  },
  onRebuyPrompt() {
    showRebuyPrompt.value = true
  }
})

// Clear winner banner when backend clears last_hand_result (on next action)
watch(
  () => props.gameState?.last_hand_result,
  (result) => {
    if (!result && winnerBanner.value) {
      winnerBanner.value = null
    }
  }
)

// Track betting round changes for chip sweep animation
watch(
  () => props.gameState?.betting_round,
  (round, oldRound) => {
    // Sweep chips to center when betting round advances
    if (oldRound && round && round !== oldRound) {
      const players = props.gameState?.players ?? []
      const total = players.length
      const chips = []
      for (let i = 0; i < total; i++) {
        const p = players[i]
        // Check if this player had a bet (use previous state — bets just got swept)
        // Since state already updated, current_bet is 0. We check pot increase instead.
        // Use a heuristic: show sweep chips for non-folded players who were active
        if (!p.folded && total > 0) {
          const pos = getSeatPositions(total)[i]
          const cx = 50, cy = 50
          const fromX = cx + (pos.x - cx) * 0.55
          const fromY = cy + (pos.y - cy) * 0.55
          chips.push({
            id: `sweep-${i}-${Date.now()}`,
            fromX,
            fromY,
            seatIdx: i
          })
        }
      }
      if (chips.length > 0) {
        sweepingChips.value = chips
        // Remove after animation completes
        setTimeout(() => {
          sweepingChips.value = []
        }, 600)
      }
    }
    prevBettingRound.value = round
  }
)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Outfit:wght@300;400;500;600&family=Fira+Code:wght@400;500&display=swap');

/* ─── Design Tokens ─── */
.poker-scene {
  --felt: #0f5e30;
  --felt-light: #1a7a42;
  --felt-dark: #0a4020;
  --rail: #2e1a08;
  --rail-light: #4a2e14;
  --rail-inner: #3d2512;
  --gold: var(--poker-gold);
  --gold-bright: var(--poker-gold-bright);
  --gold-dim: var(--poker-gold-dim);
  --bg: var(--poker-chrome);
  --bg-raised: var(--poker-chrome-raised);
  --bg-card: var(--poker-chrome-alt);
  --text: var(--poker-text);
  --text-dim: var(--poker-text-dim);
  --text-muted: var(--poker-text-muted);
  --red-suit: #dc2626;
  --black-suit: #1c1c2e;
  --card-face: #f5f1e8;
  --card-shadow: rgba(0, 0, 0, 0.35);
  --card-back: var(--poker-card-back);
  --card-back-border: var(--poker-card-back-border);

  font-family: 'Outfit', system-ui, sans-serif;
  font-size: 15px;
  color: var(--text);
  background: var(--bg);
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  user-select: none;
}

/* ─── Top Bar ─── */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1.25rem;
  background: var(--bg-raised);
  border-bottom: 1px solid var(--poker-border);
  flex-shrink: 0;
  z-index: 10;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.logo {
  font-family: 'Cinzel', serif;
  font-weight: 700;
  font-size: 1.15rem;
  color: var(--gold);
  letter-spacing: 0.06em;
}

.game-code {
  font-family: 'Fira Code', monospace;
  font-size: 0.8rem;
  color: var(--text-dim);
  background: var(--poker-hover);
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  letter-spacing: 0.08em;
}

.observer-pill {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--bg);
  background: var(--gold);
  padding: 0.12rem 0.5rem;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.meta-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1.1;
}

.meta-label {
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}

.meta-value {
  font-family: 'Fira Code', monospace;
  font-size: 0.9rem;
  color: var(--text);
}

.meta-divider {
  width: 1px;
  height: 24px;
  background: var(--poker-input-border);
}

.chat-toggle {
  position: relative;
  background: none;
  border: 1px solid var(--poker-border-strong);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 0.35rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.chat-toggle:hover,
.chat-toggle.active {
  border-color: var(--gold-dim);
  color: var(--gold);
}

.chat-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: var(--red-suit);
  color: white;
  font-size: 0.55rem;
  font-weight: 700;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ─── Turn Strip ─── */
.turn-strip {
  text-align: center;
  padding: 0.4rem 1rem;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-dim);
  background: var(--bg-raised);
  border-bottom: 1px solid var(--poker-border);
  flex-shrink: 0;
  letter-spacing: 0.02em;
  transition: all 0.3s;
}

.turn-strip.your-turn {
  background: linear-gradient(90deg, var(--felt-dark), var(--felt), var(--felt-dark));
  color: #fff;
  font-weight: 600;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

.turn-strip.finished {
  background: linear-gradient(90deg, #2a1a00, #3d2800, #2a1a00);
  color: var(--gold-bright);
  font-weight: 600;
}

/* ─── Table Container ─── */
.table-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.felt-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.75rem 1.5rem;
  min-height: 0;
  overflow: hidden;
}

.felt {
  position: relative;
  width: 100%;
  max-width: 800px;
  aspect-ratio: 16 / 9;
  background: radial-gradient(ellipse 80% 70% at 50% 45%,
      var(--felt-light) 0%,
      var(--felt) 40%,
      var(--felt-dark) 100%);
  border-radius: 50%;
  overflow: visible;
}

.felt-texture {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.06'/%3E%3C/svg%3E");
  opacity: 0.5;
  mix-blend-mode: overlay;
  pointer-events: none;
}

.rail {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 10px solid var(--rail);
  box-shadow:
    inset 0 2px 6px rgba(0, 0, 0, 0.5),
    0 2px 8px rgba(0, 0, 0, 0.6),
    inset 0 0 0 2px var(--rail-light);
  pointer-events: none;
  z-index: 1;
}

/* ─── Player Seats ─── */
.seat {
  position: absolute;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  z-index: 5;
  transition: opacity 0.3s;
}

.seat.is-folded {
  opacity: 0.35;
}

.avatar {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: hsl(var(--seat-hue), 55%, 35%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  border: 2px solid hsl(var(--seat-hue), 55%, 50%);
  transition: all 0.3s;
}

.seat.is-you .avatar {
  border-color: var(--gold);
  box-shadow:
    0 0 0 2px var(--gold-dim),
    0 2px 8px rgba(0, 0, 0, 0.4);
}

.avatar-letter {
  font-weight: 700;
  font-size: 1rem;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.turn-ring {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 2px solid var(--gold-bright);
  animation: pulse-ring 1.5s ease-in-out infinite;
}

@keyframes pulse-ring {

  0%,
  100% {
    opacity: 0.4;
    transform: scale(1);
  }

  50% {
    opacity: 1;
    transform: scale(1.08);
  }
}

.dealer-btn {
  position: absolute;
  top: -4px;
  right: -8px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  color: var(--bg);
  font-size: 0.55rem;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  z-index: 6;
}

.info-plate {
  background: var(--poker-plate-bg);
  backdrop-filter: blur(6px);
  border-radius: 6px;
  padding: 0.2rem 0.5rem;
  text-align: center;
  min-width: 60px;
  border: 1px solid var(--poker-border);
}

.player-name {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--poker-name);
  white-space: nowrap;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.player-chips {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.2rem;
  font-family: 'Fira Code', monospace;
  font-size: 0.7rem;
  color: var(--gold);
}

.chip-svg {
  flex-shrink: 0;
}

.chip-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
  box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.25);
}

.status-badge {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
}

.status-badge.folded {
  color: var(--poker-text-dim);
  background: rgba(100, 100, 100, 0.3);
}

.status-badge.all-in {
  color: #fff;
  background: linear-gradient(135deg, #c83232, #e04848);
  animation: all-in-pulse 1.2s ease-in-out infinite;
}

@keyframes all-in-pulse {

  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(200, 50, 50, 0.4);
  }

  50% {
    box-shadow: 0 0 8px 2px rgba(200, 50, 50, 0.3);
  }
}

/* ─── Chip denomination colors ─── */
.chip-white {
  background: #e8e8e8;
  border-color: #bbb;
}

.chip-red {
  background: #cc3333;
  border-color: #991e1e;
}

.chip-blue {
  background: #2255cc;
  border-color: #193d99;
}

.chip-green {
  background: #22884e;
  border-color: #196638;
}

/* ─── Sweep animation: chips fly to center ─── */
.sweep-chip {
  position: absolute;
  left: var(--from-x);
  top: var(--from-y);
  transform: translate(-50%, -50%);
  z-index: 7;
  animation: sweep-to-center 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  pointer-events: none;
}

.sweep-chip-stack {
  position: relative;
  width: 28px;
  height: 20px;
}

.sweep-single-chip {
  position: absolute;
  left: 0;
  width: 28px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.35);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.sweep-single-chip:nth-child(1) { bottom: 0; }
.sweep-single-chip:nth-child(2) { bottom: 4px; }
.sweep-single-chip:nth-child(3) { bottom: 8px; }

@keyframes sweep-to-center {
  0% {
    left: var(--from-x);
    top: var(--from-y);
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  80% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(0.8);
  }
  100% {
    left: 50%;
    top: 50%;
    opacity: 0;
    transform: translate(-50%, -50%) scale(0.5);
  }
}

/* Bet chips above seat */
.bet-above-seat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  margin-bottom: 0.15rem;
}

.bet-chip-stacks {
  position: relative;
  width: 22px;
  height: 26px;
}

.bet-chip {
  position: absolute;
  bottom: calc(var(--bi) * 3px);
  left: 0;
  width: 22px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.35);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.bet-above-seat span {
  font-family: 'Fira Code', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--gold-bright, #f0c040);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}

/* ─── Table Center ─── */
.table-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  z-index: 3;
}

.pot-area {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pot-chips {
  display: flex;
  gap: 3px;
  align-items: flex-end;
}

.chip-stack {
  position: relative;
  width: 30px;
  height: 36px;
}

.mini-chip {
  position: absolute;
  bottom: calc(var(--i) * 4px);
  left: 0;
  width: 30px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.35);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.pot-amount {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.pot-number {
  font-family: 'Fira Code', monospace;
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--gold-bright);
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
}

/* ─── Cards ─── */
.community-cards {
  display: flex;
  gap: 0.5rem;
}

.card-slot {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.card-slot.is-dealt {
  animation: card-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: var(--deal-delay, 0s);
}

@keyframes card-pop {
  from {
    transform: scale(0.8) translateY(-8px);
    opacity: 0;
  }

  to {
    transform: scale(1) translateY(0);
    opacity: 1;
  }
}

/* Transition group */
.card-deal-enter-active {
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.card-deal-enter-from {
  opacity: 0;
  transform: scale(0.5) translateY(-20px);
}

/* ─── Bottom Dock ─── */
.bottom-dock {
  flex-shrink: 0;
  background: var(--bg-raised);
  border-top: 1px solid var(--poker-border);
  padding: 0.5rem 1.25rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
}

.hole-cards-area {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.hole-cards {
  display: flex;
  gap: 0.3rem;
}

.hole-card {
  transform: rotate(calc(var(--tilt, 0deg) + var(--deck-rotation, 0deg))) translateY(var(--lift, 0px));
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  cursor: default;
}

.hole-card:hover {
  transform: rotate(var(--deck-rotation, 0deg)) translateY(-4px) scale(1.08);
  z-index: 2;
}

/* ─── Action Buttons ─── */
.action-dock {
  width: 100%;
  max-width: 640px;
}

.action-row {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
  flex-wrap: wrap;
}

.action-btn {
  position: relative;
  padding: 0.55rem 1.2rem;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-weight: 600;
  font-size: 0.95rem;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.05rem;
  min-width: 78px;
}

.btn-label {
  font-size: 0.95rem;
}

.btn-amount {
  font-family: 'Fira Code', monospace;
  font-size: 0.8rem;
  opacity: 0.8;
}

.action-btn.fold {
  background: #2a2a35;
  color: #aaa;
  border: 1px solid #3a3a45;
}

.action-btn.fold:hover {
  background: #3a3a45;
  color: #ddd;
}

.action-btn.check {
  background: #164e6e;
  color: #8ad8ff;
  border: 1px solid #1a6080;
}

.action-btn.check:hover {
  background: #1a6080;
}

.action-btn.call {
  background: #1a5a32;
  color: #8affb0;
  border: 1px solid #1f7040;
}

.action-btn.call:hover {
  background: #1f7040;
}

.action-btn.bet {
  background: #5a3800;
  color: var(--gold-bright);
  border: 1px solid #7a4e10;
}

.action-btn.bet:hover,
.action-btn.bet.active {
  background: #7a4e10;
}

.action-btn.raise {
  background: #6a1a1a;
  color: #ff8a8a;
  border: 1px solid #8a2a2a;
}

.action-btn.raise:hover,
.action-btn.raise.active {
  background: #8a2a2a;
}

.action-btn.allin {
  background: linear-gradient(135deg, #6a1a1a, #8a2a2a);
  color: #fff;
  border: 1px solid #aa3a3a;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.action-btn.allin:hover {
  background: linear-gradient(135deg, #7a2222, #9a3535);
  box-shadow: 0 0 12px rgba(200, 50, 50, 0.3);
}

/* ─── Slider Panel ─── */
.slider-panel {
  margin-top: 0.4rem;
  background: var(--bg-card);
  border: 1px solid var(--poker-border);
  border-radius: 10px;
  padding: 0.6rem 0.8rem;
}

.slider-row {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.preset-pills {
  display: flex;
  gap: 0.3rem;
}

.pill {
  flex: 1;
  background: var(--poker-hover);
  border: 1px solid var(--poker-input-border);
  color: var(--text-dim);
  padding: 0.25rem 0.3rem;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.15s;
}

.pill:hover {
  border-color: var(--gold-dim);
  color: var(--gold);
  background: rgba(201, 168, 76, 0.08);
}

.range-track {
  padding: 0 0.25rem;
}

.range-input {
  width: 100%;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--poker-input-border);
  border-radius: 2px;
  outline: none;
}

.range-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--gold);
  border: 2px solid var(--gold-bright);
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}

.slider-confirm {
  display: flex;
  gap: 0.4rem;
}

.num-input {
  flex: 1;
  background: var(--poker-input-bg);
  border: 1px solid var(--poker-input-border);
  color: var(--text);
  font-family: 'Fira Code', monospace;
  font-size: 0.85rem;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  outline: none;
  transition: border-color 0.15s;
}

.num-input:focus {
  border-color: var(--gold-dim);
}

.go-btn {
  background: var(--felt);
  color: #fff;
  border: 1px solid var(--felt-light);
  padding: 0.35rem 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-weight: 600;
  font-size: 0.85rem;
  white-space: nowrap;
  transition: all 0.15s;
}

.go-btn:hover {
  background: var(--felt-light);
}

.slider-expand-enter-active,
.slider-expand-leave-active {
  transition: all 0.2s ease;
}

.slider-expand-enter-from,
.slider-expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  padding: 0 0.8rem;
  overflow: hidden;
}

/* ─── Waiting Message ─── */
.waiting-msg {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: var(--text-dim);
  font-size: 0.95rem;
  padding: 0.5rem;
}

.waiting-dots {
  display: flex;
  gap: 3px;
}

.waiting-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--text-dim);
  animation: dot-bounce 1.2s infinite;
}

.waiting-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.waiting-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes dot-bounce {

  0%,
  80%,
  100% {
    opacity: 0.2;
    transform: scale(0.8);
  }

  40% {
    opacity: 1;
    transform: scale(1);
  }
}

/* ─── Chat Drawer ─── */
.chat-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 300px;
  background: var(--bg-raised);
  border-left: 1px solid var(--poker-border);
  display: flex;
  flex-direction: column;
  z-index: 50;
  box-shadow: -4px 0 20px var(--poker-shadow);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--poker-border);
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--gold);
}

.chat-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 1.4rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.chat-close:hover {
  color: var(--text);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0.75rem;
  list-style: none;
}

.chat-msg {
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--poker-hover);
  font-size: 0.78rem;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.chat-msg.system {
  color: var(--text-dim);
  font-style: italic;
}

.chat-text {
  flex: 1;
  word-break: break-word;
  line-height: 1.4;
}

.chat-time {
  color: var(--text-muted);
  font-family: 'Fira Code', monospace;
  font-size: 0.6rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-empty {
  color: var(--text-muted);
  font-style: italic;
  font-size: 0.78rem;
  padding: 1rem 0;
  text-align: center;
}

.chat-input-row {
  display: flex;
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border-top: 1px solid var(--poker-border);
}

.chat-input-row input {
  flex: 1;
  background: var(--poker-input-bg);
  border: 1px solid var(--poker-input-border);
  color: var(--text);
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-family: 'Outfit', sans-serif;
  font-size: 0.8rem;
  outline: none;
}

.chat-input-row input::placeholder {
  color: var(--text-muted);
}

.chat-input-row input:focus {
  border-color: var(--gold-dim);
}

.chat-input-row button {
  background: var(--gold-dim);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background 0.15s;
}

.chat-input-row button:hover:not(:disabled) {
  background: var(--gold);
}

.chat-input-row button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: transform 0.25s ease;
}

.drawer-enter-from,
.drawer-leave-to {
  transform: translateX(100%);
}

/* ─── Showdown Overlay ─── */
.showdown-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  backdrop-filter: blur(4px);
}

.showdown-modal {
  position: relative;
  background: var(--bg-raised);
  border: 1px solid var(--gold-dim);
  border-radius: 16px;
  padding: 2rem 2.5rem;
  max-width: 480px;
  width: 92%;
  overflow: hidden;
}

.showdown-glow {
  position: absolute;
  top: -50%;
  left: 50%;
  transform: translateX(-50%);
  width: 200%;
  height: 100%;
  background: radial-gradient(ellipse at center, rgba(201, 168, 76, 0.12) 0%, transparent 60%);
  pointer-events: none;
}

.showdown-content {
  position: relative;
  text-align: center;
}

.showdown-crown {
  font-size: 3rem;
  color: var(--gold);
  line-height: 1;
  margin-bottom: 0.25rem;
  text-shadow: 0 0 20px rgba(201, 168, 76, 0.4);
  animation: crown-bob 1.5s ease-in-out infinite;
}

.showdown-title {
  font-family: 'Cinzel', serif;
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--poker-text);
  margin-bottom: 0.3rem;
}

.showdown-hand-type {
  font-size: 1.1rem;
  color: var(--gold);
  font-weight: 500;
  margin-bottom: 0.5rem;
  letter-spacing: 0.03em;
}

.showdown-pot-line {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  font-family: 'Fira Code', monospace;
  font-size: 1.3rem;
  color: var(--gold-bright);
  margin-bottom: 1rem;
}

.showdown-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--gold-dim), transparent);
  margin-bottom: 1rem;
}

.showdown-community-cards {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
  margin-bottom: 0.5rem;
}

.showdown-hands {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-bottom: 1.5rem;
}

.showdown-player-hand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
}

.sh-name {
  color: var(--text-dim);
  font-size: 0.8rem;
  min-width: 70px;
  text-align: right;
}

.sh-cards {
  display: flex;
  gap: 0.2rem;
}

.showdown-dismiss {
  background: var(--gold);
  color: var(--bg);
  border: none;
  padding: 0.6rem 2.5rem;
  border-radius: 8px;
  font-family: 'Outfit', sans-serif;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.15s;
  letter-spacing: 0.02em;
}

.showdown-dismiss:hover {
  background: var(--gold-bright);
  box-shadow: 0 0 16px rgba(201, 168, 76, 0.3);
}

.showdown-fade-enter-active {
  transition: all 0.3s ease;
}

.showdown-fade-leave-active {
  transition: all 0.2s ease;
}

.showdown-fade-enter-from {
  opacity: 0;
}

.showdown-fade-leave-to {
  opacity: 0;
}

.showdown-fade-enter-from .showdown-modal {
  transform: scale(0.9) translateY(20px);
}

/* ─── Player Chip Stack (in front of active players) ─── */
.player-chip-stack {
  display: flex;
  gap: 3px;
  margin-top: -2px;
  align-items: flex-end;
}

.pcs-stack {
  position: relative;
  width: 18px;
}

.pcs-chip {
  position: relative;
  width: 18px;
  height: 5px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.3);
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  margin-top: -1.5px;
}

.pcs-chip:first-child {
  margin-top: 0;
}

/* ─── Winner Banner ─── */
.winner-banner {
  position: relative;
  flex-shrink: 0;
  background: linear-gradient(90deg,
    color-mix(in srgb, var(--poker-gold-dim) 20%, var(--poker-chrome)),
    color-mix(in srgb, var(--poker-gold-dim) 35%, var(--poker-chrome)),
    color-mix(in srgb, var(--poker-gold-dim) 20%, var(--poker-chrome)));
  border-top: 1px solid var(--gold-dim);
  border-bottom: 1px solid var(--gold-dim);
  padding: 0.6rem 1.5rem;
  overflow: hidden;
  z-index: 8;
}

.winner-banner-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 50% 50%, rgba(201, 168, 76, 0.15) 0%, transparent 70%);
  pointer-events: none;
  animation: banner-glow-pulse 2s ease-in-out infinite;
}

@keyframes banner-glow-pulse {

  0%,
  100% {
    opacity: 0.6;
  }

  50% {
    opacity: 1;
  }
}

.winner-banner-content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.winner-crown {
  font-size: 1.4rem;
  color: var(--gold);
  text-shadow: 0 0 12px rgba(201, 168, 76, 0.5);
  animation: crown-bob 1.5s ease-in-out infinite;
}

@keyframes crown-bob {

  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-2px);
  }
}

.winner-text {
  font-size: 1rem;
  color: var(--text);
  letter-spacing: 0.02em;
}

.winner-text strong {
  color: var(--poker-text);
  font-weight: 700;
}

.winner-pot {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-family: 'Fira Code', monospace;
  font-size: 1rem;
  font-weight: 600;
  color: var(--gold-bright);
}

.winner-hand-type {
  font-size: 0.85rem;
  color: var(--gold);
  font-weight: 500;
  font-style: italic;
  opacity: 0.9;
}

.winner-banner-hands {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid color-mix(in srgb, var(--gold-dim) 40%, transparent);
}

.banner-community-cards {
  display: flex;
  gap: 0.25rem;
  justify-content: center;
}

.banner-player-hands-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1.2rem;
  flex-wrap: wrap;
}

.banner-player-hand {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  opacity: 0.7;
}

.banner-player-hand.banner-hand-winner {
  opacity: 1;
}

.banner-hand-name {
  font-size: 0.75rem;
  color: var(--text-dim);
  min-width: 50px;
  text-align: right;
}

.banner-hand-winner .banner-hand-name {
  color: var(--gold);
  font-weight: 600;
}

.banner-hand-cards {
  display: flex;
  gap: 0.15rem;
}


.banner-slide-enter-active {
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.banner-slide-leave-active {
  transition: all 0.25s ease;
}

.banner-slide-enter-from {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.banner-slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

/* ─── Responsive ─── */
@media (max-width: 768px) {
  .felt {
    aspect-ratio: 4 / 3;
  }

  .card-slot :deep(.playing-card) {
    width: 50px;
    height: 70px;
  }

  .hole-card {
    width: 58px !important;
    height: 82px !important;
  }

  .community-cards :deep(.card-rank) {
    font-size: 0.65rem;
  }

  .community-cards :deep(.pip) {
    font-size: 0.55rem;
  }

  .community-cards :deep(.pips-1 .pip) {
    font-size: 1.2rem;
  }

  .action-btn {
    padding: 0.45rem 0.9rem;
    font-size: 0.85rem;
    min-width: 64px;
  }

  .btn-label {
    font-size: 0.85rem;
  }

  .chat-drawer {
    width: 260px;
  }

  .seat {
    gap: 0.1rem;
  }

  .avatar {
    width: 34px;
    height: 34px;
  }

  .avatar-letter {
    font-size: 0.85rem;
  }

  .info-plate {
    padding: 0.12rem 0.35rem;
    min-width: 50px;
  }

  .player-name {
    font-size: 0.65rem;
    max-width: 70px;
  }

  .player-chips {
    font-size: 0.6rem;
  }

  .pot-number {
    font-size: 1.15rem;
  }

  .winner-banner-content {
    gap: 0.4rem;
  }

  .winner-text {
    font-size: 0.9rem;
  }

  .winner-pot {
    font-size: 0.9rem;
  }
}

@media (max-width: 480px) {
  .top-bar {
    padding: 0.35rem 0.75rem;
  }

  .logo {
    font-size: 0.95rem;
  }

  .meta-item {
    display: none;
  }

  .meta-divider {
    display: none;
  }

  .felt-wrapper {
    padding: 0.5rem;
  }

  .card-slot :deep(.playing-card) {
    width: 44px;
    height: 62px;
  }

  .hole-card {
    width: 52px !important;
    height: 74px !important;
  }

  .bottom-dock {
    padding: 0.35rem 0.75rem 0.5rem;
  }

  .action-btn {
    padding: 0.4rem 0.7rem;
    min-width: 56px;
    font-size: 0.8rem;
  }

  .btn-label {
    font-size: 0.8rem;
  }

  .winner-text {
    font-size: 0.85rem;
  }

  .winner-pot {
    font-size: 0.85rem;
  }

  .winner-crown {
    font-size: 1.1rem;
  }
}
</style>
