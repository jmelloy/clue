<template>
  <div class="detective-notes">
    <h3 class="panel-header">Detective Notes</h3>

    <div class="notes-section">
      <h4>Suspects</h4>
      <div v-for="card in SUSPECTS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" class="note-thumb"
          :style="{ borderColor: CHARACTER_COLORS[card]?.bg || '#666' }" />
        <span class="note-card" :style="suspectStyle(card)">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
      </div>
    </div>

    <div class="notes-section">
      <h4>Weapons</h4>
      <div v-for="card in WEAPONS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" class="note-thumb note-thumb-weapon" />
        <span v-else class="note-emoji">{{ CARD_ICONS[card] || '' }}</span>
        <span class="note-card">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
      </div>
    </div>

    <div class="notes-section">
      <h4>Rooms</h4>
      <div v-for="card in ROOMS" :key="card" class="note-row" :class="noteClass(card)" @click="cycleNote(card)">
        <img v-if="CARD_IMAGES[card]" :src="CARD_IMAGES[card]" :alt="card" class="note-thumb note-thumb-room" />
        <span v-else class="note-emoji">{{ CARD_ICONS[card] || '' }}</span>
        <span class="note-card">{{ card }}</span>
        <span class="note-mark" :class="{ 'has-tooltip': notes[card] === 'seen' && shownByMap[card] }">
          {{ noteMark(card) }}
          <span v-if="notes[card] === 'seen' && shownByMap[card]" class="note-tooltip">Shown by {{ shownByMap[card]
            }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'
import {
  SUSPECTS,
  WEAPONS,
  ROOMS,
  CHARACTER_COLORS,
  CARD_ICONS,
  CARD_IMAGES
} from '../constants/clue.js'

// States: '' (unknown), 'have' (in your hand), 'seen' (shown to you), 'no' (eliminated), 'maybe' (possible)
const CYCLE = ['', 'no', 'maybe', '']

const props = defineProps({
  yourCards: { type: Array, default: () => [] },
  savedNotes: { type: Object, default: null }
})

const emit = defineEmits(['notes-changed'])

// notes: card -> state string
const notes = reactive({})
// Track who showed each card
const shownByMap = reactive({})
// Flag to prevent emitting during restoration
let restoring = false

// Restore saved notes when they arrive (e.g. on rejoin)
watch(
  () => props.savedNotes,
  (saved) => {
    if (saved) {
      restoring = true
      const noteStates = saved.notes || {}
      const shownBy = saved.shownBy || {}
      for (const [card, state] of Object.entries(noteStates)) {
        notes[card] = state
      }
      for (const [card, by] of Object.entries(shownBy)) {
        shownByMap[card] = by
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
  emit('notes-changed', {
    notes: { ...notes },
    shownBy: { ...shownByMap }
  })
}

// Watch for any notes changes and emit
watch(notes, () => emitNotesChanged(), { deep: true })

function suspectStyle(card) {
  const state = notes[card] ?? ''
  if (state === 'have' || state === 'no' || state === 'seen') return {}
  const color = CHARACTER_COLORS[card]?.name || CHARACTER_COLORS[card]?.bg
  if (!color) return {}
  // Default and 'maybe' states show the suspect's color
  return { color }
}

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

defineExpose({ markCard, getCardsShownBy })
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
</style>
