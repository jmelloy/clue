<template>
  <div class="lobby">
    <div class="lobby-header">
      <h1>CLUE</h1>
      <p class="subtitle">The Classic Mystery Game</p>
    </div>

    <!-- URL-based game join: show focused view for a specific game -->
    <template v-if="urlGameId">
      <section class="panel" v-if="urlGameLoading">
        <p class="loading">Loading game {{ urlGameId }}...</p>
      </section>

      <section class="panel" v-else-if="urlGameError">
        <p class="error">{{ urlGameError }}</p>
        <button class="back-btn" @click="$emit('clear-url-game')">Back to Lobby</button>
      </section>

      <section class="panel" v-else>
        <h2>Game {{ urlGameId }}</h2>
        <p class="game-status-info" v-if="urlGameState">
          {{ urlGameStatusText }}
          <span v-if="urlGameState.players">
            &mdash; {{ urlGameState.players.length }} player{{ urlGameState.players.length !== 1 ? 's' : '' }}
          </span>
        </p>

        <div v-if="urlGameCanJoin" class="join-section">
          <input v-model="playerName" placeholder="Your name" @keyup.enter="joinUrlGame" />
          <select v-model="playerType">
            <option value="human">Human</option>
            <option value="agent">Random Agent</option>
            <option value="llm_agent">LLM Agent</option>
          </select>
          <div class="join-buttons">
            <button :disabled="!playerName" @click="joinUrlGame">Join Game</button>
            <button class="observe-btn" @click="observeUrlGame">Watch as Observer</button>
          </div>
        </div>

        <div v-else class="join-section">
          <button class="observe-btn full-width" @click="observeUrlGame">Watch as Observer</button>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <button class="back-btn" @click="$emit('clear-url-game')">Back to Lobby</button>
      </section>
    </template>

    <!-- Normal lobby view -->
    <template v-else>
      <section class="panel">
        <h2>Create a New Game</h2>
        <input v-model="playerName" placeholder="Your name" />
        <select v-model="playerType">
          <option value="human">Human</option>
          <option value="agent">Random Agent</option>
          <option value="llm_agent">LLM Agent</option>
        </select>
        <button :disabled="!playerName" @click="createGame">Create Game</button>
      </section>

      <section class="panel">
        <h2>Join Existing Game</h2>
        <input v-model="joinGameId" placeholder="Game ID (e.g. ABC123)" />
        <input v-model="playerName" placeholder="Your name" />
        <select v-model="playerType">
          <option value="human">Human</option>
          <option value="agent">Random Agent</option>
          <option value="llm_agent">LLM Agent</option>
        </select>
        <div class="join-buttons">
          <button :disabled="!joinGameId || !playerName" @click="joinGame">Join Game</button>
          <button class="observe-btn" :disabled="!joinGameId" @click="observeGame">Watch as Observer</button>
        </div>
      </section>

      <p v-if="error" class="error">{{ error }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  urlGameId: { type: String, default: null },
})

const emit = defineEmits(['game-joined', 'observe', 'clear-url-game'])

const playerName = ref('')
const playerType = ref('human')
const joinGameId = ref('')
const error = ref('')

// URL game state
const urlGameState = ref(null)
const urlGameLoading = ref(false)
const urlGameError = ref('')

const urlGameCanJoin = computed(() => {
  return urlGameState.value?.status === 'waiting'
})

const urlGameStatusText = computed(() => {
  const status = urlGameState.value?.status
  if (status === 'waiting') return 'Waiting for players'
  if (status === 'playing') return 'Game in progress'
  if (status === 'finished') return 'Game finished'
  return ''
})

watch(() => props.urlGameId, (gid) => {
  if (gid) {
    fetchUrlGame(gid)
  } else {
    urlGameState.value = null
    urlGameLoading.value = false
    urlGameError.value = ''
  }
}, { immediate: true })

async function fetchUrlGame(gid) {
  urlGameLoading.value = true
  urlGameError.value = ''
  urlGameState.value = null
  try {
    const res = await fetch(`/games/${gid}`)
    if (!res.ok) {
      urlGameError.value = 'Game not found'
      return
    }
    urlGameState.value = await res.json()
  } catch (e) {
    urlGameError.value = 'Failed to load game: ' + e.message
  } finally {
    urlGameLoading.value = false
  }
}

async function joinUrlGame() {
  error.value = ''
  await doJoin(props.urlGameId)
}

function observeUrlGame() {
  emit('observe', { gameId: props.urlGameId })
}

async function createGame() {
  error.value = ''
  try {
    const res = await fetch('/games', { method: 'POST' })
    const { game_id } = await res.json()
    await doJoin(game_id)
  } catch (e) {
    error.value = 'Failed to create game: ' + e.message
  }
}

async function joinGame() {
  error.value = ''
  await doJoin(joinGameId.value.trim().toUpperCase())
}

async function doJoin(gameId) {
  try {
    const res = await fetch(`/games/${gameId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_name: playerName.value, player_type: playerType.value })
    })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to join'
      return
    }
    const { player_id } = await res.json()
    const stateRes = await fetch(`/games/${gameId}`)
    const state = await stateRes.json()
    emit('game-joined', { gameId, playerId: player_id, state })
  } catch (e) {
    error.value = 'Error: ' + e.message
  }
}

async function observeGame() {
  error.value = ''
  const gid = joinGameId.value.trim().toUpperCase()
  try {
    const res = await fetch(`/games/${gid}`)
    if (!res.ok) {
      error.value = 'Game not found'
      return
    }
    emit('observe', { gameId: gid })
  } catch (e) {
    error.value = 'Error: ' + e.message
  }
}
</script>

<style scoped>
.lobby {
  max-width: 480px;
  margin: 3rem auto;
  text-align: center;
}

.lobby-header {
  margin-bottom: 2rem;
}

.lobby-header h1 {
  font-size: 3rem;
  color: #c9a84c;
  letter-spacing: 0.3em;
  margin-bottom: 0.25rem;
  text-shadow: 0 0 20px rgba(201, 168, 76, 0.3);
}

.subtitle {
  color: #667;
  font-style: italic;
  font-size: 1rem;
}

.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.5rem;
  margin-bottom: 1.25rem;
}

h2 {
  margin-bottom: 1rem;
  font-size: 1.1rem;
  color: #ddd;
}

.game-status-info {
  color: #8899aa;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.join-section {
  margin-top: 0.5rem;
}

.loading {
  color: #8899aa;
  font-style: italic;
}

input, select {
  display: block;
  width: 100%;
  margin-bottom: 0.75rem;
  padding: 0.55rem 0.75rem;
  border-radius: 6px;
  border: 1px solid #334;
  background: #0f3460;
  color: #eee;
  font-size: 0.95rem;
}

input::placeholder {
  color: #557;
}

button {
  background: #c9a84c;
  color: #1a1a2e;
  border: none;
  padding: 0.6rem 1.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.95rem;
  transition: background 0.2s;
}

button:hover:not(:disabled) {
  background: #d4b85c;
}

button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.join-buttons {
  display: flex;
  gap: 0.5rem;
}

.join-buttons button {
  flex: 1;
}

.observe-btn {
  background: transparent;
  border: 1px solid #556;
  color: #aab;
  font-weight: normal;
}

.observe-btn:hover:not(:disabled) {
  border-color: #3498db;
  color: #3498db;
  background: rgba(52, 152, 219, 0.1);
}

.observe-btn.full-width {
  width: 100%;
}

.back-btn {
  background: transparent;
  border: none;
  color: #667;
  font-weight: normal;
  font-size: 0.85rem;
  margin-top: 1rem;
  cursor: pointer;
  text-decoration: underline;
}

.back-btn:hover {
  color: #aab;
}

.error {
  color: #e74c3c;
  margin-top: 1rem;
  font-size: 0.9rem;
}
</style>
