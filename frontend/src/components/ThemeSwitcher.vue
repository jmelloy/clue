<template>
  <div class="theme-switcher">
    <button
      v-for="t in themes"
      :key="t"
      class="theme-btn"
      :class="{ active: theme === t }"
      :title="labels[t]"
      @click="setTheme(t)"
    >
      <span class="theme-icon">{{ icons[t] }}</span>
    </button>
  </div>
</template>

<script setup>
import { useTheme } from "../composables/useTheme.js";

const { theme, themes, setTheme } = useTheme();

const icons = {
  dark: "\u{1F319}",    // crescent moon
  light: "\u{2600}",    // sun
  vintage: "\u{1F5FA}", // world map (closest to board game)
};

const labels = {
  dark: "Dark theme",
  light: "Light theme",
  vintage: "Vintage board theme",
};
</script>

<style scoped>
.theme-switcher {
  display: flex;
  gap: 0.25rem;
  align-items: center;
}

.theme-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1.5px solid var(--border-subtle, rgba(212, 168, 73, 0.15));
  background: var(--bg-panel, rgba(30, 24, 16, 0.95));
  cursor: pointer;
  transition: all 0.2s;
  padding: 0;
}

.theme-btn:hover {
  border-color: var(--accent, #d4a849);
  transform: scale(1.1);
}

.theme-btn.active {
  border-color: var(--accent, #d4a849);
  background: var(--accent-bg, rgba(212, 168, 73, 0.15));
  box-shadow: 0 0 8px var(--accent-glow, rgba(212, 168, 73, 0.2));
}

.theme-icon {
  font-size: 0.85rem;
  line-height: 1;
}
</style>
