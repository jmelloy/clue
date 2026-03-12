<template>
  <div v-if="faceDown" class="playing-card card-back" :class="sizeClass">
    <div class="card-back-pattern"></div>
  </div>
  <div v-else class="playing-card" :class="[suitClass, sizeClass]">
    <span class="card-corner top-left">
      <span class="card-rank">{{ rank }}</span>
      <span class="card-suit-small">{{ suitSymbol }}</span>
    </span>
    <template v-if="showCenter">
      <div v-if="isFaceCard" class="card-face-center">
        <span class="card-face-symbol">{{ faceSymbol }}</span>
      </div>
      <div v-else class="card-pips" :class="'pips-' + pipCount">
        <span v-for="(pos, i) in pips" :key="i" class="pip" :style="{
          top: pos[0] + '%',
          left: pos[1] + '%',
          transform: pos[0] > 50 ? 'translate(-50%,-50%) rotate(180deg)' : 'translate(-50%,-50%)'
        }">{{ suitSymbol }}</span>
      </div>
    </template>
    <span class="card-corner bottom-right">
      <span class="card-rank">{{ rank }}</span>
      <span class="card-suit-small">{{ suitSymbol }}</span>
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rank: { type: String, default: 'A' },
  suit: { type: String, default: 'spades' },
  faceDown: { type: Boolean, default: false },
  size: { type: String, default: 'medium', validator: v => ['tiny', 'mini', 'small', 'medium', 'large'].includes(v) }
})

const SUIT_SYMBOLS = { hearts: '\u2665', diamonds: '\u2666', clubs: '\u2663', spades: '\u2660' }
const FACE_SYMBOLS = { J: '\u265E', Q: '\u2655', K: '\u2654' }

const PIP_LAYOUTS = {
  1: [[50, 50]],
  2: [[18, 50], [82, 50]],
  3: [[18, 50], [50, 50], [82, 50]],
  4: [[18, 28], [18, 72], [82, 28], [82, 72]],
  5: [[18, 28], [18, 72], [50, 50], [82, 28], [82, 72]],
  6: [[18, 28], [18, 72], [50, 28], [50, 72], [82, 28], [82, 72]],
  7: [[18, 28], [18, 72], [34, 50], [50, 28], [50, 72], [82, 28], [82, 72]],
  8: [[18, 28], [18, 72], [34, 50], [50, 28], [50, 72], [66, 50], [82, 28], [82, 72]],
  9: [[18, 28], [18, 72], [38, 28], [38, 72], [50, 50], [62, 28], [62, 72], [82, 28], [82, 72]],
  10: [[18, 28], [18, 72], [30, 50], [38, 28], [38, 72], [62, 28], [62, 72], [70, 50], [82, 28], [82, 72]]
}

const suitSymbol = computed(() => SUIT_SYMBOLS[props.suit] ?? props.suit?.[0]?.toUpperCase() ?? '')
const suitClass = computed(() => `suit-${props.suit}`)
const sizeClass = computed(() => `card-${props.size}`)
const isFaceCard = computed(() => ['J', 'Q', 'K'].includes(props.rank))
const faceSymbol = computed(() => FACE_SYMBOLS[props.rank] ?? '')
const showCenter = computed(() => !['tiny', 'mini'].includes(props.size))

const pipCount = computed(() => {
  const n = parseInt(props.rank)
  if (!isNaN(n) && n >= 2 && n <= 10) return n
  if (props.rank === 'A') return 1
  return 0
})

const pips = computed(() => PIP_LAYOUTS[pipCount.value] || [])
</script>

<style scoped>
.playing-card {
  position: relative;
  background: var(--card-face, #f5f1e8);
  border-radius: 6px;
  box-shadow: 0 2px 8px var(--card-shadow, rgba(0, 0, 0, 0.35));
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

/* Sizes: tiny (32x44), mini (40x56), small (44x62), medium (62x88), large (100x140) */
.card-tiny { width: 32px; height: 44px; border-radius: 4px; }
.card-mini { width: 40px; height: 56px; }
.card-small { width: 44px; height: 62px; }
.card-medium { width: 62px; height: 88px; }
.card-large { width: 100px; height: 140px; border-radius: 8px; }

.playing-card.suit-hearts,
.playing-card.suit-diamonds {
  color: var(--red-suit, #dc2626);
}

.playing-card.suit-clubs,
.playing-card.suit-spades {
  color: var(--black-suit, #1c1c2e);
}

.card-corner {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1;
}

.card-corner.top-left {
  top: 4px;
  left: 5px;
}

.card-corner.bottom-right {
  bottom: 4px;
  right: 5px;
  transform: rotate(180deg);
}

.card-rank {
  font-family: 'Fira Code', monospace;
  font-size: 0.7rem;
  font-weight: 600;
}

.card-large .card-rank { font-size: 0.75rem; }
.card-small .card-rank { font-size: 0.6rem; }
.card-mini .card-rank { font-size: 0.55rem; }
.card-tiny .card-rank { font-size: 0.5rem; }

.card-suit-small {
  font-size: 0.55rem;
  line-height: 1;
}

.card-large .card-suit-small { font-size: 0.6rem; }
.card-mini .card-suit-small { font-size: 0.45rem; }
.card-tiny .card-suit-small { font-size: 0.4rem; }

.card-pips {
  position: absolute;
  top: 18px;
  bottom: 18px;
  left: 6px;
  right: 6px;
}

.card-large .card-pips {
  top: 24px;
  bottom: 24px;
  left: 10px;
  right: 10px;
}

.pip {
  position: absolute;
  font-size: 0.85rem;
  line-height: 1;
  opacity: 0.9;
}

.card-large .pip { font-size: 1.1rem; }

.pips-1 .pip { font-size: 1.8rem; }
.card-large .pips-1 .pip { font-size: 2.8rem; }

.pips-2 .pip,
.pips-3 .pip {
  font-size: 1rem;
}

.card-large .pips-2 .pip,
.card-large .pips-3 .pip {
  font-size: 1.3rem;
}

.pips-8 .pip { font-size: 0.72rem; }
.pips-9 .pip { font-size: 0.65rem; }
.pips-10 .pip { font-size: 0.6rem; }

.card-large .pips-8 .pip { font-size: 0.9rem; }
.card-large .pips-9 .pip { font-size: 0.82rem; }
.card-large .pips-10 .pip { font-size: 0.75rem; }

.card-face-center {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
  opacity: 0.85;
}

.card-large .card-face-center { font-size: 3.2rem; }

.card-face-symbol {
  line-height: 1;
}

.card-back {
  background: var(--card-back, #1a4d2e);
  border: 1px solid var(--card-back-border, #2a6b3e);
}

.card-back-pattern {
  position: absolute;
  inset: 3px;
  border-radius: 3px;
  border: 1px solid rgba(201, 168, 76, 0.2);
  background: repeating-linear-gradient(45deg,
      transparent,
      transparent 3px,
      rgba(201, 168, 76, 0.05) 3px,
      rgba(201, 168, 76, 0.05) 4px);
}

.card-back-pattern::after {
  content: '';
  position: absolute;
  inset: 4px;
  border: 1px solid rgba(201, 168, 76, 0.15);
  border-radius: 2px;
}
</style>
