import { ref, watch } from "vue";

const THEMES = ["dark", "light", "vintage"];
const STORAGE_KEY = "clue-theme";

// Shared reactive state (singleton across all component instances)
const currentTheme = ref(loadTheme());

function loadTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && THEMES.includes(saved)) return saved;
  } catch (_) {
    // localStorage may be unavailable
  }
  return "dark";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

// Apply immediately on load
applyTheme(currentTheme.value);

// Persist and apply whenever theme changes
watch(currentTheme, (theme) => {
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch (_) {
    // ignore
  }
});

export function useTheme() {
  function setTheme(theme) {
    if (THEMES.includes(theme)) {
      currentTheme.value = theme;
    }
  }

  function cycleTheme() {
    const idx = THEMES.indexOf(currentTheme.value);
    currentTheme.value = THEMES[(idx + 1) % THEMES.length];
  }

  return {
    theme: currentTheme,
    themes: THEMES,
    setTheme,
    cycleTheme,
  };
}
