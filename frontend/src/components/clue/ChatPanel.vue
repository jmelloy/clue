<template>
  <div class="chat-panel">
    <div class="log-filters">
      <label class="filter-label">
        <input type="checkbox" v-model="showSuggestions" />
        Suggestions
      </label>
      <label class="filter-label">
        <input type="checkbox" v-model="showCardShows" />
        Card Shows
      </label>
      <label class="filter-label">
        <input type="checkbox" v-model="showAccusations" />
        Accusations
      </label>
      <label class="filter-label">
        <input type="checkbox" v-model="showMoves" />
        Moves &amp; Rolls
      </label>
      <label class="filter-label">
        <input type="checkbox" v-model="showChat" />
        Chat
      </label>
    </div>

    <ul class="chat-messages" ref="chatContainer">
      <li
        v-for="(msg, i) in combinedMessages"
        :key="i"
        class="chat-message"
        :class="{ 'system-message': !isPlayerChat(msg) }"
      >
        <span class="chat-text" v-html="formatMessageHtml(msg)"></span>
        <span v-if="msgTag(msg)" class="chat-tag" :class="'chat-tag-' + msgTag(msg)">{{
          msgTagLabel(msg)
        }}</span>
        <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
      </li>
      <li v-if="!combinedMessages.length" class="chat-empty">No messages yet.</li>
    </ul>

    <div class="chat-input">
      <input v-model="inputText" placeholder="Type a message..." maxlength="300" @keyup.enter="sendMessage" />
      <button class="btn-accent" :disabled="!inputText.trim()" @click="sendMessage">Send</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { CHARACTER_COLORS } from '../../constants/clue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  players: { type: Array, default: () => [] }
})
const emit = defineEmits(['send-message'])

const inputText = ref('')
const chatContainer = ref(null)

// Log filters — all on by default
const showSuggestions = ref(true)
const showCardShows = ref(true)
const showAccusations = ref(true)
const showMoves = ref(true)
const showChat = ref(true)

const playerById = computed(() => {
  const map = {}
  for (const p of props.players) map[p.id] = p
  return map
})

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function isPlayerChat(msg) {
  if (!msg.player_id) return false
  const player = playerById.value[msg.player_id]
  if (!player) return false
  return msg.text.startsWith(player.name + ': ')
}

// Categorize log messages
function logCategory(msg) {
  const t = msg.text || ''
  if (t.includes('suggests it was') || t.includes('No one could disprove')) return 'suggestion'
  if (
    t.includes('showed a card to') ||
    t.includes('showed you:') ||
    t.includes('No one could show')
  )
    return 'cardshow'
  if (t.includes('accuses')) return 'accusation'
  if (t.includes('rolled') || t.includes('moved to') || t.includes('used the secret passage'))
    return 'move'
  return 'other'
}

// Combined messages: all player chat + filtered system log, in original order
const combinedMessages = computed(() => {
  return props.messages.filter((msg) => {
    if (isPlayerChat(msg)) return showChat.value
    const cat = logCategory(msg)
    if (cat === 'suggestion' && !showSuggestions.value) return false
    if (cat === 'cardshow' && !showCardShows.value) return false
    if (cat === 'accusation' && !showAccusations.value) return false
    if (cat === 'move' && !showMoves.value) return false
    return true
  })
})

function colorizeNames(text) {
  const entries = Object.entries(CHARACTER_COLORS).sort((a, b) => b[0].length - a[0].length)
  for (const [name, charColor] of entries) {
    const color = charColor?.name || charColor?.bg || charColor
    const esc = escapeHtml(name)
    if (text.includes(esc)) {
      text = text.replaceAll(esc, `<span style="color:${color};font-weight:bold">${esc}</span>`)
    }
  }
  for (const p of props.players) {
    const charColor = CHARACTER_COLORS[p.character]
    if (!charColor) continue
    const color = charColor?.name || charColor?.bg || charColor
    const esc = escapeHtml(p.name)
    if (text.includes(esc) && !text.includes(`">${esc}</span>`)) {
      text = text.replaceAll(esc, `<span style="color:${color};font-weight:bold">${esc}</span>`)
    }
  }
  return text
}

function formatMessageHtml(msg) {
  const escaped = escapeHtml(msg.text)

  if (isPlayerChat(msg)) {
    const player = playerById.value[msg.player_id]
    const charColor = CHARACTER_COLORS[player.character]
    const color = charColor?.name || charColor?.bg || charColor
    if (color) {
      const nameLen = escapeHtml(player.name).length
      const name = escaped.substring(0, nameLen)
      const rest = escaped.substring(nameLen)
      return `<span style="color:${color};font-weight:bold">${name}</span>${colorizeNames(rest)}`
    }
  }

  return colorizeNames(escaped)
}

function msgTag(msg) {
  const t = msg.text || ''
  if (t.includes('suggests it was')) return 'suggest'
  if (t.includes('showed a card to') || t.includes('showed you:')) return 'show'
  if (t.includes('accuses')) return 'accuse'
  if (t.includes('No one could disprove')) return 'suggest'
  return null
}

function msgTagLabel(msg) {
  const tag = msgTag(msg)
  if (tag === 'suggest') return 'suggest'
  if (tag === 'show') return 'show'
  if (tag === 'accuse') return 'accuse'
  return ''
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return
  emit('send-message', text)
  inputText.value = ''
}

// Auto-scroll to bottom when new messages arrive
watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  }
)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-family: 'Crimson Text', Georgia, serif;
}

.log-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 0.8rem;
  margin-bottom: 0.4rem;
  padding: 0.3rem 0;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.72rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.filter-label input[type='checkbox'] {
  accent-color: var(--accent);
  width: 12px;
  height: 12px;
  cursor: pointer;
}

.chat-messages {
  list-style: none;
  flex: 1;
  overflow-y: auto;
  max-height: 200px;
  margin-bottom: 0.5rem;
  padding-right: 0.2rem;
}

.chat-message {
  padding: 0.2rem 0;
  border-bottom: 1px solid var(--border-panel);
  font-size: 0.8rem;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.system-message {
  color: var(--text-muted);
  font-style: italic;
}

.chat-text {
  flex: 1;
  word-break: break-word;
  line-height: 1.3;
  color: var(--text-primary);
}

.system-message .chat-text {
  color: var(--text-muted);
}

.chat-tag {
  font-size: 0.6rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-tag-suggest {
  background: var(--tag-suggest-bg);
  color: var(--tag-suggest-text);
}

.chat-tag-show {
  background: var(--accent-bg);
  color: var(--accent);
}

.chat-tag-accuse {
  background: var(--tag-accuse-bg);
  color: var(--tag-accuse-text);
}

.chat-time {
  color: var(--text-darkest);
  font-size: 0.7rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-empty {
  color: var(--text-darkest);
  font-style: italic;
  font-size: 0.8rem;
  padding: 0.5rem 0;
}

.chat-input {
  display: flex;
  gap: 0.4rem;
}

.chat-input input {
  flex: 1;
  padding: 0.45rem 0.7rem;
  border-radius: 4px;
  border: 1px solid var(--accent-border);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  transition: border-color 0.2s;
  outline: none;
}

.chat-input input::placeholder {
  color: var(--text-darkest);
  font-style: italic;
}

.chat-input input:focus {
  border-color: var(--accent-border-focus);
  box-shadow: 0 0 0 2px var(--accent-bg);
}

.chat-input button {
  padding: 0.45rem 0.8rem;
  border-radius: 4px;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
}
</style>
