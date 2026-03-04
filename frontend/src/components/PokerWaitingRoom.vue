<template>
  <div class="waiting-room">
    <h1>TEXAS HOLD'EM</h1>
    <p class="subtitle">Waiting Room</p>

    <div class="game-id-box">
      <span>Game ID: <strong>{{ gameId }}</strong></span>
      <button class="copy-btn" @click="copyLink" :title="copied ? 'Copied!' : 'Copy invite link'">
        {{ copied ? 'Copied!' : 'Copy Link' }}
      </button>
    </div>

    <section class="panel">
      <h2>Players ({{ players.length }} / 10)</h2>
      <ul>
        <li v-for="p in players" :key="p.id">
          <span class="player-info">
            <span class="player-token" :style="{ backgroundColor: seatColor(p) }">{{ seatIndex(p) + 1 }}</span>
            <span class="player-name">{{ p.name }}</span>
            <span class="player-chips">{{ p.chips }} chips</span>
          </span>
        </li>
      </ul>
    </section>

    <button
      class="start-btn"
      :disabled="players.length < 2"
      @click="startGame"
    >
      Deal Cards
    </button>
    <p v-if="players.length < 2" class="hint">Need at least 2 players to start.</p>
    <p v-if="error" class="error">{{ error }}</p>
    <button class="leave-btn" @click="$emit('leave-game')">Leave Table</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const SEAT_COLORS = [
  '#e74c3c', '#f39c12', '#27ae60', '#2980b9', '#8e44ad',
  '#e67e22', '#1abc9c', '#e84393', '#00b894', '#6c5ce7',
]

const props = defineProps({
  gameId: String,
  playerId: String,
  players: Array,
})
const emit = defineEmits(['game-started', 'leave-game'])

const error = ref('')
const copied = ref(false)

function seatIndex(player) {
  return props.players.indexOf(player)
}

function seatColor(player) {
  return SEAT_COLORS[seatIndex(player) % SEAT_COLORS.length]
}

function copyLink() {
  const url = `${window.location.origin}/holdem/${props.gameId}`
  navigator.clipboard.writeText(url)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function startGame() {
  error.value = ''
  try {
    const res = await fetch(`/holdem/games/${props.gameId}/start`, { method: 'POST' })
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
.waiting-room {
  max-width: 480px;
  margin: 3rem auto;
  text-align: center;
}

h1 {
  font-size: 2.5rem;
  color: #27ae60;
  letter-spacing: 0.15em;
  margin-bottom: 0.1rem;
  text-shadow: 0 0 20px rgba(39, 174, 96, 0.3);
}

.subtitle {
  color: #667;
  font-style: italic;
  margin-bottom: 1.5rem;
}

.game-id-box {
  background: #16213e;
  padding: 0.8rem 1.2rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  align-items: center;
  font-size: 1.1rem;
}

.game-id-box strong {
  color: #27ae60;
  font-family: monospace;
  letter-spacing: 0.1em;
}

.copy-btn {
  background: #0f3460;
  color: #aab;
  border: 1px solid #334;
  padding: 0.3rem 0.7rem;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
}

.copy-btn:hover {
  border-color: #27ae60;
  color: #27ae60;
}

.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}

h2 {
  margin-bottom: 0.75rem;
  font-size: 1rem;
  color: #ddd;
}

ul { list-style: none; }

li {
  padding: 0.5rem 0.4rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

li:last-child { border-bottom: none; }

.player-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.player-token {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: bold;
  color: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.4);
}

.player-name {
  font-weight: bold;
  color: #eee;
}

.player-chips {
  color: #778;
  font-size: 0.85rem;
}

.start-btn {
  background: #27ae60;
  color: #fff;
  border: none;
  padding: 0.75rem 2.5rem;
  border-radius: 8px;
  font-size: 1.1rem;
  cursor: pointer;
  font-weight: bold;
  transition: background 0.2s;
}

.start-btn:hover:not(:disabled) { background: #229954; }
.start-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.hint {
  color: #667;
  margin-top: 0.5rem;
  font-size: 0.85rem;
}

.error {
  color: #e74c3c;
  margin-top: 0.5rem;
  font-size: 0.9rem;
}

.leave-btn {
  background: transparent;
  border: none;
  color: #667;
  font-size: 0.85rem;
  margin-top: 1rem;
  cursor: pointer;
  text-decoration: underline;
}

.leave-btn:hover { color: #aab; }
</style>
