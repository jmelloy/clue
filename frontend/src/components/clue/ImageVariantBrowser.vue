<template>
  <div class="variant-browser">
    <header class="browser-header">
      <h1>Clue Image Variants</h1>
      <p class="subtitle">Preview all artwork sets for the Clue game</p>
    </header>

    <nav class="variant-tabs">
      <button
        v-for="v in IMAGE_VARIANTS"
        :key="v.id"
        class="tab-btn"
        :class="{ active: activeVariantId === v.id }"
        @click="activeVariantId = v.id"
      >
        {{ v.label }}
      </button>
    </nav>

    <div v-if="variant" class="variant-content">
      <p class="variant-desc">{{ variant.description }}</p>

      <section class="image-section">
        <h2>Board</h2>
        <div class="board-preview">
          <img :src="variant.board" alt="Board" class="board-img" />
        </div>
      </section>

      <section class="image-section">
        <h2>Suspects</h2>
        <div class="image-grid">
          <div v-for="(url, name) in variant.suspects" :key="name" class="image-card">
            <img :src="url" :alt="name" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </div>
        </div>
      </section>

      <section class="image-section">
        <h2>Weapons</h2>
        <div class="image-grid">
          <div v-for="(url, name) in variant.weapons" :key="name" class="image-card">
            <img :src="url" :alt="name" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </div>
        </div>
      </section>

      <section class="image-section">
        <h2>Rooms</h2>
        <div class="image-grid">
          <div v-for="(url, name) in variant.rooms" :key="name" class="image-card">
            <img :src="url" :alt="name" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </div>
        </div>
      </section>
    </div>

    <footer class="browser-footer">
      <button class="go-home-btn" @click="$emit('go-home')">Back to Home</button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { IMAGE_VARIANTS } from '../../constants/clue'

defineEmits<{ 'go-home': [] }>()

const activeVariantId = ref(IMAGE_VARIANTS[0].id)
const variant = computed(() => IMAGE_VARIANTS.find(v => v.id === activeVariantId.value))

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.opacity = '0.2'
  img.alt = 'missing'
}
</script>

<style scoped>
.variant-browser {
  min-height: 100vh;
  background: #1a1a2e;
  color: #e8e8e8;
  font-family: 'Georgia', serif;
  padding: 0 0 3rem;
}

.browser-header {
  background: #0f0f1a;
  padding: 2rem;
  text-align: center;
  border-bottom: 2px solid #8b0000;
}

.browser-header h1 {
  margin: 0;
  font-size: 2rem;
  color: #c8a04a;
  letter-spacing: 0.05em;
}

.subtitle {
  margin: 0.4rem 0 0;
  color: #888;
  font-style: italic;
}

.variant-tabs {
  display: flex;
  gap: 0;
  border-bottom: 2px solid #333;
  background: #111;
  padding: 0 2rem;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  color: #aaa;
  cursor: pointer;
  font-size: 1rem;
  font-family: inherit;
  padding: 0.9rem 1.5rem;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -2px;
}

.tab-btn:hover {
  color: #e8e8e8;
}

.tab-btn.active {
  color: #c8a04a;
  border-bottom-color: #c8a04a;
}

.variant-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.variant-desc {
  color: #999;
  font-style: italic;
  margin: 0 0 2rem;
}

.image-section {
  margin-bottom: 3rem;
}

.image-section h2 {
  color: #c8a04a;
  border-bottom: 1px solid #333;
  padding-bottom: 0.4rem;
  margin-bottom: 1rem;
  font-size: 1.2rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.board-preview {
  max-width: 480px;
}

.board-img {
  width: 100%;
  border-radius: 4px;
  border: 1px solid #333;
  display: block;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 1rem;
}

.image-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: #111827;
  border: 1px solid #2a2a3e;
  border-radius: 6px;
  padding: 0.75rem 0.5rem 0.5rem;
  gap: 0.5rem;
  transition: border-color 0.15s;
}

.image-card:hover {
  border-color: #c8a04a;
}

.image-card img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 4px;
  display: block;
}

.image-label {
  font-size: 0.78rem;
  color: #ccc;
  text-align: center;
  line-height: 1.3;
}

.browser-footer {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
}

.go-home-btn {
  background: #8b0000;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.95rem;
  padding: 0.6rem 1.4rem;
  transition: background 0.15s;
}

.go-home-btn:hover {
  background: #a00000;
}
</style>
