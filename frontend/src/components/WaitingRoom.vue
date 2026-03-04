<template>
  <div class="waiting-room">
    <!-- Atmospheric background -->
    <div class="atmosphere">
      <div class="fog fog-1"></div>
      <div class="fog fog-2"></div>
      <div class="vignette"></div>
    </div>

    <div class="particles">
      <span v-for="n in 12" :key="n" class="particle" :style="particleStyle(n)"></span>
    </div>

    <div class="room-content">
      <!-- Header -->
      <header class="room-header">
        <h1 class="title">CLUE</h1>
        <p class="tagline">The Suspects Are Gathering</p>
      </header>

      <!-- Case file ID card -->
      <div class="case-file">
        <div class="case-file-label">Case File No.</div>
        <div class="case-file-id">{{ gameId }}</div>
        <button class="copy-btn" @click="copyLink" :class="{ copied: copied }">
          <span v-if="copied">&#x2713; Copied</span>
          <span v-else>&#x1F517; Copy Invite Link</span>
        </button>
      </div>

      <!-- Suspects table -->
      <section class="suspects-panel">
        <div class="panel-header">
          <h2>Suspects Present</h2>
          <span class="count-badge">{{ players.length }} / 6</span>
        </div>

        <div class="suspects-grid">
          <!-- Filled seats -->
          <div
            v-for="p in players"
            :key="p.id"
            class="suspect-card"
            :class="{ 'is-you': p.id === playerId }"
          >
            <div class="suspect-token" :style="tokenStyle(p)">
              {{ abbr(p.character) }}
            </div>
            <div class="suspect-details">
              <span class="suspect-name">
                {{ p.name }}
                <span v-if="p.id === playerId" class="you-tag">you</span>
              </span>
              <span class="suspect-character">{{ p.character }}</span>
            </div>
            <span class="type-badge" :class="'type-' + p.type">{{ typeLabel(p.type) }}</span>
          </div>

          <!-- Empty seats -->
          <div
            v-for="n in (6 - players.length)"
            :key="'empty-' + n"
            class="suspect-card empty"
          >
            <div class="suspect-token empty-token">?</div>
            <div class="suspect-details">
              <span class="suspect-name empty-name">Awaiting suspect...</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Add agents -->
      <div class="agent-controls" v-if="players.length < 6">
        <button class="btn-agent" @click="addAgent('agent')" :disabled="addingAgent">
          <span class="btn-agent-icon">&#x1F3B2;</span> Add Agent
        </button>
        <button class="btn-agent btn-agent-llm" @click="addAgent('llm_agent')" :disabled="addingAgent">
          <span class="btn-agent-icon">&#x1F9E0;</span> Add LLM Agent
        </button>
      </div>

      <!-- Start game -->
      <button
        class="btn-start"
        :disabled="players.length < 2"
        @click="startGame"
      >
        <span class="btn-start-text">Begin the Investigation</span>
        <span class="btn-start-arrow">&rarr;</span>
      </button>
      <p v-if="players.length < 2" class="hint">At least 2 suspects are needed to begin.</p>

      <!-- Error -->
      <p v-if="error" class="error-text">{{ error }}</p>

      <!-- Leave -->
      <button class="btn-ghost" @click="$emit('leave-game')">Leave the Mansion</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const CHARACTER_COLORS = {
  'Miss Scarlett':    { bg: '#9b1b30', text: '#fff' },
  'Colonel Mustard':  { bg: '#c8a415', text: '#1a1008' },
  'Mrs. White':       { bg: '#d8d0c8', text: '#2a2520' },
  'Reverend Green':   { bg: '#1a6b3c', text: '#fff' },
  'Mrs. Peacock':     { bg: '#1a3a6b', text: '#fff' },
  'Professor Plum':   { bg: '#5c2d82', text: '#fff' },
}

const CHARACTER_ABBR = {
  'Miss Scarlett': 'Sc',
  'Colonel Mustard': 'Mu',
  'Mrs. White': 'Wh',
  'Reverend Green': 'Gr',
  'Mrs. Peacock': 'Pe',
  'Professor Plum': 'Pl',
}

const props = defineProps({
  gameId: String,
  playerId: String,
  players: Array,
})
const emit = defineEmits(['game-started', 'leave-game'])

const error = ref('')
const copied = ref(false)
const addingAgent = ref(false)

function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

function tokenStyle(player) {
  const colors = CHARACTER_COLORS[player.character] ?? { bg: '#444', text: '#fff' }
  return { backgroundColor: colors.bg, color: colors.text }
}

function typeLabel(type) {
  if (type === 'human') return 'Human'
  if (type === 'agent') return 'AI'
  if (type === 'llm_agent') return 'LLM'
  if (type === 'wanderer') return 'NPC'
  return type
}

function particleStyle(n) {
  const x = Math.sin(n * 5.1) * 50 + 50
  const delay = (n * 2.3) % 10
  const duration = 10 + (n % 4) * 3
  const size = 1 + (n % 2)
  return {
    left: `${x}%`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
    width: `${size}px`,
    height: `${size}px`,
  }
}

function copyLink() {
  const url = `${window.location.origin}/game/${props.gameId}`
  navigator.clipboard.writeText(url)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function addAgent(agentType) {
  error.value = ''
  addingAgent.value = true
  try {
    const res = await fetch(`/games/${props.gameId}/add_agent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_type: agentType })
    })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to add agent'
    }
  } catch (e) {
    error.value = 'Error: ' + e.message
  } finally {
    addingAgent.value = false
  }
}

async function startGame() {
  error.value = ''
  try {
    const res = await fetch(`/games/${props.gameId}/start`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail ?? 'Failed to start'
      return
    }
    const state = await res.json()
    emit('game-started', state)
  } catch (e) {
    error.value = 'Error: ' + e.message
  }
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.waiting-room {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  font-family: 'Crimson Text', Georgia, serif;
  background: #0a0908;
}

/* === Atmosphere === */
.atmosphere {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.fog {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background: radial-gradient(ellipse at 40% 30%, #d4a849 0%, transparent 55%),
              radial-gradient(ellipse at 65% 75%, #6b2a2a 0%, transparent 50%);
  animation: fog-drift 25s ease-in-out infinite alternate;
}

.fog-2 {
  opacity: 0.02;
  background: radial-gradient(ellipse at 70% 20%, #d4a849 0%, transparent 50%),
              radial-gradient(ellipse at 30% 80%, #2a3a4a 0%, transparent 45%);
  animation-delay: -12s;
  animation-direction: alternate-reverse;
}

@keyframes fog-drift {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(30px, -15px) scale(1.08); }
}

.vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 35%, #0a0908 85%);
}

/* === Particles === */
.particles {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}

.particle {
  position: absolute;
  bottom: -10px;
  border-radius: 50%;
  background: rgba(212, 168, 73, 0.2);
  animation: float-up linear infinite;
  opacity: 0;
}

@keyframes float-up {
  0% { transform: translateY(0) translateX(0); opacity: 0; }
  10% { opacity: 0.5; }
  90% { opacity: 0.15; }
  100% { transform: translateY(-100vh) translateX(20px); opacity: 0; }
}

/* === Content === */
.room-content {
  position: relative;
  z-index: 2;
  max-width: 520px;
  margin: 0 auto;
  padding: 2.5rem 1.25rem 3rem;
  text-align: center;
}

/* === Header === */
.room-header {
  margin-bottom: 2rem;
  animation: fade-down 0.8s ease-out;
}

@keyframes fade-down {
  0% { opacity: 0; transform: translateY(-12px); }
  100% { opacity: 1; transform: translateY(0); }
}

.title {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 2.5rem;
  font-weight: 900;
  letter-spacing: 0.3em;
  color: #d4a849;
  text-shadow: 0 0 30px rgba(212, 168, 73, 0.15);
  margin-right: -0.3em;
}

.tagline {
  font-style: italic;
  color: #6a6050;
  font-size: 0.95rem;
  margin-top: 0.3rem;
  letter-spacing: 0.06em;
}

/* === Case file ID === */
.case-file {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1.75rem;
  padding: 0.9rem 1.25rem;
  border-radius: 6px;
  background: rgba(212, 168, 73, 0.04);
  border: 1px solid rgba(212, 168, 73, 0.1);
  animation: fade-in 0.8s ease-out 0.15s both;
}

@keyframes fade-in {
  0% { opacity: 0; }
  100% { opacity: 1; }
}

.case-file-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #6a6050;
}

.case-file-id {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.25rem;
  font-weight: 700;
  color: #d4a849;
  letter-spacing: 0.15em;
}

.copy-btn {
  padding: 0.35rem 0.75rem;
  border-radius: 4px;
  border: 1px solid rgba(212, 168, 73, 0.15);
  background: transparent;
  color: #6a6050;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.25s;
}

.copy-btn:hover {
  border-color: rgba(212, 168, 73, 0.35);
  color: #d4a849;
}

.copy-btn.copied {
  border-color: rgba(76, 175, 80, 0.3);
  color: #4caf50;
}

/* === Suspects panel === */
.suspects-panel {
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.95), rgba(18, 14, 10, 0.97));
  border: 1px solid rgba(212, 168, 73, 0.1);
  padding: 1.5rem 1.25rem;
  margin-bottom: 1.25rem;
  animation: card-appear 0.6s ease-out 0.2s both;
}

@keyframes card-appear {
  0% { opacity: 0; transform: translateY(14px); }
  100% { opacity: 1; transform: translateY(0); }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.panel-header h2 {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: #e8dcc8;
  letter-spacing: 0.02em;
}

.count-badge {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: #8a7e6b;
  padding: 0.2rem 0.6rem;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.03);
}

/* === Suspect cards === */
.suspects-grid {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.suspect-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.75rem;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: all 0.25s;
  animation: suspect-enter 0.4s ease-out both;
}

.suspect-card:nth-child(1) { animation-delay: 0.3s; }
.suspect-card:nth-child(2) { animation-delay: 0.4s; }
.suspect-card:nth-child(3) { animation-delay: 0.5s; }
.suspect-card:nth-child(4) { animation-delay: 0.6s; }
.suspect-card:nth-child(5) { animation-delay: 0.7s; }
.suspect-card:nth-child(6) { animation-delay: 0.8s; }

@keyframes suspect-enter {
  0% { opacity: 0; transform: translateX(-8px); }
  100% { opacity: 1; transform: translateX(0); }
}

.suspect-card.is-you {
  background: rgba(212, 168, 73, 0.04);
  border-color: rgba(212, 168, 73, 0.12);
}

.suspect-card.empty {
  opacity: 0.35;
}

.suspect-token {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  font-family: 'Crimson Text', Georgia, serif;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  flex-shrink: 0;
}

.empty-token {
  background: rgba(255, 255, 255, 0.05);
  color: #4a4030;
  box-shadow: none;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  font-size: 0.8rem;
}

.suspect-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  text-align: left;
  min-width: 0;
}

.suspect-name {
  color: #e8dcc8;
  font-size: 0.95rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.empty-name {
  color: #3a3528;
  font-weight: 400;
  font-style: italic;
}

.you-tag {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #d4a849;
  background: rgba(212, 168, 73, 0.1);
  padding: 0.1rem 0.35rem;
  border-radius: 2px;
}

.suspect-character {
  color: #5a5040;
  font-size: 0.8rem;
  font-style: italic;
}

.type-badge {
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.2rem 0.5rem;
  border-radius: 3px;
  flex-shrink: 0;
}

.type-human {
  background: rgba(255, 255, 255, 0.04);
  color: #6a6050;
}

.type-agent {
  background: rgba(212, 168, 73, 0.1);
  color: #d4a849;
}

.type-llm_agent {
  background: rgba(92, 45, 130, 0.15);
  color: #a070c8;
}

.type-wanderer {
  background: rgba(255, 255, 255, 0.04);
  color: #5a5040;
}

/* === Agent controls === */
.agent-controls {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
  margin-bottom: 1.5rem;
  animation: fade-in 0.6s ease-out 0.5s both;
}

.btn-agent {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 1rem;
  border-radius: 5px;
  border: 1px solid rgba(212, 168, 73, 0.15);
  background: transparent;
  color: #8a7e6b;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.25s;
}

.btn-agent:hover:not(:disabled) {
  border-color: rgba(212, 168, 73, 0.35);
  color: #d4a849;
  background: rgba(212, 168, 73, 0.04);
}

.btn-agent-llm {
  border-color: rgba(92, 45, 130, 0.2);
}

.btn-agent-llm:hover:not(:disabled) {
  border-color: rgba(92, 45, 130, 0.5);
  color: #a070c8;
  background: rgba(92, 45, 130, 0.05);
}

.btn-agent:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-agent-icon {
  font-size: 0.9rem;
}

/* === Start button === */
.btn-start {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 2.25rem;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
  animation: fade-in 0.6s ease-out 0.6s both;
}

.btn-start::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.15), transparent);
  opacity: 0;
  transition: opacity 0.3s;
}

.btn-start:hover:not(:disabled)::before {
  opacity: 1;
}

.btn-start:hover:not(:disabled) {
  box-shadow: 0 6px 30px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.btn-start:hover:not(:disabled) .btn-start-arrow {
  transform: translateX(3px);
}

.btn-start:active:not(:disabled) {
  transform: translateY(0);
}

.btn-start:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-start-arrow {
  transition: transform 0.3s;
  font-size: 1.1rem;
}

/* === Hint === */
.hint {
  color: #4a4030;
  font-style: italic;
  font-size: 0.85rem;
  margin-top: 0.6rem;
  animation: fade-in 0.6s ease-out 0.7s both;
}

/* === Error === */
.error-text {
  color: #c45050;
  font-size: 0.9rem;
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 5px;
  background: rgba(139, 42, 42, 0.1);
  border: 1px solid rgba(139, 42, 42, 0.2);
  display: inline-block;
}

/* === Ghost button === */
.btn-ghost {
  display: inline-block;
  margin-top: 1.25rem;
  padding: 0.4rem 0;
  background: none;
  border: none;
  color: #3a3528;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  cursor: pointer;
  transition: color 0.2s;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.btn-ghost:hover {
  color: #6a6050;
}

/* === Responsive === */
@media (max-width: 480px) {
  .room-content {
    padding: 2rem 1rem 2.5rem;
  }

  .title {
    font-size: 2rem;
  }

  .case-file {
    flex-direction: column;
    gap: 0.5rem;
  }

  .agent-controls {
    flex-direction: column;
    align-items: center;
  }

  .btn-agent {
    width: 100%;
    justify-content: center;
  }
}
</style>
