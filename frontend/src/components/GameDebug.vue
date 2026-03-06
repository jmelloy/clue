<template>
  <div class="debug-page">
    <header class="debug-header">
      <h1>Game Debug: {{ gameId }}</h1>
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
              <div class="kv-row"><span class="kv-key">Turn</span><span class="kv-val">{{ debugData.state.turn_number ?? '—' }}</span></div>
              <div class="kv-row"><span class="kv-key">Whose Turn</span><span class="kv-val">{{ playerName(debugData.state.whose_turn) }}</span></div>
              <div class="kv-row"><span class="kv-key">Winner</span><span class="kv-val">{{ playerName(debugData.state.winner) || '—' }}</span></div>
              <div class="kv-row"><span class="kv-key">Trace Enabled</span><span class="kv-val">{{ debugData.state.agent_trace_enabled ? 'Yes' : 'No' }}</span></div>
            </div>
          </div>

          <div class="state-card" v-if="debugData.solution">
            <h3>Solution</h3>
            <div class="solution-chips">
              <span class="chip suspect-chip">{{ debugData.solution.suspect }}</span>
              <span class="chip weapon-chip">{{ debugData.solution.weapon }}</span>
              <span class="chip room-chip">{{ debugData.solution.room }}</span>
            </div>
          </div>

          <div class="state-card">
            <h3>Players</h3>
            <table class="data-table">
              <thead><tr><th>Name</th><th>Character</th><th>Type</th><th>Active</th><th>Room</th><th>Cards</th></tr></thead>
              <tbody>
                <tr v-for="p in debugData.state.players" :key="p.id">
                  <td>{{ p.name }}</td>
                  <td>{{ p.character }}</td>
                  <td><span class="type-badge" :class="'type-' + p.type">{{ p.type }}</span></td>
                  <td>{{ p.active ? 'Yes' : 'No' }}</td>
                  <td>{{ debugData.state.current_room?.[p.id] || 'Hallway' }}</td>
                  <td>
                    <span v-for="c in (debugData.player_cards[p.id] || [])" :key="c" class="card-chip">{{ c }}</span>
                    <span v-if="!(debugData.player_cards[p.id] || []).length" class="text-dim">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

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
              {{ expandedLogEntries.includes(i) ? '▼' : '▶' }}
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
            <span class="chat-sender">{{ msg.sender || 'system' }}</span>
            <span class="chat-text">{{ msg.message || msg.text }}</span>
            <span class="chat-time" v-if="msg.timestamp">{{ formatTime(msg.timestamp) }}</span>
          </div>
          <div v-if="!debugData.chat.length" class="empty-state">No chat messages.</div>
        </div>
      </div>

      <!-- Agent Trace panel -->
      <div v-if="activeMainTab === 'trace'" class="tab-content">
        <div class="trace-controls">
          <select v-model="tracePlayerFilter" class="filter-select">
            <option value="">All Players</option>
            <option v-for="pid in tracePlayerIds" :key="pid" :value="pid">{{ playerName(pid) }}</option>
          </select>
          <select v-model="traceEventFilter" class="filter-select">
            <option value="">All Events</option>
            <option v-for="evt in traceEventTypes" :key="evt" :value="evt">{{ evt }}</option>
          </select>
          <span class="trace-count">{{ filteredTrace.length }} / {{ debugData.agent_trace.total }} entries</span>
        </div>
        <div class="trace-list">
          <div v-for="(entry, i) in filteredTrace" :key="i" class="trace-entry"
            :class="{ 'trace-llm': isLlmTrace(entry) }">
            <div class="trace-header">
              <span class="trace-time">{{ formatTime(entry.timestamp) }}</span>
              <span class="trace-player-tag">{{ playerName(entry.player_id) }}</span>
              <span class="trace-event" :class="'event-' + entry.event">{{ entry.event }}</span>
            </div>
            <div class="trace-details">
              <template v-if="entry.event === 'llm_request'">
                <div class="llm-field">
                  <span class="llm-label">Model:</span>
                  <span>{{ entry.model || '—' }}</span>
                </div>
                <div class="llm-field" v-if="entry.system_prompt">
                  <span class="llm-label">System Prompt:</span>
                  <pre class="llm-prompt">{{ entry.system_prompt }}</pre>
                </div>
                <div class="llm-field" v-if="entry.user_prompt">
                  <span class="llm-label">User Prompt:</span>
                  <pre class="llm-prompt">{{ entry.user_prompt }}</pre>
                </div>
              </template>
              <template v-else-if="entry.event === 'llm_response'">
                <div class="llm-field">
                  <span class="llm-label">Status:</span>
                  <span :class="entry.status === 'success' ? 'text-success' : 'text-error'">{{ entry.status }}</span>
                </div>
                <div class="llm-field" v-if="entry.content">
                  <span class="llm-label">Response:</span>
                  <pre class="llm-response">{{ entry.content }}</pre>
                </div>
                <div class="llm-field" v-if="entry.usage">
                  <span class="llm-label">Usage:</span>
                  <span class="usage-info">{{ JSON.stringify(entry.usage) }}</span>
                </div>
                <div class="llm-field" v-if="entry.error">
                  <span class="llm-label">Error:</span>
                  <span class="text-error">{{ entry.error }}</span>
                </div>
              </template>
              <template v-else>
                <pre class="json-block trace-json">{{ JSON.stringify(omitKeys(entry, ['timestamp', 'player_id', 'agent_type', 'event']), null, 2) }}</pre>
              </template>
            </div>
          </div>
          <div v-if="!filteredTrace.length" class="empty-state">No trace entries{{ tracePlayerFilter || traceEventFilter ? ' matching filters' : '' }}.</div>
        </div>
      </div>

      <!-- Per-Agent tabs -->
      <div v-if="activeMainTab === 'agents'" class="tab-content">
        <div class="agent-tabs">
          <button v-for="agent in agentList" :key="agent.player_id" class="agent-tab"
            :class="{ active: selectedAgentId === agent.player_id }" @click="selectedAgentId = agent.player_id">
            {{ agent.character || playerName(agent.player_id) }}
            <span class="agent-type-tag">{{ agent.agent_type }}</span>
          </button>
        </div>

        <div v-if="selectedAgent" class="agent-detail">
          <!-- Agent overview -->
          <div class="agent-section">
            <h3>Status & Location</h3>
            <div class="kv-list">
              <div class="kv-row"><span class="kv-key">Type</span><span class="kv-val">{{ selectedAgent.agent_type }}</span></div>
              <div class="kv-row"><span class="kv-key">Status</span><span class="kv-val">{{ selectedAgent.status }}</span></div>
              <div class="kv-row"><span class="kv-key">Room</span><span class="kv-val">{{ selectedAgent.room || 'Hallway' }}</span></div>
              <div class="kv-row"><span class="kv-key">Position</span><span class="kv-val">{{ selectedAgent.position ? `[${selectedAgent.position[0]}, ${selectedAgent.position[1]}]` : '—' }}</span></div>
              <div class="kv-row" v-if="selectedAgent.action_description"><span class="kv-key">Last Action</span><span class="kv-val">{{ selectedAgent.action_description }}</span></div>
            </div>
          </div>

          <!-- Cards held -->
          <div class="agent-section" v-if="debugData.player_cards[selectedAgentId]?.length">
            <h3>Cards Held</h3>
            <div class="card-chips">
              <span v-for="c in debugData.player_cards[selectedAgentId]" :key="c" class="card-chip">{{ c }}</span>
            </div>
          </div>

          <!-- Card Knowledge -->
          <div class="agent-section" v-if="selectedAgent.seen_cards?.length || selectedAgent.unknown_suspects">
            <h3>Card Knowledge ({{ selectedAgent.seen_cards?.length || 0 }} seen)</h3>
            <div class="unknown-group">
              <span class="unknown-label suspect-label">Suspects?</span>
              <span v-for="s in (selectedAgent.unknown_suspects || [])" :key="s" class="chip suspect-chip">{{ s }}</span>
              <span v-if="!selectedAgent.unknown_suspects?.length" class="text-success">all eliminated</span>
            </div>
            <div class="unknown-group">
              <span class="unknown-label weapon-label">Weapons?</span>
              <span v-for="w in (selectedAgent.unknown_weapons || [])" :key="w" class="chip weapon-chip">{{ w }}</span>
              <span v-if="!selectedAgent.unknown_weapons?.length" class="text-success">all eliminated</span>
            </div>
            <div class="unknown-group">
              <span class="unknown-label room-label">Rooms?</span>
              <span v-for="r in (selectedAgent.unknown_rooms || [])" :key="r" class="chip room-chip">{{ r }}</span>
              <span v-if="!selectedAgent.unknown_rooms?.length" class="text-success">all eliminated</span>
            </div>
            <div v-if="selectedAgent.seen_cards?.length" class="seen-line">
              <strong>Seen:</strong> {{ selectedAgent.seen_cards.join(', ') }}
            </div>
          </div>

          <!-- Known card holders -->
          <div class="agent-section" v-if="Object.keys(selectedAgent.player_has_cards || {}).length">
            <h3>Known Card Holders</h3>
            <div v-for="(cards, pid) in selectedAgent.player_has_cards" :key="pid" class="holder-row">
              <span class="holder-name">{{ playerName(pid) }}:</span>
              <span v-for="c in cards" :key="c" class="card-chip">{{ c }}</span>
            </div>
          </div>

          <!-- Decided Action -->
          <div class="agent-section" v-if="selectedAgent.decided_action">
            <h3>Last Decided Action</h3>
            <pre class="json-block">{{ JSON.stringify(selectedAgent.decided_action, null, 2) }}</pre>
          </div>

          <!-- Unrefuted Suggestions -->
          <div class="agent-section" v-if="selectedAgent.unrefuted_suggestions?.length">
            <h3>Unrefuted Suggestions</h3>
            <div v-for="(s, i) in selectedAgent.unrefuted_suggestions" :key="i" class="unrefuted-item">
              {{ s.suspect }} / {{ s.weapon }} / {{ s.room }}
            </div>
          </div>

          <!-- LLM Memory -->
          <div class="agent-section" v-if="agentMemory.length">
            <h3>LLM Memory ({{ agentMemory.length }} entries)</h3>
            <div class="memory-list">
              <div v-for="(entry, i) in agentMemory" :key="i" class="memory-entry">
                <span class="memory-index">[{{ i + 1 }}]</span>
                <span class="memory-text">{{ entry }}</span>
              </div>
            </div>
          </div>

          <!-- Agent Trace (filtered to this agent) -->
          <div class="agent-section" v-if="agentTraceEntries.length">
            <h3>Agent Trace ({{ agentTraceEntries.length }} entries)</h3>
            <div class="trace-list compact">
              <div v-for="(entry, i) in agentTraceEntries" :key="i" class="trace-entry"
                :class="{ 'trace-llm': isLlmTrace(entry) }">
                <div class="trace-header">
                  <span class="trace-time">{{ formatTime(entry.timestamp) }}</span>
                  <span class="trace-event" :class="'event-' + entry.event">{{ entry.event }}</span>
                </div>
                <div class="trace-details">
                  <template v-if="entry.event === 'llm_request'">
                    <div class="llm-field">
                      <span class="llm-label">Model:</span> {{ entry.model || '—' }}
                    </div>
                    <div class="llm-field" v-if="entry.system_prompt">
                      <span class="llm-label">System:</span>
                      <pre class="llm-prompt">{{ entry.system_prompt }}</pre>
                    </div>
                    <div class="llm-field" v-if="entry.user_prompt">
                      <span class="llm-label">User:</span>
                      <pre class="llm-prompt">{{ entry.user_prompt }}</pre>
                    </div>
                  </template>
                  <template v-else-if="entry.event === 'llm_response'">
                    <div class="llm-field">
                      <span class="llm-label">Status:</span>
                      <span :class="entry.status === 'success' ? 'text-success' : 'text-error'">{{ entry.status }}</span>
                    </div>
                    <div class="llm-field" v-if="entry.content">
                      <span class="llm-label">Response:</span>
                      <pre class="llm-response">{{ entry.content }}</pre>
                    </div>
                    <div class="llm-field" v-if="entry.usage">
                      <span class="llm-label">Usage:</span> {{ JSON.stringify(entry.usage) }}
                    </div>
                    <div class="llm-field" v-if="entry.error">
                      <span class="llm-label">Error:</span>
                      <span class="text-error">{{ entry.error }}</span>
                    </div>
                  </template>
                  <template v-else>
                    <pre class="json-block trace-json">{{ JSON.stringify(omitKeys(entry, ['timestamp', 'player_id', 'agent_type', 'event']), null, 2) }}</pre>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">Select an agent above.</div>
      </div>

      <!-- Agent Events panel -->
      <div v-if="activeMainTab === 'events'" class="tab-content">
        <div class="events-list">
          <div v-for="(evt, i) in debugData.agent_events" :key="i" class="event-entry">
            <span class="event-type-tag">{{ evt.type }}</span>
            <pre class="json-block">{{ JSON.stringify(evt, null, 2) }}</pre>
          </div>
          <div v-if="!debugData.agent_events.length" class="empty-state">No agent events.</div>
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
const selectedAgentId = ref(null)
const rawStateExpanded = ref(false)
const logFilter = ref('')
const expandedLogEntries = ref([])
const tracePlayerFilter = ref('')
const traceEventFilter = ref('')
let refreshInterval = null

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
  return p ? `${p.name} (${p.character})` : pid.substring(0, 8)
}

const mainTabs = computed(() => {
  const d = debugData.value
  if (!d) return []
  return [
    { id: 'state', label: 'Game State' },
    { id: 'log', label: 'Game Log', count: d.game_log.length },
    { id: 'chat', label: 'Chat', count: d.chat.length },
    { id: 'trace', label: 'Agent Trace', count: d.agent_trace.total },
    { id: 'agents', label: 'Agents', count: d.agent_debug.length },
    { id: 'events', label: 'Agent Events', count: d.agent_events.length },
  ]
})

// Agent list (non-wanderer agents first, then all)
const agentList = computed(() => {
  if (!debugData.value) return []
  return debugData.value.agent_debug
})

const selectedAgent = computed(() => {
  if (!selectedAgentId.value || !debugData.value) return null
  return debugData.value.agent_debug.find(a => a.player_id === selectedAgentId.value) || null
})

const agentMemory = computed(() => {
  if (!selectedAgentId.value || !debugData.value) return []
  // Prefer player_memory (full Redis dump), fall back to agent debug memory
  return debugData.value.player_memory[selectedAgentId.value]
    || selectedAgent.value?.memory
    || []
})

const agentTraceEntries = computed(() => {
  if (!selectedAgentId.value || !debugData.value) return []
  return debugData.value.agent_trace.by_player[selectedAgentId.value] || []
})

function toggleLogEntry(i) {
  const idx = expandedLogEntries.value.indexOf(i)
  if (idx >= 0) expandedLogEntries.value.splice(idx, 1)
  else expandedLogEntries.value.push(i)
}

// Log filtering
const filteredLog = computed(() => {
  if (!debugData.value) return []
  let entries = debugData.value.game_log
  if (logFilter.value) {
    const q = logFilter.value.toLowerCase()
    entries = entries.filter(e => JSON.stringify(e).toLowerCase().includes(q))
  }
  return entries
})

// Trace filtering
const tracePlayerIds = computed(() => {
  if (!debugData.value) return []
  return Object.keys(debugData.value.agent_trace.by_player)
})

const traceEventTypes = computed(() => {
  if (!debugData.value) return []
  const types = new Set(debugData.value.agent_trace.entries.map(e => e.event))
  return [...types].sort()
})

const filteredTrace = computed(() => {
  if (!debugData.value) return []
  let entries = debugData.value.agent_trace.entries
  if (tracePlayerFilter.value) {
    entries = entries.filter(e => e.player_id === tracePlayerFilter.value)
  }
  if (traceEventFilter.value) {
    entries = entries.filter(e => e.event === traceEventFilter.value)
  }
  return entries
})

function isLlmTrace(entry) {
  return entry.event === 'llm_request' || entry.event === 'llm_response'
}

function omitKeys(obj, keys) {
  const result = {}
  for (const [k, v] of Object.entries(obj)) {
    if (!keys.includes(k)) result[k] = v
  }
  return result
}

function logSummary(entry) {
  switch (entry.type) {
    case 'move': return `rolled ${entry.dice}` + (entry.room ? `, entered ${entry.room}` : '')
    case 'suggestion': return `${entry.suspect} / ${entry.weapon} / ${entry.room}`
    case 'accusation': return `${entry.suspect} / ${entry.weapon} / ${entry.room} — ${entry.correct ? 'CORRECT' : 'WRONG'}`
    case 'card_shown': return `${playerName(entry.player_id)} showed card to ${playerName(entry.to_player_id)}`
    case 'roll': return `rolled ${entry.dice}`
    case 'end_turn': return `ended turn, next: ${playerName(entry.next_player_id)}`
    case 'secret_passage': return `used passage from ${entry.from_room} to ${entry.room}`
    case 'game_started': return 'game started'
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
    const res = await fetch(`/games/${props.gameId}/debug`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${res.status}`)
    }
    debugData.value = await res.json()
    // Auto-select first agent if none selected
    if (!selectedAgentId.value && debugData.value.agent_debug.length) {
      selectedAgentId.value = debugData.value.agent_debug[0].player_id
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

/* Solution chips */
.solution-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.chip {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  border: 1px solid;
}

.suspect-chip { background: var(--badge-clue-bg); border-color: var(--badge-clue-border); color: var(--badge-clue-text); }
.weapon-chip { background: var(--badge-holdem-bg); border-color: var(--badge-holdem-border); color: var(--badge-holdem-text); }
.room-chip { background: var(--tag-wanderer-bg); border-color: var(--tag-wanderer-text); color: var(--tag-wanderer-text); }

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

.type-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}

.type-human { background: #1a2a3a; color: #5dade2; }
.type-agent { background: #1a3a1a; color: #2ecc71; }
.type-llm_agent { background: #2a1a3a; color: #bb86fc; }
.type-wanderer { background: #2a2a1a; color: #f39c12; }

.card-chip {
  display: inline-block;
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.7rem;
  margin: 0.1rem;
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
  min-width: 70px;
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

.log-suggestion .log-type { background: #2a2a00; color: #f39c12; }
.log-accusation .log-type { background: #3a1111; color: #ff6666; }
.log-move .log-type { background: #1a2a3a; color: #5dade2; }
.log-roll .log-type { background: #1a3a1a; color: #2ecc71; }

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

/* Trace */
.trace-controls {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.filter-select {
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 0.8rem;
}

.trace-count {
  font-size: 0.75rem;
  color: var(--text-dim);
  margin-left: auto;
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 700px;
  overflow-y: auto;
}

.trace-list.compact {
  max-height: 500px;
}

.trace-entry {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.5rem;
}

.trace-entry.trace-llm {
  border-left: 3px solid #bb86fc;
}

.trace-header {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.3rem;
}

.trace-time {
  font-size: 0.65rem;
  color: var(--text-dim);
}

.trace-player-tag {
  font-size: 0.7rem;
  font-weight: bold;
  color: var(--accent);
}

.trace-event {
  font-size: 0.65rem;
  font-weight: bold;
  text-transform: uppercase;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  background: var(--bg-input);
  color: var(--text-secondary);
}

.event-llm_request { background: #2a1a3a; color: #bb86fc; }
.event-llm_response { background: #1a2a1a; color: #2ecc71; }
.event-decide_action { background: #2a2a1a; color: #f39c12; }

.trace-details {
  font-size: 0.75rem;
}

.trace-json {
  margin: 0;
  font-size: 0.7rem;
}

/* LLM-specific formatting */
.llm-field {
  margin-bottom: 0.3rem;
}

.llm-label {
  font-weight: bold;
  color: var(--text-muted);
  font-size: 0.7rem;
  margin-right: 0.3rem;
}

.llm-prompt, .llm-response {
  background: var(--bg-input);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.4rem;
  font-size: 0.7rem;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 0.2rem;
}

.llm-response {
  border-left: 3px solid #2ecc71;
}

.usage-info {
  font-size: 0.7rem;
  color: var(--text-dim);
}

/* Agent tabs & detail */
.agent-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 1rem;
}

.agent-tab {
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--border-panel);
  background: var(--bg-input);
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.agent-tab.active {
  background: var(--accent-bg);
  border-color: var(--accent-border-hover);
  color: var(--accent);
}

.agent-type-tag {
  font-size: 0.6rem;
  padding: 0.05rem 0.25rem;
  border-radius: 3px;
  background: var(--bg-panel-solid);
  color: var(--text-dim);
  text-transform: uppercase;
}

.agent-detail {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.agent-section {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 6px;
  padding: 0.75rem;
}

.agent-section h3 {
  font-size: 0.8rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.5rem 0;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid var(--border-panel);
}

/* Unknown groups (reused from AgentDebugPanel) */
.unknown-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.3rem;
}

.unknown-label {
  font-size: 0.7rem;
  font-weight: bold;
  text-transform: uppercase;
  min-width: 70px;
}

.suspect-label { color: var(--badge-clue-text); }
.weapon-label { color: var(--badge-holdem-text); }
.room-label { color: var(--tag-wanderer-text); }

.card-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
}

.seen-line {
  font-size: 0.75rem;
  color: var(--text-dim);
  margin-top: 0.3rem;
}

.holder-row {
  font-size: 0.75rem;
  margin-bottom: 0.25rem;
}

.holder-name {
  font-weight: bold;
  color: var(--text-muted);
  margin-right: 0.3rem;
}

.unrefuted-item {
  font-size: 0.75rem;
  color: #f39c12;
  padding: 0.15rem 0;
}

/* Memory */
.memory-list {
  max-height: 400px;
  overflow-y: auto;
}

.memory-entry {
  font-size: 0.75rem;
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--border-panel);
}

.memory-index {
  color: var(--text-dim);
  font-weight: bold;
  margin-right: 0.3rem;
}

.memory-text {
  color: var(--text-secondary);
  word-break: break-word;
}

/* Events */
.events-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 700px;
  overflow-y: auto;
}

.event-entry {
  background: var(--bg-panel-solid);
  border: 1px solid var(--border-panel);
  border-radius: 4px;
  padding: 0.5rem;
}

.event-type-tag {
  font-size: 0.7rem;
  font-weight: bold;
  text-transform: uppercase;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background: var(--bg-input);
  color: var(--text-secondary);
  margin-bottom: 0.3rem;
  display: inline-block;
}

/* Utility */
.text-success { color: #2ecc71; }
.text-error { color: #ff6666; }
.text-dim { color: var(--text-dim); }

.empty-state {
  text-align: center;
  color: var(--text-dim);
  font-style: italic;
  padding: 2rem;
  font-size: 0.85rem;
}
</style>
