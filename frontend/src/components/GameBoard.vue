<template>
  <div class="game-board">
    <header>
      <h1>🔍 Clue</h1>
      <div class="status">
        <span v-if="gameState?.status === 'finished'">
          🏆 Game Over! Winner: <strong>{{ winnerName }}</strong>
          <span v-if="gameState.solution"> — Solution: {{ gameState.solution.suspect }} with the {{ gameState.solution.weapon }} in the {{ gameState.solution.room }}</span>
        </span>
        <span v-else>
          Turn {{ gameState?.turn_number }} — {{ isMyTurn ? '⭐ Your turn!' : `Waiting for ${currentPlayerName}` }}
        </span>
      </div>
    </header>

    <div class="columns">
      <!-- Left: Board info -->
      <section class="panel board-panel">
        <h2>Players</h2>
        <ul class="player-list">
          <li
            v-for="p in gameState?.players"
            :key="p.id"
            :class="{ active: gameState?.whose_turn === p.id, eliminated: !p.active }"
          >
            {{ p.name }} ({{ p.character }})
            <span v-if="gameState?.current_room?.[p.id]"> — {{ gameState.current_room[p.id] }}</span>
          </li>
        </ul>

        <h2 style="margin-top:1rem">Your Cards</h2>
        <div class="cards">
          <span v-for="card in yourCards" :key="card" class="card">{{ card }}</span>
          <span v-if="!yourCards.length" class="no-cards">No cards yet</span>
        </div>

        <div v-if="gameState?.last_roll" style="margin-top:1rem">
          🎲 Last roll: <strong>{{ gameState.last_roll[0] }} + {{ gameState.last_roll[1] }} = {{ gameState.last_roll[0] + gameState.last_roll[1] }}</strong>
        </div>
      </section>

      <!-- Right: Actions -->
      <section v-if="isMyTurn && gameState?.status === 'playing'" class="panel actions-panel">
        <h2>Actions</h2>

        <!-- Step 1: Roll & Move -->
        <div v-if="!gameState.dice_rolled" class="action-group">
          <h3>Move</h3>
          <select v-model="targetRoom">
            <option value="">— Choose a room —</option>
            <option v-for="room in ROOMS" :key="room" :value="room">{{ room }}</option>
          </select>
          <button :disabled="!targetRoom" @click="doMove">🎲 Roll & Move</button>
        </div>

        <!-- Step 2: Suggest -->
        <div v-if="myCurrentRoom && gameState.dice_rolled" class="action-group">
          <h3>Suggest (in {{ myCurrentRoom }})</h3>
          <select v-model="suggestSuspect">
            <option value="">— Suspect —</option>
            <option v-for="s in SUSPECTS" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-model="suggestWeapon">
            <option value="">— Weapon —</option>
            <option v-for="w in WEAPONS" :key="w" :value="w">{{ w }}</option>
          </select>
          <button :disabled="!suggestSuspect || !suggestWeapon" @click="doSuggest">🔎 Suggest</button>
          <div v-if="cardShown" class="shown-card">
            Card shown: <strong>{{ cardShown.card }}</strong> (by {{ playerName(cardShown.by) }})
          </div>
        </div>

        <!-- Accuse -->
        <div class="action-group">
          <h3>Final Accusation</h3>
          <select v-model="accuseSuspect">
            <option value="">— Suspect —</option>
            <option v-for="s in SUSPECTS" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-model="accuseWeapon">
            <option value="">— Weapon —</option>
            <option v-for="w in WEAPONS" :key="w" :value="w">{{ w }}</option>
          </select>
          <select v-model="accuseRoom">
            <option value="">— Room —</option>
            <option v-for="r in ROOMS" :key="r" :value="r">{{ r }}</option>
          </select>
          <button
            :disabled="!accuseSuspect || !accuseWeapon || !accuseRoom"
            class="accuse-btn"
            @click="doAccuse"
          >⚠️ Accuse!</button>
        </div>

        <!-- End turn -->
        <button class="end-turn-btn" @click="doEndTurn">✅ End Turn</button>
      </section>
    </div>

    <!-- Move Log -->
    <section class="panel log-panel">
      <h2>Move Log</h2>
      <ul class="log">
        <li v-for="(entry, i) in log" :key="i" class="log-entry">
          <span class="log-type">[{{ entry.type }}]</span>
          <span v-if="entry.player_id"> {{ playerName(entry.player_id) }}</span>
          <span v-if="entry.room"> → {{ entry.room }}</span>
          <span v-if="entry.suspect"> suggested {{ entry.suspect }} / {{ entry.weapon }} / {{ entry.room }}</span>
          <span v-if="entry.dice"> rolled {{ entry.dice[0] }}+{{ entry.dice[1] }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'

const SUSPECTS = ['Miss Scarlett', 'Colonel Mustard', 'Mrs. White', 'Reverend Green', 'Mrs. Peacock', 'Professor Plum']
const WEAPONS = ['Candlestick', 'Knife', 'Lead Pipe', 'Revolver', 'Rope', 'Wrench']
const ROOMS = ['Kitchen', 'Ballroom', 'Conservatory', 'Billiard Room', 'Library', 'Study', 'Hall', 'Lounge', 'Dining Room']

const props = defineProps({
  gameId: String,
  playerId: String,
  gameState: Object,
  yourCards: Array,
  cardShown: Object,
})
const emit = defineEmits(['action'])

const log = ref([])
const targetRoom = ref('')
const suggestSuspect = ref('')
const suggestWeapon = ref('')
const accuseSuspect = ref('')
const accuseWeapon = ref('')
const accuseRoom = ref('')

const isMyTurn = computed(() => props.gameState?.whose_turn === props.playerId)
const myCurrentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const currentPlayerName = computed(() => {
  const pid = props.gameState?.whose_turn
  return playerName(pid)
})

const winnerName = computed(() => {
  const wid = props.gameState?.winner
  return playerName(wid)
})

function playerName(pid) {
  if (!pid) return '?'
  const p = props.gameState?.players?.find(pl => pl.id === pid)
  return p ? p.name : pid
}

function doMove() {
  emit('action', { type: 'move', room: targetRoom.value })
  targetRoom.value = ''
}

function doSuggest() {
  emit('action', { type: 'suggest', suspect: suggestSuspect.value, weapon: suggestWeapon.value, room: myCurrentRoom.value })
  suggestSuspect.value = ''
  suggestWeapon.value = ''
}

function doAccuse() {
  emit('action', { type: 'accuse', suspect: accuseSuspect.value, weapon: accuseWeapon.value, room: accuseRoom.value })
}

function doEndTurn() {
  emit('action', { type: 'end_turn' })
}
</script>

<style scoped>
.game-board { padding: 1rem; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
h1 { color: #c9a84c; }
.status { font-size: 1.1rem; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
.panel { background: #16213e; border-radius: 8px; padding: 1.2rem; }
.board-panel h2, .actions-panel h2 { color: #c9a84c; margin-bottom: 0.5rem; }
.player-list { list-style: none; }
.player-list li { padding: 0.3rem 0; }
.player-list li.active { font-weight: bold; color: #f1c40f; }
.player-list li.eliminated { opacity: 0.4; text-decoration: line-through; }
.cards { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.4rem; }
.card { background: #0f3460; padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.85rem; }
.no-cards { color: #888; font-style: italic; }
.action-group { margin-bottom: 1rem; }
.action-group h3 { margin-bottom: 0.4rem; font-size: 0.95rem; color: #aaa; }
select { display: block; width: 100%; margin-bottom: 0.4rem; padding: 0.4rem; border-radius: 4px; border: 1px solid #444; background: #0f3460; color: #eee; }
button { background: #c9a84c; color: #1a1a2e; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-weight: bold; margin-bottom: 0.4rem; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.accuse-btn { background: #e74c3c; color: #fff; }
.end-turn-btn { background: #27ae60; color: #fff; width: 100%; margin-top: 0.5rem; }
.shown-card { margin-top: 0.4rem; color: #2ecc71; font-style: italic; }
.log-panel { margin-top: 1rem; max-height: 200px; overflow-y: auto; }
.log { list-style: none; }
.log-entry { padding: 0.2rem 0; font-size: 0.85rem; border-bottom: 1px solid #1a1a2e; }
.log-type { color: #c9a84c; font-weight: bold; }
</style>
