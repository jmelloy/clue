<template>
  <div class="chat-panel">
    <h2>Game Log &amp; Chat</h2>
    <ul class="chat-messages" ref="chatContainer">
      <li
        v-for="(msg, i) in messages"
        :key="i"
        class="chat-message"
        :class="{ 'system-message': isSystemMsg(msg) }"
      >
        <span class="chat-text" v-html="formatMessageHtml(msg)"></span>
        <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
      </li>
      <li v-if="!messages.length" class="chat-empty">No messages yet.</li>
    </ul>
    <div class="chat-input">
      <input
        v-model="inputText"
        placeholder="Type a message..."
        maxlength="300"
        @keyup.enter="sendMessage"
      />
      <button :disabled="!inputText.trim()" @click="sendMessage">Send</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const CHARACTER_COLORS = {
  'Miss Scarlett':    '#e74c3c',
  'Colonel Mustard':  '#f39c12',
  'Mrs. White':       '#ecf0f1',
  'Reverend Green':   '#27ae60',
  'Mrs. Peacock':     '#2980b9',
  'Professor Plum':   '#8e44ad',
}

const props = defineProps({
  messages: { type: Array, default: () => [] },
  players: { type: Array, default: () => [] },
})
const emit = defineEmits(['send-message'])

const inputText = ref('')
const chatContainer = ref(null)

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

function isSystemMsg(msg) {
  return !isPlayerChat(msg)
}

function colorizeNames(text) {
  // Color character names — sort longest first to avoid partial matches
  const entries = Object.entries(CHARACTER_COLORS).sort((a, b) => b[0].length - a[0].length)
  for (const [name, color] of entries) {
    const esc = escapeHtml(name)
    if (text.includes(esc)) {
      text = text.replaceAll(esc, `<span style="color:${color};font-weight:bold">${esc}</span>`)
    }
  }
  // Color player display names (may differ from character names)
  for (const p of props.players) {
    const color = CHARACTER_COLORS[p.character]
    if (!color) continue
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
    // Player chat: "PlayerName: message text"
    const player = playerById.value[msg.player_id]
    const color = CHARACTER_COLORS[player.character]
    if (color) {
      const nameLen = escapeHtml(player.name).length
      const name = escaped.substring(0, nameLen)
      const rest = escaped.substring(nameLen)
      return `<span style="color:${color};font-weight:bold">${name}</span>${colorizeNames(rest)}`
    }
  }

  // System / action message: color all known names
  return colorizeNames(escaped)
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

h2 {
  font-family: 'Playfair Display', Georgia, serif;
  color: #d4a849;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.03em;
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
  border-bottom: 1px solid rgba(212, 168, 73, 0.04);
  font-size: 0.8rem;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.system-message {
  color: #6a6050;
  font-style: italic;
}

.chat-text {
  flex: 1;
  word-break: break-word;
  line-height: 1.3;
  color: #e8dcc8;
}

.system-message .chat-text {
  color: #6a6050;
}

.chat-time {
  color: #3a3528;
  font-size: 0.7rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-empty {
  color: #3a3528;
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
  border: 1px solid rgba(212, 168, 73, 0.12);
  background: rgba(255, 255, 255, 0.03);
  color: #e8dcc8;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  transition: border-color 0.2s;
  outline: none;
}

.chat-input input::placeholder {
  color: #3a3528;
  font-style: italic;
}

.chat-input input:focus {
  border-color: rgba(212, 168, 73, 0.3);
  box-shadow: 0 0 0 2px rgba(212, 168, 73, 0.06);
}

.chat-input button {
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
  border: none;
  padding: 0.45rem 0.8rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
  transition: all 0.2s;
}

.chat-input button:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(212, 168, 73, 0.2);
  transform: translateY(-1px);
}

.chat-input button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
