<template>
  <div class="waiting-room">
    <h1>🎲 Waiting Room</h1>

    <div class="game-id-box">
      <span>Game ID: <strong>{{ gameId }}</strong></span>
      <button @click="copyId">📋 Copy</button>
    </div>

    <section class="panel">
      <h2>Players ({{ players.length }})</h2>
      <ul>
        <li v-for="p in players" :key="p.id">
          {{ p.name }} — <em>{{ p.character }}</em>
          <span class="badge">{{ p.type }}</span>
        </li>
      </ul>
    </section>

    <button
      class="start-btn"
      :disabled="players.length < 2"
      @click="startGame"
    >
      Start Game
    </button>
    <p v-if="players.length < 2" class="hint">Need at least 2 players to start.</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  gameId: String,
  playerId: String,
  players: Array,
})
const emit = defineEmits(['game-started'])

const error = ref('')

function copyId() {
  navigator.clipboard.writeText(props.gameId)
}

async function startGame() {
  error.value = ''
  try {
    const res = await fetch(`/games/${props.gameId}/start`, { method: 'POST' })
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
.waiting-room { max-width: 500px; margin: 3rem auto; text-align: center; }
h1 { color: #c9a84c; margin-bottom: 1.5rem; }
.game-id-box { background: #16213e; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; display: flex; justify-content: center; gap: 1rem; align-items: center; }
.panel { background: #16213e; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }
ul { list-style: none; }
li { padding: 0.4rem 0; display: flex; justify-content: space-between; align-items: center; }
.badge { background: #0f3460; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; }
.start-btn { background: #27ae60; color: #fff; border: none; padding: 0.75rem 2rem; border-radius: 6px; font-size: 1.1rem; cursor: pointer; font-weight: bold; }
.start-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.hint { color: #888; margin-top: 0.5rem; font-size: 0.9rem; }
.error { color: #e74c3c; margin-top: 0.5rem; }
button { background: #c9a84c; color: #1a1a2e; border: none; padding: 0.4rem 0.9rem; border-radius: 4px; cursor: pointer; }
</style>
