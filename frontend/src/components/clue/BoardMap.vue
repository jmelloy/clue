<template>
  <div class="board-map">
    <div class="board-container" :class="{ 'vintage-board': theme === 'vintage' }">
      <!-- Background grid of 25x24 cells -->
      <div class="board-grid">
        <div v-for="(cell, i) in cells" :key="i" :class="cellClasses(cell)" :style="cellStyle(cell)"
          :data-door-dir="cell.doorDir" @click="handleCellClick(cell)"></div>
      </div>
      <!-- Overlay: labels, passages, player tokens -->
      <div class="board-overlay">
        <!-- Room name labels -->
        <div v-for="room in roomLabels" :key="'lbl-' + room.name" class="room-label"
          :style="overlayPos(room.centerRow, room.centerCol)">
          {{ room.name }}
        </div>
        <!-- Center magnifying glass + CLUE label -->
        <div class="center-emblem" :style="overlayPos(11, 11)">
          <img src="/images/clue/magnifying-glass.jpg" alt="Clue" class="center-magnifying-glass" />
          <div class="center-label">CLUE</div>
        </div>
        <!-- Secret passage indicators -->
        <div v-for="sp in secretPassages" :key="'sp-' + sp.from" class="secret-passage"
          :style="overlayPos(sp.row, sp.col)" :title="'Secret passage to ' + sp.to">
          &#x21C9; {{ sp.to }}
        </div>
        <!-- Player tokens -->
        <div v-for="token in playerTokens" :key="'tk-' + token.id" class="player-token" :class="{
          'my-token': token.id === playerId,
          'wanderer-token': token.type === 'wanderer',
          'weapon-token': token.isWeapon,
          'is-turn': token.id === gameState?.whose_turn,
          'has-image': !token.isWeapon && !!CARD_IMAGES[token.character]
        }" :style="tokenStyle(token)">
          <span v-if="token.isWeapon" class="weapon-emoji" :title="token.name">{{ CARD_ICONS[token.name] || token.name.charAt(0) }}</span>
          <img v-else-if="CARD_IMAGES[token.character]" :src="CARD_IMAGES[token.character]" :alt="token.character"
            :title="token.name === token.character ? token.character : `${token.name} (${token.character})`"
            class="token-portrait" />
          <span v-else>{{ abbr(token.character) }}</span>
          <span class="token-tooltip">{{ token.isWeapon ? token.name : (token.name === token.character ? token.character : `${token.name} (${token.character})`) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CARD_IMAGES, CARD_ICONS, THEME_CARD_IMAGES, WEAPONS, abbr, characterColors } from '../../constants/clue'
import { useTheme } from '../../composables/useTheme'

const { theme } = useTheme()


// ── Board layout data (matches backend board.py) ──

const BOARD_ROWS = [
  'ssssss . hhhhhh . oooooo',
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
  '         .    .         '
]

const ROOM_KEY_MAP = {
  s: 'Study',
  h: 'Hall',
  o: 'Lounge',
  l: 'Library',
  b: 'Billiard Room',
  n: 'Dining Room',
  c: 'Conservatory',
  a: 'Ballroom',
  k: 'Kitchen'
}

const DOORS = {
  '3,6': 'Study',
  '6,11': 'Hall',
  '6,12': 'Hall',
  '4,9': 'Hall',
  '5,17': 'Lounge',
  '8,6': 'Library',
  '10,3': 'Library',
  '12,1': 'Billiard Room',
  '15,5': 'Billiard Room',
  '12,16': 'Dining Room',
  '9,17': 'Dining Room',
  '19,4': 'Conservatory',
  '17,9': 'Ballroom',
  '17,14': 'Ballroom',
  '19,8': 'Ballroom',
  '19,15': 'Ballroom',
  '18,19': 'Kitchen'
}

const DOOR_DIRECTIONS = {
  '3,6': 'south',
  '4,9': 'west',
  '6,11': 'south',
  '6,12': 'south',
  '5,17': 'south',
  '8,6': 'east',
  '10,3': 'south',
  '12,1': 'north',
  '15,5': 'east',
  '12,16': 'west',
  '9,17': 'north',
  '19,4': 'east',
  '17,9': 'north',
  '17,14': 'north',
  '19,8': 'west',
  '19,15': 'east',
  '18,19': 'north'
}

const STARTS = {
  '0,16': 'Scarlet',
  '7,23': 'Mustard',
  '24,14': 'White',
  '24,9': 'Green',
  '5,0': 'Plum',
  '18,0': 'Peacock'
}

const ROOM_COLORS = {
  Study: '#2a2218',
  Hall: '#2a2218',
  Lounge: '#2a2218',
  Library: '#2a2218',
  'Billiard Room': '#2a2218',
  'Dining Room': '#2a2218',
  Conservatory: '#2a2218',
  Ballroom: '#2a2218',
  Kitchen: '#2a2218'
}

// ── Pre-compute room info from board layout ──

const ROOM_INFO = {}
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || '').padEnd(24)
  for (let c = 0; c < 24; c++) {
    const room = ROOM_KEY_MAP[line[c]]
    if (room) {
      if (!ROOM_INFO[room]) {
        ROOM_INFO[room] = {
          name: room,
          minRow: r,
          maxRow: r,
          minCol: c,
          maxCol: c
        }
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

// First pass: determine cell types and room membership in 2D grids
const GRID_TYPES = []
const GRID_ROOMS = []
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || '').padEnd(24)
  const typeRow = []
  const roomRow = []
  for (let c = 0; c < 24; c++) {
    const key = `${r},${c}`
    const ch = line[c]
    const isCenter = r >= 8 && r <= 15 && c >= 9 && c <= 14
    if (DOORS[key] || ROOM_KEY_MAP[ch] || ch === '.' || isCenter) {
      typeRow.push('usable')
    } else {
      typeRow.push('wall')
    }
    // Track which room each cell belongs to (doors count as their room)
    roomRow.push(DOORS[key] || ROOM_KEY_MAP[ch] || null)
  }
  GRID_TYPES.push(typeRow)
  GRID_ROOMS.push(roomRow)
}

function isWallOrEdge(r, c) {
  if (r < 0 || r >= 25 || c < 0 || c >= 24) return true
  return GRID_TYPES[r][c] === 'wall'
}

function roomAt(r, c) {
  if (r < 0 || r >= 25 || c < 0 || c >= 24) return null
  return GRID_ROOMS[r][c]
}

const CELL_DATA = []
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || '').padEnd(24)
  for (let c = 0; c < 24; c++) {
    const key = `${r},${c}`
    const ch = line[c]
    const doorRoom = DOORS[key]
    const startChar = STARTS[key]

    // Compute exposed edges for usable cells
    const edges = {
      top: isWallOrEdge(r - 1, c),
      right: isWallOrEdge(r, c + 1),
      bottom: isWallOrEdge(r + 1, c),
      left: isWallOrEdge(r, c - 1)
    }

    // Compute room boundary edges (where this cell's room differs from neighbor)
    const cellRoom = GRID_ROOMS[r][c]
    const roomEdges = cellRoom ? {
      top: roomAt(r - 1, c) !== cellRoom,
      right: roomAt(r, c + 1) !== cellRoom,
      bottom: roomAt(r + 1, c) !== cellRoom,
      left: roomAt(r, c - 1) !== cellRoom
    } : null

    if (doorRoom) {
      CELL_DATA.push({
        row: r,
        col: c,
        type: 'door',
        room: doorRoom,
        doorDir: DOOR_DIRECTIONS[key],
        edges,
        roomEdges
      })
    } else if (ROOM_KEY_MAP[ch]) {
      CELL_DATA.push({ row: r, col: c, type: 'room', room: ROOM_KEY_MAP[ch], edges, roomEdges })
    } else if (ch === '.') {
      CELL_DATA.push({
        row: r,
        col: c,
        type: startChar ? 'start' : 'hallway',
        room: null,
        startChar,
        edges
      })
    } else {
      const isCenter = r >= 8 && r <= 15 && c >= 9 && c <= 14
      // Garden cells: non-center walls near usable cells (direct or diagonal neighbors)
      let gardenRing = 0
      if (!isCenter) {
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            if (dr === 0 && dc === 0) continue
            if (!isWallOrEdge(r + dr, c + dc)) { gardenRing = 1; break }
          }
          if (gardenRing) break
        }
        // Second ring: within 2 cells of usable space
        if (!gardenRing) {
          outer: for (let dr = -2; dr <= 2; dr++) {
            for (let dc = -2; dc <= 2; dc++) {
              if (dr === 0 && dc === 0) continue
              if (!isWallOrEdge(r + dr, c + dc)) { gardenRing = 2; break outer }
            }
          }
        }
      }
      CELL_DATA.push({ row: r, col: c, type: 'wall', room: null, isCenter, gardenRing, edges })
    }
  }
}

// ── Component ──

const props = defineProps({
  gameState: Object,
  playerId: String,
  selectedRoom: String,
  selectable: Boolean,
  reachableRooms: { type: Array, default: () => [] },
  reachablePositions: { type: Array, default: () => [] }
})

const emit = defineEmits(['select-room', 'select-position'])

const cells = CELL_DATA

const currentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const reachablePositionSet = computed(() => {
  const set = new Set()
  for (const pos of props.reachablePositions) {
    set.add(`${pos[0]},${pos[1]}`)
  }
  return set
})

const hasReachableData = computed(
  () => props.reachableRooms.length > 0 || props.reachablePositions.length > 0
)

const roomLabels = computed(() => Object.values(ROOM_INFO))

const secretPassages = [
  {
    from: 'Study',
    to: 'Kitchen',
    row: ROOM_INFO['Study'].minRow + 0.8,
    col: ROOM_INFO['Study'].minCol + 1.5
  },
  {
    from: 'Kitchen',
    to: 'Study',
    row: ROOM_INFO['Kitchen'].maxRow - 0.3,
    col: ROOM_INFO['Kitchen'].maxCol - 1.5
  },
  {
    from: 'Lounge',
    to: 'Conservatory',
    row: ROOM_INFO['Lounge'].minRow + 0.8,
    col: ROOM_INFO['Lounge'].maxCol - 1.5
  },
  {
    from: 'Conservatory',
    to: 'Lounge',
    row: ROOM_INFO['Conservatory'].maxRow - 0.3,
    col: ROOM_INFO['Conservatory'].minCol + 1.5
  }
]

// Get the active suggestion (last suggestion this turn, if any)
const activeSuggestion = computed(() => {
  const suggestions = props.gameState?.suggestions_this_turn ?? []
  return suggestions.length > 0 ? suggestions[suggestions.length - 1] : null
})

const playerTokens = computed(() => {
  const players = props.gameState?.players ?? []
  const roomMap = props.gameState?.current_room ?? {}
  const posMap = props.gameState?.player_positions ?? {}
  const weaponPos = props.gameState?.weapon_positions ?? {}
  const suggestion = activeSuggestion.value
  const tokens = []

  // Build weapon items for rooms
  const weaponsByRoom = {}
  for (const [weapon, room] of Object.entries(weaponPos)) {
    if (ROOM_INFO[room]) {
      if (!weaponsByRoom[room]) weaponsByRoom[room] = []
      weaponsByRoom[room].push(weapon)
    }
  }

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

  // Get all rooms that have players or weapons
  const allRooms = new Set([...Object.keys(byRoom), ...Object.keys(weaponsByRoom)])

  // Distribute players and weapons within each room
  for (const roomName of allRooms) {
    const info = ROOM_INFO[roomName]
    const rPlayers = byRoom[roomName] || []
    const rWeapons = weaponsByRoom[roomName] || []
    const cR = info.centerRow
    const cC = info.centerCol + 0.5
    const roomW = info.maxCol - info.minCol + 1
    const roomH = info.maxRow - info.minRow + 1

    // Check if this room has an active suggestion
    const isSuggestionRoom = suggestion && suggestion.room === roomName

    if (isSuggestionRoom) {
      // Separate suspects (character + weapon in suggestion) from bystanders
      const suspectedPlayers = []
      const bystanderPlayers = []
      const suspectedWeapons = []
      const bystanderWeapons = []

      for (const p of rPlayers) {
        if (p.character === suggestion.suspect) {
          suspectedPlayers.push(p)
        } else {
          bystanderPlayers.push(p)
        }
      }
      for (const w of rWeapons) {
        if (w === suggestion.weapon) {
          suspectedWeapons.push(w)
        } else {
          bystanderWeapons.push(w)
        }
      }

      // Center row for suspects (middle of room)
      const centerItems = [...suspectedPlayers.map(p => ({ kind: 'player', data: p })),
                           ...suspectedWeapons.map(w => ({ kind: 'weapon', data: w }))]
      const nCenter = centerItems.length
      const centerSpacing = Math.min(1.8, Math.max(1.2, (roomW - 2) / Math.max(1, nCenter - 1)))
      const centerStartC = cC - (centerSpacing * (nCenter - 1)) / 2
      for (let i = 0; i < nCenter; i++) {
        const item = centerItems[i]
        if (item.kind === 'player') {
          tokens.push({ ...item.data, row: cR + 0.8, col: centerStartC + i * centerSpacing })
        } else {
          tokens.push({
            id: `weapon-${item.data}`,
            name: item.data,
            character: item.data,
            type: 'weapon',
            isWeapon: true,
            row: cR + 0.8,
            col: centerStartC + i * centerSpacing
          })
        }
      }

      // Bystanders pushed to top edge of room
      const bystanders = [...bystanderPlayers.map(p => ({ kind: 'player', data: p })),
                          ...bystanderWeapons.map(w => ({ kind: 'weapon', data: w }))]
      const nBy = bystanders.length
      if (nBy > 0) {
        const byRow = info.minRow + 1.0
        const bySpacing = Math.min(1.6, Math.max(1.0, (roomW - 2) / Math.max(1, nBy - 1)))
        const byStartC = cC - (bySpacing * (nBy - 1)) / 2
        for (let i = 0; i < nBy; i++) {
          const item = bystanders[i]
          if (item.kind === 'player') {
            tokens.push({ ...item.data, row: byRow, col: byStartC + i * bySpacing })
          } else {
            tokens.push({
              id: `weapon-${item.data}`,
              name: item.data,
              character: item.data,
              type: 'weapon',
              isWeapon: true,
              row: byRow,
              col: byStartC + i * bySpacing
            })
          }
        }
      }
    } else {
      // No active suggestion: players in center row, weapons below
      const n = rPlayers.length
      const spacing = Math.min(1.8, Math.max(1.2, (roomW - 2) / Math.max(1, n - 1)))
      const startC = cC - (spacing * (n - 1)) / 2
      for (let i = 0; i < n; i++) {
        tokens.push({ ...rPlayers[i], row: cR + 0.8, col: startC + i * spacing })
      }

      // Weapons on a row below players
      const nW = rWeapons.length
      if (nW > 0) {
        const wRow = cR + (n > 0 ? 2.0 : 0.8)
        const wSpacing = Math.min(1.5, Math.max(0.9, (roomW - 2) / Math.max(1, nW - 1)))
        const wStartC = cC - (wSpacing * (nW - 1)) / 2
        for (let i = 0; i < nW; i++) {
          tokens.push({
            id: `weapon-${rWeapons[i]}`,
            name: rWeapons[i],
            character: rWeapons[i],
            type: 'weapon',
            isWeapon: true,
            row: wRow,
            col: wStartC + i * wSpacing
          })
        }
      }
    }
  }

  // Hallway players at exact position
  for (const p of hallway) {
    const pos = posMap[p.id]
    tokens.push({ ...p, row: pos[0] + 0.5, col: pos[1] + 0.5 })
  }

  return tokens
})

function cellClasses(cell) {
  const cls = ['cell', `cell-${cell.type}`]
  if (cell.isCenter) cls.push('cell-center')
  if (cell.gardenRing === 1) cls.push('cell-garden')
  else if (cell.gardenRing === 2) cls.push('cell-garden-far')
  if (cell.startChar) cls.push('cell-start-' + cell.startChar.toLowerCase())
  // Add edge classes for mansion border (usable cells + center)
  if ((cell.type !== 'wall' || cell.isCenter) && cell.edges) {
    if (cell.edges.top) cls.push('edge-top')
    if (cell.edges.right) cls.push('edge-right')
    if (cell.edges.bottom) cls.push('edge-bottom')
    if (cell.edges.left) cls.push('edge-left')
  }
  // Room boundary edges (gold wall inset)
  if (cell.roomEdges) {
    if (cell.roomEdges.top) cls.push('room-edge-top')
    if (cell.roomEdges.right) cls.push('room-edge-right')
    if (cell.roomEdges.bottom) cls.push('room-edge-bottom')
    if (cell.roomEdges.left) cls.push('room-edge-left')
  }
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

function cellStyle(cell) {
  if (cell.room) {
    // Vintage theme: room artwork is baked into the board background image
    if (theme.value === 'vintage') return {}
    const overrides = THEME_CARD_IMAGES[theme.value]
    const img = overrides?.[cell.room] || CARD_IMAGES[cell.room]
    const info = ROOM_INFO[cell.room]
    if (img && info) {
      const roomCols = info.maxCol - info.minCol + 1
      const roomRows = info.maxRow - info.minRow + 1
      const dc = cell.col - info.minCol
      const dr = cell.row - info.minRow
      const posX = roomCols > 1 ? (dc / (roomCols - 1)) * 100 : 50
      const posY = roomRows > 1 ? (dr / (roomRows - 1)) * 100 : 50
      return {
        backgroundImage: `url(${img})`,
        backgroundSize: `${roomCols * 100}% ${roomRows * 100}%`,
        backgroundPosition: `${posX}% ${posY}%`,
        backgroundColor: 'var(--board-room)'
      }
    }
    return { backgroundColor: 'var(--board-room)' }
  }
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
    transform: 'translate(-50%, -50%)'
  }
}

function tokenStyle(token) {
  if (token.isWeapon) {
    return {
      left: `${(token.col / 24) * 100}%`,
      top: `${(token.row / 25) * 100}%`,
      transform: 'translate(-50%, -50%)'
    }
  }
  const { bg, text } = characterColors(token.character)
  const style = {
    left: `${(token.col / 24) * 100}%`,
    top: `${(token.row / 25) * 100}%`,
    transform: 'translate(-50%, -50%)',
    backgroundColor: bg,
    color: text,
    '--token-border': bg
  }
  if (token.type === 'wanderer') {
    style.opacity = 0.85
  }
  return style
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Crimson+Text:wght@400;600&display=swap');

.board-map {
  user-select: none;
}

@media (max-width: 480px) {
  .board-map {
    padding: 0;
  }
}

.board-container {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  max-width: min(690px, calc(100vh - 180px));
  margin: 0 auto;
  aspect-ratio: 24 / 25;
  background: transparent;
  border-radius: 6px;
  overflow: hidden;
}

/* Vintage theme: full board image (PNG with transparent edges) as background.
   The board image is 1440x1440 (square). The playable 24x25 grid sits inside
   the decorative red border. We show the full image and position the CSS grid
   over just the playable area using inset values on .board-grid. */
.board-container.vintage-board {
  background-image: url('/images/clue/board.png');
  background-size: 100% 100%;
  background-position: center;
  background-repeat: no-repeat;
  border: none;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
  background-color: transparent;
  /* Override aspect ratio to match the square image with decorative border */
  aspect-ratio: 1 / 1;
}

/* Hide overlay labels in vintage — the board image has its own */
.board-container.vintage-board .room-label,
.board-container.vintage-board .center-emblem,
.board-container.vintage-board .secret-passage {
  display: none;
}

/* Hide door indicators in vintage — visible on the board image */
.board-container.vintage-board .cell-door::after {
  display: none;
}

/* ── Grid ── */
.board-grid {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  grid-template-rows: repeat(25, 1fr);
  position: absolute;
  inset: 0;
  gap: 0;
  z-index: 1;
  background: transparent;
}

/* In vintage mode, make the grid transparent so the board image shows through,
   and position it over just the playable area (inside the decorative border).
   Measured from the 1440x1440 board.png via pixel scanning:
   - Tile pitch: ~53.7px wide × ~51.7px tall (24 cols × 25 rows)
   - Grid origin: ~(79, 74), Grid end: ~(1369, 1367)
   - Insets tuned visually with Playwright debug overlay */
[data-theme="vintage"] .board-grid {
  background: transparent;
  background-image: none;
  top: 5.0%;
  left: 5.5%;
  right: 5.0%;
  bottom: 5.0%;
}

/* In vintage mode, the overlay also needs matching inset */
[data-theme="vintage"] .board-overlay {
  top: 5.0%;
  left: 5.5%;
  right: 5.0%;
  bottom: 5.0%;
  width: auto;
  height: auto;
}

/* ── Cell types ── */
.cell {
  min-width: 0;
  min-height: 0;
}

.cell-room {
  border: 0.5px solid rgba(255, 255, 255, 0.03);
  filter: var(--board-room-filter);
}

[data-theme="vintage"] .cell-room {
  border-color: transparent;
}

[data-theme="light"] .cell-room {
  border-color: rgba(0, 0, 0, 0.06);
}

/* ── Room boundary gold walls (inset border around each room) ── */
.room-edge-top,
.room-edge-right,
.room-edge-bottom,
.room-edge-left {
  position: relative;
}

.room-edge-top { border-top: 2px solid #c8a84e; }
.room-edge-right { border-right: 2px solid #c8a84e; }
.room-edge-bottom { border-bottom: 2px solid #c8a84e; }
.room-edge-left { border-left: 2px solid #c8a84e; }

[data-theme="light"] .room-edge-top { border-top-color: #b8963e; }
[data-theme="light"] .room-edge-right { border-right-color: #b8963e; }
[data-theme="light"] .room-edge-bottom { border-bottom-color: #b8963e; }
[data-theme="light"] .room-edge-left { border-left-color: #b8963e; }

[data-theme="vintage"] .room-edge-top,
[data-theme="vintage"] .room-edge-right,
[data-theme="vintage"] .room-edge-bottom,
[data-theme="vintage"] .room-edge-left {
  border-color: transparent;
}

.cell-door {
  position: relative;
  border: 0.5px solid rgba(255, 255, 255, 0.06);
  overflow: visible;
}

/* Door direction indicators — bright gold bar on top of room image */
.cell-door[data-door-dir]::after {
  content: '';
  position: absolute;
  background: #e8be4a;
  border-radius: 1px;
  z-index: 3;
  box-shadow: 0 0 5px rgba(232, 190, 74, 0.9), 0 0 2px rgba(255, 255, 255, 0.5);
}

.cell-door[data-door-dir='north']::after {
  top: 0;
  left: 15%;
  right: 15%;
  height: 3px;
}

.cell-door[data-door-dir='south']::after {
  bottom: 0;
  left: 15%;
  right: 15%;
  height: 3px;
}

.cell-door[data-door-dir='east']::after {
  right: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
}

.cell-door[data-door-dir='west']::after {
  left: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
}

.cell-hallway {
  background: var(--board-hallway);
  border: 0.5px solid rgba(160, 140, 100, 0.4);
}

[data-theme="vintage"] .cell-hallway {
  background: transparent;
  border-color: transparent;
}

.cell-start {
  background: var(--board-hallway);
  border: 0.5px solid rgba(160, 140, 100, 0.4);
  position: relative;
}

[data-theme="vintage"] .cell-start {
  background: transparent;
  border-color: transparent;
}

.cell-start::after {
  content: '';
  position: absolute;
  inset: 30%;
  border-radius: 50%;
  background: rgba(120, 100, 60, 0.2);
}

.cell-wall {
  background: transparent;
}

/* Garden cells — greenery/shrubs around the mansion exterior */
.cell-garden {
  background:
    radial-gradient(ellipse 80% 70% at 20% 30%, rgba(30, 70, 20, 0.5) 0%, transparent 60%),
    radial-gradient(ellipse 70% 80% at 75% 65%, rgba(25, 65, 18, 0.45) 0%, transparent 55%),
    radial-gradient(ellipse 60% 50% at 50% 15%, rgba(40, 85, 30, 0.35) 0%, transparent 50%),
    radial-gradient(ellipse 50% 60% at 85% 25%, rgba(20, 55, 15, 0.4) 0%, transparent 45%),
    radial-gradient(circle at 40% 70%, rgba(35, 80, 25, 0.3) 0%, transparent 40%);
}

.cell-garden-far {
  background:
    radial-gradient(ellipse 90% 80% at 50% 50%, rgba(25, 60, 18, 0.2) 0%, transparent 70%),
    radial-gradient(circle at 30% 40%, rgba(20, 50, 15, 0.15) 0%, transparent 50%);
}

[data-theme="light"] .cell-garden {
  background:
    radial-gradient(ellipse 80% 70% at 20% 30%, rgba(40, 100, 30, 0.3) 0%, transparent 60%),
    radial-gradient(ellipse 70% 80% at 75% 65%, rgba(35, 90, 25, 0.28) 0%, transparent 55%),
    radial-gradient(ellipse 60% 50% at 50% 15%, rgba(50, 110, 40, 0.2) 0%, transparent 50%),
    radial-gradient(ellipse 50% 60% at 85% 25%, rgba(30, 80, 22, 0.25) 0%, transparent 45%),
    radial-gradient(circle at 40% 70%, rgba(45, 105, 35, 0.18) 0%, transparent 40%);
}

[data-theme="light"] .cell-garden-far {
  background:
    radial-gradient(ellipse 90% 80% at 50% 50%, rgba(35, 85, 25, 0.12) 0%, transparent 70%),
    radial-gradient(circle at 30% 40%, rgba(30, 75, 22, 0.08) 0%, transparent 50%);
}

[data-theme="vintage"] .cell-garden,
[data-theme="vintage"] .cell-garden-far {
  background: transparent;
}

/* ── Starting position color splashes ── */
.cell-start-scarlet { background: radial-gradient(circle, rgba(192, 57, 43, 0.4) 0%, rgba(192, 57, 43, 0.15) 50%, var(--board-hallway) 85%); }
.cell-start-mustard { background: radial-gradient(circle, rgba(232, 184, 18, 0.4) 0%, rgba(232, 184, 18, 0.15) 50%, var(--board-hallway) 85%); }
.cell-start-white { background: radial-gradient(circle, rgba(220, 220, 220, 0.45) 0%, rgba(200, 200, 200, 0.15) 50%, var(--board-hallway) 85%); }
.cell-start-green { background: radial-gradient(circle, rgba(26, 158, 63, 0.4) 0%, rgba(26, 158, 63, 0.15) 50%, var(--board-hallway) 85%); }
.cell-start-peacock { background: radial-gradient(circle, rgba(26, 95, 180, 0.4) 0%, rgba(26, 95, 180, 0.15) 50%, var(--board-hallway) 85%); }
.cell-start-plum { background: radial-gradient(circle, rgba(123, 45, 142, 0.4) 0%, rgba(123, 45, 142, 0.15) 50%, var(--board-hallway) 85%); }

.cell-start-scarlet::after { background: rgba(192, 57, 43, 0.5); box-shadow: 0 0 3px rgba(192, 57, 43, 0.6); }
.cell-start-mustard::after { background: rgba(232, 184, 18, 0.5); box-shadow: 0 0 3px rgba(232, 184, 18, 0.6); }
.cell-start-white::after { background: rgba(220, 220, 220, 0.55); box-shadow: 0 0 3px rgba(200, 200, 200, 0.5); }
.cell-start-green::after { background: rgba(26, 158, 63, 0.5); box-shadow: 0 0 3px rgba(26, 158, 63, 0.6); }
.cell-start-peacock::after { background: rgba(26, 95, 180, 0.5); box-shadow: 0 0 3px rgba(26, 95, 180, 0.6); }
.cell-start-plum::after { background: rgba(123, 45, 142, 0.5); box-shadow: 0 0 3px rgba(123, 45, 142, 0.6); }

[data-theme="vintage"] .cell-start-scarlet,
[data-theme="vintage"] .cell-start-mustard,
[data-theme="vintage"] .cell-start-white,
[data-theme="vintage"] .cell-start-green,
[data-theme="vintage"] .cell-start-peacock,
[data-theme="vintage"] .cell-start-plum {
  background: transparent;
}

[data-theme="vintage"] .cell-start-scarlet::after,
[data-theme="vintage"] .cell-start-mustard::after,
[data-theme="vintage"] .cell-start-white::after,
[data-theme="vintage"] .cell-start-green::after,
[data-theme="vintage"] .cell-start-peacock::after,
[data-theme="vintage"] .cell-start-plum::after {
  background: transparent;
  box-shadow: none;
}

/* Center dead space (staircase area) */
.cell-wall.cell-center {
  background: var(--board-center);
  border: none;
}

[data-theme="vintage"] .cell-wall.cell-center {
  background: transparent;
  border-color: transparent;
}

/* ── Mansion edge borders (rendered via ::before to sit on top of room images,
      ::after is reserved for door direction indicators) ── */
.edge-top,
.edge-right,
.edge-bottom,
.edge-left {
  position: relative;
}

.edge-top::before,
.edge-right::before,
.edge-bottom::before,
.edge-left::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  border: 0 solid var(--mansion-edge);
}

.edge-top::before { border-top-width: 3px; box-shadow: 0 -4px 8px var(--mansion-glow); }
.edge-right::before { border-right-width: 3px; box-shadow: 4px 0 8px var(--mansion-glow); }
.edge-bottom::before { border-bottom-width: 3px; box-shadow: 0 4px 8px var(--mansion-glow); }
.edge-left::before { border-left-width: 3px; box-shadow: -4px 0 8px var(--mansion-glow); }

/* Corner cells — combine shadows */
.edge-top.edge-left::before { border-top-width: 3px; border-left-width: 3px; box-shadow: 0 -4px 8px var(--mansion-glow), -4px 0 8px var(--mansion-glow); }
.edge-top.edge-right::before { border-top-width: 3px; border-right-width: 3px; box-shadow: 0 -4px 8px var(--mansion-glow), 4px 0 8px var(--mansion-glow); }
.edge-bottom.edge-left::before { border-bottom-width: 3px; border-left-width: 3px; box-shadow: 0 4px 8px var(--mansion-glow), -4px 0 8px var(--mansion-glow); }
.edge-bottom.edge-right::before { border-bottom-width: 3px; border-right-width: 3px; box-shadow: 0 4px 8px var(--mansion-glow), 4px 0 8px var(--mansion-glow); }

[data-theme="vintage"] .edge-top::before,
[data-theme="vintage"] .edge-right::before,
[data-theme="vintage"] .edge-bottom::before,
[data-theme="vintage"] .edge-left::before {
  border-color: transparent;
  box-shadow: none;
}

/* ── Interactive states ── */
.cell.clickable {
  cursor: pointer;
}

.cell.clickable:hover {
  outline: 1px solid rgba(212, 168, 73, 0.4);
  z-index: 1;
}

.cell-room.clickable:hover,
.cell-door.clickable:hover {
  filter: saturate(0.45) brightness(1);
}

.cell-hallway.clickable:hover,
.cell-start.clickable:hover {
  filter: brightness(1.3);
}

.cell.selected {
  filter: saturate(0.5) brightness(1.2);
  outline: 1px solid rgba(212, 168, 73, 0.7);
  z-index: 1;
}

.cell.my-room {
  box-shadow: inset 0 0 0 1px rgba(212, 168, 73, 0.2);
}

/* ── Reachable highlights ── */
.cell.reachable {
  outline: 1px solid rgba(76, 175, 80, 0.5);
  z-index: 1;
  animation: reachable-glow 2s ease-in-out infinite;
}

.cell-room.reachable {
  filter: saturate(0.45) brightness(1.05);
}

.cell-hallway.reachable,
.cell-start.reachable {
  background: #d8cca0;
}

[data-theme="light"] .cell-hallway.reachable,
[data-theme="light"] .cell-start.reachable {
  background: rgba(76, 175, 80, 0.25);
}

[data-theme="light"] .cell-room.reachable {
  filter: saturate(0.6) brightness(0.95);
  outline-color: rgba(56, 142, 60, 0.6);
}

[data-theme="light"] .cell.reachable-door {
  outline-color: rgba(56, 142, 60, 0.8);
}

[data-theme="vintage"] .cell-hallway.reachable,
[data-theme="vintage"] .cell-start.reachable {
  background: rgba(76, 175, 80, 0.2);
}

.cell.unreachable {
  filter: saturate(0.25) brightness(0.7);
  opacity: 0.85;
}

.cell-door.unreachable {
  filter: saturate(0.25) brightness(0.7);
  opacity: 0.85;
}

.cell.reachable-door {
  filter: saturate(0.4) brightness(1);
  outline: 1px solid rgba(76, 175, 80, 0.7);
  z-index: 2;
  animation: reachable-glow 2s ease-in-out infinite;
}

@keyframes reachable-glow {

  0%,
  100% {
    box-shadow: inset 0 0 0 0 rgba(76, 175, 80, 0);
  }

  50% {
    box-shadow: inset 0 0 4px 1px rgba(76, 175, 80, 0.25);
  }
}

/* ── Overlay ── */
.board-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 2;
}

/* ── Room labels ── */
.room-label {
  position: absolute;
  color: var(--board-label-color);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: clamp(8px, 1.4vw, 13px);
  font-weight: 600;
  white-space: nowrap;
  text-align: center;
  text-shadow: 0 0 6px rgba(0, 0, 0, 1), 0 0 12px rgba(0, 0, 0, 0.8), 0 1px 3px rgba(0, 0, 0, 1);
  letter-spacing: 0.05em;
  background: var(--board-label-bg);
  padding: 1px 5px;
  border-radius: 3px;
}

[data-theme="light"] .room-label {
  text-shadow: 0 0 4px rgba(255, 255, 255, 0.6);
}

/* ── Center emblem (magnifying glass + CLUE) ── */
.center-emblem {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  pointer-events: none;
}

.center-magnifying-glass {
  width: clamp(60px, 12vw, 130px);
  height: auto;
  border-radius: 50%;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.7));
  object-fit: contain;
}

.center-label {
  color: var(--accent);
  font-family: 'Playfair Display', Georgia, serif;
  font-size: clamp(12px, 2.5vw, 24px);
  font-weight: 900;
  letter-spacing: 0.35em;
  text-shadow:
    0 0 15px var(--accent-glow),
    0 1px 4px rgba(0, 0, 0, 0.9);
  margin-top: -2px;
  text-indent: 0.35em; /* offset letter-spacing for visual centering */
}

[data-theme="vintage"] .center-label {
  text-shadow: 0 0 15px rgba(0, 0, 0, 0.6);
}

/* ── Secret passage ── */
.secret-passage {
  position: absolute;
  color: var(--board-passage-color);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: clamp(7px, 1.2vw, 11px);
  font-weight: 600;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
  padding: 1px 4px;
  border: 1px dashed rgba(200, 160, 96, 0.35);
  border-radius: 3px;
  background: var(--board-passage-bg);
  letter-spacing: 0.02em;
}

.secret-passage::before {
  content: '';
  display: inline-block;
  width: 0.6em;
  height: 0.75em;
  border: 1.5px solid currentColor;
  border-bottom: none;
  border-radius: 3px 3px 0 0;
  margin-right: 0.25em;
  vertical-align: text-bottom;
  opacity: 0.8;
}

/* ── Player tokens ── */
.player-token {
  position: absolute;
  width: clamp(20px, 3.5vw, 34px);
  height: clamp(20px, 3.5vw, 34px);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(8px, 1.3vw, 12px);
  font-weight: bold;
  font-family: 'Crimson Text', Georgia, serif;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 0 2px rgba(0, 0, 0, 0.5);
  z-index: 10;
  transition: left 0.15s linear, top 0.15s linear;
  overflow: visible;
}

.player-token.has-image {
  background: none !important;
  border: 2.5px solid;
  border-color: var(--token-border, rgba(255, 255, 255, 0.5));
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(0, 0, 0, 0.6);
}

.token-portrait {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
  border-radius: 50%;
  display: block;
  clip-path: circle(50%);
}

.player-token.my-token {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.8), 0 0 6px 3px rgba(212, 168, 73, 0.6);
  z-index: 11;
}

.player-token.my-token.has-image {
  border-width: 2.5px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9), 0 0 6px 3px rgba(212, 168, 73, 0.6);
}

.player-token.wanderer-token {
  z-index: 9;
}

.player-token.wanderer-token.has-image {
  z-index: 9;
}

.player-token.weapon-token {
  width: clamp(20px, 3.2vw, 32px);
  height: clamp(20px, 3.2vw, 32px);
  border-radius: 4px;
  z-index: 8;
  font-size: clamp(7px, 1.1vw, 10px);
  background: rgba(20, 20, 30, 0.85);
  border: 1.5px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.15);
}

.player-token.weapon-token .weapon-emoji {
  font-size: clamp(12px, 2vw, 20px);
  line-height: 1;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5));
}

.player-token.is-turn {
  animation: token-pulse 2s ease-in-out infinite;
}

.player-token.is-turn.has-image {
  animation: token-pulse-img 2s ease-in-out infinite;
}

@keyframes token-pulse {

  0%,
  100% {
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 4px 1px rgba(212, 168, 73, 0.5);
  }

  50% {
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 10px 5px rgba(212, 168, 73, 0.7);
  }
}

@keyframes token-pulse-img {

  0%,
  100% {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9), 0 0 4px 1px rgba(212, 168, 73, 0.5);
  }

  50% {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9), 0 0 10px 5px rgba(212, 168, 73, 0.7);
  }
}

/* ── Token tooltip ── */
.token-tooltip {
  display: none;
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  background: var(--tooltip-bg);
  color: var(--tooltip-text);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  padding: 3px 8px;
  border-radius: 4px;
  pointer-events: none;
  z-index: 100;
}

.player-token {
  pointer-events: auto;
}

.player-token:hover {
  z-index: 50;
}

.player-token:hover .token-tooltip {
  display: block;
}
</style>
