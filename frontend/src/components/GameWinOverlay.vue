<template>
  <Teleport to="body">
    <Transition name="win-overlay">
      <div v-if="visible" class="win-overlay" @click="$emit('close')">
        <div class="win-overlay__content" @click.stop>
          <div class="win-overlay__banner">
            <div class="win-overlay__trophy">&#127942;</div>
            <h2 class="win-overlay__title">{{ winnerName }} wins!</h2>
            <p class="win-overlay__subtitle">Case Closed</p>
          </div>

          <div class="win-overlay__cards">
            <div class="win-overlay__card-slot" style="animation-delay: 0.2s">
              <div class="win-overlay__card-label">Suspect</div>
              <ClueCard :name="suspect" use-full-image size="large" />
            </div>
            <div class="win-overlay__card-slot" style="animation-delay: 0.5s">
              <div class="win-overlay__card-label">Weapon</div>
              <ClueCard :name="weapon" use-full-image size="large" />
            </div>
            <div class="win-overlay__card-slot" style="animation-delay: 0.8s">
              <div class="win-overlay__card-label">Room</div>
              <ClueCard :name="room" use-full-image size="large" />
            </div>
          </div>

          <button class="win-overlay__dismiss" @click="$emit('close')">
            Continue
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
  winnerName: { type: String, default: "" },
  suspect: { type: String, default: "" },
  weapon: { type: String, default: "" },
  room: { type: String, default: "" },
});

defineEmits(["close"]);
</script>

<style scoped>
.win-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
}

.win-overlay__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  padding: 48px 64px;
  background: linear-gradient(
    145deg,
    rgba(42, 32, 24, 0.97),
    rgba(26, 20, 8, 0.98)
  );
  border: 2px solid rgba(212, 168, 73, 0.4);
  border-radius: 20px;
  box-shadow: 0 0 60px rgba(212, 168, 73, 0.15), 0 30px 80px rgba(0, 0, 0, 0.7);
  animation: win-appear 0.5s ease;
  max-width: 90vw;
}

@keyframes win-appear {
  from {
    opacity: 0;
    transform: scale(0.7);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.win-overlay__banner {
  text-align: center;
}

.win-overlay__trophy {
  font-size: 4rem;
  animation: trophy-bounce 0.8s ease 0.3s both;
}

@keyframes trophy-bounce {
  0% {
    transform: scale(0);
    opacity: 0;
  }
  50% {
    transform: scale(1.3);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

.win-overlay__title {
  font-family: "Playfair Display", Georgia, serif;
  font-size: 2.8rem;
  font-weight: 900;
  color: #d4a849;
  letter-spacing: 0.05em;
  text-shadow: 0 2px 8px rgba(212, 168, 73, 0.3);
  margin: 8px 0 0;
}

.win-overlay__subtitle {
  font-family: "Crimson Text", Georgia, serif;
  font-size: 1.2rem;
  color: #8a7e6b;
  font-style: italic;
  margin-top: 4px;
}

.win-overlay__cards {
  display: flex;
  gap: 32px;
  justify-content: center;
  flex-wrap: wrap;
}

.win-overlay__card-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  animation: card-deal 0.5s ease both;
}

@keyframes card-deal {
  from {
    opacity: 0;
    transform: translateY(30px) scale(0.8);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.win-overlay__card-label {
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #6a6050;
  font-weight: 600;
}

.win-overlay__dismiss {
  padding: 14px 48px;
  border-radius: 8px;
  border: 1px solid rgba(212, 168, 73, 0.4);
  background: linear-gradient(135deg, rgba(212, 168, 73, 0.15), rgba(212, 168, 73, 0.08));
  color: #d4a849;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 1.15rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.25s;
  letter-spacing: 0.04em;
}

.win-overlay__dismiss:hover {
  background: linear-gradient(135deg, rgba(212, 168, 73, 0.25), rgba(212, 168, 73, 0.15));
  border-color: rgba(212, 168, 73, 0.6);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(212, 168, 73, 0.15);
}

/* Transition */
.win-overlay-enter-active {
  transition: opacity 0.4s ease;
}

.win-overlay-leave-active {
  transition: opacity 0.3s ease;
}

.win-overlay-enter-from,
.win-overlay-leave-to {
  opacity: 0;
}
</style>
