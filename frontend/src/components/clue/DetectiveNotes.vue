<template>
  <div class="detective-notes">
    <h3 class="panel-header">
      Detective Notes
      <label v-if="trackedPlayers.length" class="autofill-label" @click.stop>
        <input type="checkbox" v-model="autoFillEnabled" class="autofill-checkbox" />
        Auto-fill
      </label>
    </h3>
    <div v-if="trackedPlayers.length" class="player-columns-legend">
      <div class="legend-spacer"></div>
      <div v-for="p in trackedPlayers" :key="p.id" class="player-col-header"
        :title="p.name + (p.character !== p.name ? ' (' + p.character + ')' : '')">
        {{ playerInitial(p) }}
      </div>
    </div>

    <div class="notes-section">
      <h4>Suspects</h4>
      <div v-for="card in SUSPECTS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" :title="card" class="note-thumb"
          :style="{ borderColor: CHARACTER_COLORS[card]?.bg || '#666' }" />
        <span class="note-card">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
        <template v-if="trackedPlayers.length">
          <button
            v-for="p in trackedPlayers"
            :key="p.id"
            type="button"
            class="player-col-cell"
            :class="playerCellClass(p.id, card)"
            @click.stop="cyclePlayerMark(p.id, card)"
          >
            {{ playerMarkDisplay(p.id, card) }}
          </button>
        </template>
      </div>
    </div>

    <div class="notes-section">
      <h4>Weapons</h4>
      <div v-for="card in WEAPONS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" :title="card" class="note-thumb note-thumb-weapon" />
        <span v-else class="note-emoji">{{ CARD_ICONS[card] || '' }}</span>
        <span class="note-card">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
        <template v-if="trackedPlayers.length">
          <button
            v-for="p in trackedPlayers"
            :key="p.id"
            type="button"
            class="player-col-cell"
            :class="playerCellClass(p.id, card)"
            @click.stop="cyclePlayerMark(p.id, card)"
          >
            {{ playerMarkDisplay(p.id, card) }}
          </button>
        </template>
      </div>
    </div>

    <div class="notes-section">
      <h4>Rooms</h4>
      <div v-for="card in ROOMS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" :title="card" class="note-thumb note-thumb-room" />
        <span v-else class="note-emoji">{{ CARD_ICONS[card] || '' }}</span>
        <span class="note-card">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
        <template v-if="trackedPlayers.length">
          <button
            v-for="p in trackedPlayers"
            :key="p.id"
            type="button"
            class="player-col-cell"
            :class="playerCellClass(p.id, card)"
            @click.stop="cyclePlayerMark(p.id, card)"
          >
            {{ playerMarkDisplay(p.id, card) }}
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch } from 'vue'
import {
  SUSPECTS,
  WEAPONS,
  ROOMS,
  CHARACTER_COLORS,
  CARD_ICONS,
  CARD_IMAGES
} from '../../constants/clue'

// States: '' (unknown), 'have' (in your hand), 'seen' (shown to you), 'no' (eliminated), 'maybe' (possible)
const CYCLE = ['', 'no', 'maybe', '']

const props = defineProps({
  yourCards: { type: Array, default: () => [] },
  savedNotes: { type: Object, default: null },
  players: { type: Array, default: () => [] },
  playerId: { type: String, default: '' }
})

const emit = defineEmits(['notes-changed'])

// notes: card -> state string
const notes = reactive({})
// Track who showed each card
const shownByMap = reactive({})
// Track player marks per card: { playerId: { card: '✗'|'✓'|'?' } }
const playerDoesntHave = reactive({})
// Prefer using `playerMarks` as the clearer name; kept `playerDoesntHave` for backward compatibility.
const playerMarks = playerDoesntHave
// Whether auto-fill from suggestions is enabled
const autoFillEnabled = ref(true)
// Symbols for player column cycling
const PLAYER_MARK_CYCLE = ['', '\u2717', '\u2713', '?']
// Flag to prevent emitting during restoration
let restoring = false

// Non-wandering players other than ourselves
const trackedPlayers = computed(() =>
  props.players.filter(p => p.type !== 'wanderer' && p.id !== props.playerId)
)

function playerInitial(p) {
  const name = p.name || p.character || '?'
  const parts = name.trim().split(/\s+/)
  return parts[parts.length - 1][0].toUpperCase()
}

// Restore saved notes when they arrive (e.g. on rejoin)
watch(
  () => props.savedNotes,
  (saved) => {
    if (saved) {
      restoring = true
      const noteStates = saved.notes || {}
      const shownBy = saved.shownBy || {}
      // Prefer `playerMarks` if present, fall back to legacy `playerDoesntHave`
      const doesntHave = saved.playerMarks || saved.playerDoesntHave || {}
      for (const [card, state] of Object.entries(noteStates)) {
        notes[card] = state
      }
      for (const [card, by] of Object.entries(shownBy)) {
        shownByMap[card] = by
      }
      for (const [pid, cards] of Object.entries(doesntHave)) {
        // Backward compat: convert boolean `true` to '✗'
        const converted = {}
        for (const [card, val] of Object.entries(cards)) {
          converted[card] = val === true ? '\u2717' : val
        }
        playerMarks[pid] = converted
      }
      if (saved.autoFillEnabled !== undefined) {
        autoFillEnabled.value = saved.autoFillEnabled
      }
      restoring = false
    }
  },
  { immediate: true }
)

// Auto-mark cards in hand
watch(
  () => props.yourCards,
  (cards) => {
    for (const card of cards) {
      notes[card] = 'have'
    }
  },
  { immediate: true }
)

function emitNotesChanged() {
  if (restoring) return
  // Deep-copy playerDoesntHave
  const doesntHaveCopy = {}
  for (const [pid, cards] of Object.entries(playerDoesntHave)) {
    doesntHaveCopy[pid] = { ...cards }
  }
  emit('notes-changed', {
    notes: { ...notes },
    shownBy: { ...shownByMap },
    playerDoesntHave: doesntHaveCopy,
    autoFillEnabled: autoFillEnabled.value
  })
}

// Watch for any notes changes and emit
watch(notes, () => emitNotesChanged(), { deep: true, flush: 'sync' })
watch(playerDoesntHave, () => emitNotesChanged(), { deep: true, flush: 'sync' })
watch(autoFillEnabled, () => emitNotesChanged(), { flush: 'sync' })

function noteMark(card) {
  const state = notes[card] ?? ''
  if (state === 'have') return '\u2713'
  if (state === 'seen') return '\u{1F441}'
  if (state === 'no') return '\u2717'
  if (state === 'maybe') return '\u{25C6}' // ◆ diamond — person of interest
  return ''
}

function noteClass(card) {
  const state = notes[card] ?? ''
  return {
    'note-have': state === 'have',
    'note-seen': state === 'seen',
    'note-no': state === 'no',
    'note-maybe': state === 'maybe'
  }
}

function cycleNote(card) {
  // Don't let users change cards they hold
  if (notes[card] === 'have') return
  const current = notes[card] ?? ''
  const idx = CYCLE.indexOf(current)
  const next = CYCLE[(idx + 1) % CYCLE.length]
  notes[card] = next
}

function playerMarkDisplay(playerId, card) {
  return playerDoesntHave[playerId]?.[card] || ''
}

function playerCellClass(playerId, card) {
  const mark = playerDoesntHave[playerId]?.[card] || ''
  return {
    'mark-no': mark === '\u2717',
    'mark-yes': mark === '\u2713',
    'mark-maybe': mark === '?'
  }
}

function cyclePlayerMark(playerId, card) {
  if (!playerDoesntHave[playerId]) {
    playerDoesntHave[playerId] = {}
  }
  const current = playerDoesntHave[playerId][card] || ''
  const idx = PLAYER_MARK_CYCLE.indexOf(current)
  const next = PLAYER_MARK_CYCLE[(idx + 1) % PLAYER_MARK_CYCLE.length]
  if (next) {
    playerDoesntHave[playerId][card] = next
  } else {
    delete playerDoesntHave[playerId][card]
  }
}

// Expose for parent to programmatically mark cards
function markCard(card, state, shownBy) {
  if (notes[card] !== 'have') {
    notes[card] = state
    if (shownBy) shownByMap[card] = shownBy
  }
}

function noteTitle(card) {
  const state = notes[card] ?? ''
  if (state === 'seen' && shownByMap[card]) return `Shown by ${shownByMap[card]}`
  return ''
}

// Get all cards shown by a specific player name
function getCardsShownBy(playerName) {
  const cards = []
  for (const [card, by] of Object.entries(shownByMap)) {
    if (by === playerName) cards.push(card)
  }
  return cards
}

// Mark that a player doesn't have specific cards (from suggestion tracking)
function markPlayerDoesntHaveCards(playerId, cards) {
  if (!autoFillEnabled.value) return
  if (!playerDoesntHave[playerId]) {
    playerDoesntHave[playerId] = {}
  }
  for (const card of cards) {
    // Only auto-fill if not already manually marked
    if (!playerDoesntHave[playerId][card]) {
      playerDoesntHave[playerId][card] = '\u2717'
    }
  }
}

defineExpose({ markCard, getCardsShownBy, markPlayerDoesntHaveCards })
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.detective-notes {
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.8rem;
}

/* Panel header is in styles/components.css */

h4 {
  color: var(--text-secondary);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.2rem;
  padding-bottom: 0.15rem;
  border-bottom: 1px solid var(--accent-border);
  font-weight: 600;
}

.notes-section {
  margin-bottom: 0.5rem;
}

.note-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.15rem 0.3rem;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-primary);
}

.note-row:hover {
  background: var(--bg-hover);
}

.note-card {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-mark {
  width: 20px;
  text-align: center;
  font-weight: bold;
  flex-shrink: 0;
}

/* State colors */
.note-have {
  color: var(--success);
  opacity: 0.7;
}

.note-have .note-mark {
  color: var(--success);
}

.note-seen {
  color: var(--text-dim);
}

.note-seen .note-mark {
  color: var(--note-seen-color);
}

.note-no {
  color: var(--text-faint);
  text-decoration: line-through;
}

.note-no .note-mark {
  color: var(--error);
}

.note-maybe {
  background: var(--accent-bg);
}

.note-maybe .note-card {
  font-weight: 600;
}

.note-maybe .note-mark {
  color: var(--accent);
  font-size: 0.7rem;
}

/* Suspect thumbnail */
.note-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  object-fit: cover;
  object-position: center 15%;
  flex-shrink: 0;
  margin-right: 0.25rem;
  border: 1.5px solid;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  transition: all 0.15s;
}

.note-no .note-thumb {
  opacity: 0.25;
  filter: grayscale(1);
}

.note-have .note-thumb,
.note-seen .note-thumb {
  opacity: 0.5;
}

.note-thumb-room {
  border-radius: 3px;
  object-position: center center;
  border-color: var(--tag-wanderer-text);
}

.note-thumb-weapon {
  border-radius: 3px;
  object-position: center center;
  border-color: var(--tag-accuse-text);
}

.note-row:hover .note-thumb {
  box-shadow: 0 1px 6px rgba(212, 168, 73, 0.2);
}

/* Card emoji for weapons */
.note-emoji {
  font-size: 0.75rem;
  flex-shrink: 0;
  margin-right: 0.2rem;
  width: 18px;
  text-align: center;
  line-height: 1;
}

.note-no .note-emoji {
  opacity: 0.25;
  filter: grayscale(1);
}

.note-have .note-emoji,
.note-seen .note-emoji {
  opacity: 0.5;
}

/* Tooltip for "shown by" on eye icon */
.note-mark.has-tooltip {
  position: relative;
  cursor: help;
}

.note-tooltip {
  display: none;
  position: absolute;
  right: 100%;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-panel-solid);
  border: 1px solid var(--accent-border-hover);
  color: var(--accent);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: normal;
  font-style: normal;
  white-space: nowrap;
  z-index: 10;
  pointer-events: none;
  margin-right: 4px;
}

.note-mark.has-tooltip:hover .note-tooltip {
  display: block;
}

/* Player column tracking */
.player-columns-legend {
  display: flex;
  justify-content: flex-end;
  gap: 0;
  padding: 0 0.3rem;
  margin-bottom: 0.2rem;
  border-bottom: 1px solid var(--accent-border);
  padding-bottom: 0.15rem;
}

.legend-spacer {
  flex: 1;
}

.player-col-header {
  width: 20px;
  text-align: center;
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-secondary);
  cursor: help;
  flex-shrink: 0;
}

.player-col-cell {
  width: 20px;
  text-align: center;
  font-size: 0.6rem;
  font-weight: bold;
  flex-shrink: 0;
  color: var(--text-faint);
}

.player-col-cell:hover {
  background: var(--bg-hover);
  border-radius: 2px;
}

.player-col-cell.mark-no {
  color: var(--error);
  opacity: 0.7;
}

.player-col-cell.mark-yes {
  color: var(--success);
  opacity: 0.8;
}

.player-col-cell.mark-maybe {
  color: var(--accent);
  opacity: 0.8;
}

/* Make header a flex row so the checkbox sits on the right */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Auto-fill toggle in header */
.autofill-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.6rem;
  font-weight: 400;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  text-transform: none;
  letter-spacing: 0;
}

.autofill-checkbox {
  width: 12px;
  height: 12px;
  cursor: pointer;
  accent-color: var(--accent);
}
</style>
