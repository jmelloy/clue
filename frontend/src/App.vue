<template>
  <div id="clue-app">
    <Lobby v-if="!gameId" @game-joined="onGameJoined" />
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
      :card-shown="cardShown"
      @action="sendAction"
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
const cardShown = ref(null)

const gameStatus = computed(() => gameState.value?.status ?? 'waiting')
const players = computed(() => gameState.value?.players ?? [])

let ws = null

function connectWS() {
  if (!gameId.value || !playerId.value) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/${gameId.value}/${playerId.value}`)
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data)
    handleMessage(msg)
  }
}

function handleMessage(msg) {
  if (msg.type === 'game_state') {
    gameState.value = msg.state ?? { ...gameState.value, ...msg }
    if (msg.state?.your_cards) yourCards.value = msg.state.your_cards
  } else if (msg.type === 'player_joined') {
    if (gameState.value) {
      gameState.value = { ...gameState.value, players: msg.players }
    }
  } else if (msg.type === 'game_started') {
    if (msg.your_cards) yourCards.value = msg.your_cards
    if (gameState.value) {
      gameState.value = { ...gameState.value, status: 'playing', whose_turn: msg.whose_turn }
    }
  } else if (msg.type === 'card_shown') {
    cardShown.value = { card: msg.card, by: msg.shown_by }
  } else if (msg.type === 'player_moved') {
    if (gameState.value) {
      const rooms = { ...gameState.value.current_room, [msg.player_id]: msg.room }
      gameState.value = { ...gameState.value, current_room: rooms, last_roll: msg.dice }
    }
  } else if (msg.type === 'game_over') {
    if (gameState.value) {
      gameState.value = { ...gameState.value, status: 'finished', winner: msg.winner, solution: msg.solution }
    }
  }
}

function onGameJoined({ gameId: gid, playerId: pid, state }) {
  gameId.value = gid
  playerId.value = pid
  gameState.value = state
  connectWS()
}

function onGameStarted(state) {
  gameState.value = { ...gameState.value, ...state, status: 'playing' }
}

async function sendAction(action) {
  await fetch(`/games/${gameId.value}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId.value, action })
  })
}
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, serif; background: #1a1a2e; color: #eee; min-height: 100vh; }
#clue-app { max-width: 960px; margin: 0 auto; padding: 1rem; }
</style>
