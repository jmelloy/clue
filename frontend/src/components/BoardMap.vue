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
        >
          {{ room.name }}
        </div>
        <!-- Center CLUE label -->
        <div class="center-label" :style="overlayPos(12, 11)">CLUE</div>
        <!-- Secret passage indicators -->
        <div
          v-for="sp in secretPassages"
          :key="'sp-' + sp.from"
          class="secret-passage"
          :style="overlayPos(sp.row, sp.col)"
          :title="'Secret passage to ' + sp.to"
        >
          &#x21C9; {{ sp.to }}
        </div>
        <!-- Player tokens -->
        <div
          v-for="token in playerTokens"
          :key="'tk-' + token.id"
          class="player-token"
          :class="{
            'my-token': token.id === playerId,
            'wanderer-token': token.type === 'wanderer',
            'is-turn': token.id === gameState?.whose_turn,
            'has-image': !!CARD_IMAGES[token.character],
          }"
          :style="tokenStyle(token)"
        >
          <img
            v-if="CARD_IMAGES[token.character]"
            :src="CARD_IMAGES[token.character]"
            :alt="token.character"
            class="token-portrait"
          />
          <span v-else>{{ abbr(token.character) }}</span>
          <span class="token-tooltip">
            {{ token.type === 'wanderer' ? token.character : `${token.name} (${token.character})` }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import {
  CARD_IMAGES,
  abbr,
  characterColors,
} from "../constants/clue.js";

// ── Board layout data (matches backend board.py) ──

const BOARD_ROWS = [
  "ssssss . hhhhhh . oooooo",
  "sssssss..hhhhhh..ooooooo",
  "sssssss..hhhhhh..ooooooo",
  "sssssss..hhhhhh..ooooooo",
  " ........hhhhhh..ooooooo",
  ".........hhhhhh..ooooooo",
  " lllll...hhhhhh........ ",
  "lllllll.................",
  "lllllll..     .........",
  "lllllll..     ..nnnnnnnn",
  " lllll...     ..nnnnnnnn",
  " ........     ..nnnnnnnn",
  "bbbbbb...     ..nnnnnnnn",
  "bbbbbb...     ..nnnnnnnn",
  "bbbbbb...     ..nnnnnnnn",
  "bbbbbb.............nnnnn",
  "bbbbbb.................",
  " .......aaaaaaaa........",
  "........aaaaaaaa..kkkkk",
  " cccc...aaaaaaaa..kkkkkk",
  "cccccc..aaaaaaaa..kkkkkk",
  "cccccc..aaaaaaaa..kkkkkk",
  "cccccc..aaaaaaaa..kkkkkk",
  "cccccc ...aaaa... kkkkkk",
  "         .    .         ",
];

const ROOM_KEY_MAP = {
  s: "Study",
  h: "Hall",
  o: "Lounge",
  l: "Library",
  b: "Billiard Room",
  n: "Dining Room",
  c: "Conservatory",
  a: "Ballroom",
  k: "Kitchen",
};

const DOORS = {
  "3,6": "Study",
  "6,11": "Hall",
  "6,12": "Hall",
  "4,9": "Hall",
  "5,17": "Lounge",
  "8,6": "Library",
  "10,3": "Library",
  "12,1": "Billiard Room",
  "15,5": "Billiard Room",
  "12,16": "Dining Room",
  "9,17": "Dining Room",
  "19,4": "Conservatory",
  "17,9": "Ballroom",
  "17,14": "Ballroom",
  "19,8": "Ballroom",
  "19,15": "Ballroom",
  "18,19": "Kitchen",
};

const DOOR_DIRECTIONS = {
  "3,6": "south",
  "4,9": "west",
  "6,11": "south",
  "6,12": "south",
  "5,17": "south",
  "8,6": "east",
  "10,3": "south",
  "12,1": "north",
  "15,5": "east",
  "12,16": "west",
  "9,17": "north",
  "19,4": "east",
  "17,9": "north",
  "17,14": "north",
  "19,8": "west",
  "19,15": "east",
  "18,19": "north",
};

const STARTS = {
  "24,9": "Scarlet",
  "7,23": "Mustard",
  "24,14": "White",
  "0,16": "Green",
  "5,0": "Plum",
  "18,0": "Peacock",
};

const ROOM_COLORS = {
  Study: "#2a2218",
  Hall: "#2a2218",
  Lounge: "#2a2218",
  Library: "#2a2218",
  "Billiard Room": "#2a2218",
  "Dining Room": "#2a2218",
  Conservatory: "#2a2218",
  Ballroom: "#2a2218",
  Kitchen: "#2a2218",
};


// ── Pre-compute room info from board layout ──

const ROOM_INFO = {};
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || "").padEnd(24);
  for (let c = 0; c < 24; c++) {
    const room = ROOM_KEY_MAP[line[c]];
    if (room) {
      if (!ROOM_INFO[room]) {
        ROOM_INFO[room] = {
          name: room,
          minRow: r,
          maxRow: r,
          minCol: c,
          maxCol: c,
        };
      } else {
        ROOM_INFO[room].minRow = Math.min(ROOM_INFO[room].minRow, r);
        ROOM_INFO[room].maxRow = Math.max(ROOM_INFO[room].maxRow, r);
        ROOM_INFO[room].minCol = Math.min(ROOM_INFO[room].minCol, c);
        ROOM_INFO[room].maxCol = Math.max(ROOM_INFO[room].maxCol, c);
      }
    }
  }
}
for (const room of Object.values(ROOM_INFO)) {
  room.centerRow = (room.minRow + room.maxRow) / 2;
  room.centerCol = (room.minCol + room.maxCol) / 2;
}

// ── Build flat cell array (25 rows x 24 cols = 600 cells) ──

const CELL_DATA = [];
for (let r = 0; r < 25; r++) {
  const line = (BOARD_ROWS[r] || "").padEnd(24);
  for (let c = 0; c < 24; c++) {
    const key = `${r},${c}`;
    const ch = line[c];
    const doorRoom = DOORS[key];
    const startChar = STARTS[key];

    if (doorRoom) {
      CELL_DATA.push({
        row: r,
        col: c,
        type: "door",
        room: doorRoom,
        doorDir: DOOR_DIRECTIONS[key],
      });
    } else if (ROOM_KEY_MAP[ch]) {
      CELL_DATA.push({ row: r, col: c, type: "room", room: ROOM_KEY_MAP[ch] });
    } else if (ch === ".") {
      CELL_DATA.push({
        row: r,
        col: c,
        type: startChar ? "start" : "hallway",
        room: null,
        startChar,
      });
    } else {
      const isCenter = r >= 8 && r <= 15 && c >= 9 && c <= 14;
      CELL_DATA.push({ row: r, col: c, type: "wall", room: null, isCenter });
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
  reachablePositions: { type: Array, default: () => [] },
});

const emit = defineEmits(["select-room", "select-position"]);

const cells = CELL_DATA;

const currentRoom = computed(
  () => props.gameState?.current_room?.[props.playerId] ?? null
);

const reachablePositionSet = computed(() => {
  const set = new Set();
  for (const pos of props.reachablePositions) {
    set.add(`${pos[0]},${pos[1]}`);
  }
  return set;
});

const hasReachableData = computed(
  () => props.reachableRooms.length > 0 || props.reachablePositions.length > 0
);

const roomLabels = computed(() => Object.values(ROOM_INFO));

const secretPassages = [
  {
    from: "Study",
    to: "Kitchen",
    row: ROOM_INFO["Study"].minRow + 0.8,
    col: ROOM_INFO["Study"].minCol + 1.5,
  },
  {
    from: "Kitchen",
    to: "Study",
    row: ROOM_INFO["Kitchen"].maxRow - 0.3,
    col: ROOM_INFO["Kitchen"].maxCol - 1.5,
  },
  {
    from: "Lounge",
    to: "Conservatory",
    row: ROOM_INFO["Lounge"].minRow + 0.8,
    col: ROOM_INFO["Lounge"].maxCol - 1.5,
  },
  {
    from: "Conservatory",
    to: "Lounge",
    row: ROOM_INFO["Conservatory"].maxRow - 0.3,
    col: ROOM_INFO["Conservatory"].minCol + 1.5,
  },
];

const playerTokens = computed(() => {
  const players = props.gameState?.players ?? [];
  const roomMap = props.gameState?.current_room ?? {};
  const posMap = props.gameState?.player_positions ?? {};
  const tokens = [];

  // Group players by room
  const byRoom = {};
  const hallway = [];
  for (const p of players) {
    const room = roomMap[p.id];
    if (room && ROOM_INFO[room]) {
      if (!byRoom[room]) byRoom[room] = [];
      byRoom[room].push(p);
    } else if (posMap[p.id]) {
      hallway.push(p);
    }
  }

  // Distribute players within each room
  for (const [roomName, rPlayers] of Object.entries(byRoom)) {
    const info = ROOM_INFO[roomName];
    const cR = info.centerRow + 0.8;
    const cC = info.centerCol + 0.5;
    const n = rPlayers.length;
    const roomW = info.maxCol - info.minCol + 1;
    const spacing = Math.min(
      1.8,
      Math.max(1.2, (roomW - 2) / Math.max(1, n - 1))
    );
    const startC = cC - (spacing * (n - 1)) / 2;
    for (let i = 0; i < n; i++) {
      tokens.push({ ...rPlayers[i], row: cR, col: startC + i * spacing });
    }
  }

  // Hallway players at exact position
  for (const p of hallway) {
    const pos = posMap[p.id];
    tokens.push({ ...p, row: pos[0] + 0.5, col: pos[1] + 0.5 });
  }

  return tokens;
});

function cellClasses(cell) {
  const cls = ["cell", `cell-${cell.type}`];
  if (cell.isCenter) cls.push("cell-center");
  if (cell.room) {
    if (props.selectable) cls.push("clickable");
    if (props.selectedRoom === cell.room) cls.push("selected");
    if (currentRoom.value === cell.room) cls.push("my-room");
    // Highlight reachable/unreachable rooms when selectable
    if (props.selectable && hasReachableData.value) {
      if (props.reachableRooms.includes(cell.room)) {
        cls.push("reachable");
      } else {
        cls.push("unreachable");
      }
    }
  } else if (
    (cell.type === "hallway" || cell.type === "start") &&
    props.selectable
  ) {
    cls.push("clickable");
    // Highlight reachable hallway positions
    if (hasReachableData.value) {
      const key = `${cell.row},${cell.col}`;
      if (reachablePositionSet.value.has(key)) {
        cls.push("reachable");
      }
    }
  } else if (
    cell.type === "door" &&
    props.selectable &&
    hasReachableData.value
  ) {
    // Highlight doors of reachable rooms
    if (props.reachableRooms.includes(cell.room)) {
      cls.push("reachable-door");
    }
  }
  return cls;
}

function cellStyle(cell) {
  if (cell.room) {
    const img = CARD_IMAGES[cell.room];
    const info = ROOM_INFO[cell.room];
    if (img && info) {
      const roomCols = info.maxCol - info.minCol + 1;
      const roomRows = info.maxRow - info.minRow + 1;
      const dc = cell.col - info.minCol;
      const dr = cell.row - info.minRow;
      const posX = roomCols > 1 ? (dc / (roomCols - 1)) * 100 : 50;
      const posY = roomRows > 1 ? (dr / (roomRows - 1)) * 100 : 50;
      return {
        backgroundImage: `url(${img})`,
        backgroundSize: `${roomCols * 100}% ${roomRows * 100}%`,
        backgroundPosition: `${posX}% ${posY}%`,
        backgroundColor: '#1a1610',
      };
    }
    return { backgroundColor: '#1a1610' };
  }
  return {};
}

function handleCellClick(cell) {
  if (!props.selectable) return;
  if (cell.room) {
    emit("select-room", cell.room);
  } else if (cell.type === "hallway" || cell.type === "start") {
    emit("select-position", [cell.row, cell.col]);
  }
}

function overlayPos(row, col) {
  return {
    left: `${((col + 0.5) / 24) * 100}%`,
    top: `${((row + 0.5) / 25) * 100}%`,
    transform: "translate(-50%, -50%)",
  };
}

function tokenStyle(token) {
  const { bg, text } = characterColors(token.character);
  const style = {
    left: `${(token.col / 24) * 100}%`,
    top: `${(token.row / 25) * 100}%`,
    transform: "translate(-50%, -50%)",
    backgroundColor: bg,
    color: text,
    "--token-border": bg,
  };
  if (token.type === "wanderer") {
    style.opacity = 0.85;
  }
  return style;
}
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Crimson+Text:wght@400;600&display=swap");

.board-map {
  user-select: none;
}

.board-container {
  position: relative;
  width: 100%;
  max-width: 690px;
  margin: 0 auto;
  aspect-ratio: 24 / 25;
  background: #1a1510;
  border-radius: 6px;
  overflow: hidden;
  border: 4px solid #8b1a1a;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5), inset 0 0 0 2px rgba(139, 26, 26, 0.3);
}

/* ── Grid ── */
.board-grid {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  grid-template-rows: repeat(25, 1fr);
  width: 100%;
  height: 100%;
  gap: 0;
  background: #1a1510;
  background-image: linear-gradient(to right, #15110c 1px, transparent 1px),
    linear-gradient(to bottom, #15110c 1px, transparent 1px);
  background-size: calc(100% / 24) 100%, 100% calc(100% / 25);
}

/* ── Cell types ── */
.cell {
  min-width: 0;
  min-height: 0;
}

.cell-room {
  border: 0.5px solid rgba(255, 255, 255, 0.03);
  filter: saturate(0.35) brightness(0.9);
}

.cell-door {
  position: relative;
  border: 0.5px solid rgba(255, 255, 255, 0.06);
  overflow: visible;
}

/* Door direction indicators — bright gold bar on top of room image */
.cell-door[data-door-dir]::after {
  content: "";
  position: absolute;
  background: #e8be4a;
  border-radius: 1px;
  z-index: 3;
  box-shadow: 0 0 5px rgba(232, 190, 74, 0.9), 0 0 2px rgba(255, 255, 255, 0.5);
}

.cell-door[data-door-dir="north"]::after {
  top: 0;
  left: 15%;
  right: 15%;
  height: 3px;
}

.cell-door[data-door-dir="south"]::after {
  bottom: 0;
  left: 15%;
  right: 15%;
  height: 3px;
}

.cell-door[data-door-dir="east"]::after {
  right: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
}

.cell-door[data-door-dir="west"]::after {
  left: 0;
  top: 15%;
  bottom: 15%;
  width: 3px;
}

.cell-hallway {
  background: #c8b88a;
  border: 0.5px solid rgba(160, 140, 100, 0.4);
}

.cell-start {
  background: #c8b88a;
  border: 0.5px solid rgba(160, 140, 100, 0.4);
  position: relative;
}

.cell-start::after {
  content: "";
  position: absolute;
  inset: 30%;
  border-radius: 50%;
  background: rgba(120, 100, 60, 0.2);
}

.cell-wall {
  background: #2a2a1e;
}

/* Center dead space (staircase area) */
.cell-wall.cell-center {
  background: #3a2e1e;
  border: 0.5px solid rgba(80, 65, 40, 0.3);
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
  filter: saturate(0.45) brightness(1.0);
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

.cell.unreachable {
  filter: saturate(0.25) brightness(0.7);
  opacity: 0.85;
}

.cell-door.unreachable {
  filter: saturate(0.25) brightness(0.7);
  opacity: 0.85;
}

.cell.reachable-door {
  filter: saturate(0.4) brightness(1.0);
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
}

/* ── Room labels ── */
.room-label {
  position: absolute;
  color: #f0e0b0;
  font-family: "Crimson Text", Georgia, serif;
  font-size: clamp(8px, 1.4vw, 13px);
  font-weight: 600;
  white-space: nowrap;
  text-align: center;
  text-shadow: 0 0 6px rgba(0, 0, 0, 1), 0 0 12px rgba(0, 0, 0, 0.8), 0 1px 3px rgba(0, 0, 0, 1);
  letter-spacing: 0.05em;
  background: rgba(0, 0, 0, 0.45);
  padding: 1px 5px;
  border-radius: 3px;
}

/* ── Center label ── */
.center-label {
  position: absolute;
  color: #d4a849;
  font-family: "Playfair Display", Georgia, serif;
  font-size: clamp(14px, 2.8vw, 26px);
  font-weight: 900;
  letter-spacing: 0.3em;
  text-shadow: 0 0 15px rgba(212, 168, 73, 0.4);
}

/* ── Secret passage ── */
.secret-passage {
  position: absolute;
  color: #c8a060;
  font-family: "Crimson Text", Georgia, serif;
  font-size: clamp(7px, 1.2vw, 11px);
  font-weight: 600;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
  padding: 1px 4px;
  border: 1px dashed rgba(200, 160, 96, 0.35);
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.4);
  letter-spacing: 0.02em;
}

.secret-passage::before {
  content: "";
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
  font-family: "Crimson Text", Georgia, serif;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 0 2px rgba(0, 0, 0, 0.5);
  z-index: 10;
  transition: left 0.4s ease, top 0.4s ease;
  overflow: hidden;
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

.player-token.is-turn {
  animation: token-pulse 2s ease-in-out infinite;
}

.player-token.is-turn.has-image {
  animation: token-pulse-img 2s ease-in-out infinite;
}

@keyframes token-pulse {
  0%,
  100% {
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8),
      0 0 4px 1px rgba(212, 168, 73, 0.5);
  }
  50% {
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.8),
      0 0 10px 5px rgba(212, 168, 73, 0.7);
  }
}

@keyframes token-pulse-img {
  0%,
  100% {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9),
      0 0 4px 1px rgba(212, 168, 73, 0.5);
  }
  50% {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.9),
      0 0 10px 5px rgba(212, 168, 73, 0.7);
  }
}

/* ── Token tooltip ── */
.token-tooltip {
  display: none;
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.85);
  color: #f0e0b0;
  font-family: "Crimson Text", Georgia, serif;
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

.player-token:hover .token-tooltip {
  display: block;
}
</style>
