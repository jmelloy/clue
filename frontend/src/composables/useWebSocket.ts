import { ref, onUnmounted, type Ref } from 'vue'

export interface UseWebSocketReturn {
  messages: Ref<unknown[]>
  send: (data: string | Record<string, unknown>) => void
  connected: Ref<boolean>
  disconnect: () => void
}

/**
 * Composable for WebSocket connection management.
 */
export function useWebSocket(gameId: string, playerId: string): UseWebSocketReturn {
  const messages = ref<unknown[]>([])
  const connected = ref(false)
  let ws: WebSocket | null = null

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/api/ws/${gameId}/${playerId}`)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onclose = () => {
      connected.value = false
    }

    ws.onerror = () => {
      connected.value = false
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)
        messages.value.push(msg)
      } catch {
        console.warn(
          '[useWebSocket] Failed to parse WebSocket message as JSON. Check message format.'
        )
      }
    }
  }

  function send(data: string | Record<string, unknown>) {
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
