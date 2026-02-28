import { ref, onUnmounted } from 'vue'

/**
 * Composable for WebSocket connection management.
 * @param {string} gameId
 * @param {string} playerId
 */
export function useWebSocket(gameId, playerId) {
  const messages = ref([])
  const connected = ref(false)
  let ws = null

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/${gameId}/${playerId}`)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onclose = () => {
      connected.value = false
    }

    ws.onerror = () => {
      connected.value = false
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        messages.value.push(msg)
      } catch (e) {
        console.warn('[useWebSocket] Failed to parse WebSocket message as JSON. Check message format.')
      }
    }
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
  }

  onUnmounted(disconnect)

  connect()

  return { messages, send, connected, disconnect }
}
