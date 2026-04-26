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
        <h2>Suspects</h2>
        <div class="image-grid">
          <button
            v-for="(url, name) in variant.suspects"
            :key="name"
            type="button"
            class="image-card"
            @click="openLightbox(url, String(name))"
          >
            <img :src="url" :alt="String(name)" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </button>
        </div>
      </section>

      <section class="image-section">
        <h2>Weapons</h2>
        <div class="image-grid">
          <button
            v-for="(url, name) in variant.weapons"
            :key="name"
            type="button"
            class="image-card"
            @click="openLightbox(url, String(name))"
          >
            <img :src="url" :alt="String(name)" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </button>
        </div>
      </section>

      <section class="image-section">
        <h2>Rooms</h2>
        <div class="image-grid">
          <button
            v-for="(url, name) in variant.rooms"
            :key="name"
            type="button"
            class="image-card"
            @click="openLightbox(url, String(name))"
          >
            <img :src="url" :alt="String(name)" @error="onImgError" />
            <span class="image-label">{{ name }}</span>
          </button>
        </div>
      </section>

      <section class="image-section">
        <h2>Board</h2>
        <button
          type="button"
          class="board-preview"
          @click="openLightbox(variant.board, 'Board')"
        >
          <img :src="variant.board" alt="Board" class="board-img" />
        </button>
      </section>
    </div>

    <footer class="browser-footer">
      <button class="go-home-btn" @click="$emit('go-home')">Back to Home</button>
    </footer>

    <div
      v-if="lightbox"
      class="lightbox"
      role="dialog"
      aria-modal="true"
      :aria-label="lightbox.label"
      @click.self="closeLightbox"
    >
      <button
        type="button"
        class="lightbox-close"
        aria-label="Close"
        @click="closeLightbox"
      >
        ×
      </button>
      <figure class="lightbox-figure" @click.self="closeLightbox">
        <img :src="lightbox.url" :alt="lightbox.label" class="lightbox-img" />
        <figcaption class="lightbox-caption">{{ lightbox.label }}</figcaption>
      </figure>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { IMAGE_VARIANTS } from '../../constants/clue'

defineEmits<{ 'go-home': [] }>()

const activeVariantId = ref(IMAGE_VARIANTS[0].id)
const variant = computed(() => IMAGE_VARIANTS.find(v => v.id === activeVariantId.value))

const lightbox = ref<{ url: string; label: string } | null>(null)

function openLightbox(url: string, label: string) {
  lightbox.value = { url, label }
}

function closeLightbox() {
  lightbox.value = null
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && lightbox.value) closeLightbox()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

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
  width: 100%;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  display: block;
  font: inherit;
  color: inherit;
  border-radius: 4px;
  transition: transform 0.15s, box-shadow 0.15s;
}

.board-preview:hover,
.board-preview:focus-visible {
  transform: scale(1.01);
  box-shadow: 0 0 0 2px #c8a04a;
  outline: none;
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
  transition: border-color 0.15s, transform 0.15s;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
  width: 100%;
}

.image-card:hover,
.image-card:focus-visible {
  border-color: #c8a04a;
  transform: translateY(-2px);
  outline: none;
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

.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
  cursor: zoom-out;
}

.lightbox-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: none;
  border: none;
  color: #e8e8e8;
  font-size: 2.5rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  transition: background 0.15s;
}

.lightbox-close:hover,
.lightbox-close:focus-visible {
  background: rgba(255, 255, 255, 0.1);
  outline: none;
}

.lightbox-figure {
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  max-width: 100%;
  max-height: 100%;
  cursor: default;
}

.lightbox-img {
  max-width: 100%;
  max-height: calc(100vh - 8rem);
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid #333;
  background: #1a1a2e;
}

.lightbox-caption {
  color: #c8a04a;
  font-size: 1rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
</style>
