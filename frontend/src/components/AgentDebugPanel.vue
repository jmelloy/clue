<template>
  <div class="agent-debug-panel">
    <h2 class="collapsible-header" @click="collapsed = !collapsed">
      <span>Agent Debug</span>
      <span class="collapse-indicator" :class="{ collapsed }">&#9660;</span>
    </h2>
    <div v-if="!collapsed">
      <!-- Agent selector tabs -->
      <div v-if="agentIds.length > 1" class="agent-tabs">
        <button
          v-for="aid in agentIds"
          :key="aid"
          class="agent-tab"
          :class="{ active: selectedAgent === aid }"
          @click="selectedAgent = aid"
        >
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

        <!-- Decided action -->
        <div v-if="currentDebug.decided_action" class="debug-section">
          <h3>Last Action</h3>
          <code class="action-json">{{
            JSON.stringify(currentDebug.decided_action)
          }}</code>
        </div>

        <!-- Card knowledge -->
        <div class="debug-section">
          <h3
            class="collapsible-header"
            @click="cardsExpanded = !cardsExpanded"
          >
            <span
              >Card Knowledge ({{
                currentDebug.seen_cards?.length || 0
              }}
              seen)</span
            >
            <span
              class="collapse-indicator"
              :class="{ collapsed: !cardsExpanded }"
              >&#9660;</span
            >
          </h3>
          <div v-if="cardsExpanded">
            <div class="unknown-group">
              <span class="unknown-label suspect-label">Suspects?</span>
              <span
                v-for="s in currentDebug.unknown_suspects"
                :key="s"
                class="unknown-chip suspect-chip"
                >{{ s }}</span
              >
              <span
                v-if="!currentDebug.unknown_suspects?.length"
                class="all-known"
                >all eliminated</span
              >
            </div>
            <div class="unknown-group">
              <span class="unknown-label weapon-label">Weapons?</span>
              <span
                v-for="w in currentDebug.unknown_weapons"
                :key="w"
                class="unknown-chip weapon-chip"
                >{{ w }}</span
              >
              <span
                v-if="!currentDebug.unknown_weapons?.length"
                class="all-known"
                >all eliminated</span
              >
            </div>
            <div class="unknown-group">
              <span class="unknown-label room-label">Rooms?</span>
              <span
                v-for="r in currentDebug.unknown_rooms"
                :key="r"
                class="unknown-chip room-chip"
                >{{ r }}</span
              >
              <span v-if="!currentDebug.unknown_rooms?.length" class="all-known"
                >all eliminated</span
              >
            </div>
            <div class="seen-cards-line">
              <span class="seen-label">Seen:</span>
              <span class="seen-list">{{
                currentDebug.seen_cards?.join(", ") || "none"
              }}</span>
            </div>
          </div>
        </div>

        <!-- Known card holders -->
        <div
          v-if="Object.keys(currentDebug.player_has_cards || {}).length"
          class="debug-section"
        >
          <h3
            class="collapsible-header"
            @click="holdersExpanded = !holdersExpanded"
          >
            <span>Known Card Holders</span>
            <span
              class="collapse-indicator"
              :class="{ collapsed: !holdersExpanded }"
              >&#9660;</span
            >
          </h3>
          <div v-if="holdersExpanded">
            <div
              v-for="(cards, pid) in currentDebug.player_has_cards"
              :key="pid"
              class="holder-row"
            >
              <span class="holder-name">{{ playerName(pid) }}:</span>
              <span v-for="c in cards" :key="c" class="holder-card">{{
                c
              }}</span>
            </div>
          </div>
        </div>

        <!-- Unrefuted suggestions -->
        <div
          v-if="currentDebug.unrefuted_suggestions?.length"
          class="debug-section"
        >
          <h3>Unrefuted Suggestions</h3>
          <div
            v-for="(s, i) in currentDebug.unrefuted_suggestions"
            :key="i"
            class="unrefuted-item"
          >
            {{ s.suspect }} / {{ s.weapon }} / {{ s.room }}
          </div>
        </div>

        <!-- Recent inferences -->
        <div
          v-if="currentDebug.recent_inferences?.length"
          class="debug-section"
        >
          <h3>Pending Inferences</h3>
          <div
            v-for="(inf, i) in currentDebug.recent_inferences"
            :key="i"
            class="inference-item"
          >
            {{ inf }}
          </div>
        </div>

        <!-- LLM Memory -->
        <div v-if="currentDebug.memory?.length" class="debug-section">
          <h3
            class="collapsible-header"
            @click="memoryExpanded = !memoryExpanded"
          >
            <span>LLM Memory ({{ currentDebug.memory.length }} entries)</span>
            <span
              class="collapse-indicator"
              :class="{ collapsed: !memoryExpanded }"
              >&#9660;</span
            >
          </h3>
          <div v-if="memoryExpanded" class="memory-list">
            <div
              v-for="(entry, i) in currentDebug.memory"
              :key="i"
              class="memory-entry"
            >
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
import { ref, computed, watch } from "vue";

const props = defineProps({
  agentDebugData: { type: Object, default: () => ({}) },
  players: { type: Array, default: () => [] },
});

const collapsed = ref(false);
const cardsExpanded = ref(true);
const holdersExpanded = ref(false);
const memoryExpanded = ref(true);
const selectedAgent = ref(null);

const agentIds = computed(() => {
  const ids = Object.keys(props.agentDebugData || {});
  // Filter out wanderers for a cleaner view
  return ids.filter((id) => {
    const data = props.agentDebugData[id];
    return data && data.agent_type !== "wanderer";
  });
});

// Auto-select first agent
watch(
  agentIds,
  (ids) => {
    if (
      ids.length &&
      (!selectedAgent.value || !ids.includes(selectedAgent.value))
    ) {
      selectedAgent.value = ids[0];
    }
  },
  { immediate: true }
);

const currentDebug = computed(() => {
  if (!selectedAgent.value) return null;
  return props.agentDebugData[selectedAgent.value] || null;
});

function agentLabel(pid) {
  const data = props.agentDebugData[pid];
  if (data?.character) return data.character;
  const p = props.players?.find((pl) => pl.id === pid);
  return p ? p.name : pid.substring(0, 8);
}

function playerName(pid) {
  const p = props.players?.find((pl) => pl.id === pid);
  return p ? p.name : pid.substring(0, 8);
}
</script>

<style scoped>
.agent-debug-panel {
  background: #16213e;
  border-radius: 8px;
  padding: 0.8rem;
  border: 1px solid rgba(142, 68, 173, 0.3);
}

.agent-debug-panel h2 {
  color: #a569bd;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.collapsible-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.collapsible-header:hover {
  opacity: 0.85;
}

.collapse-indicator {
  font-size: 0.65rem;
  transition: transform 0.2s ease;
  color: #667;
}

.collapse-indicator.collapsed {
  transform: rotate(-90deg);
}

/* Agent tabs */
.agent-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}

.agent-tab {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid #334;
  color: #aaa;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  cursor: pointer;
}

.agent-tab.active {
  background: rgba(142, 68, 173, 0.2);
  border-color: rgba(142, 68, 173, 0.5);
  color: #d2b4de;
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
  background: rgba(255, 255, 255, 0.03);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #667;
  flex-shrink: 0;
}

.status-thinking .status-dot {
  background: #f39c12;
  animation: pulse 1s ease-in-out infinite;
}

.status-decided .status-dot {
  background: #2ecc71;
}

.status-idle .status-dot {
  background: #667;
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
  color: #aaa;
}

.status-desc {
  color: #d2b4de;
  font-style: italic;
}

/* Sections */
.debug-section {
  margin-bottom: 0.5rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.debug-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.debug-section h3 {
  font-size: 0.7rem;
  color: #8899aa;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.3rem;
}

/* Action JSON */
.action-json {
  display: block;
  background: rgba(0, 0, 0, 0.3);
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  color: #2ecc71;
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
  color: #e8a49c;
}
.weapon-label {
  color: #94c6e8;
}
.room-label {
  color: #8ed8ad;
}

.unknown-chip {
  font-size: 0.65rem;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  border: 1px solid;
}

.suspect-chip {
  background: rgba(231, 76, 60, 0.1);
  border-color: rgba(231, 76, 60, 0.3);
  color: #e8a49c;
}

.weapon-chip {
  background: rgba(52, 152, 219, 0.1);
  border-color: rgba(52, 152, 219, 0.3);
  color: #94c6e8;
}

.room-chip {
  background: rgba(46, 204, 113, 0.1);
  border-color: rgba(46, 204, 113, 0.3);
  color: #8ed8ad;
}

.all-known {
  font-size: 0.65rem;
  color: #2ecc71;
  font-style: italic;
}

.seen-cards-line {
  font-size: 0.65rem;
  color: #778;
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
  color: #aaa;
  font-weight: bold;
  margin-right: 0.3rem;
}

.holder-card {
  display: inline-block;
  background: rgba(142, 68, 173, 0.15);
  border: 1px solid rgba(142, 68, 173, 0.3);
  color: #d2b4de;
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
  color: #d2b4de;
  padding: 0.15rem 0;
  border-left: 2px solid rgba(142, 68, 173, 0.4);
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
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}

.memory-index {
  color: #667;
  margin-right: 0.3rem;
  font-weight: bold;
}

.memory-text {
  color: #aab;
  word-break: break-word;
}

.no-debug {
  font-size: 0.75rem;
  color: #556;
  font-style: italic;
  text-align: center;
  padding: 0.5rem;
}
</style>
