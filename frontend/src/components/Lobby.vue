<template>
  <div class="lobby" :class="'lobby--' + selectedGame">
    <!-- Subtle ambient background -->
    <div class="ambient">
      <div class="ambient-grain"></div>
      <div class="ambient-glow"></div>
    </div>

    <div class="lobby-content">
      <!-- Header -->
      <header class="lobby-header">
        <div class="brand">
          <div class="brand-mark">
            <span class="mark-die">&#x2680;</span>
            <span class="mark-die">&#x2681;</span>
            <span class="mark-die">&#x2682;</span>
          </div>
          <h1 class="brand-title">Game Night</h1>
          <p class="brand-sub">Pick a game. Gather your players. Let's go.</p>
        </div>
      </header>

      <!-- URL-based game join view -->
      <template v-if="urlGameId">
        <section class="panel" v-if="urlGameLoading">
          <div class="panel-body">
            <p class="loading-text">
              <span class="loading-spinner"></span>
              Looking up game {{ urlGameId }}...
            </p>
          </div>
        </section>

        <section class="panel" v-else-if="urlGameError">
          <div class="panel-body">
            <p class="error-text">{{ urlGameError }}</p>
            <button class="btn-ghost" @click="$emit('clear-url-game')">Back to lobby</button>
          </div>
        </section>

        <section class="panel" v-else>
          <div class="panel-body">
            <div class="panel-header">
              <span class="panel-label">Game {{ urlGameId }}</span>
              <h2>{{ urlGameType === 'holdem' ? "Texas Hold'em" : 'Clue' }}</h2>
            </div>
            <p class="status-badge" :class="urlGameState?.status" v-if="urlGameState">
              <span class="status-dot"></span>
              {{ urlGameStatusText }}
              <span v-if="urlGameState.players" class="player-count">
                {{ urlGameState.players.length }}{{ urlGameType !== 'holdem' ? '/6' : '' }} players
              </span>
            </p>

            <!-- Rejoin as existing player -->
            <div v-if="urlGameState?.players?.length" class="players-section">
              <h3 class="section-label">Choose a player</h3>
              <ul class="player-list">
                <li v-for="p in urlGameState.players" :key="p.id" class="player-item" :class="{
                  eliminated: !p.active && urlGameState.status !== 'waiting'
                }" @click="rejoinAs(p)">
                  <div class="player-token" :class="{ 'has-portrait': CARD_IMAGES[p.character] }"
                    :style="tokenColor(p.character)">
                    <img v-if="CARD_IMAGES[p.character]" :src="CARD_IMAGES[p.character]" :alt="p.character"
                      class="player-portrait" />
                    <span v-else>{{ charAbbr(p.character) || p.name?.charAt(0) || '?' }}</span>
                  </div>
                  <div class="player-info">
                    <span class="player-name">{{ p.name }}</span>
                    <span v-if="p.character && p.character !== p.name" class="player-character">{{ p.character }}</span>
                  </div>
                  <span v-if="!p.active && urlGameState.status !== 'waiting'"
                    class="badge badge-out">Out</span>
                  <span v-else-if="p.type !== 'human'" class="badge badge-ai">{{
                    agentLabel(p.type)
                    }}</span>
                  <span v-else class="badge badge-human">Human</span>
                </li>
              </ul>
              <button class="btn-secondary full-width" @click="observeUrlGame">
                <span class="btn-icon">&#x1F441;</span> Watch
              </button>

              <details v-if="urlGameCanJoin" class="join-expand">
                <summary>Join as new player...</summary>
                <div class="form-stack">
                  <div class="input-wrap">
                    <input v-model="playerName" placeholder="Your name" @keyup.enter="joinUrlGame" />
                  </div>
                  <div class="select-wrap" v-if="urlGameType !== 'holdem'">
                    <select v-model="playerType">
                      <option value="human">Human Player</option>
                      <option value="agent">AI Agent</option>
                      <option value="llm_agent">LLM Agent</option>
                    </select>
                  </div>
                  <button class="btn-accent btn-primary" :disabled="!playerName" @click="joinUrlGame">
                    Join Game
                  </button>
                </div>
              </details>
            </div>

            <!-- No players yet -->
            <div v-else-if="urlGameCanJoin" class="form-stack">
              <div class="input-wrap">
                <input v-model="playerName" placeholder="Your name" @keyup.enter="joinUrlGame" />
              </div>
              <div class="select-wrap" v-if="urlGameType !== 'holdem'">
                <select v-model="playerType">
                  <option value="human">Human Player</option>
                  <option value="agent">AI Agent</option>
                  <option value="llm_agent">LLM Agent</option>
                </select>
              </div>
              <div class="btn-row">
                <button class="btn-accent btn-primary" :disabled="!playerName" @click="joinUrlGame">
                  Join Game
                </button>
                <button class="btn-secondary" @click="observeUrlGame">
                  <span class="btn-icon">&#x1F441;</span> Watch
                </button>
              </div>
            </div>

            <div v-else class="form-stack">
              <button class="btn-secondary full-width" @click="observeUrlGame">
                <span class="btn-icon">&#x1F441;</span> Watch as spectator
              </button>
            </div>

            <p v-if="error" class="error-text">{{ error }}</p>
            <button class="btn-ghost" @click="$emit('clear-url-game')">Back to lobby</button>
          </div>
        </section>
      </template>

      <!-- Normal lobby: game selection -->
      <template v-else>
        <!-- Game type cards -->
        <div class="game-grid">
          <button
            class="game-card game-card--clue"
            :class="{ selected: selectedGame === 'clue' }"
            @click="selectGame('clue')"
          >
            <div class="game-card-visual">
              <span class="game-card-icon">&#x1F50D;</span>
            </div>
            <div class="game-card-text">
              <h2 class="game-card-title">Clue</h2>
              <p class="game-card-desc">Deduce the suspect, weapon, and room. 3&ndash;6 players.</p>
            </div>
            <div class="game-card-arrow">&rsaquo;</div>
          </button>

          <button
            class="game-card game-card--holdem"
            :class="{ selected: selectedGame === 'holdem' }"
            @click="selectGame('holdem')"
          >
            <div class="game-card-visual">
              <span class="game-card-icon">&#x1F0CF;</span>
            </div>
            <div class="game-card-text">
              <h2 class="game-card-title">Texas Hold'em</h2>
              <p class="game-card-desc">No-limit poker. Bet, bluff, and take the pot.</p>
            </div>
            <div class="game-card-arrow">&rsaquo;</div>
          </button>
        </div>

        <!-- Action panels (create / join) — shown when a game is selected -->
        <transition name="slide-fade">
          <div v-if="selectedGame" class="action-panels">
            <div class="action-grid">
              <!-- Create -->
              <section class="panel panel-create">
                <div class="panel-body">
                  <div class="panel-header">
                    <span class="panel-label">{{ selectedGame === 'holdem' ? 'New Table' : 'New Game' }}</span>
                    <h2>Create</h2>
                  </div>
                  <div class="form-stack">
                    <div class="input-wrap">
                      <input v-model="playerName" placeholder="Your name" @keyup.enter="createGame" />
                    </div>
                    <div class="select-wrap" v-if="selectedGame === 'clue'">
                      <select v-model="playerType">
                        <option value="human">Human Player</option>
                        <option value="agent">AI Agent</option>
                        <option value="llm_agent">LLM Agent</option>
                      </select>
                    </div>
                    <template v-if="selectedGame === 'holdem'">
                      <div class="input-wrap buyin-row">
                        <label class="input-label">Buy-in</label>
                        <div class="dollar-input">
                          <span class="dollar-sign">$</span>
                          <input v-model.number="holdemBuyIn" type="number" min="1" step="1" placeholder="20" />
                        </div>
                      </div>
                      <label class="checkbox-row">
                        <input type="checkbox" v-model="holdemAllowRebuys" />
                        <span class="checkbox-label">Allow rebuys</span>
                      </label>
                    </template>
                    <button class="btn-accent btn-primary" :disabled="!playerName" @click="createGame">
                      {{ selectedGame === 'holdem' ? 'Deal Me In' : 'Start Game' }}
                    </button>
                  </div>
                </div>
              </section>

              <!-- Join -->
              <section class="panel panel-join">
                <div class="panel-body">
                  <div class="panel-header">
                    <span class="panel-label">Have a code?</span>
                    <h2>Join</h2>
                  </div>
                  <div class="form-stack">
                    <div class="input-wrap input-code">
                      <input v-model="joinGameId" placeholder="Game ID (e.g. ABC123)" @keyup.enter="joinGame"
                        style="text-transform: uppercase; letter-spacing: 0.15em" />
                    </div>
                    <div class="input-wrap">
                      <input v-model="playerName" placeholder="Your name" />
                    </div>
                    <div class="select-wrap" v-if="selectedGame === 'clue'">
                      <select v-model="playerType">
                        <option value="human">Human Player</option>
                        <option value="agent">AI Agent</option>
                        <option value="llm_agent">LLM Agent</option>
                      </select>
                    </div>
                    <div class="btn-row">
                      <button class="btn-accent btn-primary" :disabled="!joinGameId || !playerName" @click="joinGame">
                        Join
                      </button>
                      <button class="btn-secondary" :disabled="!joinGameId" @click="observeGame">
                        <span class="btn-icon">&#x1F441;</span> Watch
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </transition>

        <p v-if="error" class="error-text error-global">{{ error }}</p>
      </template>

      <!-- Footer -->
      <footer class="lobby-footer">
        <div class="footer-rule"></div>
        <div class="footer-theme">
          <ThemeSwitcher />
        </div>
        <a href="/admin" class="admin-link">Admin</a>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  urlGameId: { type: String, default: null },
  urlGameType: { type: String, default: 'clue' }
})

const emit = defineEmits(['game-joined', 'observe', 'rejoin', 'clear-url-game'])

const playerName = ref('')
const playerType = ref('human')
const selectedGame = ref(null)
const joinGameId = ref('')
const error = ref('')

// Hold'em game creation options
const holdemBuyIn = ref(20)
const holdemAllowRebuys = ref(false)

// URL game state
const urlGameState = ref(null)
const urlGameLoading = ref(false)
const urlGameError = ref('')

import { CHARACTER_COLORS, CHARACTER_ABBR, CARD_IMAGES } from '../constants/clue.js'
import ThemeSwitcher from './ThemeSwitcher.vue'

function selectGame(type) {
  selectedGame.value = selectedGame.value === type ? null : type
}

function tokenColor(character) {
  const c = CHARACTER_COLORS[character] || { bg: '#444', text: '#fff' }
  return { backgroundColor: c.bg, color: c.text, borderColor: c.bg }
}

function charAbbr(character) {
  return CHARACTER_ABBR[character] || ''
}

function agentLabel(type) {
  if (type === 'agent') return 'AI'
  if (type === 'llm_agent') return 'LLM'
  if (type === 'wanderer') return 'NPC'
  return type
}

const urlGameCanJoin = computed(() => {
  return urlGameState.value?.status === 'waiting'
})

const urlGameStatusText = computed(() => {
  const status = urlGameState.value?.status
  if (status === 'waiting') return 'Waiting for players'
  if (status === 'playing') return 'In progress'
  if (status === 'finished') return 'Finished'
  return ''
})

watch(
  () => props.urlGameId,
  (gid) => {
    if (gid) {
      fetchUrlGame(gid)
    } else {
      urlGameState.value = null
      urlGameLoading.value = false
      urlGameError.value = ''
    }
  },
  { immediate: true }
)

async function fetchUrlGame(gid) {
  urlGameLoading.value = true
  urlGameError.value = ''
  urlGameState.value = null
  try {
    const endpoint = props.urlGameType === 'holdem' ? `/holdem/games/${gid}` : `/games/${gid}`
    const res = await fetch(endpoint)
    if (!res.ok) {
      urlGameError.value = 'Game not found'
      return
    }
    const state = await res.json()
    urlGameState.value = state
    if (state.game_type === 'holdem') selectedGame.value = 'holdem'
  } catch (e) {
    urlGameError.value = 'Failed to load game: ' + e.message
  } finally {
    urlGameLoading.value = false
  }
}

async function joinUrlGame() {
  error.value = ''
  if (props.urlGameType === 'holdem' || selectedGame.value === 'holdem') {
    await doJoinHoldem(props.urlGameId)
  } else {
    await doJoin(props.urlGameId)
  }
}

function observeUrlGame() {
  emit('observe', { gameId: props.urlGameId, gameType: props.urlGameType })
}

function rejoinAs(player) {
  emit('rejoin', { gameId: props.urlGameId, playerId: player.id, gameType: props.urlGameType })
}

async function createGame() {
  error.value = ''
  try {
    if (selectedGame.value === 'holdem') {
      const buyInCents = Math.round(holdemBuyIn.value * 100)
      const res = await fetch('/holdem/games', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          buy_in: buyInCents,
          allow_rebuys: holdemAllowRebuys.value
        })
      })
      const { game_id } = await res.json()
      await doJoinHoldem(game_id)
    } else {
      const res = await fetch('/games', { method: 'POST' })
      const { game_id } = await res.json()
      await doJoin(game_id)
    }
  } catch (e) {
    error.value = 'Failed to create game: ' + e.message
  }
}

async function joinGame() {
  error.value = ''
  if (selectedGame.value === 'holdem') {
    await doJoinHoldem(joinGameId.value.trim().toUpperCase())
  } else {
    await doJoin(joinGameId.value.trim().toUpperCase())
  }
}

async function doJoin(gameId) {
  try {
    const res = await fetch(`/games/${gameId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_name: playerName.value,
        player_type: playerType.value
      })
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

async function doJoinHoldem(gameId) {
  try {
    const res = await fetch(`/holdem/games/${gameId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_name: playerName.value })
    })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to join'
      return
    }
    const { player_id } = await res.json()
    const stateRes = await fetch(`/holdem/games/${gameId}`)
    const state = await stateRes.json()
    emit('game-joined', { gameId, playerId: player_id, state, gameType: 'holdem' })
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
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,800&family=DM+Sans:wght@400;500;600&display=swap');

/* ==============================
   LOBBY SHELL
   ============================== */
.lobby {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  font-family: 'DM Sans', system-ui, sans-serif;
  background: var(--bg-page);
  color: var(--text-primary);
}

/* === Ambient background === */
.ambient {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.ambient-grain {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-size: 256px 256px;
}

.ambient-glow {
  position: absolute;
  inset: 0;
  opacity: var(--fog-opacity, 0.03);
  background:
    radial-gradient(ellipse at 25% 0%, var(--lobby-glow-1, rgba(180, 140, 60, 0.15)) 0%, transparent 55%),
    radial-gradient(ellipse at 75% 100%, var(--lobby-glow-2, rgba(60, 90, 140, 0.1)) 0%, transparent 50%);
}

/* ==============================
   CONTENT
   ============================== */
.lobby-content {
  position: relative;
  z-index: 2;
  max-width: 640px;
  margin: 0 auto;
  padding: 2.5rem 1.25rem 3rem;
}

/* ==============================
   HEADER / BRAND
   ============================== */
.brand {
  text-align: center;
  margin-bottom: 2.5rem;
  animation: brand-in 0.8s ease-out;
}

@keyframes brand-in {
  0% { opacity: 0; transform: translateY(-12px); }
  100% { opacity: 1; transform: translateY(0); }
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  margin-bottom: 0.75rem;
}

.mark-die {
  font-size: 1.3rem;
  opacity: 0.25;
  transition: opacity 0.3s;
}

.brand:hover .mark-die {
  opacity: 0.5;
}

.brand-title {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 2.8rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  line-height: 1.1;
}

.brand-sub {
  font-size: 0.95rem;
  color: var(--text-muted);
  margin-top: 0.5rem;
  letter-spacing: 0.01em;
}

/* ==============================
   GAME CARDS (type selection)
   ============================== */
.game-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
  animation: cards-in 0.6s ease-out 0.15s both;
}

@keyframes cards-in {
  0% { opacity: 0; transform: translateY(12px); }
  100% { opacity: 1; transform: translateY(0); }
}

.game-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.1rem 1.25rem;
  border-radius: 10px;
  border: 1.5px solid var(--border-card);
  background: var(--bg-panel);
  cursor: pointer;
  transition: all 0.25s ease;
  text-align: left;
  font-family: inherit;
  color: inherit;
  position: relative;
  overflow: hidden;
}

.game-card::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}

.game-card--clue::before {
  background: linear-gradient(135deg, rgba(180, 50, 50, 0.04) 0%, rgba(212, 168, 73, 0.04) 100%);
}

.game-card--holdem::before {
  background: linear-gradient(135deg, rgba(40, 120, 80, 0.04) 0%, rgba(60, 90, 160, 0.04) 100%);
}

.game-card:hover {
  border-color: var(--accent-border-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}

.game-card:hover::before {
  opacity: 1;
}

.game-card.selected {
  border-color: var(--accent-border-focus);
  box-shadow: 0 2px 16px var(--accent-glow);
}

.game-card.selected::before {
  opacity: 1;
}

.game-card-visual {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 1.5rem;
  transition: transform 0.25s;
}

.game-card:hover .game-card-visual {
  transform: scale(1.08);
}

.game-card--clue .game-card-visual {
  background: linear-gradient(135deg, #c0392b18 0%, #d4a84918 100%);
}

.game-card--holdem .game-card-visual {
  background: linear-gradient(135deg, #1a9e3f18 0%, #1a5fb418 100%);
}

.game-card-text {
  flex: 1;
  min-width: 0;
}

.game-card-title {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 1.15rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin-bottom: 0.15rem;
}

.game-card-desc {
  font-size: 0.82rem;
  color: var(--text-muted);
  line-height: 1.4;
}

.game-card-arrow {
  font-size: 1.6rem;
  color: var(--text-faint);
  transition: color 0.2s, transform 0.2s;
  flex-shrink: 0;
  line-height: 1;
}

.game-card.selected .game-card-arrow {
  color: var(--accent);
  transform: rotate(90deg);
}

/* ==============================
   ACTION PANELS (Create / Join)
   ============================== */
.slide-fade-enter-active {
  transition: all 0.35s ease;
}
.slide-fade-leave-active {
  transition: all 0.2s ease;
}
.slide-fade-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.action-grid {
  display: grid;
  gap: 1rem;
}

@media (min-width: 540px) {
  .action-grid {
    grid-template-columns: 1fr 1fr;
  }
}

/* ==============================
   PANELS (cards)
   ============================== */
.panel {
  border-radius: 10px;
  background: var(--bg-panel);
  border: 1px solid var(--border-card);
  overflow: hidden;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.panel:hover {
  border-color: var(--accent-border-hover);
}

.panel-body {
  padding: 1.5rem 1.25rem 1.25rem;
}

.panel-header {
  margin-bottom: 0.75rem;
}

.panel-label {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--accent);
  opacity: 0.7;
  margin-bottom: 0.2rem;
}

.panel-header h2 {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* ==============================
   STATUS BADGE
   ============================== */
.status-badge {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
  padding: 0.45rem 0.7rem;
  border-radius: 6px;
  background: var(--bg-input);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-badge.waiting .status-dot {
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent-glow);
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-badge.playing .status-dot {
  background: var(--success);
  box-shadow: 0 0 6px rgba(76, 175, 80, 0.3);
}

.status-badge.finished .status-dot {
  background: var(--text-dim);
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.player-count {
  margin-left: auto;
  font-size: 0.75rem;
  opacity: 0.65;
}

/* ==============================
   FORMS
   ============================== */
.form-stack {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.input-wrap {
  position: relative;
}

.input-wrap input,
.select-wrap select {
  display: block;
  width: 100%;
  padding: 0.6rem 0.85rem;
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: 'DM Sans', system-ui, sans-serif;
  font-size: 0.9rem;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
  outline: none;
}

.input-wrap input::placeholder {
  color: var(--text-dim);
}

.input-wrap input:focus,
.select-wrap select:focus {
  border-color: var(--accent-border-focus);
  background: var(--bg-input-focus);
  box-shadow: 0 0 0 3px var(--accent-bg);
}

.select-wrap {
  position: relative;
}

.select-wrap select {
  appearance: none;
  cursor: pointer;
  padding-right: 2rem;
}

.select-wrap::after {
  content: '\25BE';
  position: absolute;
  right: 0.85rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-dim);
  pointer-events: none;
  font-size: 0.75rem;
}

/* ==============================
   BUTTONS
   ============================== */
/* extends .btn-accent from components.css */
.btn-primary {
  padding: 0.6rem 1.25rem;
  font-family: 'DM Sans', system-ui, sans-serif;
  font-size: 0.88rem;
  letter-spacing: 0.02em;
}

.btn-primary:disabled {
  opacity: 0.35;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.55rem 1rem;
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-family: 'DM Sans', system-ui, sans-serif;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  border-color: var(--accent-border-focus);
  color: var(--accent);
  background: var(--accent-bg);
}

.btn-secondary:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-secondary.full-width {
  width: 100%;
}

.btn-icon {
  font-size: 0.8rem;
}

.btn-ghost {
  display: inline-block;
  margin-top: 0.75rem;
  padding: 0.35rem 0;
  background: none;
  border: none;
  color: var(--text-dim);
  font-family: 'DM Sans', system-ui, sans-serif;
  font-size: 0.8rem;
  cursor: pointer;
  transition: color 0.2s;
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-color: var(--border-card);
}

.btn-ghost:hover {
  color: var(--text-secondary);
}

.btn-row {
  display: flex;
  gap: 0.5rem;
}

.btn-row .btn-primary {
  flex: 1;
}

/* ==============================
   PLAYER LIST (URL join view)
   ============================== */
.section-label {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.6rem;
}

.player-list {
  list-style: none;
  margin-bottom: 0.75rem;
}

.player-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
  margin-bottom: 0.2rem;
}

.player-item:hover {
  background: var(--bg-hover);
  border-color: var(--accent-border);
}

.player-item.eliminated {
  opacity: 0.4;
}

.player-token {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
  flex-shrink: 0;
  overflow: hidden;
}

.player-token.has-portrait {
  background: none !important;
  border: 2px solid;
  border-color: inherit;
}

.player-portrait {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
  border-radius: 50%;
  display: block;
}

.player-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  text-align: left;
  min-width: 0;
}

.player-name {
  color: var(--text-primary);
  font-size: 0.85rem;
  font-weight: 500;
}

.player-character {
  color: var(--text-muted);
  font-size: 0.7rem;
}

.badge {
  font-size: 0.6rem;
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 600;
  flex-shrink: 0;
}

.badge-out {
  background: var(--error-bg);
  color: var(--error);
}

.badge-ai {
  background: var(--accent-bg);
  color: var(--accent);
}

.badge-human {
  background: var(--bg-input);
  color: var(--text-dim);
}

/* ==============================
   JOIN EXPAND
   ============================== */
.join-expand {
  margin-top: 0.6rem;
}

.join-expand summary {
  color: var(--text-dim);
  font-size: 0.8rem;
  cursor: pointer;
  transition: color 0.2s;
}

.join-expand summary:hover {
  color: var(--text-secondary);
}

.join-expand .form-stack {
  margin-top: 0.6rem;
}

/* ==============================
   LOADING
   ============================== */
.loading-text {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  color: var(--text-muted);
}

.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--accent-border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ==============================
   ERRORS
   ============================== */
.error-text {
  color: var(--error);
  font-size: 0.85rem;
  margin-top: 0.6rem;
  padding: 0.45rem 0.7rem;
  border-radius: 6px;
  background: var(--error-bg);
  border: 1px solid var(--error-border);
}

.error-global {
  text-align: center;
  margin-top: 1rem;
}

/* ==============================
   HOLD'EM BUY-IN
   ============================== */
.buyin-row {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.input-label {
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.dollar-input {
  position: relative;
  display: flex;
  align-items: center;
}

.dollar-sign {
  position: absolute;
  left: 0.7rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  pointer-events: none;
}

.dollar-input input {
  display: block;
  width: 100%;
  padding: 0.6rem 0.85rem 0.6rem 1.5rem;
  border: 1px solid var(--accent-border);
  border-radius: 6px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: 'DM Sans', system-ui, sans-serif;
  font-size: 0.9rem;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
  outline: none;
  -moz-appearance: textfield;
}

.dollar-input input::-webkit-outer-spin-button,
.dollar-input input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.dollar-input input:focus {
  border-color: var(--accent-border-focus);
  background: var(--bg-input-focus);
  box-shadow: 0 0 0 3px var(--accent-bg);
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  cursor: pointer;
  padding: 0.2rem 0;
}

.checkbox-row input[type='checkbox'] {
  width: 15px;
  height: 15px;
  accent-color: var(--accent);
  cursor: pointer;
}

.checkbox-label {
  font-size: 0.85rem;
  color: var(--text-muted);
}

/* ==============================
   FOOTER
   ============================== */
.lobby-footer {
  margin-top: 2.5rem;
  text-align: center;
  animation: fade-in 1.5s ease-out 0.6s both;
}

@keyframes fade-in {
  0% { opacity: 0; }
  100% { opacity: 1; }
}

.footer-rule {
  width: 40px;
  height: 1px;
  background: var(--border-card);
  margin: 0 auto 0.75rem;
}

.footer-theme {
  display: flex;
  justify-content: center;
  margin-bottom: 0.5rem;
}

.admin-link {
  display: inline-block;
  font-size: 0.65rem;
  color: var(--text-dim);
  text-decoration: none;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  transition: color 0.2s;
}

.admin-link:hover {
  color: var(--accent);
}

/* ==============================
   RESPONSIVE
   ============================== */
@media (max-width: 539px) {
  .brand-title {
    font-size: 2.2rem;
  }

  .panel-body {
    padding: 1.25rem 1rem 1rem;
  }
}
</style>
