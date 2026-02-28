<template>
  <div class="chat-panel">
    <h2>Chat</h2>
    <ul class="chat-messages" ref="chatContainer">
      <li v-for="(msg, i) in messages" :key="i" class="chat-message">
        <span class="chat-text">{{ msg.text }}</span>
        <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
      </li>
      <li v-if="!messages.length" class="chat-empty">No messages yet.</li>
    </ul>
    <div class="chat-input">
      <input
        v-model="inputText"
        placeholder="Type a message…"
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
.chat-panel { display: flex; flex-direction: column; height: 100%; }
h2 { color: #c9a84c; margin-bottom: 0.5rem; }
.chat-messages {
  list-style: none;
  flex: 1;
  overflow-y: auto;
  max-height: 260px;
  margin-bottom: 0.5rem;
  padding-right: 0.2rem;
}
.chat-message {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 0.25rem 0;
  border-bottom: 1px solid #1a1a2e;
  font-size: 0.85rem;
  gap: 0.5rem;
}
.chat-text { flex: 1; word-break: break-word; }
.chat-time { color: #888; font-size: 0.75rem; white-space: nowrap; }
.chat-empty { color: #888; font-style: italic; font-size: 0.85rem; }
.chat-input { display: flex; gap: 0.4rem; }
.chat-input input {
  flex: 1;
  padding: 0.4rem;
  border-radius: 4px;
  border: 1px solid #444;
  background: #0f3460;
  color: #eee;
  font-size: 0.9rem;
}
.chat-input button {
  background: #c9a84c;
  color: #1a1a2e;
  border: none;
  padding: 0.4rem 0.8rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
  font-size: 0.9rem;
}
.chat-input button:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
