<template>
  <div class="player-pawn" :class="{
    'has-image': !!imageSrc,
    'wanderer-pawn': wanderer
  }" :style="pawnStyle">
    <img v-if="imageSrc" :src="imageSrc" :alt="character" class="pawn-portrait" />
    <span v-else>{{ abbr(character) }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CARD_IMAGES, abbr, characterColors } from '../../constants/clue'

const props = defineProps({
  character: { type: String, required: true },
  size: { type: String, default: null },
  wanderer: { type: Boolean, default: false }
})

const imageSrc = computed(() => CARD_IMAGES[props.character] || '')

const pawnStyle = computed(() => {
  const { bg, text } = characterColors(props.character)
  const style = {
    backgroundColor: bg,
    color: text,
    '--pawn-border': bg
  }
  if (props.size) {
    style.width = props.size
    style.height = props.size
  }
  if (props.wanderer) {
    style.opacity = 0.5
  }
  return style
})
</script>

<style scoped>
.player-pawn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 0.55rem;
  font-weight: bold;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  flex-shrink: 0;
  overflow: hidden;
}

.player-pawn.has-image {
  background: none !important;
  border: 1.5px solid;
  border-color: var(--pawn-border, rgba(255, 255, 255, 0.5));
}

.pawn-portrait {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
  border-radius: 50%;
  display: block;
  clip-path: circle(50%);
}
</style>
