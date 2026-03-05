import { ref, watch, readonly } from 'vue'

const THEMES = ['dark', 'light', 'vintage']
const STORAGE_KEY = 'clue-theme'

// Shared singleton state
const current = ref(loadSaved())

function loadSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && THEMES.includes(saved)) return saved
  } catch (_) { /* SSR / blocked storage */ }
  return 'dark'
}

// Apply the data-theme attribute on <html> whenever theme changes
watch(current, (t) => {
  document.documentElement.setAttribute('data-theme', t)
  try { localStorage.setItem(STORAGE_KEY, t) } catch (_) { /* */ }
}, { immediate: true })

export function useTheme() {
  function setTheme(t) {
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
