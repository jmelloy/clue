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
          :data-door-dir="cell.doorDir"
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
        >&#x21C9; {{ sp.to }}</div>
        <!-- Player tokens -->
        <div
          v-for="token in playerTokens"
          :key="'tk-' + token.id"
          class="player-token"
          :class="{ 'my-token': token.id === playerId, 'wanderer-token': token.type === 'wanderer', 'is-turn': token.id === gameState?.whose_turn }"
          :style="tokenStyle(token)"
          :title="token.type === 'wanderer' ? `${token.character} (wandering)` : `${token.name} (${token.character})`"
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

// Fallback door/start data (used when boardData prop is not available)
const DEFAULT_DOORS = {
  '3,6': { room: 'Study', direction: 'south' },
  '6,11': { room: 'Hall', direction: 'south' },
  '6,12': { room: 'Hall', direction: 'south' },
  '4,9': { room: 'Hall', direction: 'west' },
  '5,17': { room: 'Lounge', direction: 'south' },
  '8,6': { room: 'Library', direction: 'east' },
  '10,3': { room: 'Library', direction: 'south' },
  '12,1': { room: 'Billiard Room', direction: 'north' },
  '15,5': { room: 'Billiard Room', direction: 'east' },
  '12,16': { room: 'Dining Room', direction: 'west' },
  '9,17': { room: 'Dining Room', direction: 'north' },
  '19,4': { room: 'Conservatory', direction: 'north' },
  '17,9': { room: 'Ballroom', direction: 'north' },
  '17,14': { room: 'Ballroom', direction: 'north' },
  '19,8': { room: 'Ballroom', direction: 'west' },
  '19,15': { room: 'Ballroom', direction: 'east' },
  '18,19': { room: 'Kitchen', direction: 'north' },
}

const DEFAULT_STARTS = {
  '24,9': 'Scarlet', '7,23': 'Mustard', '24,14': 'White',
  '0,16': 'Green', '5,0': 'Plum', '18,0': 'Peacock',
}

const ROOM_COLORS = {
  'Study':           '#5c3a1e',
  'Hall':            '#c4a265',
  'Lounge':          '#8b3a3a',
  'Library':         '#3a6b4a',
  'Billiard Room':   '#2d6b4a',
  'Dining Room':     '#b8726b',
  'Conservatory':    '#5a8a5a',
  'Ballroom':        '#7a8aaa',
  'Kitchen':         '#c4a870',
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

// ── Component ──

const props = defineProps({
  gameState: Object,
  playerId: String,
  selectedRoom: String,
  selectable: Boolean,
  reachableRooms: { type: Array, default: () => [] },
  reachablePositions: { type: Array, default: () => [] },
  boardData: { type: Object, default: null },
})

const emit = defineEmits(['select-room', 'select-position'])

// Use backend board data when available, fall back to hardcoded defaults
const doors = computed(() => props.boardData?.doors ?? DEFAULT_DOORS)
const starts = computed(() => props.boardData?.starts ?? DEFAULT_STARTS)

// ── Build flat cell array (25 rows x 24 cols = 600 cells) ──

const cells = computed(() => {
  const d = doors.value
  const s = starts.value
  const result = []
  for (let r = 0; r < 25; r++) {
    const line = (BOARD_ROWS[r] || '').padEnd(24)
    for (let c = 0; c < 24; c++) {
      const key = `${r},${c}`
      const ch = line[c]
      const doorInfo = d[key]
      const startChar = s[key]

      if (doorInfo) {
        result.push({ row: r, col: c, type: 'door', room: doorInfo.room, doorDir: doorInfo.direction })
      } else if (ROOM_KEY_MAP[ch]) {
        result.push({ row: r, col: c, type: 'room', room: ROOM_KEY_MAP[ch] })
      } else if (ch === '.') {
        result.push({ row: r, col: c, type: startChar ? 'start' : 'hallway', room: null, startChar })
      } else {
        result.push({ row: r, col: c, type: 'wall', room: null })
      }
    }
  }
  return result
})

const currentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const reachablePositionSet = computed(() => {
  const set = new Set()
  for (const pos of props.reachablePositions) {
    set.add(`${pos[0]},${pos[1]}`)
  }
  return set
})

const hasReachableData = computed(() => props.reachableRooms.length > 0 || props.reachablePositions.length > 0)

const roomLabels = computed(() => Object.values(ROOM_INFO))

const secretPassages = [
  { from: 'Study', to: 'Kitchen', row: ROOM_INFO['Study'].minRow + 0.8, col: ROOM_INFO['Study'].minCol + 1.5 },
  { from: 'Kitchen', to: 'Study', row: ROOM_INFO['Kitchen'].maxRow - 0.3, col: ROOM_INFO['Kitchen'].maxCol - 1.5 },
  { from: 'Lounge', to: 'Conservatory', row: ROOM_INFO['Lounge'].minRow + 0.8, col: ROOM_INFO['Lounge'].maxCol - 1.5 },
  { from: 'Conservatory', to: 'Lounge', row: ROOM_INFO['Conservatory'].maxRow - 0.3, col: ROOM_INFO['Conservatory'].minCol + 1.5 },
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
    // Highlight reachable/unreachable rooms when selectable
    if (props.selectable && hasReachableData.value) {
      if (props.reachableRooms.includes(cell.room)) {
        cls.push('reachable')
      } else {
        cls.push('unreachable')
      }
    }
  } else if ((cell.type === 'hallway' || cell.type === 'start') && props.selectable) {
    cls.push('clickable')
    // Highlight reachable hallway positions
    if (hasReachableData.value) {
      const key = `${cell.row},${cell.col}`
      if (reachablePositionSet.value.has(key)) {
        cls.push('reachable')
      }
    }
  } else if (cell.type === 'door' && props.selectable && hasReachableData.value) {
    // Highlight doors of reachable rooms
    if (props.reachableRooms.includes(cell.room)) {
      cls.push('reachable-door')
    }
  }
  return cls
}

function cellStyle(_cell) {
  // Cells are transparent — the board background image provides the visuals
  return {}
}

function handleCellClick(cell) {
  if (!props.selectable) return
  if (cell.room) {
    emit('select-room', cell.room)
  } else if (cell.type === 'hallway' || cell.type === 'start') {
    emit('select-position', [cell.row, cell.col])
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
  const style = {
    left: `${((token.col) / 24) * 100}%`,
    top: `${((token.row) / 25) * 100}%`,
    transform: 'translate(-50%, -50%)',
    backgroundColor: colors.bg,
    color: colors.text,
  }
  if (token.type === 'wanderer') {
    style.opacity = 0.5
  }
  return style
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
  background: #1a4a2a;
  border-radius: 4px;
  overflow: hidden;
  border: 4px solid #2a1a0a;
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.3), 0 4px 12px rgba(0, 0, 0, 0.5);
}

/* ── Grid ── */
.board-grid {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  grid-template-rows: repeat(25, 1fr);
  width: 100%;
  height: 100%;
  gap: 0;
  background: #1a4a2a;
  /* Classic Clue board background image */
  background-image: url('/assets/board.jpg');
  background-size: 114% 112%;
  background-position: 49% 44%;
  background-repeat: no-repeat;
}

/* ── Cell types ── */
.cell {
  min-width: 0;
  min-height: 0;
}

.cell-room {
  background: transparent;
  border: none;
}

.cell-door {
  position: relative;
  background: transparent;
  border: none;
  overflow: visible;
}

/* Door direction indicators — hidden when using board image */
.cell-door[data-door-dir]::after {
  display: none;
}

.cell-hallway {
  background: transparent;
  border: none;
}

.cell-start {
  background: transparent;
  border: none;
  position: relative;
}

.cell-start::after {
  display: none;
}

.cell-wall {
  background: transparent;
}

/* ── Interactive states ── */
.cell.clickable {
  cursor: pointer;
}

.cell.clickable:hover {
  background: rgba(255, 255, 200, 0.25);
  outline: 2px solid rgba(255, 255, 200, 0.6);
  z-index: 1;
}

.cell.selected {
  background: rgba(255, 255, 200, 0.35);
  outline: 2px solid rgba(255, 255, 200, 0.8);
  z-index: 1;
}

.cell.my-room {
  background: rgba(255, 255, 200, 0.15);
}

/* ── Reachable highlights ── */
.cell.reachable {
  outline: 1px solid rgba(46, 204, 113, 0.6);
  z-index: 1;
  animation: reachable-glow 2s ease-in-out infinite;
}

.cell-room.reachable {
  background: rgba(46, 204, 113, 0.2);
}

.cell-hallway.reachable,
.cell-start.reachable {
  background: rgba(46, 204, 113, 0.25);
}

.cell.unreachable {
  background: rgba(0, 0, 0, 0.3);
}

.cell-door.unreachable {
  background: rgba(0, 0, 0, 0.15);
}

.cell.reachable-door {
  background: rgba(46, 204, 113, 0.3);
  outline: 1px solid rgba(46, 204, 113, 0.8);
  z-index: 2;
  animation: reachable-glow 2s ease-in-out infinite;
}

@keyframes reachable-glow {
  0%, 100% { box-shadow: inset 0 0 0 0 rgba(46, 204, 113, 0); }
  50% { box-shadow: inset 0 0 4px 1px rgba(46, 204, 113, 0.3); }
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

/* ── Room labels (hidden — board image provides them) ── */
.room-label {
  display: none;
}

/* ── Center label (hidden — board image provides it) ── */
.center-label {
  display: none;
}

/* ── Secret passage (hidden — board image shows them) ── */
.secret-passage {
  display: none;
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

.player-token.wanderer-token {
  border: 1.5px dashed rgba(255, 255, 255, 0.4);
  z-index: 9;
}

.player-token.is-turn {
  animation: token-pulse 2s ease-in-out infinite;
}

@keyframes token-pulse {
  0%, 100% {
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6), 0 0 0 1.5px rgba(241, 196, 15, 0.7);
  }
  50% {
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6), 0 0 8px 3px rgba(241, 196, 15, 0.6);
  }
}
</style>
