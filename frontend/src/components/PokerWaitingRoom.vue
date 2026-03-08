<template>
  <div class="waiting-scene">
    <!-- Decorative background -->
    <div class="bg-pattern"></div>

    <div class="waiting-card">
      <!-- Header -->
      <div class="card-header">
        <div class="brand-mark">
          <span class="suit-deco">&#9824;</span>
          <span class="suit-deco">&#9829;</span>
        </div>
        <h1>Texas Hold'em</h1>
        <p class="tagline">Waiting for players</p>
      </div>

      <!-- Game ID -->
      <div class="game-id-row">
        <div class="game-id-display">
          <span class="id-label">Table Code</span>
          <span class="id-value">{{ gameId }}</span>
        </div>
        <button class="copy-btn" @click="copyLink" :class="{ copied: copied }">
          <template v-if="copied">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Copied
          </template>
          <template v-else>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            Copy Link
          </template>
        </button>
      </div>

      <!-- Players -->
      <div class="players-section">
        <div class="section-header">
          <span>Seated Players</span>
          <span class="player-count">{{ players.length }}<span class="count-max"> / 10</span></span>
        </div>
        <div class="player-list">
          <TransitionGroup name="player-item">
            <div v-for="(p, idx) in players" :key="p.id" class="player-row">
              <div class="player-avatar" :style="{ '--hue': seatHue(idx) }">
                {{ p.name.charAt(0).toUpperCase() }}
              </div>
              <div class="player-details">
                <span class="p-name">{{ p.name }}</span>
                <span class="p-chips">
                  <svg width="10" height="10" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" fill="#c9a84c" stroke="#8b7635" stroke-width="2" />
                  </svg>
                  ${{ Number(p.chips).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                </span>
              </div>
              <div class="seat-num">#{{ idx + 1 }}</div>
            </div>
          </TransitionGroup>

          <!-- Empty seats -->
          <div v-for="n in Math.max(0, 2 - players.length)" :key="'empty-' + n" class="player-row empty-seat">
            <div class="player-avatar empty">?</div>
            <div class="player-details">
              <span class="p-name empty-text">Waiting for player...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-section">
        <div class="action-buttons-row">
          <button class="add-agent-btn" :disabled="players.length >= 10 || addingAgent" @click="addAgent">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="8" r="4" />
              <path d="M20 21a8 8 0 00-16 0" />
              <line x1="20" y1="8" x2="20" y2="14" />
              <line x1="17" y1="11" x2="23" y2="11" />
            </svg>
            {{ addingAgent ? 'Adding...' : 'Add Bot' }}
          </button>
          <button class="deal-btn" :disabled="players.length < 2" @click="startGame">
            <span class="deal-icon">&#9830;</span>
            Deal Cards
          </button>
        </div>
        <p v-if="players.length < 2" class="hint">Need at least 2 players to start</p>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>

      <!-- Footer -->
      <div class="card-footer">
        <button class="leave-link" @click="$emit('leave-game')">Leave Table</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const SEAT_HUES = [0, 35, 120, 210, 270, 330, 55, 170, 300, 85]

const props = defineProps({
  gameId: String,
  playerId: String,
  players: Array
})
const emit = defineEmits(['game-started', 'leave-game'])

const error = ref('')
const copied = ref(false)
const addingAgent = ref(false)

function seatHue(idx) {
  return SEAT_HUES[idx % SEAT_HUES.length]
}

function copyLink() {
  const url = `${window.location.origin}/holdem/${props.gameId}`
  navigator.clipboard.writeText(url)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 2000)
}

async function addAgent() {
  error.value = ''
  addingAgent.value = true
  try {
    const res = await fetch(`/api/holdem/games/${props.gameId}/add_agent`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to add agent'
    }
  } catch (e) {
    error.value = 'Error: ' + e.message
  } finally {
    addingAgent.value = false
  }
}

async function startGame() {
  error.value = ''
  try {
    const res = await fetch(`/api/holdem/games/${props.gameId}/start`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to start'
      return
    }
    const state = await res.json()
    emit('game-started', state)
  } catch (e) {
    error.value = 'Error: ' + e.message
  }
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Outfit:wght@300;400;500;600&family=Fira+Code:wght@400;500&display=swap');

.waiting-scene {
  --gold: var(--poker-gold);
  --gold-bright: var(--poker-gold-bright);
  --gold-dim: var(--poker-gold-dim);
  --bg: var(--poker-chrome);
  --bg-raised: var(--poker-chrome-raised);
  --bg-card: var(--poker-chrome-alt);
  --felt: #0f5e30;
  --text: var(--poker-text);
  --text-dim: var(--poker-text-dim);
  --text-muted: var(--poker-text-muted);

  font-family: 'Outfit', system-ui, sans-serif;
  color: var(--text);
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  position: relative;
  overflow: hidden;
  padding: 2rem 1rem;
}

/* ─── Background ─── */
.bg-pattern {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(ellipse at 30% 20%,
      rgba(201, 168, 76, 0.04) 0%,
      transparent 50%),
    radial-gradient(ellipse at 70% 80%, rgba(15, 94, 48, 0.06) 0%, transparent 50%);
  pointer-events: none;
}

.bg-pattern::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 5 L35 25 L55 30 L35 35 L30 55 L25 35 L5 30 L25 25 Z' fill='none' stroke='rgba(201,168,76,0.03)' stroke-width='0.5'/%3E%3C/svg%3E");
  background-size: 60px 60px;
  opacity: 0.8;
}

/* ─── Card Container ─── */
.waiting-card {
  position: relative;
  background: var(--bg-raised);
  border: 1px solid var(--poker-border-strong);
  border-radius: 16px;
  max-width: 440px;
  width: 100%;
  overflow: hidden;
}

.waiting-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--gold-dim), transparent);
}

/* ─── Header ─── */
.card-header {
  text-align: center;
  padding: 2rem 2rem 1.25rem;
  background: linear-gradient(180deg, var(--poker-hover) 0%, transparent 100%);
}

.brand-mark {
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.suit-deco {
  font-size: 1.2rem;
  opacity: 0.25;
}

.suit-deco:first-child {
  color: var(--text);
}

.suit-deco:last-child {
  color: #dc2626;
}

h1 {
  font-family: 'Cinzel', serif;
  font-weight: 700;
  font-size: 1.6rem;
  color: var(--gold);
  letter-spacing: 0.06em;
  margin: 0;
  line-height: 1.2;
}

.tagline {
  font-size: 0.85rem;
  color: var(--text-dim);
  margin-top: 0.3rem;
  letter-spacing: 0.04em;
}

/* ─── Game ID Row ─── */
.game-id-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 1.5rem;
  padding: 0.75rem 1rem;
  background: var(--poker-hover);
  border: 1px solid var(--poker-border);
  border-radius: 10px;
}

.game-id-display {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.id-label {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}

.id-value {
  font-family: 'Fira Code', monospace;
  font-size: 1.15rem;
  font-weight: 500;
  color: var(--gold);
  letter-spacing: 0.15em;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--poker-input-bg);
  border: 1px solid var(--poker-input-border);
  color: var(--text-dim);
  padding: 0.4rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'Outfit', sans-serif;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all 0.2s;
}

.copy-btn:hover {
  border-color: var(--gold-dim);
  color: var(--gold);
}

.copy-btn.copied {
  border-color: var(--felt);
  color: var(--success, #4caf50);
}

/* ─── Players Section ─── */
.players-section {
  margin: 1rem 1.5rem 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.6rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

.player-count {
  font-family: 'Fira Code', monospace;
  font-size: 0.8rem;
  color: var(--text);
}

.count-max {
  color: var(--text-muted);
}

.player-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.player-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 0.65rem;
  background: var(--poker-hover);
  border: 1px solid var(--poker-border);
  border-radius: 8px;
  transition: all 0.2s;
}

.player-row:hover:not(.empty-seat) {
  background: var(--poker-input-bg);
  border-color: var(--poker-input-border);
}

.player-row.empty-seat {
  opacity: 0.35;
  border-style: dashed;
}

.player-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: hsl(var(--hue, 0), 55%, 35%);
  border: 2px solid hsl(var(--hue, 0), 55%, 50%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.85rem;
  color: #fff;
  flex-shrink: 0;
}

.player-avatar.empty {
  background: var(--poker-border);
  border: 2px dashed var(--poker-border-strong);
  color: var(--text-muted);
  font-size: 0.8rem;
}

.player-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
}

.p-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--poker-name);
}

.p-chips {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-family: 'Fira Code', monospace;
  font-size: 0.7rem;
  color: var(--gold);
}

.empty-text {
  font-weight: 400;
  color: var(--text-muted);
  font-size: 0.8rem;
}

.seat-num {
  font-family: 'Fira Code', monospace;
  font-size: 0.65rem;
  color: var(--text-muted);
}

/* Player transition */
.player-item-enter-active {
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.player-item-leave-active {
  transition: all 0.2s ease;
}

.player-item-enter-from {
  opacity: 0;
  transform: translateX(-10px);
}

.player-item-leave-to {
  opacity: 0;
  transform: translateX(10px);
}

/* ─── Actions ─── */
.actions-section {
  padding: 1.25rem 1.5rem 0;
  text-align: center;
}

.action-buttons-row {
  display: flex;
  gap: 0.5rem;
}

.add-agent-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.8rem 1rem;
  background: var(--poker-input-bg);
  color: var(--text-dim);
  border: 1px solid var(--poker-input-border);
  border-radius: 10px;
  font-family: 'Outfit', sans-serif;
  font-weight: 500;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.add-agent-btn:hover:not(:disabled) {
  border-color: var(--gold-dim);
  color: var(--gold);
  background: var(--poker-hover);
}

.add-agent-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.deal-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.8rem 1.5rem;
  background: linear-gradient(135deg, var(--felt), #1a7a42);
  color: #fff;
  border: 1px solid var(--poker-border-strong);
  border-radius: 10px;
  font-family: 'Outfit', sans-serif;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.03em;
}

.deal-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #1a7a42, #22965a);
  box-shadow: 0 4px 20px rgba(15, 94, 48, 0.3);
  transform: translateY(-1px);
}

.deal-btn:active:not(:disabled) {
  transform: translateY(0);
}

.deal-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.deal-icon {
  font-size: 1.1rem;
  color: #dc2626;
}

.hint {
  font-size: 0.78rem;
  color: var(--text-dim);
  margin-top: 0.5rem;
}

.error-msg {
  font-size: 0.8rem;
  color: var(--error, #dc2626);
  margin-top: 0.5rem;
  font-weight: 500;
}

/* ─── Footer ─── */
.card-footer {
  padding: 1rem 1.5rem 1.5rem;
  text-align: center;
}

.leave-link {
  background: none;
  border: none;
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  transition: color 0.15s;
}

.leave-link:hover {
  color: var(--text-dim);
}

/* ─── Responsive ─── */
@media (max-width: 480px) {
  .waiting-scene {
    padding: 1rem 0.75rem;
  }

  .card-header {
    padding: 1.5rem 1.25rem 1rem;
  }

  h1 {
    font-size: 1.3rem;
  }

  .game-id-row {
    margin: 0 1rem;
  }

  .players-section {
    margin: 1rem 1rem 0;
  }

  .actions-section {
    padding: 1rem 1rem 0;
  }

  .card-footer {
    padding: 0.75rem 1rem 1.25rem;
  }
}
</style>
