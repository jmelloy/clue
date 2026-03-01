<template>
  <div class="chat-panel">
    <h2>Game Log &amp; Chat</h2>
    <ul class="chat-messages" ref="chatContainer">
      <li
        v-for="(msg, i) in messages"
        :key="i"
        class="chat-message"
        :class="{ 'system-message': !msg.player_id }"
      >
        <span class="chat-text">{{ msg.text }}</span>
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
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  players: { type: Array, default: () => [] },
})
const emit = defineEmits(['send-message'])

const inputText = ref('')
const chatContainer = ref(null)

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
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

h2 {
  color: #c9a84c;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
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
  border-bottom: 1px solid rgba(255,255,255,0.03);
  font-size: 0.8rem;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.system-message {
  color: #8899aa;
  font-style: italic;
}

.chat-text {
  flex: 1;
  word-break: break-word;
  line-height: 1.3;
}

.chat-time {
  color: #556;
  font-size: 0.7rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.chat-empty {
  color: #556;
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
  padding: 0.4rem 0.6rem;
  border-radius: 5px;
  border: 1px solid #334;
  background: #0f3460;
  color: #eee;
  font-size: 0.85rem;
}

.chat-input input::placeholder {
  color: #557;
}

.chat-input button {
  background: #c9a84c;
  color: #1a1a2e;
  border: none;
  padding: 0.4rem 0.8rem;
  border-radius: 5px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.85rem;
  transition: background 0.2s;
}

.chat-input button:hover:not(:disabled) {
  background: #d4b85c;
}

.chat-input button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
