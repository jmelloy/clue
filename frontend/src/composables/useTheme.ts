import { ref, watch, readonly, type DeepReadonly, type Ref } from 'vue'
import type { Theme } from '../types'

const THEMES: Theme[] = ['dark', 'light', 'vintage']
const STORAGE_KEY = 'clue-theme'

// Shared singleton state
const current = ref<Theme>(loadSaved())

function loadSaved(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && THEMES.includes(saved as Theme)) return saved as Theme
  } catch {
    /* SSR / blocked storage */
  }
  return 'dark'
}

// Apply the data-theme attribute on <html> whenever theme changes
watch(
  current,
  (t) => {
    document.documentElement.setAttribute('data-theme', t)
    try {
      localStorage.setItem(STORAGE_KEY, t)
    } catch {
      /* */
    }
  },
  { immediate: true }
)

export interface UseThemeReturn {
  theme: DeepReadonly<Ref<Theme>>
  themes: Theme[]
  setTheme: (t: Theme) => void
  cycleTheme: () => void
}

export function useTheme(): UseThemeReturn {
  function setTheme(t: Theme) {
    if (THEMES.includes(t)) current.value = t
  }

  function cycleTheme() {
    const i = THEMES.indexOf(current.value)
    current.value = THEMES[(i + 1) % THEMES.length]
  }

  return {
    theme: readonly(current),
    themes: THEMES,
    setTheme,
    cycleTheme
  }
}
