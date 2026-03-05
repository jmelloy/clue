<template>
  <div id="clue-app">
    <AdminGames v-if="isAdminRoute" @go-home="onAdminGoHome" @observe-game="onAdminObserveGame" />
    <Lobby v-else-if="!gameId" :url-game-id="urlGameId" :url-game-type="currentGameType" @game-joined="onGameJoined"
      @observe="onObserve" @rejoin="onRejoin" @clear-url-game="urlGameId = null" />

    <!-- Clue game views -->
    <template v-else-if="currentGameType === 'clue'">
      <WaitingRoom v-if="gameStatus === 'waiting'" :game-id="gameId" :player-id="playerId" :players="players"
        @game-started="onGameStarted" @leave-game="leaveGame" />
      <GameBoard v-else :game-id="gameId" :player-id="playerId" :game-state="gameState" :board-data="boardData"
        :your-cards="yourCards" :available-actions="availableActions" :show-card-request="showCardRequest"
        :card-shown="cardShown" :chat-messages="chatMessages" :is-observer="isObserver" :auto-end-timer="autoEndTimer"
        :auto-show-card-timer="autoShowCardTimer" :reachable-rooms="reachableRooms"
        :reachable-positions="reachablePositions" :saved-notes="savedNotes" :agent-debug-data="agentDebugData"
        :observer-player-state="observerPlayerState" @action="sendAction" @send-chat="sendChat"
        @dismiss-card-shown="cardShown = null" @select-player="onObserverSelectPlayer" />
    </template>

    <!-- Texas Hold'em views -->
    <template v-else-if="currentGameType === 'holdem'">
      <PokerWaitingRoom v-if="gameStatus === 'waiting'" :game-id="gameId" :player-id="playerId" :players="players"
        @game-started="onGameStarted" @leave-game="leaveGame" />
      <PokerTable v-else ref="pokerTableRef" :game-id="gameId" :player-id="playerId" :game-state="gameState"
        :your-cards="yourCards" :available-actions="availableActions" :chat-messages="chatMessages"
        :is-observer="isObserver" @action="sendHoldemAction" @send-chat="sendHoldemChat" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Lobby from './components/Lobby.vue'
import WaitingRoom from './components/WaitingRoom.vue'
import GameBoard from './components/GameBoard.vue'
import PokerWaitingRoom from './components/PokerWaitingRoom.vue'
import PokerTable from './components/PokerTable.vue'
import AdminGames from './components/AdminGames.vue'

const gameId = ref(null)
const playerId = ref(null)
const gameState = ref(null)
const yourCards = ref([])
const availableActions = ref([])
const showCardRequest = ref(null)
const cardShown = ref(null)
const chatMessages = ref([])
const isObserver = ref(false)
const urlGameId = ref(null)
const autoEndTimer = ref(null)
const autoShowCardTimer = ref(null)
const reachableRooms = ref([])
const reachablePositions = ref([])
const savedNotes = ref(null)
const boardData = ref(null)
const agentDebugData = ref({})
const observerPlayerState = ref(null)
const currentGameType = ref('clue') // 'clue' or 'holdem'
const isAdminRoute = ref(false)
const pokerTableRef = ref(null)

const gameStatus = computed(() => gameState.value?.status ?? 'waiting')
const players = computed(() => gameState.value?.players ?? [])

let ws = null
let reconnectTimer = null

// --- URL routing ---

function parseGameIdFromUrl() {
  // Check admin route
  if (window.location.pathname === '/admin') return { admin: true }
  // Check holdem route first
  const holdemMatch = window.location.pathname.match(/^\/holdem\/([A-Za-z0-9]+)/)
  if (holdemMatch) return { gameId: holdemMatch[1].toUpperCase(), gameType: 'holdem' }
  // Check clue route
  const clueMatch = window.location.pathname.match(/^\/game\/([A-Za-z0-9]+)/)
  if (clueMatch) return { gameId: clueMatch[1].toUpperCase(), gameType: 'clue' }
  return null
}

function pushGameUrl(gid) {
  const prefix = currentGameType.value === 'holdem' ? '/holdem' : '/game'
  const url = `${prefix}/${gid}`
  if (window.location.pathname !== url) {
    window.history.pushState({ gameId: gid, gameType: currentGameType.value }, '', url)
  }
}

function pushLobbyUrl() {
  if (window.location.pathname !== '/') {
    window.history.pushState({}, '', '/')
  }
}

function onPopState() {
  const parsed = parseGameIdFromUrl()
  if (parsed && parsed.admin) {
    isAdminRoute.value = true
    return
  }
  isAdminRoute.value = false
  if (parsed && gameId.value && parsed.gameId === gameId.value) {
    return
  }
  if (!parsed) {
    leaveGame()
  } else if (parsed.gameId !== gameId.value) {
    resetState()
    currentGameType.value = parsed.gameType
    urlGameId.value = parsed.gameId
  }
}

onMounted(async () => {
  window.addEventListener('popstate', onPopState)
  const parsed = parseGameIdFromUrl()
  if (parsed && parsed.admin) {
    isAdminRoute.value = true
  } else if (parsed) {
    currentGameType.value = parsed.gameType
    urlGameId.value = parsed.gameId
  }
  try {
    const res = await fetch('/board')
    if (res.ok) boardData.value = await res.json()
  } catch (_) {
    /* fall back to hardcoded board data */
  }
})

onUnmounted(() => {
  window.removeEventListener('popstate', onPopState)
})

// --- WebSocket ---

function connectWS() {
  if (!gameId.value || !playerId.value) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const wsPath =
    currentGameType.value === 'holdem'
      ? `/ws/holdem/${gameId.value}/${playerId.value}`
      : `/ws/${gameId.value}/${playerId.value}`
  ws = new WebSocket(`${proto}://${location.host}${wsPath}`)

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
      if (currentGameType.value === 'holdem') {
        handleHoldemMessage(msg)
      } else {
        handleMessage(msg)
      }
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
        // Restore detective notes on reconnect
        if (msg.state.detective_notes) savedNotes.value = msg.state.detective_notes
        // Restore showCardRequest from pending_show_card on reconnect
        const pending = msg.state.pending_show_card
        if (pending && pending.player_id === playerId.value) {
          showCardRequest.value = {
            suggestingPlayerId: pending.suggesting_player_id,
            suspect: pending.suspect,
            weapon: pending.weapon,
            room: pending.room
          }
        } else {
          showCardRequest.value = null
        }
      } else {
        // Partial update: merge individual fields
        const { type: _type, ...fields } = msg
        gameState.value = { ...gameState.value, ...fields }
      }
      autoEndTimer.value = null
      autoShowCardTimer.value = null
      reachableRooms.value = []
      reachablePositions.value = []
      // Update position/room in debug data for all players
      if (gameState.value) {
        const updated = { ...agentDebugData.value }
        for (const pid of Object.keys(updated)) {
          updated[pid] = {
            ...updated[pid],
            position: gameState.value.player_positions?.[pid] ?? null,
            room: gameState.value.current_room?.[pid] ?? null
          }
        }
        agentDebugData.value = updated
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
      if (msg.state) {
        // Broadcast with full state object — use it directly
        gameState.value = msg.state
      } else if (gameState.value) {
        // Individual per-player message with top-level fields
        gameState.value = {
          ...gameState.value,
          status: 'playing',
          whose_turn: msg.whose_turn
        }
      }
      break

    case 'your_turn':
      if (msg.available_actions) availableActions.value = msg.available_actions
      if (msg.reachable_rooms) reachableRooms.value = msg.reachable_rooms
      if (msg.reachable_positions) reachablePositions.value = msg.reachable_positions
      showCardRequest.value = null
      autoEndTimer.value = null
      break

    case 'auto_end_timer':
      autoEndTimer.value = {
        playerId: msg.player_id,
        seconds: msg.seconds,
        startedAt: Date.now()
      }
      break

    case 'auto_show_card_timer':
      autoShowCardTimer.value = {
        playerId: msg.player_id,
        seconds: msg.seconds,
        startedAt: Date.now()
      }
      break

    case 'show_card_request':
      showCardRequest.value = {
        suggestingPlayerId: msg.suggesting_player_id,
        suspect: msg.suspect,
        weapon: msg.weapon,
        room: msg.room
      }
      if (msg.available_actions) availableActions.value = msg.available_actions
      break

    case 'dice_rolled':
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          last_roll: msg.last_roll,
          dice_rolled: true
        }
      }
      if (msg.reachable_rooms) reachableRooms.value = msg.reachable_rooms
      break

    case 'player_moved':
      if (gameState.value) {
        const rooms = {
          ...gameState.value.current_room,
          [msg.player_id]: msg.room
        }
        const positions = { ...(gameState.value.player_positions || {}) }
        if (msg.position) positions[msg.player_id] = msg.position
        const updates = {
          current_room: rooms,
          player_positions: positions,
          moved: true
        }
        gameState.value = { ...gameState.value, ...updates }
      }
      // Clear reachable highlights after movement
      reachableRooms.value = []
      reachablePositions.value = []
      // Update debug data for moved player
      if (agentDebugData.value[msg.player_id]) {
        agentDebugData.value = {
          ...agentDebugData.value,
          [msg.player_id]: {
            ...agentDebugData.value[msg.player_id],
            position: msg.position ?? null,
            room: msg.room ?? null
          }
        }
      }
      break

    case 'suggestion_made':
      if (gameState.value) {
        const suggUpdate = {
          suggestions_this_turn: [
            ...(gameState.value.suggestions_this_turn ?? []),
            {
              suspect: msg.suspect,
              weapon: msg.weapon,
              room: msg.room,
              suggested_by: msg.player_id
            }
          ]
        }
        // Update player positions if a suspect player was moved
        if (msg.player_positions) suggUpdate.player_positions = msg.player_positions
        // Update weapon positions (weapon moved to suggestion room)
        if (msg.weapon_positions) suggUpdate.weapon_positions = msg.weapon_positions
        gameState.value = { ...gameState.value, ...suggUpdate }
      }
      break

    case 'card_shown':
      cardShown.value = { card: msg.card, by: msg.shown_by }
      if (msg.available_actions) availableActions.value = msg.available_actions
      showCardRequest.value = null
      autoShowCardTimer.value = null
      break

    case 'card_shown_public':
      // A card was shown between two players (we don't see which card)
      // Clear any pending show card state
      showCardRequest.value = null
      autoShowCardTimer.value = null
      break

    case 'accusation_made':
      if (gameState.value && !msg.correct) {
        // Mark the player as eliminated
        const updatedPlayers = gameState.value.players.map((p) =>
          p.id === msg.player_id ? { ...p, active: false } : p
        )
        gameState.value = { ...gameState.value, players: updatedPlayers }
      }
      break

    case 'game_over':
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          status: 'finished',
          winner: msg.winner,
          solution: msg.solution
        }
      }
      availableActions.value = []
      autoEndTimer.value = null
      autoShowCardTimer.value = null
      break

    case 'chat_message':
      chatMessages.value = [...chatMessages.value, msg]
      break

    case 'agent_debug':
      if (msg.player_id) {
        agentDebugData.value = {
          ...agentDebugData.value,
          [msg.player_id]: msg
        }
      }
      break

    case 'pong':
      // keep-alive response, no action needed
      break
  }
}

// --- Game lifecycle ---

function resetState() {
  if (ws) {
    ws.onclose = null // prevent reconnect
    ws.close()
    ws = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  gameId.value = null
  playerId.value = null
  gameState.value = null
  yourCards.value = []
  availableActions.value = []
  showCardRequest.value = null
  cardShown.value = null
  chatMessages.value = []
  isObserver.value = false
  autoEndTimer.value = null
  autoShowCardTimer.value = null
  reachableRooms.value = []
  reachablePositions.value = []
  savedNotes.value = null
  agentDebugData.value = {}
  observerPlayerState.value = null
  currentGameType.value = 'clue'
}

function leaveGame() {
  resetState()
  urlGameId.value = null
  pushLobbyUrl()
}

function onAdminGoHome() {
  isAdminRoute.value = false
  pushLobbyUrl()
}

function onAdminObserveGame({ gameId: gid, gameType: gType }) {
  isAdminRoute.value = false
  currentGameType.value = gType
  gameId.value = gid
  isObserver.value = true
  urlGameId.value = null
  pushGameUrl(gid)
  connectWS()
  fetchState(gid)
}

function onGameJoined({ gameId: gid, playerId: pid, state, gameType: gType }) {
  if (gType) currentGameType.value = gType
  gameId.value = gid
  playerId.value = pid
  gameState.value = state
  isObserver.value = false
  urlGameId.value = null
  pushGameUrl(gid)
  connectWS()
  if (currentGameType.value === 'holdem') {
    loadHoldemChat(gid)
  } else {
    loadChat(gid)
  }
}

function onObserve({ gameId: gid, gameType: gType }) {
  if (gType) currentGameType.value = gType
  gameId.value = gid
  // Generate a random observer ID for WS connection
  playerId.value = 'OBS_' + Math.random().toString(36).substring(2, 10)
  isObserver.value = true
  urlGameId.value = null

  // Fetch current state
  const endpoint = currentGameType.value === 'holdem' ? `/holdem/games/${gid}` : `/games/${gid}`
  fetch(endpoint)
    .then((r) => r.json())
    .then((state) => {
      gameState.value = state
    })
    .catch(() => { })

  // Fetch initial agent debug data (Clue only)
  if (currentGameType.value === 'clue') loadAgentDebug(gid)

  pushGameUrl(gid)
  connectWS()
  if (currentGameType.value === 'holdem') {
    loadHoldemChat(gid)
  } else {
    loadChat(gid)
  }
}

function onRejoin({ gameId: gid, playerId: pid, gameType: gType }) {
  if (gType) currentGameType.value = gType
  gameId.value = gid
  playerId.value = pid
  isObserver.value = false
  urlGameId.value = null

  // Fetch current state
  const endpoint = currentGameType.value === 'holdem' ? `/holdem/games/${gid}` : `/games/${gid}`
  fetch(endpoint)
    .then((r) => r.json())
    .then((state) => {
      gameState.value = state
    })
    .catch(() => { })

  pushGameUrl(gid)
  connectWS() // WS will send player-specific state (cards, actions)
  if (currentGameType.value === 'holdem') {
    loadHoldemChat(gid)
  } else {
    loadChat(gid)
  }
}

function loadChat(gid) {
  fetch(`/games/${gid}/chat`)
    .then((r) => r.json())
    .then((data) => {
      chatMessages.value = data.messages ?? []
    })
    .catch(() => { })
}

function loadAgentDebug(gid) {
  fetch(`/games/${gid}/agent_debug`)
    .then((r) => r.json())
    .then((data) => {
      if (data.agents) {
        const debugMap = {}
        for (const agent of data.agents) {
          debugMap[agent.player_id] = agent
        }
        agentDebugData.value = debugMap
      }
    })
    .catch(() => { })
}

function onObserverSelectPlayer(pid) {
  if (!isObserver.value || !gameId.value) return
  fetch(`/games/${gameId.value}/player/${pid}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data) {
        observerPlayerState.value = {
          playerId: pid,
          your_cards: data.your_cards || [],
          available_actions: data.available_actions || [],
          detective_notes: data.detective_notes || null
        }
      }
    })
    .catch(() => { })
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
    const result = await res.json()
    if (result.available_actions) availableActions.value = result.available_actions
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

// --- Texas Hold'em ---

function handleHoldemMessage(msg) {
  switch (msg.type) {
    case 'game_state':
      if (msg.state) {
        gameState.value = msg.state
        if (msg.state.your_cards) yourCards.value = msg.state.your_cards
        if (msg.state.available_actions) availableActions.value = msg.state.available_actions
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
      if (msg.state) {
        gameState.value = msg.state
      } else if (gameState.value) {
        gameState.value = { ...gameState.value, status: 'playing', whose_turn: msg.whose_turn }
      }
      break

    case 'your_turn':
      if (msg.available_actions) availableActions.value = msg.available_actions
      break

    case 'player_action':
      refreshHoldemState()
      break

    case 'community_cards':
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          community_cards: msg.cards,
          betting_round: msg.betting_round
        }
      }
      break

    case 'showdown':
      if (pokerTableRef.value) {
        pokerTableRef.value.onShowdown(msg)
      }
      refreshHoldemState()
      break

    case 'new_hand':
      refreshHoldemState()
      break

    case 'game_over':
      if (gameState.value) {
        gameState.value = { ...gameState.value, status: 'finished', winner: msg.winner }
      }
      availableActions.value = []
      break

    case 'chat_message':
      chatMessages.value = [...chatMessages.value, msg]
      break

    case 'pong':
      break
  }
}

async function refreshHoldemState() {
  if (!gameId.value || !playerId.value) return
  try {
    const res = await fetch(`/holdem/games/${gameId.value}/player/${playerId.value}`)
    if (res.ok) {
      const state = await res.json()
      gameState.value = state
      if (state.your_cards) yourCards.value = state.your_cards
      if (state.available_actions) availableActions.value = state.available_actions
    }
  } catch (_) {
    /* rely on WS */
  }
}

async function sendHoldemAction(action) {
  const res = await fetch(`/holdem/games/${gameId.value}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId.value, action })
  })
  if (res.ok) {
    const result = await res.json()
    if (result.available_actions) availableActions.value = result.available_actions
    await refreshHoldemState()
  }
}

async function sendHoldemChat(text) {
  await fetch(`/holdem/games/${gameId.value}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId.value, text })
  })
}

function loadHoldemChat(gid) {
  fetch(`/holdem/games/${gid}/chat`)
    .then((r) => r.json())
    .then((data) => {
      chatMessages.value = data.messages ?? []
    })
    .catch(() => { })
}

// Keep-alive ping every 30 seconds
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }))
  }
}, 30000)
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Georgia', serif;
  background: #1c1812;
  color: #e8dcc8;
  min-height: 100vh;
}

#clue-app {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0.75rem;
}
</style>
