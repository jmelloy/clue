<template>
  <div class="theme-switcher" :class="'current-' + theme">
    <button
      v-for="t in themes"
      :key="t"
      class="theme-btn"
      :class="{ active: theme === t }"
      :title="labels[t]"
      @click="setTheme(t)"
    >
      <span class="theme-icon">{{ icons[t] }}</span>
      <span class="theme-label">{{ labels[t] }}</span>
    </button>
  </div>
</template>

<script setup>
import { useTheme } from '../composables/useTheme'

const { theme, themes, setTheme } = useTheme()

const icons = { dark: '\u{1F319}', light: '\u{2600}', vintage: '\u{1F3B2}' }
const labels = { dark: 'Dark', light: 'Light', vintage: 'Vintage' }
</script>

<style scoped>
.theme-switcher {
  display: flex;
  gap: 2px;
  background: var(--bg-input, rgba(255,255,255,0.03));
  border-radius: 5px;
  padding: 2px;
  border: 1px solid var(--border-panel, rgba(212,168,73,0.08));
}

.theme-btn {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 3px;
  background: transparent;
  color: var(--text-dim, #5a5040);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.2s;
}

.theme-btn:hover {
  color: var(--text-secondary, #8a7e6b);
  background: var(--bg-hover, rgba(212,168,73,0.04));
}

.theme-btn.active {
  color: var(--accent, #d4a849);
  background: var(--accent-bg, rgba(212,168,73,0.06));
}

.theme-icon {
  font-size: 0.8rem;
  line-height: 1;
}

.theme-label {
  letter-spacing: 0.03em;
}

@media (max-width: 500px) {
  .theme-label {
    display: none;
  }

  .theme-btn {
    padding: 0.25rem 0.35rem;
  }
}
</style>
