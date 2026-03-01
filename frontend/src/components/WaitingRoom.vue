<template>
  <div class="waiting-room">
    <h1>CLUE</h1>
    <p class="subtitle">Waiting Room</p>

    <div class="game-id-box">
      <span>Game ID: <strong>{{ gameId }}</strong></span>
      <button class="copy-btn" @click="copyLink" :title="copied ? 'Copied!' : 'Copy invite link'">
        {{ copied ? 'Copied!' : 'Copy Link' }}
      </button>
    </div>

    <section class="panel">
      <h2>Players ({{ players.length }} / 6)</h2>
      <ul>
        <li v-for="p in players" :key="p.id">
          <span class="player-info">
            <span class="player-token" :style="tokenStyle(p)">{{ abbr(p.character) }}</span>
            <span class="player-name">{{ p.name }}</span>
            <span class="player-character">{{ p.character }}</span>
          </span>
          <span class="badge">{{ p.type }}</span>
        </li>
      </ul>
    </section>

    <div class="add-agent-section" v-if="players.length < 6">
      <div class="add-agent-buttons">
        <button class="add-agent-btn" @click="addAgent('agent')" :disabled="addingAgent">
          + Add Agent
        </button>
        <button class="add-agent-btn llm" @click="addAgent('llm_agent')" :disabled="addingAgent">
          + Add LLM Agent
        </button>
      </div>
    </div>

    <button
      class="start-btn"
      :disabled="players.length < 2"
      @click="startGame"
    >
      Start Game
    </button>
    <p v-if="players.length < 2" class="hint">Need at least 2 players to start.</p>
    <p v-if="error" class="error">{{ error }}</p>
    <button class="leave-btn" @click="$emit('leave-game')">Leave Game</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

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
  players: Array,
})
const emit = defineEmits(['game-started', 'leave-game'])

const error = ref('')
const copied = ref(false)
const addingAgent = ref(false)

function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

function tokenStyle(player) {
  const colors = CHARACTER_COLORS[player.character] ?? { bg: '#666', text: '#fff' }
  return { backgroundColor: colors.bg, color: colors.text }
}

function copyLink() {
  const url = `${window.location.origin}/game/${props.gameId}`
  navigator.clipboard.writeText(url)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function addAgent(agentType) {
  error.value = ''
  addingAgent.value = true
  try {
    const res = await fetch(`/games/${props.gameId}/add_agent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_type: agentType })
    })
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
.waiting-room {
  max-width: 480px;
  margin: 3rem auto;
  text-align: center;
}

h1 {
  font-size: 2.5rem;
  color: #c9a84c;
  letter-spacing: 0.3em;
  margin-bottom: 0.1rem;
  text-shadow: 0 0 20px rgba(201, 168, 76, 0.3);
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
  color: #c9a84c;
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
  border-color: #c9a84c;
  color: #c9a84c;
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

ul {
  list-style: none;
}

li {
  padding: 0.5rem 0.4rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

li:last-child {
  border-bottom: none;
}

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
  font-size: 0.65rem;
  font-weight: bold;
  box-shadow: 0 1px 3px rgba(0,0,0,0.4);
}

.player-name {
  font-weight: bold;
  color: #eee;
}

.player-character {
  color: #778;
  font-style: italic;
  font-size: 0.85rem;
}

.badge {
  background: #0f3460;
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-size: 0.7rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.add-agent-section {
  margin-bottom: 1rem;
}

.add-agent-buttons {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
}

.add-agent-btn {
  background: #0f3460;
  color: #aab;
  border: 1px solid #334;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.2s;
}

.add-agent-btn:hover:not(:disabled) {
  border-color: #c9a84c;
  color: #c9a84c;
}

.add-agent-btn.llm {
  border-color: #8e44ad40;
}

.add-agent-btn.llm:hover:not(:disabled) {
  border-color: #8e44ad;
  color: #8e44ad;
}

.add-agent-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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

.start-btn:hover:not(:disabled) {
  background: #229954;
}

.start-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

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
  font-weight: normal;
  font-size: 0.85rem;
  margin-top: 1rem;
  cursor: pointer;
  text-decoration: underline;
}

.leave-btn:hover {
  color: #aab;
}
</style>
