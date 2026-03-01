<template>
  <div class="board-map">
    <div class="board-grid">
      <!-- Row 1: Study, Hall, Lounge -->
      <div
        class="room"
        :class="roomClasses('Study')"
        @click="selectRoom('Study')"
        style="grid-row:1;grid-column:1"
      >
        <div class="room-name">Study</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Study')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
        <div class="secret-passage" title="Secret passage to Kitchen">&#x2922; Kitchen</div>
      </div>

      <div class="corridor-h" style="grid-row:1;grid-column:2">
        <div class="corridor-line-h"></div>
      </div>

      <div
        class="room"
        :class="roomClasses('Hall')"
        @click="selectRoom('Hall')"
        style="grid-row:1;grid-column:3"
      >
        <div class="room-name">Hall</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Hall')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
      </div>

      <div class="corridor-h" style="grid-row:1;grid-column:4">
        <div class="corridor-line-h"></div>
      </div>

      <div
        class="room"
        :class="roomClasses('Lounge')"
        @click="selectRoom('Lounge')"
        style="grid-row:1;grid-column:5"
      >
        <div class="room-name">Lounge</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Lounge')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
        <div class="secret-passage" title="Secret passage to Conservatory">&#x2923; Conserv.</div>
      </div>

      <!-- Row 2: Vertical corridors -->
      <div class="corridor-v" style="grid-row:2;grid-column:1"><div class="corridor-line-v"></div></div>
      <div style="grid-row:2;grid-column:2"></div>
      <div class="corridor-v" style="grid-row:2;grid-column:3"><div class="corridor-line-v"></div></div>
      <div style="grid-row:2;grid-column:4"></div>
      <div class="corridor-v" style="grid-row:2;grid-column:5"><div class="corridor-line-v"></div></div>

      <!-- Row 3: Library, Center, Dining Room -->
      <div
        class="room"
        :class="roomClasses('Library')"
        @click="selectRoom('Library')"
        style="grid-row:3;grid-column:1"
      >
        <div class="room-name">Library</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Library')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
      </div>

      <div class="corridor-h" style="grid-row:3;grid-column:2">
        <div class="corridor-line-h"></div>
      </div>

      <div class="center-area" style="grid-row:3/6;grid-column:3">
        <div class="center-label">CLUE</div>
        <div class="center-icon">&#128270;</div>
      </div>

      <div class="corridor-h" style="grid-row:3;grid-column:4">
        <div class="corridor-line-h"></div>
      </div>

      <div
        class="room"
        :class="roomClasses('Dining Room')"
        @click="selectRoom('Dining Room')"
        style="grid-row:3;grid-column:5"
      >
        <div class="room-name">Dining Room</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Dining Room')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
      </div>

      <!-- Row 4: Vertical corridors -->
      <div class="corridor-v" style="grid-row:4;grid-column:1"><div class="corridor-line-v"></div></div>
      <div style="grid-row:4;grid-column:2"></div>
      <!-- center spans row 3-5 col 3 -->
      <div style="grid-row:4;grid-column:4"></div>
      <div class="corridor-v" style="grid-row:4;grid-column:5"><div class="corridor-line-v"></div></div>

      <!-- Row 5: Billiard Room, center continues, empty -->
      <div
        class="room"
        :class="roomClasses('Billiard Room')"
        @click="selectRoom('Billiard Room')"
        style="grid-row:5;grid-column:1"
      >
        <div class="room-name">Billiard Room</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Billiard Room')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
      </div>

      <div class="corridor-h" style="grid-row:5;grid-column:2">
        <div class="corridor-line-h"></div>
      </div>

      <!-- center area already spans here (row 3-5, col 3) -->
      <div style="grid-row:5;grid-column:4"></div>
      <div style="grid-row:5;grid-column:5"></div>

      <!-- Row 6: Vertical corridors -->
      <div class="corridor-v" style="grid-row:6;grid-column:1"><div class="corridor-line-v"></div></div>
      <div style="grid-row:6;grid-column:2"></div>
      <div class="corridor-v" style="grid-row:6;grid-column:3"><div class="corridor-line-v"></div></div>
      <div style="grid-row:6;grid-column:4"></div>
      <div class="corridor-v" style="grid-row:6;grid-column:5"><div class="corridor-line-v"></div></div>

      <!-- Row 7: Conservatory, Ballroom, Kitchen -->
      <div
        class="room"
        :class="roomClasses('Conservatory')"
        @click="selectRoom('Conservatory')"
        style="grid-row:7;grid-column:1"
      >
        <div class="room-name">Conservatory</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Conservatory')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
        <div class="secret-passage" title="Secret passage to Lounge">&#x2921; Lounge</div>
      </div>

      <div class="corridor-h" style="grid-row:7;grid-column:2">
        <div class="corridor-line-h"></div>
      </div>

      <div
        class="room"
        :class="roomClasses('Ballroom')"
        @click="selectRoom('Ballroom')"
        style="grid-row:7;grid-column:3"
      >
        <div class="room-name">Ballroom</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Ballroom')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
      </div>

      <div class="corridor-h" style="grid-row:7;grid-column:4">
        <div class="corridor-line-h"></div>
      </div>

      <div
        class="room"
        :class="roomClasses('Kitchen')"
        @click="selectRoom('Kitchen')"
        style="grid-row:7;grid-column:5"
      >
        <div class="room-name">Kitchen</div>
        <div class="room-players">
          <span
            v-for="p in playersInRoom('Kitchen')"
            :key="p.id"
            class="player-token"
            :style="tokenStyle(p)"
            :title="p.name + ' (' + p.character + ')'"
          >{{ abbr(p.character) }}</span>
        </div>
        <div class="secret-passage" title="Secret passage to Study">&#x2920; Study</div>
      </div>
    </div>

    <!-- Players in hallway -->
    <div v-if="hallwayPlayers.length" class="hallway-section">
      <span class="hallway-label">In hallway:</span>
      <span
        v-for="p in hallwayPlayers"
        :key="p.id"
        class="player-token hallway-token"
        :style="tokenStyle(p)"
        :title="p.name + ' (' + p.character + ')'"
      >{{ abbr(p.character) }} {{ p.name }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const CHARACTER_COLORS = {
  'Miss Scarlett':    { bg: '#e74c3c', text: '#fff' },
  'Colonel Mustard':  { bg: '#f39c12', text: '#1a1a2e' },
  'Mrs. White':       { bg: '#ecf0f1', text: '#1a1a2e' },
  'Reverend Green':   { bg: '#27ae60', text: '#fff' },
  'Mrs. Peacock':     { bg: '#2980b9', text: '#fff' },
  'Professor Plum':   { bg: '#8e44ad', text: '#fff' },
}

const CHARACTER_ABBR = {
  'Miss Scarlett': 'Sc',
  'Colonel Mustard': 'Mu',
  'Mrs. White': 'Wh',
  'Reverend Green': 'Gr',
  'Mrs. Peacock': 'Pe',
  'Professor Plum': 'Pl',
}

const props = defineProps({
  gameState: Object,
  playerId: String,
  selectedRoom: String,
  selectable: Boolean,
})

const emit = defineEmits(['select-room'])

const players = computed(() => props.gameState?.players ?? [])
const currentRoom = computed(() => props.gameState?.current_room ?? {})

function playersInRoom(roomName) {
  return players.value.filter(p => currentRoom.value[p.id] === roomName)
}

const hallwayPlayers = computed(() => {
  return players.value.filter(p => !currentRoom.value[p.id])
})

function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

function tokenStyle(player) {
  const colors = CHARACTER_COLORS[player.character] ?? { bg: '#666', text: '#fff' }
  return {
    backgroundColor: colors.bg,
    color: colors.text,
  }
}

function roomClasses(roomName) {
  const classes = {}
  const myRoom = currentRoom.value[props.playerId]
  if (myRoom === roomName) classes['my-room'] = true
  if (props.selectedRoom === roomName) classes['selected'] = true
  if (props.selectable) classes['selectable'] = true
  return classes
}

function selectRoom(roomName) {
  if (props.selectable) {
    emit('select-room', roomName)
  }
}
</script>

<style scoped>
.board-map {
  user-select: none;
}

.board-grid {
  display: grid;
  grid-template-columns: 1fr 20px 1fr 20px 1fr;
  grid-template-rows: auto 16px auto 16px auto 16px auto;
  gap: 0;
  max-width: 560px;
  margin: 0 auto;
}

.room {
  background: #1e3a5f;
  border: 2px solid #2c5282;
  border-radius: 8px;
  padding: 0.6rem;
  min-height: 80px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  transition: all 0.2s ease;
  position: relative;
}

.room.selectable {
  cursor: pointer;
}

.room.selectable:hover {
  border-color: #c9a84c;
  background: #1e3a6f;
  box-shadow: 0 0 12px rgba(201, 168, 76, 0.3);
}

.room.selected {
  border-color: #c9a84c;
  background: #2a4a3f;
  box-shadow: 0 0 16px rgba(201, 168, 76, 0.5);
}

.room.my-room {
  border-color: #f1c40f;
  box-shadow: 0 0 8px rgba(241, 196, 15, 0.3);
}

.room-name {
  font-weight: bold;
  font-size: 0.8rem;
  color: #c9a84c;
  text-align: center;
  line-height: 1.1;
}

.room-players {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  justify-content: center;
  min-height: 22px;
}

.player-token {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 0.6rem;
  font-weight: bold;
  box-shadow: 0 1px 3px rgba(0,0,0,0.4);
  flex-shrink: 0;
}

.hallway-token {
  width: auto;
  border-radius: 12px;
  padding: 0.15rem 0.5rem;
  font-size: 0.7rem;
  gap: 0.25rem;
}

.secret-passage {
  font-size: 0.6rem;
  color: #e67e22;
  font-style: italic;
  position: absolute;
  bottom: 2px;
  right: 4px;
  opacity: 0.8;
}

/* Corridors */
.corridor-h {
  display: flex;
  align-items: center;
  justify-content: center;
}

.corridor-line-h {
  width: 100%;
  height: 3px;
  background: linear-gradient(90deg, transparent, #4a6fa5, transparent);
  border-radius: 2px;
}

.corridor-v {
  display: flex;
  align-items: center;
  justify-content: center;
}

.corridor-line-v {
  width: 3px;
  height: 100%;
  min-height: 12px;
  background: linear-gradient(180deg, transparent, #4a6fa5, transparent);
  border-radius: 2px;
}

/* Center area */
.center-area {
  background: radial-gradient(ellipse at center, #1a1a2e 0%, #0d1117 100%);
  border: 2px solid #333;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  min-height: 80px;
}

.center-label {
  font-size: 1.4rem;
  font-weight: bold;
  color: #c9a84c;
  letter-spacing: 0.3em;
  text-shadow: 0 0 10px rgba(201, 168, 76, 0.5);
}

.center-icon {
  font-size: 1.8rem;
  opacity: 0.7;
}

/* Hallway section */
.hallway-section {
  margin-top: 0.5rem;
  padding: 0.4rem 0.6rem;
  background: #0f1a2e;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
}

.hallway-label {
  color: #888;
  font-style: italic;
}
</style>
