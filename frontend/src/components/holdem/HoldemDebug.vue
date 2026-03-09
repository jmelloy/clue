<template>
  <div class="debug-page">
    <header class="debug-header">
      <h1>Hold'em Debug: {{ gameId }}</h1>
      <div class="header-actions">
        <button class="btn-refresh" @click="fetchDebug" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <label class="auto-refresh-label">
          <input type="checkbox" v-model="autoRefresh" /> Auto-refresh (5s)
        </label>
        <button class="btn-back" @click="$emit('go-home')">Back to Lobby</button>
      </div>
    </header>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div v-if="debugData" class="debug-layout">
      <!-- Top-level tabs -->
      <div class="main-tabs">
        <button v-for="tab in mainTabs" :key="tab.id" class="main-tab"
          :class="{ active: activeMainTab === tab.id }" @click="activeMainTab = tab.id">
          {{ tab.label }}
          <span v-if="tab.count !== undefined" class="tab-count">{{ tab.count }}</span>
        </button>
      </div>

      <!-- Game State panel -->
      <div v-if="activeMainTab === 'state'" class="tab-content">
        <div class="state-grid">
          <div class="state-card">
            <h3>Overview</h3>
            <div class="kv-list">
              <div class="kv-row"><span class="kv-key">Status</span><span class="kv-val badge" :class="'badge-' + debugData.state.status">{{ debugData.state.status }}</span></div>
              <div class="kv-row"><span class="kv-key">Hand #</span><span class="kv-val">{{ debugData.state.hand_number }}</span></div>
              <div class="kv-row"><span class="kv-key">Whose Turn</span><span class="kv-val">{{ playerName(debugData.state.whose_turn) }}</span></div>
              <div class="kv-row"><span class="kv-key">Betting Round</span><span class="kv-val badge" :class="'badge-' + debugData.state.betting_round">{{ debugData.state.betting_round }}</span></div>
              <div class="kv-row"><span class="kv-key">Pot</span><span class="kv-val">{{ formatCurrency(debugData.state.pot) }}</span></div>
              <div class="kv-row"><span class="kv-key">Current Bet</span><span class="kv-val">{{ formatCurrency(debugData.state.current_bet) }}</span></div>
              <div class="kv-row"><span class="kv-key">Blinds</span><span class="kv-val">{{ formatCurrency(debugData.state.small_blind) }} / {{ formatCurrency(debugData.state.big_blind) }}</span></div>
              <div class="kv-row"><span class="kv-key">Dealer</span><span class="kv-val">{{ playerName(debugData.state.players[debugData.state.dealer_index]?.id) }}</span></div>
              <div class="kv-row"><span class="kv-key">Last Raiser</span><span class="kv-val">{{ playerName(debugData.state.last_raiser) || '—' }}</span></div>
              <div class="kv-row"><span class="kv-key">Winner</span><span class="kv-val">{{ playerName(debugData.state.winner) || '—' }}</span></div>
              <div v-if="debugData.state.winning_hand" class="kv-row"><span class="kv-key">Winning Hand</span><span class="kv-val">{{ debugData.state.winning_hand }}</span></div>
            </div>
          </div>

          <!-- Community Cards -->
          <div class="state-card">
            <h3>Community Cards</h3>
            <div v-if="debugData.state.community_cards.length" class="card-display">
              <span v-for="(card, i) in debugData.state.community_cards" :key="i"
                class="playing-card" :class="cardColor(card)">
                {{ card.rank }}{{ suitSymbol(card.suit) }}
              </span>
            </div>
            <div v-else class="empty-state-inline">No cards dealt yet</div>
          </div>

          <!-- Players table -->
          <div class="state-card full-width">
            <h3>Players</h3>
            <table class="data-table">
              <thead>
                <tr>
                  <th>Seat</th>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Chips</th>
                  <th>Current Bet</th>
                  <th>Status</th>
                  <th>Hole Cards</th>
                  <th v-if="hasAgentConfigs">Personality</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(p, idx) in debugData.state.players" :key="p.id"
                  :class="{ 'row-turn': p.id === debugData.state.whose_turn, 'row-folded': p.folded, 'row-eliminated': !p.active }">
                  <td>{{ idx + 1 }}<span v-if="idx === debugData.state.dealer_index" class="dealer-badge">D</span></td>
                  <td>{{ p.name }}</td>
                  <td><span class="type-badge" :class="'type-' + p.player_type">{{ p.player_type }}</span></td>
                  <td class="mono">{{ formatCurrency(p.chips) }}</td>
                  <td class="mono">{{ formatCurrency(p.current_bet) }}</td>
                  <td>
                    <span v-if="!p.active" class="status-tag eliminated">Out</span>
                    <span v-else-if="p.all_in" class="status-tag all-in">All-In</span>
                    <span v-else-if="p.folded" class="status-tag folded">Folded</span>
                    <span v-else class="status-tag active">Active</span>
                  </td>
                  <td>
                    <template v-if="debugData.player_cards[p.id]?.length">
                      <span v-for="c in debugData.player_cards[p.id]" :key="c" class="card-chip">{{ c }}</span>
                    </template>
                    <span v-else class="text-dim">—</span>
                  </td>
                  <td v-if="hasAgentConfigs">
                    <template v-if="debugData.agent_configs[p.id]">
                      <span class="personality-badge">{{ debugData.agent_configs[p.id].personality }}</span>
                    </template>
                    <span v-else class="text-dim">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Agent Configs -->
          <div v-if="hasAgentConfigs" class="state-card full-width">
            <h3>Agent Configurations</h3>
            <table class="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Personality</th>
                  <th>Aggression</th>
                  <th>Tightness</th>
                  <th>Bluff</th>
                  <th>Slowplay</th>
                  <th>Chat</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(config, pid) in debugData.agent_configs" :key="pid">
                  <td>{{ playerName(pid) }}</td>
                  <td><span class="personality-badge">{{ config.personality }}</span></td>
                  <td><span class="stat-bar"><span class="stat-fill" :style="{ width: (config.aggression * 100) + '%' }"></span></span> {{ (config.aggression * 100).toFixed(0) }}%</td>
                  <td><span class="stat-bar"><span class="stat-fill" :style="{ width: (config.tightness * 100) + '%' }"></span></span> {{ (config.tightness * 100).toFixed(0) }}%</td>
                  <td><span class="stat-bar"><span class="stat-fill" :style="{ width: (config.bluff_frequency * 100) + '%' }"></span></span> {{ (config.bluff_frequency * 100).toFixed(0) }}%</td>
                  <td><span class="stat-bar"><span class="stat-fill" :style="{ width: (config.slowplay_frequency * 100) + '%' }"></span></span> {{ (config.slowplay_frequency * 100).toFixed(0) }}%</td>
                  <td><span class="stat-bar"><span class="stat-fill" :style="{ width: (config.chat_frequency * 100) + '%' }"></span></span> {{ (config.chat_frequency * 100).toFixed(0) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Raw state -->
          <div class="state-card full-width">
            <h3 class="collapsible" @click="rawStateExpanded = !rawStateExpanded">
              Raw Game State
              <span class="collapse-arrow" :class="{ collapsed: !rawStateExpanded }">&#9660;</span>
            </h3>
            <pre v-if="rawStateExpanded" class="json-block">{{ JSON.stringify(debugData.state, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- Game Log panel -->
      <div v-if="activeMainTab === 'log'" class="tab-content">
        <div class="log-controls">
          <input v-model="logFilter" placeholder="Filter log entries..." class="filter-input" />
        </div>
        <div class="log-list">
          <div v-for="(entry, i) in filteredLog" :key="i" class="log-entry" :class="'log-' + entry.type">
            <span class="log-index">{{ i + 1 }}</span>
            <span class="log-type">{{ entry.type }}</span>
            <span class="log-player" v-if="entry.player_id">{{ playerName(entry.player_id) }}</span>
            <span class="log-detail">{{ logSummary(entry) }}</span>
            <button class="log-expand-btn" @click="toggleLogEntry(i)">
              {{ expandedLogEntries.includes(i) ? '&#9660;' : '&#9654;' }}
            </button>
            <pre v-if="expandedLogEntries.includes(i)" class="json-block log-json">{{ JSON.stringify(entry, null, 2) }}</pre>
          </div>
          <div v-if="!filteredLog.length" class="empty-state">No log entries{{ logFilter ? ' matching filter' : '' }}.</div>
        </div>
      </div>

      <!-- Chat panel -->
      <div v-if="activeMainTab === 'chat'" class="tab-content">
        <div class="chat-list">
          <div v-for="(msg, i) in debugData.chat" :key="i" class="chat-entry">
            <span class="chat-sender">{{ msg.player_id ? playerName(msg.player_id) : 'system' }}</span>
            <span class="chat-text">{{ msg.text }}</span>
            <span class="chat-time" v-if="msg.timestamp">{{ formatTime(msg.timestamp) }}</span>
          </div>
          <div v-if="!debugData.chat.length" class="empty-state">No chat messages.</div>
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="empty-state">No debug data loaded yet. Click Refresh.</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  gameId: { type: String, required: true }
})

defineEmits(['go-home'])

const debugData = ref(null)
const loading = ref(false)
const error = ref(null)
const autoRefresh = ref(false)
const activeMainTab = ref('state')
const rawStateExpanded = ref(false)
const logFilter = ref('')
const expandedLogEntries = ref([])
let refreshInterval = null

const SUIT_SYMBOLS = { hearts: '\u2665', diamonds: '\u2666', clubs: '\u2663', spades: '\u2660' }

function suitSymbol(suit) {
  return SUIT_SYMBOLS[suit] || suit
}

function cardColor(card) {
  return (card.suit === 'hearts' || card.suit === 'diamonds') ? 'card-red' : 'card-black'
}

const playerMap = computed(() => {
  if (!debugData.value?.state?.players) return {}
  const m = {}
  for (const p of debugData.value.state.players) {
    m[p.id] = p
  }
  return m
})

function playerName(pid) {
  if (!pid) return '—'
  const p = playerMap.value[pid]
  return p ? p.name : pid.substring(0, 8)
}

function formatCurrency(amount) {
  if (amount == null) return '—'
  return `$${(amount / 100).toFixed(2)}`
}

const hasAgentConfigs = computed(() => {
  return debugData.value && Object.keys(debugData.value.agent_configs).length > 0
})

const mainTabs = computed(() => {
  const d = debugData.value
  if (!d) return []
  return [
    { id: 'state', label: 'Game State' },
    { id: 'log', label: 'Game Log', count: d.game_log.length },
    { id: 'chat', label: 'Chat', count: d.chat.length },
  ]
})

function toggleLogEntry(i) {
  const idx = expandedLogEntries.value.indexOf(i)
  if (idx >= 0) expandedLogEntries.value.splice(idx, 1)
  else expandedLogEntries.value.push(i)
}

const filteredLog = computed(() => {
  if (!debugData.value) return []
  let entries = debugData.value.game_log
  if (logFilter.value) {
    const q = logFilter.value.toLowerCase()
    entries = entries.filter(e => JSON.stringify(e).toLowerCase().includes(q))
  }
  return entries
})

function logSummary(entry) {
  switch (entry.type) {
    case 'hand_started': return `Hand #${entry.hand_number}, dealer: ${playerName(entry.dealer)}`
    case 'player_action': return `${playerName(entry.player_id)} ${entry.action}${entry.amount ? ' ' + formatCurrency(entry.amount) : ''}`
    case 'community_cards': return `${entry.betting_round}: ${(entry.cards || []).map(c => c.rank + suitSymbol(c.suit)).join(' ')}`
    case 'showdown_log': return `Winners: ${(entry.winners || []).map(w => playerName(w)).join(', ')} — ${entry.winning_hand} (${formatCurrency(entry.pot)})`
    default: return ''
  }
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString()
  } catch {
    return ts
  }
}

async function fetchDebug() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams()
    const d = debugData.value
    if (d) {
      params.set('log_offset', d.game_log.length)
      params.set('chat_offset', d.chat.length)
    }
    const qs = params.toString()
    const res = await fetch(`/api/holdem/games/${props.gameId}/debug${qs ? '?' + qs : ''}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${res.status}`)
    }
    const fresh = await res.json()

    if (d) {
      // Incremental update: replace state, append lists
      d.state = fresh.state
      d.player_cards = fresh.player_cards
      d.agent_configs = fresh.agent_configs
      d.game_log.push(...fresh.game_log)
      d.chat.push(...fresh.chat)
    } else {
      debugData.value = fresh
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(autoRefresh, (val) => {
  if (val) {
    refreshInterval = setInterval(fetchDebug, 5000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

onMounted(() => {
  fetchDebug()
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<style scoped>
.debug-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem;
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
}

.debug-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid var(--border-panel);
}

.debug-header h1 {
  font-size: 1.3rem;
  margin: 0;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-refresh, .btn-back {
  padding: 0.35rem 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--border-panel);
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-refresh:hover, .btn-back:hover {
  background: var(--accent-bg);
  border-color: var(--accent-border-hover);
}

.auto-refresh-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.error-banner {
  background: #3a1111;
  border: 1px solid #cc3333;
  color: #ff6666;
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

/* Main tabs */
.main-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 1rem;
  border-bottom: 2px solid var(--border-panel);
  padding-bottom: 0.25rem;
}

.main-tab {
  padding: 0.4rem 0.8rem;
  border: 1px solid transparent;
  border-bottom: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.8rem;
  border-radius: 4px 4px 0 0;
  transition: all 0.15s;
}

.main-tab:hover {
  background: var(--bg-input);
  color: var(--text-primary);
}

.main-tab.active {
  background: var(--accent-bg);
  border-color: var(--accent-border-hover);
  color: var(--accent);
  font-weight: bold;
}

.tab-count {
  font-size: 0.65rem;
  background: var(--bg-input);
  padding: 0.1rem 0.35rem;
  border-radius: 8px;
  margin-left: 0.3rem;
  color: var(--text-dim);
}

.main-tab.active .tab-count {
  background: var(--accent-border);
  color: var(--accent);
}

.tab-content {
  min-height: 300px;
}

/* State grid */
.state-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1rem;
}

.state-card {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 6px;
  padding: 0.75rem;
}

.state-card.full-width {
  grid-column: 1 / -1;
}

.state-card h3 {
  font-size: 0.8rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid var(--border-panel);
}

/* Key-value list */
.kv-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.kv-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8rem;
  padding: 0.15rem 0;
}

.kv-key {
  color: var(--text-muted);
  font-weight: 600;
}

.kv-val {
  color: var(--text-primary);
}

/* Badges */
.badge {
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.7rem;
  font-weight: bold;
  text-transform: uppercase;
}

.badge-waiting { background: #2a2a00; color: #f39c12; }
.badge-playing { background: #002a00; color: #2ecc71; }
.badge-finished { background: #1a1a2e; color: #9b59b6; }
.badge-preflop { background: #1a2a3a; color: #5dade2; }
.badge-flop { background: #1a3a1a; color: #2ecc71; }
.badge-turn { background: #2a2a1a; color: #f39c12; }
.badge-river { background: #2a1a1a; color: #e74c3c; }
.badge-showdown { background: #2a1a2a; color: #bb86fc; }

/* Playing cards */
.card-display {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.playing-card {
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.4rem 0.5rem;
  font-size: 1rem;
  font-weight: bold;
  min-width: 2.5rem;
  text-align: center;
}

.card-red { color: #e74c3c; }
.card-black { color: #2c3e50; }

.empty-state-inline {
  color: var(--text-dim);
  font-style: italic;
  font-size: 0.8rem;
}

/* Data table */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.75rem;
}

.data-table th {
  text-align: left;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border-panel);
  color: var(--text-muted);
  font-size: 0.65rem;
  text-transform: uppercase;
}

.data-table td {
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border-panel);
  color: var(--text-primary);
}

.mono {
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.row-turn { background: rgba(243, 156, 18, 0.08); }
.row-folded { opacity: 0.6; }
.row-eliminated { opacity: 0.35; }

.dealer-badge {
  display: inline-block;
  background: #f39c12;
  color: #000;
  font-size: 0.55rem;
  font-weight: bold;
  width: 1rem;
  height: 1rem;
  line-height: 1rem;
  text-align: center;
  border-radius: 50%;
  margin-left: 0.3rem;
}

.type-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}

.type-human { background: #1a2a3a; color: #5dade2; }
.type-holdem_agent { background: #1a3a1a; color: #2ecc71; }

.status-tag {
  font-size: 0.65rem;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-weight: bold;
}

.status-tag.active { background: #002a00; color: #2ecc71; }
.status-tag.folded { background: #2a2a2a; color: #999; }
.status-tag.all-in { background: #3a1a1a; color: #e74c3c; }
.status-tag.eliminated { background: #1a1a1a; color: #666; }

.card-chip {
  display: inline-block;
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.7rem;
  margin: 0.1rem;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.personality-badge {
  font-size: 0.7rem;
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  background: #2a1a3a;
  color: #bb86fc;
  font-weight: bold;
}

/* Stat bars */
.stat-bar {
  display: inline-block;
  width: 50px;
  height: 8px;
  background: var(--bg-input);
  border-radius: 4px;
  overflow: hidden;
  margin-right: 0.3rem;
  vertical-align: middle;
}

.stat-fill {
  display: block;
  height: 100%;
  background: var(--accent);
  border-radius: 4px;
}

/* JSON blocks */
.json-block {
  background: var(--bg-input);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.5rem;
  font-size: 0.7rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  margin: 0.3rem 0 0 0;
  max-height: 500px;
  overflow-y: auto;
}

.collapsible {
  cursor: pointer;
  user-select: none;
}

.collapse-arrow {
  font-size: 0.7rem;
  transition: transform 0.2s;
  display: inline-block;
  margin-left: 0.3rem;
}

.collapse-arrow.collapsed {
  transform: rotate(-90deg);
}

/* Game Log */
.log-controls {
  margin-bottom: 0.5rem;
}

.filter-input {
  width: 100%;
  max-width: 400px;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 0.8rem;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 700px;
  overflow-y: auto;
}

.log-entry {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.4rem 0.6rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
}

.log-index {
  color: var(--text-dim);
  font-size: 0.65rem;
  min-width: 2rem;
}

.log-type {
  font-weight: bold;
  text-transform: uppercase;
  font-size: 0.65rem;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  background: var(--bg-input);
  color: var(--text-secondary);
  min-width: 85px;
  text-align: center;
}

.log-player {
  color: var(--accent);
  font-weight: 600;
  font-size: 0.75rem;
}

.log-detail {
  color: var(--text-primary);
  flex: 1;
}

.log-expand-btn {
  background: none;
  border: 1px solid var(--border-panel);
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 3px;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 0.8rem;
  line-height: 1;
}

.log-json {
  width: 100%;
  flex-basis: 100%;
  margin-top: 0.3rem;
}

.log-hand_started .log-type { background: #1a3a1a; color: #2ecc71; }
.log-player_action .log-type { background: #1a2a3a; color: #5dade2; }
.log-community_cards .log-type { background: #2a2a1a; color: #f39c12; }
.log-showdown_log .log-type { background: #2a1a2a; color: #bb86fc; }

/* Chat */
.chat-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 600px;
  overflow-y: auto;
}

.chat-entry {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.35rem 0.6rem;
  font-size: 0.8rem;
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}

.chat-sender {
  font-weight: bold;
  color: var(--accent);
  min-width: 80px;
}

.chat-text {
  color: var(--text-primary);
  flex: 1;
}

.chat-time {
  color: var(--text-dim);
  font-size: 0.65rem;
}

/* Utility */
.text-dim { color: var(--text-dim); }

.empty-state {
  text-align: center;
  color: var(--text-dim);
  font-style: italic;
  padding: 2rem;
  font-size: 0.85rem;
}
</style>
