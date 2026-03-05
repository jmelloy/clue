<template>
  <div
    class="clue-card"
    :class="[`clue-card--${type}`, { 'clue-card--clickable': clickable }]"
    @click="$emit('click')"
  >
    <div class="clue-card__frame" :class="`clue-card__frame--${type}`">
      <img
        v-if="imageUrl"
        :src="imageUrl"
        :alt="name"
        class="clue-card__image"
        :class="`clue-card__image--${type}`"
      />
      <span v-else class="clue-card__icon">{{ icon }}</span>
    </div>
    <div class="clue-card__label">{{ name }}</div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import {
  cardType,
  cardIcon,
  cardFullImageUrl,
  cardImageUrl,
  hasCardImage,
} from "../constants/clue.js";

const props = defineProps({
  name: { type: String, required: true },
  size: { type: String, default: "medium" }, // "small", "medium", "large"
  clickable: { type: Boolean, default: false },
  useFullImage: { type: Boolean, default: false },
});

defineEmits(["click"]);

const type = computed(() => cardType(props.name));
const icon = computed(() => cardIcon(props.name));
const imageUrl = computed(() => {
  if (props.useFullImage) return cardFullImageUrl(props.name);
  return hasCardImage(props.name) ? cardImageUrl(props.name) : "";
});
</script>

<style scoped>
.clue-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px;
  background: linear-gradient(145deg, #2a2018, #1a1408);
  border: 2px solid rgba(212, 168, 73, 0.25);
  border-radius: 8px;
  width: 110px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  transition: all 0.25s ease;
}

.clue-card--clickable {
  cursor: pointer;
}

.clue-card--clickable:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5), 0 0 15px rgba(212, 168, 73, 0.15);
  border-color: rgba(212, 168, 73, 0.5);
}

/* --- Suspect: circle frame --- */
.clue-card--suspect {
  border-color: rgba(155, 27, 48, 0.4);
}

.clue-card__frame--suspect {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  overflow: hidden;
  border: 3px solid rgba(155, 27, 48, 0.6);
  box-shadow: 0 0 12px rgba(155, 27, 48, 0.2), inset 0 0 8px rgba(0, 0, 0, 0.4);
  background: rgba(155, 27, 48, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.clue-card__image--suspect {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
}

/* --- Weapon: diamond frame --- */
.clue-card--weapon {
  border-color: rgba(26, 58, 107, 0.4);
}

.clue-card__frame--weapon {
  width: 80px;
  height: 80px;
  transform: rotate(45deg);
  overflow: hidden;
  border: 3px solid rgba(26, 58, 107, 0.6);
  box-shadow: 0 0 12px rgba(26, 58, 107, 0.2), inset 0 0 8px rgba(0, 0, 0, 0.4);
  background: rgba(26, 58, 107, 0.1);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.clue-card__image--weapon {
  width: 140%;
  height: 140%;
  object-fit: cover;
  object-position: center center;
  transform: rotate(-45deg);
}

/* --- Room: plain rectangular frame --- */
.clue-card--room {
  border-color: rgba(26, 107, 60, 0.4);
}

.clue-card__frame--room {
  width: 90px;
  height: 65px;
  overflow: hidden;
  border: 2px solid rgba(26, 107, 60, 0.5);
  box-shadow: 0 0 8px rgba(26, 107, 60, 0.15), inset 0 0 6px rgba(0, 0, 0, 0.3);
  background: rgba(26, 107, 60, 0.1);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.clue-card__image--room {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center center;
}

/* --- Icon fallback --- */
.clue-card__icon {
  font-size: 2rem;
}

/* --- Label --- */
.clue-card__label {
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.75rem;
  font-weight: 700;
  text-align: center;
  letter-spacing: 0.03em;
  line-height: 1.2;
  color: #d4a849;
}
</style>
