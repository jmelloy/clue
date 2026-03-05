<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div v-if="visible" class="card-lightbox" @click="$emit('close')">
        <div class="card-lightbox__content" @click.stop>
          <div class="card-lightbox__header">
            <span class="card-lightbox__eye">&#128065;</span>
            <div class="card-lightbox__text">
              <strong>{{ shownByName }}</strong> showed you a card
            </div>
          </div>
          <div class="card-lightbox__card-area">
            <div class="card-lightbox__reveal">
              <ClueCard :name="cardName" use-full-image size="large" />
            </div>
          </div>
          <button class="card-lightbox__dismiss" @click="$emit('close')">
            Dismiss
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import ClueCard from "./ClueCard.vue";

defineProps({
  visible: { type: Boolean, default: false },
  cardName: { type: String, default: "" },
  shownByName: { type: String, default: "Someone" },
});

defineEmits(["close"]);
</script>

<style scoped>
.card-lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.card-lightbox__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  padding: 40px 56px;
  background: linear-gradient(145deg, #2a2018, #1a1408);
  border: 2px solid rgba(212, 168, 73, 0.3);
  border-radius: 16px;
  box-shadow: 0 0 40px rgba(212, 168, 73, 0.1), 0 24px 60px rgba(0, 0, 0, 0.6);
  animation: lightbox-enter 0.4s ease;
}

@keyframes lightbox-enter {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.card-lightbox__header {
  display: flex;
  align-items: center;
  gap: 14px;
  color: #e8dcc8;
  font-size: 1.3rem;
  font-family: "Crimson Text", Georgia, serif;
}

.card-lightbox__eye {
  font-size: 2.2rem;
}

.card-lightbox__card-area {
  display: flex;
  justify-content: center;
}

.card-lightbox__reveal {
  animation: card-flip 0.6s ease;
  transform-style: preserve-3d;
}

@keyframes card-flip {
  0% {
    transform: rotateY(90deg) scale(0.8);
    opacity: 0;
  }
  50% {
    transform: rotateY(0deg) scale(1.05);
    opacity: 1;
  }
  100% {
    transform: rotateY(0deg) scale(1);
  }
}

.card-lightbox__dismiss {
  padding: 12px 40px;
  border-radius: 8px;
  border: 1px solid rgba(212, 168, 73, 0.3);
  background: rgba(212, 168, 73, 0.1);
  color: #d4a849;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 1.05rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.card-lightbox__dismiss:hover {
  background: rgba(212, 168, 73, 0.2);
  border-color: rgba(212, 168, 73, 0.5);
}

/* Transition */
.lightbox-enter-active {
  transition: opacity 0.3s ease;
}

.lightbox-leave-active {
  transition: opacity 0.2s ease;
}

.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}
</style>
