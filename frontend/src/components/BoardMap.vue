<template>
  <div class="board-map">
    <div class="board-container">
      <!-- Background grid of 25x24 cells -->
      <div class="board-grid">
        <div
          v-for="(cell, i) in cells"
          :key="i"
          :class="cellClasses(cell)"
          :style="cellStyle(cell)"
          @click="handleCellClick(cell)"
        ></div>
      </div>
      <!-- Overlay: labels, passages, player tokens -->
      <div class="board-overlay">
        <!-- Room name labels -->
        <div
          v-for="room in roomLabels"
          :key="'lbl-' + room.name"
          class="room-label"
          :style="overlayPos(room.centerRow, room.centerCol)"
        >{{ room.name }}</div>
        <!-- Center CLUE label -->
        <div class="center-label" :style="overlayPos(12, 11)">CLUE</div>
        <!-- Secret passage indicators -->
        <div
          v-for="sp in secretPassages"
          :key="'sp-' + sp.from"
          class="secret-passage"
          :style="overlayPos(sp.row, sp.col)"
          :title="'Secret passage to ' + sp.to"
        >&#x2194; {{ sp.to }}</div>
        <!-- Player tokens -->
        <div
          v-for="token in playerTokens"
          :key="'tk-' + token.id"
          class="player-token"
          :class="{ 'my-token': token.id === playerId }"
          :style="tokenStyle(token)"
          :title="`${token.name} (${token.character})`"
        >{{ abbr(token.character) }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// ── Board layout data (matches backend board.py) ──

const BOARD_ROWS = [
  'ssssss .        . oooooo',
  'sssssss..hhhhhh..ooooooo',
  'sssssss..hhhhhh..ooooooo',
  'sssssss..hhhhhh..ooooooo',
  ' ........hhhhhh..ooooooo',
  '.........hhhhhh..ooooooo',
  ' lllll...hhhhhh........ ',
  'lllllll.................',
  'lllllll..     .........',
  'lllllll..     ..nnnnnnnn',
  ' lllll...     ..nnnnnnnn',
  ' ........     ..nnnnnnnn',
  'bbbbbb...     ..nnnnnnnn',
  'bbbbbb...     ..nnnnnnnn',
  'bbbbbb...     ..nnnnnnnn',
  'bbbbbb.............nnnnn',
  'bbbbbb.................',
  ' .......aaaaaaaa........',
  '........aaaaaaaa..kkkkk',
  ' cccc...aaaaaaaa..kkkkkk',
  'cccccc..aaaaaaaa..kkkkkk',
  'cccccc..aaaaaaaa..kkkkkk',
  'cccccc..aaaaaaaa..kkkkkk',
  'cccccc ...aaaa... kkkkkk',
  '         .    .         ',
]

const ROOM_KEY_MAP = {
  's': 'Study', 'h': 'Hall', 'o': 'Lounge',
  'l': 'Library', 'b': 'Billiard Room', 'n': 'Dining Room',
  'c': 'Conservatory', 'a': 'Ballroom', 'k': 'Kitchen',
}

const DOORS = {
  '3,6': 'Study', '6,11': 'Hall', '6,12': 'Hall', '4,9': 'Hall',
  '5,17': 'Lounge', '8,6': 'Library', '10,3': 'Library',
  '12,1': 'Billiard Room', '15,5': 'Billiard Room',
  '12,16': 'Dining Room', '9,17': 'Dining Room',
  '19,4': 'Conservatory',
  '17,9': 'Ballroom', '17,14': 'Ballroom', '19,8': 'Ballroom', '19,15': 'Ballroom',
  '18,19': 'Kitchen',
}

const STARTS = {
  '24,9': 'Scarlet', '7,23': 'Mustard', '24,14': 'White',
  '0,16': 'Green', '5,0': 'Plum', '18,0': 'Peacock',
}

const ROOM_COLORS = {
  'Study':           '#1e3d5c',
  'Hall':            '#2d4a5a',
  'Lounge':          '#5c1e2e',
  'Library':         '#1e4d4d',
  'Billiard Room':   '#1e4d2d',
  'Dining Room':     '#5a4a1e',
  'Conservatory':    '#3d4d1e',
  'Ballroom':        '#3d1e4d',
  'Kitchen':         '#5a3a1e',
}

const CHARACTER_COLORS = {
  'Miss Scarlett':    { bg: '#e74c3c', text: '#fff' },
  'Colonel Mustard':  { bg: '#f39c12', text: '#1a1a2e' },
  'Mrs. White':       { bg: '#ecf0f1', text: '#1a1a2e' },
  'Reverend Green':   { bg: '#27ae60', text: '#fff' },
  'Mrs. Peacock':     { bg: '#2980b9', text: '#fff' },
  'Professor Plum':   { bg: '#8e44ad', text: '#fff' },
}

const CHARACTER_ABBR = {
  'Miss Scarlett': 'Sc', 'Colonel Mustard': 'Mu', 'Mrs. White': 'Wh',
  'Reverend Green': 'Gr', 'Mrs. Peacock': 'Pe', 'Professor Plum': 'Pl',
}

// ── Pre-compute room info from board layout ──

const ROOM_INFO = {}
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || '').padEnd(24)
  for (let c = 0; c < 24; c++) {
    const room = ROOM_KEY_MAP[line[c]]
    if (room) {
      if (!ROOM_INFO[room]) {
        ROOM_INFO[room] = { name: room, minRow: r, maxRow: r, minCol: c, maxCol: c }
      } else {
        ROOM_INFO[room].minRow = Math.min(ROOM_INFO[room].minRow, r)
        ROOM_INFO[room].maxRow = Math.max(ROOM_INFO[room].maxRow, r)
        ROOM_INFO[room].minCol = Math.min(ROOM_INFO[room].minCol, c)
        ROOM_INFO[room].maxCol = Math.max(ROOM_INFO[room].maxCol, c)
      }
    }
  }
}
for (const room of Object.values(ROOM_INFO)) {
  room.centerRow = (room.minRow + room.maxRow) / 2
  room.centerCol = (room.minCol + room.maxCol) / 2
}

// ── Build flat cell array (25 rows x 24 cols = 600 cells) ──

const CELL_DATA = []
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || '').padEnd(24)
  for (let c = 0; c < 24; c++) {
    const key = `${r},${c}`
    const ch = line[c]
    const doorRoom = DOORS[key]
    const startChar = STARTS[key]

    if (doorRoom) {
      CELL_DATA.push({ row: r, col: c, type: 'door', room: doorRoom })
    } else if (ROOM_KEY_MAP[ch]) {
      CELL_DATA.push({ row: r, col: c, type: 'room', room: ROOM_KEY_MAP[ch] })
    } else if (ch === '.') {
      CELL_DATA.push({ row: r, col: c, type: startChar ? 'start' : 'hallway', room: null, startChar })
    } else {
      CELL_DATA.push({ row: r, col: c, type: 'wall', room: null })
    }
  }
}

// ── Component ──

const props = defineProps({
  gameState: Object,
  playerId: String,
  selectedRoom: String,
  selectable: Boolean,
})

const emit = defineEmits(['select-room'])

const cells = CELL_DATA

const currentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const roomLabels = computed(() => Object.values(ROOM_INFO))

const secretPassages = [
  { from: 'Study', to: 'Kitchen', row: ROOM_INFO['Study'].maxRow - 0.5, col: ROOM_INFO['Study'].maxCol - 1 },
  { from: 'Kitchen', to: 'Study', row: ROOM_INFO['Kitchen'].minRow + 0.5, col: ROOM_INFO['Kitchen'].minCol + 1 },
  { from: 'Lounge', to: 'Conservatory', row: ROOM_INFO['Lounge'].maxRow - 0.5, col: ROOM_INFO['Lounge'].minCol + 1 },
  { from: 'Conservatory', to: 'Lounge', row: ROOM_INFO['Conservatory'].minRow + 0.5, col: ROOM_INFO['Conservatory'].maxCol - 1 },
]

const playerTokens = computed(() => {
  const players = props.gameState?.players ?? []
  const roomMap = props.gameState?.current_room ?? {}
  const posMap = props.gameState?.player_positions ?? {}
  const tokens = []

  // Group players by room
  const byRoom = {}
  const hallway = []
  for (const p of players) {
    const room = roomMap[p.id]
    if (room && ROOM_INFO[room]) {
      if (!byRoom[room]) byRoom[room] = []
      byRoom[room].push(p)
    } else if (posMap[p.id]) {
      hallway.push(p)
    }
  }

  // Distribute players within each room
  for (const [roomName, rPlayers] of Object.entries(byRoom)) {
    const info = ROOM_INFO[roomName]
    const cR = info.centerRow + 0.8
    const cC = info.centerCol + 0.5
    const n = rPlayers.length
    const roomW = info.maxCol - info.minCol + 1
    const spacing = Math.min(1.8, Math.max(1.2, (roomW - 2) / Math.max(1, n - 1)))
    const startC = cC - (spacing * (n - 1)) / 2
    for (let i = 0; i < n; i++) {
      tokens.push({ ...rPlayers[i], row: cR, col: startC + i * spacing })
    }
  }

  // Hallway players at exact position
  for (const p of hallway) {
    const pos = posMap[p.id]
    tokens.push({ ...p, row: pos[0] + 0.5, col: pos[1] + 0.5 })
  }

  return tokens
})

function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

function cellClasses(cell) {
  const cls = ['cell', `cell-${cell.type}`]
  if (cell.room) {
    if (props.selectable) cls.push('clickable')
    if (props.selectedRoom === cell.room) cls.push('selected')
    if (currentRoom.value === cell.room) cls.push('my-room')
  }
  return cls
}

function cellStyle(cell) {
  if (cell.room && ROOM_COLORS[cell.room]) {
    return { backgroundColor: ROOM_COLORS[cell.room] }
  }
  return {}
}

function handleCellClick(cell) {
  if (props.selectable && cell.room) {
    emit('select-room', cell.room)
  }
}

function overlayPos(row, col) {
  return {
    left: `${((col + 0.5) / 24) * 100}%`,
    top: `${((row + 0.5) / 25) * 100}%`,
    transform: 'translate(-50%, -50%)',
  }
}

function tokenStyle(token) {
  const colors = CHARACTER_COLORS[token.character] ?? { bg: '#666', text: '#fff' }
  return {
    left: `${((token.col) / 24) * 100}%`,
    top: `${((token.row) / 25) * 100}%`,
    transform: 'translate(-50%, -50%)',
    backgroundColor: colors.bg,
    color: colors.text,
  }
}
</script>

<style scoped>
.board-map {
  user-select: none;
}

.board-container {
  position: relative;
  width: 100%;
  max-width: 576px;
  margin: 0 auto;
  aspect-ratio: 24 / 25;
  background: #0d1117;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid #2c3e50;
}

/* ── Grid ── */
.board-grid {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  grid-template-rows: repeat(25, 1fr);
  width: 100%;
  height: 100%;
  gap: 0;
  background: #0d1117;
  /* Draw 1px grid lines without affecting layout, so overlay % math stays aligned */
  background-image:
    linear-gradient(to right, #020409 1px, transparent 1px),
    linear-gradient(to bottom, #020409 1px, transparent 1px);
  background-size:
    calc(100% / 24) 100%,
    100% calc(100% / 25);
}

/* ── Cell types ── */
.cell {
  min-width: 0;
  min-height: 0;
}

.cell-room {
  border: 0.5px solid rgba(255, 255, 255, 0.04);
}

.cell-door {
  filter: brightness(1.4);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
}

.cell-hallway {
  background: #2a2a3e;
  border: 0.5px solid rgba(255, 255, 255, 0.03);
}

.cell-start {
  background: #2a2a3e;
  border: 0.5px solid rgba(255, 255, 255, 0.03);
  position: relative;
}

.cell-start::after {
  content: '';
  position: absolute;
  inset: 30%;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
}

.cell-wall {
  background: transparent;
}

/* ── Interactive states ── */
.cell.clickable {
  cursor: pointer;
}

.cell.clickable:hover {
  filter: brightness(1.3);
  outline: 1px solid rgba(201, 168, 76, 0.5);
  z-index: 1;
}

.cell.selected {
  filter: brightness(1.4);
  outline: 1px solid rgba(201, 168, 76, 0.8);
  z-index: 1;
}

.cell.my-room {
  box-shadow: inset 0 0 0 1px rgba(241, 196, 15, 0.3);
}

/* ── Overlay ── */
.board-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

/* ── Room labels ── */
.room-label {
  position: absolute;
  color: #c9a84c;
  font-size: clamp(7px, 1.2vw, 11px);
  font-weight: bold;
  white-space: nowrap;
  text-align: center;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
  letter-spacing: 0.03em;
}

/* ── Center label ── */
.center-label {
  position: absolute;
  color: #c9a84c;
  font-size: clamp(12px, 2.5vw, 22px);
  font-weight: bold;
  letter-spacing: 0.3em;
  text-shadow: 0 0 12px rgba(201, 168, 76, 0.5);
}

/* ── Secret passage ── */
.secret-passage {
  position: absolute;
  color: #e67e22;
  font-size: clamp(5px, 0.9vw, 8px);
  font-style: italic;
  white-space: nowrap;
  opacity: 0.85;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}

/* ── Player tokens ── */
.player-token {
  position: absolute;
  width: clamp(14px, 2.5vw, 22px);
  height: clamp(14px, 2.5vw, 22px);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(6px, 1vw, 9px);
  font-weight: bold;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6), 0 0 0 1.5px rgba(0, 0, 0, 0.3);
  z-index: 10;
  transition: left 0.4s ease, top 0.4s ease;
}

.player-token.my-token {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6), 0 0 0 2px rgba(241, 196, 15, 0.7);
  z-index: 11;
}
</style>
