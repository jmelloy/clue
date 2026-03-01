<template>
  <div id="clue-app">
    <Lobby v-if="!gameId" @game-joined="onGameJoined" @observe="onObserve" />
    <WaitingRoom
      v-else-if="gameStatus === 'waiting'"
      :game-id="gameId"
      :player-id="playerId"
      :players="players"
      @game-started="onGameStarted"
    />
    <GameBoard
      v-else
      :game-id="gameId"
      :player-id="playerId"
      :game-state="gameState"
      :your-cards="yourCards"
      :available-actions="availableActions"
      :show-card-request="showCardRequest"
      :card-shown="cardShown"
      :chat-messages="chatMessages"
      :is-observer="isObserver"
      @action="sendAction"
      @send-chat="sendChat"
      @dismiss-card-shown="cardShown = null"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import Lobby from './components/Lobby.vue'
import WaitingRoom from './components/WaitingRoom.vue'
import GameBoard from './components/GameBoard.vue'

const gameId = ref(null)
const playerId = ref(null)
const gameState = ref(null)
const yourCards = ref([])
const availableActions = ref([])
const showCardRequest = ref(null)
const cardShown = ref(null)
const chatMessages = ref([])
const isObserver = ref(false)

const gameStatus = computed(() => gameState.value?.status ?? 'waiting')
const players = computed(() => gameState.value?.players ?? [])

let ws = null
let reconnectTimer = null

function connectWS() {
  if (!gameId.value || !playerId.value) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/${gameId.value}/${playerId.value}`)

  ws.onopen = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  ws.onclose = () => {
    // Auto-reconnect after 3 seconds
    if (gameId.value && playerId.value) {
      reconnectTimer = setTimeout(connectWS, 3000)
    }
  }

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data)
      handleMessage(msg)
    } catch (e) {
      // ignore non-JSON messages
    }
  }
}

function handleMessage(msg) {
  switch (msg.type) {
    case 'game_state':
      if (msg.state) {
        gameState.value = msg.state
        if (msg.state.your_cards) yourCards.value = msg.state.your_cards
        if (msg.state.available_actions) availableActions.value = msg.state.available_actions
      } else {
        // Partial update: merge individual fields
        const { type: _type, ...fields } = msg
        gameState.value = { ...gameState.value, ...fields }
      }
      break

    case 'player_joined':
      if (gameState.value) {
        gameState.value = { ...gameState.value, players: msg.players }
      }
      break

    case 'game_started':
      if (msg.your_cards) yourCards.value = msg.your_cards
      if (msg.available_actions) availableActions.value = msg.available_actions
      if (gameState.value) {
        gameState.value = { ...gameState.value, status: 'playing', whose_turn: msg.whose_turn }
      }
      break

    case 'your_turn':
      if (msg.available_actions) availableActions.value = msg.available_actions
      showCardRequest.value = null
      break

    case 'show_card_request':
      showCardRequest.value = {
        suggestingPlayerId: msg.suggesting_player_id,
        suspect: msg.suspect,
        weapon: msg.weapon,
        room: msg.room,
      }
      if (msg.available_actions) availableActions.value = msg.available_actions
      break

    case 'player_moved':
      if (gameState.value) {
        const rooms = { ...gameState.value.current_room, [msg.player_id]: msg.room }
        gameState.value = { ...gameState.value, current_room: rooms, last_roll: [msg.dice, 0], dice_rolled: true }
      }
      break

    case 'suggestion_made':
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          suggestions_this_turn: [
            ...(gameState.value.suggestions_this_turn ?? []),
            { suspect: msg.suspect, weapon: msg.weapon, room: msg.room, suggested_by: msg.player_id },
          ],
        }
      }
      break

    case 'card_shown':
      cardShown.value = { card: msg.card, by: msg.shown_by }
      if (msg.available_actions) availableActions.value = msg.available_actions
      showCardRequest.value = null
      break

    case 'card_shown_public':
      // A card was shown between two players (we don't see which card)
      // Clear any pending show card state
      showCardRequest.value = null
      break

    case 'accusation_made':
      if (gameState.value && !msg.correct) {
        // Mark the player as eliminated
        const updatedPlayers = gameState.value.players.map(p =>
          p.id === msg.player_id ? { ...p, active: false } : p
        )
        gameState.value = { ...gameState.value, players: updatedPlayers }
      }
      break

    case 'game_over':
      if (gameState.value) {
        gameState.value = { ...gameState.value, status: 'finished', winner: msg.winner, solution: msg.solution }
      }
      availableActions.value = []
      break

    case 'chat_message':
      chatMessages.value = [...chatMessages.value, msg]
      break

    case 'pong':
      // keep-alive response, no action needed
      break
  }
}

function onGameJoined({ gameId: gid, playerId: pid, state }) {
  gameId.value = gid
  playerId.value = pid
  gameState.value = state
  isObserver.value = false
  connectWS()
  loadChat(gid)
}

function onObserve({ gameId: gid }) {
  gameId.value = gid
  // Generate a random observer ID for WS connection
  playerId.value = 'OBS_' + Math.random().toString(36).substring(2, 10)
  isObserver.value = true

  // Fetch current state
  fetch(`/games/${gid}`)
    .then(r => r.json())
    .then(state => { gameState.value = state })
    .catch(() => {})

  connectWS()
  loadChat(gid)
}

function loadChat(gid) {
  fetch(`/games/${gid}/chat`)
    .then(r => r.json())
    .then(data => { chatMessages.value = data.messages ?? [] })
    .catch(() => {})
}

function onGameStarted(state) {
  gameState.value = { ...gameState.value, ...state, status: 'playing' }
}

async function sendAction(action) {
  const res = await fetch(`/games/${gameId.value}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId.value, action })
  })
  if (res.ok) {
    // Refresh full state to stay in sync
    try {
      const stateRes = await fetch(`/games/${gameId.value}`)
      if (stateRes.ok) {
        const freshState = await stateRes.json()
        gameState.value = freshState
      }
    } catch (e) {
      // rely on WS updates
    }
  }
}

async function sendChat(text) {
  await fetch(`/games/${gameId.value}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId.value, text })
  })
}

// Keep-alive ping every 30 seconds
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }))
  }
}, 30000)
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Georgia', serif; background: #1a1a2e; color: #eee; min-height: 100vh; }
#clue-app { max-width: 1280px; margin: 0 auto; padding: 0.75rem; }
</style>
