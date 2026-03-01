<template>
  <div class="lobby">
    <div class="lobby-header">
      <h1>CLUE</h1>
      <p class="subtitle">The Classic Mystery Game</p>
    </div>

    <section class="panel">
      <h2>Create a New Game</h2>
      <input v-model="playerName" placeholder="Your name" />
      <select v-model="playerType">
        <option value="human">Human</option>
        <option value="llm">LLM Agent</option>
      </select>
      <button :disabled="!playerName" @click="createGame">Create Game</button>
    </section>

    <section class="panel">
      <h2>Join Existing Game</h2>
      <input v-model="joinGameId" placeholder="Game ID (e.g. ABC123)" />
      <input v-model="playerName" placeholder="Your name" />
      <select v-model="playerType">
        <option value="human">Human</option>
        <option value="llm">LLM Agent</option>
      </select>
      <div class="join-buttons">
        <button :disabled="!joinGameId || !playerName" @click="joinGame">Join Game</button>
        <button class="observe-btn" :disabled="!joinGameId" @click="observeGame">Watch as Observer</button>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['game-joined', 'observe'])

const playerName = ref('')
const playerType = ref('human')
const joinGameId = ref('')
const error = ref('')

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

.error {
  color: #e74c3c;
  margin-top: 1rem;
  font-size: 0.9rem;
}
</style>
