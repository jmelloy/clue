<template>
  <div class="agent-debug-panel">
    <h2 class="panel-header collapsible-header" @click="collapsed = !collapsed">
      <span>Player Debug</span>
      <span class="collapse-indicator" :class="{ collapsed }">&#9660;</span>
    </h2>
    <div v-if="!collapsed">
      <!-- Agent selector tabs -->
      <div v-if="agentIds.length > 1" class="agent-tabs">
        <button v-for="aid in agentIds" :key="aid" class="agent-tab" :class="{ active: selectedAgent === aid }"
          @click="selectedAgent = aid">
          {{ agentLabel(aid) }}
        </button>
      </div>

      <div v-if="currentDebug" class="debug-content">
        <!-- Status bar -->
        <div class="debug-status" :class="'status-' + currentDebug.status">
          <span class="status-dot"></span>
          <span class="status-label">{{ currentDebug.status }}</span>
          <span v-if="currentDebug.action_description" class="status-desc">{{
            currentDebug.action_description
            }}</span>
        </div>

        <!-- Player Info -->
        <div class="debug-section player-info-section">
          <div class="info-row">
            <span class="info-label">Type:</span>
            <span class="info-value agent-type-badge" :class="'type-' + (currentDebug.agent_type || 'human')">{{
              currentDebug.agent_type || 'human' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Active:</span>
            <span class="info-value" :class="selectedPlayer?.active !== false ? 'active-yes' : 'active-no'">{{
              selectedPlayer?.active !== false ? 'Yes' : 'Eliminated' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Turn:</span>
            <span v-if="isTheirTurn" class="info-value turn-active">
              Their turn
              <span v-if="turnState">({{ turnState.diceRolled ? 'rolled' : 'not rolled' }}<span v-if="turnState.lastRoll">, {{ turnState.lastRoll.reduce((a, b) => a + b, 0) }} spaces</span>{{ turnState.moved ? ', moved' : '' }})</span>
            </span>
            <span v-else class="info-value turn-waiting">Waiting</span>
          </div>
          <div v-if="wasMovedBySuggestion" class="info-row">
            <span class="info-label"></span>
            <span class="info-value moved-by-suggestion">Moved by suggestion</span>
          </div>
          <div v-if="props.gameState" class="info-row">
            <span class="info-label">Turn #:</span>
            <span class="info-value">{{ props.gameState.turn_number }}</span>
          </div>
        </div>

        <!-- Position & Room -->
        <div class="debug-section location-section">
          <div class="location-row">
            <span class="location-label">Room:</span>
            <span class="location-value" :class="{ 'in-room': currentDebug.room }">{{
              currentDebug.room || 'Hallway'
              }}</span>
          </div>
          <div class="location-row">
            <span class="location-label">Position:</span>
            <span class="location-value">{{
              currentDebug.position
                ? `[${currentDebug.position[0]}, ${currentDebug.position[1]}]`
                : '—'
            }}</span>
          </div>
          <div v-if="currentDebug.reachable_rooms?.length" class="location-row">
            <span class="location-label">Reachable:</span>
            <span class="reachable-chips">
              <span v-for="r in currentDebug.reachable_rooms" :key="r" class="unknown-chip room-chip">{{ r }}</span>
            </span>
          </div>
        </div>

        <!-- Decided action -->
        <div v-if="currentDebug.decided_action" class="debug-section">
          <h3>Last Action</h3>
          <code class="action-json">{{ JSON.stringify(currentDebug.decided_action) }}</code>
        </div>

        <!-- Card knowledge -->
        <div class="debug-section">
          <h3 class="collapsible-header" @click="cardsExpanded = !cardsExpanded">
            <span>Card Knowledge ({{ currentDebug.seen_cards?.length || 0 }} seen)</span>
            <span class="collapse-indicator" :class="{ collapsed: !cardsExpanded }">&#9660;</span>
          </h3>
          <div v-if="cardsExpanded">
            <div class="unknown-group">
              <span class="unknown-label suspect-label">Suspects?</span>
              <span v-for="s in currentDebug.unknown_suspects" :key="s" class="unknown-chip suspect-chip">{{ s }}</span>
              <span v-if="!currentDebug.unknown_suspects?.length" class="all-known">all eliminated</span>
            </div>
            <div class="unknown-group">
              <span class="unknown-label weapon-label">Weapons?</span>
              <span v-for="w in currentDebug.unknown_weapons" :key="w" class="unknown-chip weapon-chip">{{ w }}</span>
              <span v-if="!currentDebug.unknown_weapons?.length" class="all-known">all eliminated</span>
            </div>
            <div class="unknown-group">
              <span class="unknown-label room-label">Rooms?</span>
              <span v-for="r in currentDebug.unknown_rooms" :key="r" class="unknown-chip room-chip">{{ r }}</span>
              <span v-if="!currentDebug.unknown_rooms?.length" class="all-known">all eliminated</span>
            </div>
            <div class="seen-cards-line">
              <span class="seen-label">Seen:</span>
              <span class="seen-list">{{ currentDebug.seen_cards?.join(', ') || 'none' }}</span>
            </div>
            <div v-if="currentDebug.inferred_cards?.length" class="seen-cards-line">
              <span class="seen-label">Inferred:</span>
              <span class="inferred-list">{{ currentDebug.inferred_cards.join(', ') }}</span>
            </div>
          </div>
        </div>

        <!-- Known card holders -->
        <div v-if="Object.keys(currentDebug.player_has_cards || {}).length" class="debug-section">
          <h3 class="collapsible-header" @click="holdersExpanded = !holdersExpanded">
            <span>Known Card Holders</span>
            <span class="collapse-indicator" :class="{ collapsed: !holdersExpanded }">&#9660;</span>
          </h3>
          <div v-if="holdersExpanded">
            <div v-for="(cards, pid) in currentDebug.player_has_cards" :key="pid" class="holder-row">
              <span class="holder-name">{{ playerName(pid) }}:</span>
              <span v-for="c in cards" :key="c" class="holder-card">{{ c }}</span>
            </div>
          </div>
        </div>

        <!-- Unrefuted suggestions -->
        <div v-if="currentDebug.unrefuted_suggestions?.length" class="debug-section">
          <h3>Unrefuted Suggestions</h3>
          <div v-for="(s, i) in currentDebug.unrefuted_suggestions" :key="i" class="unrefuted-item">
            {{ s.suspect }} / {{ s.weapon }} / {{ s.room }}
          </div>
        </div>

        <!-- Recent inferences -->
        <div v-if="currentDebug.recent_inferences?.length" class="debug-section">
          <h3>Pending Inferences</h3>
          <div v-for="(inf, i) in currentDebug.recent_inferences" :key="i" class="inference-item">
            {{ inf }}
          </div>
        </div>

        <!-- LLM Memory -->
        <div v-if="currentDebug.memory?.length" class="debug-section">
          <h3 class="collapsible-header" @click="memoryExpanded = !memoryExpanded">
            <span>LLM Memory ({{ currentDebug.memory.length }} entries)</span>
            <span class="collapse-indicator" :class="{ collapsed: !memoryExpanded }">&#9660;</span>
          </h3>
          <div v-if="memoryExpanded" class="memory-list">
            <div v-for="(entry, i) in currentDebug.memory" :key="i" class="memory-entry">
              <span class="memory-index">[{{ i + 1 }}]</span>
              <span class="memory-text">{{ entry }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="no-debug">No agent debug data received yet.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  agentDebugData: { type: Object, default: () => ({}) },
  players: { type: Array, default: () => [] },
  gameState: { type: Object, default: null }
})

const collapsed = ref(false)
const cardsExpanded = ref(true)
const holdersExpanded = ref(false)
const memoryExpanded = ref(true)
const selectedAgent = ref(null)

const agentIds = computed(() => {
  const ids = Object.keys(props.agentDebugData || {})
  // Filter out wanderers for a cleaner view
  return ids.filter((id) => {
    const data = props.agentDebugData[id]
    return data && data.agent_type !== 'wanderer'
  })
})

// Auto-select first agent
watch(
  agentIds,
  (ids) => {
    if (ids.length && (!selectedAgent.value || !ids.includes(selectedAgent.value))) {
      selectedAgent.value = ids[0]
    }
  },
  { immediate: true }
)

const currentDebug = computed(() => {
  if (!selectedAgent.value) return null
  return props.agentDebugData[selectedAgent.value] || null
})

const selectedPlayer = computed(() => {
  if (!selectedAgent.value || !props.players?.length) return null
  return props.players.find((p) => p.id === selectedAgent.value) || null
})

const isTheirTurn = computed(() => {
  return props.gameState?.whose_turn === selectedAgent.value
})

const wasMovedBySuggestion = computed(() => {
  return props.gameState?.was_moved_by_suggestion?.[selectedAgent.value] ?? false
})

const turnState = computed(() => {
  if (!isTheirTurn.value || !props.gameState) return null
  return {
    diceRolled: props.gameState.dice_rolled,
    moved: props.gameState.moved,
    lastRoll: props.gameState.last_roll
  }
})

function agentLabel(pid) {
  const data = props.agentDebugData[pid]
  if (data?.character) return data.character
  const p = props.players?.find((pl) => pl.id === pid)
  return p ? p.name : pid.substring(0, 8)
}

function playerName(pid) {
  const p = props.players?.find((pl) => pl.id === pid)
  return p ? p.name : pid.substring(0, 8)
}
</script>

<style scoped>
.agent-debug-panel {
  background: var(--bg-panel-solid);
  border-radius: 8px;
  padding: 0.8rem;
  border: 1px solid var(--border-panel);
}

/* Panel headers and collapsible headers are in styles/components.css */

/* Agent tabs */
.agent-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}

.agent-tab {
  background: var(--bg-input);
  border: 1px solid var(--border-panel);
  color: var(--text-muted);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  cursor: pointer;
}

.agent-tab.active {
  background: var(--accent-bg);
  border-color: var(--accent-border-hover);
  color: var(--accent);
}

/* Status */
.debug-status {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-bottom: 0.5rem;
  background: var(--bg-input);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}

.status-thinking .status-dot {
  background: #f39c12;
  animation: pulse 1s ease-in-out infinite;
}

.status-decided .status-dot {
  background: var(--success);
}

.status-idle .status-dot {
  background: var(--text-dim);
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.4;
  }
}

.status-label {
  font-weight: bold;
  text-transform: uppercase;
  font-size: 0.65rem;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.status-desc {
  color: var(--text-primary);
  font-style: italic;
}

/* Sections */
.debug-section {
  margin-bottom: 0.5rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--border-panel);
}

.debug-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.debug-section h3 {
  font-size: 0.7rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.3rem;
}

/* Action JSON */
.action-json {
  display: block;
  background: var(--bg-input);
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  color: var(--success);
  word-break: break-all;
}

/* Unknown cards */
.unknown-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.2rem;
  margin-bottom: 0.25rem;
}

.unknown-label {
  font-size: 0.65rem;
  font-weight: bold;
  text-transform: uppercase;
  min-width: 60px;
}

.suspect-label {
  color: var(--badge-clue-text);
}

.weapon-label {
  color: var(--badge-holdem-text);
}

.room-label {
  color: var(--tag-wanderer-text);
}

.unknown-chip {
  font-size: 0.65rem;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  border: 1px solid;
}

.suspect-chip {
  background: var(--badge-clue-bg);
  border-color: var(--badge-clue-border);
  color: var(--badge-clue-text);
}

.weapon-chip {
  background: var(--badge-holdem-bg);
  border-color: var(--badge-holdem-border);
  color: var(--badge-holdem-text);
}

.room-chip {
  background: var(--tag-wanderer-bg);
  border-color: var(--tag-wanderer-text);
  color: var(--tag-wanderer-text);
}

.all-known {
  font-size: 0.65rem;
  color: var(--success);
  font-style: italic;
}

.seen-cards-line {
  font-size: 0.65rem;
  color: var(--text-dim);
  margin-top: 0.2rem;
}

.seen-label {
  font-weight: bold;
  margin-right: 0.3rem;
}

.seen-list {
  word-break: break-word;
}

/* Card holders */
.holder-row {
  font-size: 0.7rem;
  margin-bottom: 0.2rem;
}

.holder-name {
  color: var(--text-muted);
  font-weight: bold;
  margin-right: 0.3rem;
}

.holder-card {
  display: inline-block;
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-size: 0.65rem;
  margin-right: 0.2rem;
}

/* Unrefuted */
.unrefuted-item {
  font-size: 0.7rem;
  color: #f39c12;
  padding: 0.15rem 0;
}

/* Inferences */
.inference-item {
  font-size: 0.65rem;
  color: var(--text-primary);
  padding: 0.15rem 0;
  border-left: 2px solid var(--accent-border-hover);
  padding-left: 0.4rem;
  margin-bottom: 0.15rem;
}

/* Memory */
.memory-list {
  max-height: 200px;
  overflow-y: auto;
}

.memory-entry {
  font-size: 0.65rem;
  padding: 0.2rem 0;
  border-bottom: 1px solid var(--border-panel);
}

.memory-index {
  color: var(--text-dim);
  margin-right: 0.3rem;
  font-weight: bold;
}

.memory-text {
  color: var(--text-secondary);
  word-break: break-word;
}

/* Player info */
.player-info-section {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.7rem;
}

.info-label {
  color: var(--text-secondary);
  font-weight: bold;
  text-transform: uppercase;
  font-size: 0.65rem;
  min-width: 60px;
}

.info-value {
  color: var(--text-secondary);
}

.agent-type-badge {
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-size: 0.65rem;
  font-weight: bold;
  text-transform: uppercase;
}

.type-random {
  background: var(--badge-clue-bg);
  color: var(--badge-clue-text);
}

.type-llm {
  background: var(--accent-bg);
  color: var(--accent);
}

.type-human {
  background: var(--bg-input);
  color: var(--text-muted);
}

.type-wanderer {
  background: var(--tag-wanderer-bg);
  color: var(--tag-wanderer-text);
}

.active-yes {
  color: var(--success);
}

.active-no {
  color: var(--error, #e74c3c);
  font-weight: bold;
}

.turn-active {
  color: #f39c12;
  font-weight: bold;
}

.turn-waiting {
  color: var(--text-dim);
}

.moved-by-suggestion {
  color: #f39c12;
  font-style: italic;
  font-size: 0.65rem;
}

.inferred-list {
  color: var(--accent);
  word-break: break-word;
}

/* Location info */
.location-section {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.location-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.7rem;
}

.location-label {
  color: var(--text-secondary);
  font-weight: bold;
  text-transform: uppercase;
  font-size: 0.65rem;
  min-width: 60px;
}

.location-value {
  color: var(--text-secondary);
}

.location-value.in-room {
  color: var(--tag-wanderer-text);
  font-weight: bold;
}

.reachable-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
}

.no-debug {
  font-size: 0.75rem;
  color: var(--text-dim);
  font-style: italic;
  text-align: center;
  padding: 0.5rem;
}
</style>
