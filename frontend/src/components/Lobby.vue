<template>
  <div class="lobby">
    <h1>🔍 Clue Board Game</h1>

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
      <button :disabled="!joinGameId || !playerName" @click="joinGame">Join Game</button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['game-joined'])

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
</script>

<style scoped>
.lobby { max-width: 500px; margin: 4rem auto; text-align: center; }
h1 { font-size: 2.5rem; margin-bottom: 2rem; color: #c9a84c; }
.panel { background: #16213e; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
h2 { margin-bottom: 1rem; font-size: 1.2rem; }
input, select { display: block; width: 100%; margin-bottom: 0.75rem; padding: 0.5rem; border-radius: 4px; border: 1px solid #444; background: #0f3460; color: #eee; }
button { background: #c9a84c; color: #1a1a2e; border: none; padding: 0.6rem 1.5rem; border-radius: 4px; cursor: pointer; font-weight: bold; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #e74c3c; margin-top: 1rem; }
</style>
