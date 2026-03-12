import { ref, readonly, type DeepReadonly, type Ref } from 'vue'
import type { Deck } from '../types'

export const DECKS: Deck[] = ['css', 'classic', 'modern', 'vintage']
const STORAGE_KEY = 'clue-deck'

// Shared singleton state (mirrors the pattern used by useTheme)
const current = ref<Deck>(loadSaved())

function loadSaved(): Deck {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && DECKS.includes(saved as Deck)) return saved as Deck
  } catch {
    /* SSR / blocked storage */
  }
  return 'css'
}

export interface UseDeckReturn {
  deck: DeepReadonly<Ref<Deck>>
  decks: Deck[]
  setDeck: (d: Deck) => void
}

export function useDeck(): UseDeckReturn {
  function setDeck(d: Deck) {
    if (DECKS.includes(d)) {
      current.value = d
      try {
        localStorage.setItem(STORAGE_KEY, d)
      } catch {
        /* blocked storage */
      }
    }
  }

  return {
    deck: readonly(current),
    decks: DECKS,
    setDeck,
  }
}
