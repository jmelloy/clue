<template>
  <div class="admin-container">
    <div class="admin-header">
      <h1 class="admin-title">Game Administration</h1>
      <div class="admin-actions">
        <button class="refresh-btn" @click="fetchGames" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <button class="back-btn" @click="$emit('go-home')">Back to Lobby</button>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ games.length }}</div>
        <div class="stat-label">Total Games</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ playingCount }}</div>
        <div class="stat-label">In Progress</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ waitingCount }}</div>
        <div class="stat-label">Waiting</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ finishedCount }}</div>
        <div class="stat-label">Finished</div>
      </div>
    </div>

    <div class="filter-row">
      <button v-for="f in filters" :key="f.value" class="filter-btn" :class="{ active: activeFilter === f.value }"
        @click="activeFilter = f.value">
        {{ f.label }}
      </button>
    </div>

    <div v-if="!loading && filteredGames.length === 0" class="empty-state">No games found.</div>

    <div class="games-grid">
      <div v-for="game in filteredGames" :key="game.game_id" class="game-card" :class="[`status-${game.status}`]"
        @click="openGame(game)">
        <div class="game-card-header">
          <span class="game-id">{{ game.game_id }}</span>
          <span class="game-type-badge" :class="game.game_type">
            {{ game.game_type === 'clue' ? 'Clue' : "Hold'em" }}
          </span>
        </div>

        <div class="game-status-row">
          <span class="status-dot" :class="game.status"></span>
          <span class="status-text">{{ game.status }}</span>
          <span v-if="game.winner" class="winner-text">Winner: {{ playerName(game, game.winner) }}</span>
        </div>

        <div class="players-list">
          <div v-for="(p, i) in game.players" :key="i" class="player-row">
            <span class="player-name">{{ p.name }}</span>
            <span class="player-type" :class="p.type">{{ p.type }}</span>
            <span v-if="p.character" class="player-character">{{ p.character }}</span>
            <span v-if="p.chips != null" class="player-chips">${{ (p.chips / 100).toFixed(2) }}</span>
          </div>
        </div>

        <div class="game-meta">
          <span v-if="game.turn_number != null">Turn {{ game.turn_number }}</span>
          <span v-if="game.hand_number != null">Hand #{{ game.hand_number }}</span>
          <span v-if="game.pot != null">Pot: ${{ (game.pot / 100).toFixed(2) }}</span>
        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div v-if="selectedGame" class="modal-overlay" @click.self="selectedGame = null">
      <div class="modal-content">
        <div class="modal-header">
          <h2>
            {{ selectedGame.game_id }}
            <span class="game-type-badge" :class="selectedGame.game_type">{{
              selectedGame.game_type === 'clue' ? 'Clue' : "Hold'em"
              }}</span>
          </h2>
          <button class="close-btn" @click="selectedGame = null">&times;</button>
        </div>
        <div v-if="detailLoading" class="modal-loading">Loading details...</div>
        <div v-else-if="gameDetail" class="modal-body">
          <h3>State</h3>
          <pre class="json-view">{{ JSON.stringify(gameDetail.state, null, 2) }}</pre>
          <h3 v-if="gameDetail.log && gameDetail.log.length">
            Log ({{ gameDetail.log.length }} entries)
          </h3>
          <pre v-if="gameDetail.log && gameDetail.log.length" class="json-view log-view">{{
            JSON.stringify(gameDetail.log.slice(-20), null, 2)
          }}</pre>
        </div>
        <div class="modal-footer">
          <button class="observe-btn" @click="observeGame(selectedGame)">Observe Game</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits(['go-home', 'observe-game'])

const games = ref([])
const loading = ref(false)
const error = ref(null)
const activeFilter = ref('all')
const selectedGame = ref(null)
const gameDetail = ref(null)
const detailLoading = ref(false)

const filters = [
  { label: 'All', value: 'all' },
  { label: 'In Progress', value: 'playing' },
  { label: 'Waiting', value: 'waiting' },
  { label: 'Finished', value: 'finished' },
  { label: 'Clue', value: 'clue' },
  { label: "Hold'em", value: 'holdem' }
]

const playingCount = computed(() => games.value.filter((g) => g.status === 'playing').length)
const waitingCount = computed(() => games.value.filter((g) => g.status === 'waiting').length)
const finishedCount = computed(() => games.value.filter((g) => g.status === 'finished').length)

const filteredGames = computed(() => {
  if (activeFilter.value === 'all') return games.value
  if (['clue', 'holdem'].includes(activeFilter.value)) {
    return games.value.filter((g) => g.game_type === activeFilter.value)
  }
  return games.value.filter((g) => g.status === activeFilter.value)
})

function playerName(game, playerId) {
  const p = game.players.find((pl) => pl.name === playerId)
  return p ? p.name : playerId
}

async function fetchGames() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch('/api/admin/games')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    games.value = data.games
  } catch (e) {
    error.value = `Failed to load games: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function openGame(game) {
  selectedGame.value = game
  detailLoading.value = true
  gameDetail.value = null
  try {
    const res = await fetch(`/api/admin/games/${game.game_id}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    gameDetail.value = await res.json()
  } catch (e) {
    error.value = `Failed to load game details: ${e.message}`
  } finally {
    detailLoading.value = false
  }
}

function observeGame(game) {
  emit('observe-game', { gameId: game.game_id, gameType: game.game_type })
}

onMounted(fetchGames)
</script>

<style scoped>
.admin-container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
  font-family: 'Crimson Text', Georgia, serif;
  color: var(--text-primary);
  min-height: 100vh;
  min-height: 100dvh;
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.admin-title {
  font-size: 1.8rem;
  color: var(--accent);
  margin: 0;
  letter-spacing: 0.05em;
}

.admin-actions {
  display: flex;
  gap: 0.75rem;
}

.refresh-btn,
.back-btn {
  padding: 0.5rem 1.2rem;
  border-radius: 6px;
  border: 1px solid var(--accent-border-hover);
  background: var(--bg-panel);
  color: var(--accent);
  font-family: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  transition: all 0.3s;
}

.refresh-btn:hover,
.back-btn:hover {
  border-color: var(--accent-border-focus);
  box-shadow: 0 2px 12px var(--accent-glow);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
  color: var(--error);
  font-size: 0.9rem;
}

/* Stats */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-card);
  border-radius: 8px;
  padding: 1rem;
  text-align: center;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent);
}

.stat-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-secondary);
  margin-top: 0.25rem;
}

/* Filters */
.filter-row {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

.filter-btn {
  padding: 0.4rem 1rem;
  border-radius: 20px;
  border: 1px solid var(--accent-border);
  background: transparent;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.3s;
  letter-spacing: 0.05em;
}

.filter-btn:hover {
  border-color: var(--accent-border-hover);
  color: var(--accent);
}

.filter-btn.active {
  background: var(--accent-bg);
  border-color: var(--accent-border-hover);
  color: var(--accent);
}

.empty-state {
  text-align: center;
  color: var(--text-dim);
  padding: 3rem;
  font-size: 1.1rem;
}

/* Game cards grid */
.games-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.game-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-card);
  border-radius: 10px;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.3s;
}

.game-card:hover {
  border-color: var(--accent-border-hover);
  box-shadow: 0 4px 20px var(--accent-glow);
  transform: translateY(-1px);
}

.game-card.status-playing {
  border-left: 3px solid var(--success);
}

.game-card.status-waiting {
  border-left: 3px solid var(--accent);
}

.game-card.status-finished {
  border-left: 3px solid var(--text-dim);
}

.game-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.game-id {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.1em;
  font-family: monospace;
}

.game-type-badge {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-weight: 600;
}

.game-type-badge.clue {
  background: var(--badge-clue-bg);
  color: var(--badge-clue-text);
  border: 1px solid var(--badge-clue-border);
}

.game-type-badge.holdem {
  background: var(--badge-holdem-bg);
  color: var(--badge-holdem-text);
  border: 1px solid var(--badge-holdem-border);
}

.game-status-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.playing {
  background: var(--success);
  box-shadow: 0 0 6px var(--success-border);
}

.status-dot.waiting {
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent-glow);
}

.status-dot.finished {
  background: var(--text-dim);
}

.status-text {
  font-size: 0.85rem;
  text-transform: capitalize;
  color: var(--text-secondary);
}

.winner-text {
  font-size: 0.8rem;
  color: var(--success);
  margin-left: auto;
}

.players-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.75rem;
}

.player-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.player-name {
  color: var(--text-primary);
}

.player-type {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-dim);
}

.player-type.agent,
.player-type.holdem_agent {
  color: var(--tag-agent-text);
  background: var(--tag-agent-bg);
}

.player-type.llm_agent {
  color: var(--tag-llm-text);
  background: var(--tag-llm-bg);
}

.player-type.wanderer {
  color: var(--tag-wanderer-text);
  background: var(--tag-wanderer-bg);
}

.player-character {
  color: var(--text-secondary);
  font-style: italic;
  font-size: 0.8rem;
}

.player-chips {
  margin-left: auto;
  color: var(--success);
  font-family: monospace;
  font-size: 0.8rem;
}

.game-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: var(--text-dim);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
}

.modal-content {
  background: var(--bg-panel-solid);
  border: 1px solid var(--accent-border-hover);
  border-radius: 12px;
  max-width: 800px;
  width: 100%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-card);
}

.modal-header h2 {
  margin: 0;
  color: var(--accent);
  font-size: 1.3rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0.25rem;
  line-height: 1;
}

.close-btn:hover {
  color: var(--accent);
}

.modal-loading {
  padding: 3rem;
  text-align: center;
  color: var(--text-secondary);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.modal-body h3 {
  color: var(--accent);
  font-size: 1rem;
  margin: 1rem 0 0.5rem;
  letter-spacing: 0.05em;
}

.modal-body h3:first-child {
  margin-top: 0;
}

.json-view {
  background: var(--bg-input);
  border: 1px solid var(--border-card);
  border-radius: 6px;
  padding: 1rem;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 0.75rem;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.log-view {
  max-height: 300px;
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-card);
  display: flex;
  justify-content: flex-end;
}

.observe-btn {
  padding: 0.5rem 1.5rem;
  border-radius: 6px;
  border: 1px solid var(--success-border);
  background: var(--success-bg);
  color: var(--success);
  font-family: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: all 0.3s;
}

.observe-btn:hover {
  filter: brightness(1.15);
}

@media (max-width: 600px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .games-grid {
    grid-template-columns: 1fr;
  }

  .admin-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
