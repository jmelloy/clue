<template>
  <div class="detective-notes">
    <h3>Detective Notes</h3>

    <div class="notes-section">
      <h4>Suspects</h4>
      <div
        v-for="card in SUSPECTS"
        :key="card"
        class="note-row"
        :class="noteClass(card)"
        @click="cycleNote(card)"
      >
        <span class="note-card">{{ card }}</span>
        <span class="note-mark">{{ noteMark(card) }}</span>
      </div>
    </div>

    <div class="notes-section">
      <h4>Weapons</h4>
      <div
        v-for="card in WEAPONS"
        :key="card"
        class="note-row"
        :class="noteClass(card)"
        @click="cycleNote(card)"
      >
        <span class="note-card">{{ card }}</span>
        <span class="note-mark">{{ noteMark(card) }}</span>
      </div>
    </div>

    <div class="notes-section">
      <h4>Rooms</h4>
      <div
        v-for="card in ROOMS"
        :key="card"
        class="note-row"
        :class="noteClass(card)"
        @click="cycleNote(card)"
      >
        <span class="note-card">{{ card }}</span>
        <span class="note-mark">{{ noteMark(card) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'

const SUSPECTS = ['Miss Scarlett', 'Colonel Mustard', 'Mrs. White', 'Reverend Green', 'Mrs. Peacock', 'Professor Plum']
const WEAPONS = ['Candlestick', 'Knife', 'Lead Pipe', 'Revolver', 'Rope', 'Wrench']
const ROOMS = ['Kitchen', 'Ballroom', 'Conservatory', 'Billiard Room', 'Library', 'Study', 'Hall', 'Lounge', 'Dining Room']

// States: '' (unknown), 'have' (in your hand), 'seen' (shown to you), 'no' (eliminated), 'maybe' (possible)
const CYCLE = ['', 'no', 'maybe', '']

const props = defineProps({
  yourCards: { type: Array, default: () => [] },
})

// notes: card -> state string
const notes = reactive({})

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

function noteMark(card) {
  const state = notes[card] ?? ''
  if (state === 'have') return '\u2713'
  if (state === 'seen') return '\u{1F441}'
  if (state === 'no') return '\u2717'
  if (state === 'maybe') return '?'
  return ''
}

function noteClass(card) {
  const state = notes[card] ?? ''
  return {
    'note-have': state === 'have',
    'note-seen': state === 'seen',
    'note-no': state === 'no',
    'note-maybe': state === 'maybe',
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
function markCard(card, state) {
  if (notes[card] !== 'have') {
    notes[card] = state
  }
}

defineExpose({ markCard })
</script>

<style scoped>
.detective-notes {
  font-size: 0.8rem;
}

h3 {
  color: #c9a84c;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

h4 {
  color: #8899aa;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.2rem;
  padding-bottom: 0.15rem;
  border-bottom: 1px solid #2c3e50;
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
}

.note-row:hover {
  background: rgba(255, 255, 255, 0.05);
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
  color: #2ecc71;
  opacity: 0.7;
}

.note-have .note-mark {
  color: #2ecc71;
}

.note-seen .note-mark {
  color: #3498db;
}

.note-no {
  color: #666;
  text-decoration: line-through;
}

.note-no .note-mark {
  color: #e74c3c;
}

.note-maybe .note-mark {
  color: #f39c12;
}
</style>
