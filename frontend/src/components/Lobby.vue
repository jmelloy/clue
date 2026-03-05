<template>
  <div class="lobby">
    <!-- Atmospheric background layers -->
    <div class="atmosphere">
      <div class="fog fog-1"></div>
      <div class="fog fog-2"></div>
      <div class="vignette"></div>
    </div>

    <!-- Floating dust particles -->
    <div class="particles">
      <span
        v-for="n in 20"
        :key="n"
        class="particle"
        :style="particleStyle(n)"
      ></span>
    </div>

    <div class="lobby-content">
      <!-- Hero title -->
      <header class="hero">
        <div class="chandelier">
          <div class="chain"></div>
          <div class="light-fixture">
            <div class="glow"></div>
          </div>
        </div>
        <div class="title-frame">
          <div class="frame-corner tl"></div>
          <div class="frame-corner tr"></div>
          <div class="frame-corner bl"></div>
          <div class="frame-corner br"></div>
          <h1 class="title">CLUE</h1>
          <p class="tagline">A Mystery Awaits at Tudor Mansion</p>
        </div>
        <div class="weapon-icons">
          <span class="weapon-icon" title="Candlestick">&#x1F56F;</span>
          <span class="divider-dot"></span>
          <span class="weapon-icon" title="Knife">&#x1F5E1;</span>
          <span class="divider-dot"></span>
          <span class="weapon-icon" title="Revolver">&#x1F52B;</span>
          <span class="divider-dot"></span>
          <span class="weapon-icon" title="Rope">&#x1FA62;</span>
          <span class="divider-dot"></span>
          <span class="weapon-icon" title="Wrench">&#x1F527;</span>
          <span class="divider-dot"></span>
          <span class="weapon-icon" title="Lead Pipe">&#x26CF;</span>
        </div>
      </header>

      <!-- URL-based game join view -->
      <template v-if="urlGameId">
        <section class="card" v-if="urlGameLoading">
          <div class="card-inner">
            <p class="loading-text">
              <span class="loading-spinner"></span>
              Investigating game {{ urlGameId }}...
            </p>
          </div>
        </section>

        <section class="card" v-else-if="urlGameError">
          <div class="card-inner">
            <p class="error-text">{{ urlGameError }}</p>
            <button class="btn-ghost" @click="$emit('clear-url-game')">
              Return to Foyer
            </button>
          </div>
        </section>

        <section class="card" v-else>
          <div class="card-inner">
            <div class="card-header">
              <span class="card-label">Case File</span>
              <h2>Game {{ urlGameId }}</h2>
            </div>
            <p
              class="status-badge"
              :class="urlGameState?.status"
              v-if="urlGameState"
            >
              <span class="status-dot"></span>
              {{ urlGameStatusText }}
              <span v-if="urlGameState.players" class="player-count">
                {{ urlGameState.players.length }}/6 suspects
              </span>
            </p>

            <!-- Rejoin as existing player -->
            <div v-if="urlGameState?.players?.length" class="suspects-section">
              <h3 class="section-label">Choose Your Identity</h3>
              <ul class="suspect-list">
                <li
                  v-for="p in urlGameState.players"
                  :key="p.id"
                  class="suspect-item"
                  :class="{
                    eliminated: !p.active && urlGameState.status !== 'waiting',
                  }"
                  @click="rejoinAs(p)"
                >
                  <div
                    class="suspect-token"
                    :class="{ 'has-portrait': CARD_IMAGES[p.character] }"
                    :style="tokenColor(p.character)"
                  >
                    <img
                      v-if="CARD_IMAGES[p.character]"
                      :src="CARD_IMAGES[p.character]"
                      :alt="p.character"
                      class="suspect-portrait"
                    />
                    <span v-else>{{ charAbbr(p.character) }}</span>
                  </div>
                  <div class="suspect-info">
                    <span class="suspect-name">{{ p.name }}</span>
                    <span class="suspect-character">{{ p.character }}</span>
                  </div>
                  <span
                    v-if="!p.active && urlGameState.status !== 'waiting'"
                    class="badge badge-eliminated"
                    >Eliminated</span
                  >
                  <span
                    v-else-if="p.type !== 'human'"
                    class="badge badge-agent"
                    >{{ agentLabel(p.type) }}</span
                  >
                  <span v-else class="badge badge-human">Human</span>
                </li>
              </ul>
              <button class="btn-secondary full-width" @click="observeUrlGame">
                <span class="btn-icon">&#x1F441;</span> Observe as Spectator
              </button>

              <details v-if="urlGameCanJoin" class="new-player-details">
                <summary>Enter as a new suspect...</summary>
                <div class="form-group">
                  <div class="input-wrapper">
                    <input
                      v-model="playerName"
                      placeholder="Your alias"
                      @keyup.enter="joinUrlGame"
                    />
                  </div>
                  <div class="select-wrapper">
                    <select v-model="playerType">
                      <option value="human">Human Player</option>
                      <option value="agent">Random Agent</option>
                      <option value="llm_agent">LLM Agent</option>
                    </select>
                  </div>
                  <button
                    class="btn-primary"
                    :disabled="!playerName"
                    @click="joinUrlGame"
                  >
                    Enter the Mansion
                  </button>
                </div>
              </details>
            </div>

            <!-- No players yet -->
            <div v-else-if="urlGameCanJoin" class="form-group">
              <div class="input-wrapper">
                <input
                  v-model="playerName"
                  placeholder="Your alias"
                  @keyup.enter="joinUrlGame"
                />
              </div>
              <div class="select-wrapper">
                <select v-model="playerType">
                  <option value="human">Human Player</option>
                  <option value="agent">Random Agent</option>
                  <option value="llm_agent">LLM Agent</option>
                </select>
              </div>
              <div class="btn-row">
                <button
                  class="btn-primary"
                  :disabled="!playerName"
                  @click="joinUrlGame"
                >
                  Enter the Mansion
                </button>
                <button class="btn-secondary" @click="observeUrlGame">
                  <span class="btn-icon">&#x1F441;</span> Observe
                </button>
              </div>
            </div>

            <div v-else class="form-group">
              <button class="btn-secondary full-width" @click="observeUrlGame">
                <span class="btn-icon">&#x1F441;</span> Observe as Spectator
              </button>
            </div>

            <p v-if="error" class="error-text">{{ error }}</p>
            <button class="btn-ghost" @click="$emit('clear-url-game')">
              Return to Foyer
            </button>
          </div>
        </section>
      </template>

      <!-- Normal lobby -->
      <template v-else>
        <!-- Game Type Selector -->
        <div class="game-type-selector">
          <button
            class="game-type-btn"
            :class="{ active: gameType === 'clue' }"
            @click="gameType = 'clue'"
          >
            <span class="game-type-icon">&#x1F50D;</span>
            <span class="game-type-label">Clue</span>
          </button>
          <button
            class="game-type-btn"
            :class="{ active: gameType === 'holdem' }"
            @click="gameType = 'holdem'"
          >
            <span class="game-type-icon">&#x1F0CF;</span>
            <span class="game-type-label">Texas Hold'em</span>
          </button>
        </div>

        <div class="lobby-grid">
          <!-- Create Game -->
          <section class="card card-create">
            <div class="card-inner">
              <div class="card-header">
                <span class="card-label">{{ gameType === 'holdem' ? 'New Table' : 'New Investigation' }}</span>
                <h2>Host a Game</h2>
              </div>
              <p class="card-desc">
                {{ gameType === 'holdem' ? 'Take your seat at the table and test your nerve.' : 'Gather your suspects and uncover the truth. As host, you\'ll set the stage for murder.' }}
              </p>
              <div class="form-group">
                <div class="input-wrapper">
                  <input
                    v-model="playerName"
                    placeholder="Your alias"
                    @keyup.enter="createGame"
                  />
                </div>
                <div class="select-wrapper" v-if="gameType === 'clue'">
                  <select v-model="playerType">
                    <option value="human">Human Player</option>
                    <option value="agent">Random Agent</option>
                    <option value="llm_agent">LLM Agent</option>
                  </select>
                </div>
                <template v-if="gameType === 'holdem'">
                  <div class="input-wrapper holdem-buyin-row">
                    <label class="input-label">Buy-in</label>
                    <div class="dollar-input">
                      <span class="dollar-sign">$</span>
                      <input
                        v-model.number="holdemBuyIn"
                        type="number"
                        min="1"
                        step="1"
                        placeholder="20"
                      />
                    </div>
                  </div>
                  <label class="checkbox-row">
                    <input type="checkbox" v-model="holdemAllowRebuys" />
                    <span class="checkbox-label">Allow rebuys</span>
                  </label>
                </template>
                <button
                  class="btn-primary"
                  :disabled="!playerName"
                  @click="createGame"
                >
                  {{ gameType === 'holdem' ? 'Deal Me In' : 'Open the Case' }}
                </button>
              </div>
            </div>
            <div class="card-decoration">
              <svg viewBox="0 0 120 120" class="deco-magnifier">
                <circle
                  cx="50"
                  cy="50"
                  r="35"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  opacity="0.15"
                />
                <line
                  x1="75"
                  y1="75"
                  x2="110"
                  y2="110"
                  stroke="currentColor"
                  stroke-width="3"
                  stroke-linecap="round"
                  opacity="0.15"
                />
              </svg>
            </div>
          </section>

          <!-- Join Game -->
          <section class="card card-join">
            <div class="card-inner">
              <div class="card-header">
                <span class="card-label">Active Case</span>
                <h2>Join a Game</h2>
              </div>
              <p class="card-desc">
                {{ gameType === 'holdem' ? 'Got a table number? Enter it to take your seat.' : 'You\'ve received an invitation to Tudor Mansion. Enter the case number to join.' }}
              </p>
              <div class="form-group">
                <div class="input-wrapper input-code">
                  <input
                    v-model="joinGameId"
                    placeholder="Game ID (e.g. ABC123)"
                    @keyup.enter="joinGame"
                    style="text-transform: uppercase; letter-spacing: 0.15em"
                  />
                </div>
                <div class="input-wrapper">
                  <input v-model="playerName" placeholder="Your alias" />
                </div>
                <div class="select-wrapper" v-if="gameType === 'clue'">
                  <select v-model="playerType">
                    <option value="human">Human Player</option>
                    <option value="agent">Random Agent</option>
                    <option value="llm_agent">LLM Agent</option>
                  </select>
                </div>
                <div class="btn-row">
                  <button
                    class="btn-primary"
                    :disabled="!joinGameId || !playerName"
                    @click="joinGame"
                  >
                    Enter the Mansion
                  </button>
                  <button
                    class="btn-secondary"
                    :disabled="!joinGameId"
                    @click="observeGame"
                  >
                    <span class="btn-icon">&#x1F441;</span> Observe
                  </button>
                </div>
              </div>
            </div>
            <div class="card-decoration">
              <svg viewBox="0 0 120 120" class="deco-envelope">
                <rect
                  x="10"
                  y="30"
                  width="100"
                  height="70"
                  rx="4"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  opacity="0.12"
                />
                <polyline
                  points="10,30 60,72 110,30"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  opacity="0.12"
                />
              </svg>
            </div>
          </section>
        </div>

        <p v-if="error" class="error-text error-global">{{ error }}</p>
      </template>

      <!-- Footer -->
      <footer class="lobby-footer">
        <div class="footer-line"></div>
        <p>&ldquo;The truth is rarely pure and never simple.&rdquo;</p>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";

const props = defineProps({
  urlGameId: { type: String, default: null },
  urlGameType: { type: String, default: "clue" },
});

const emit = defineEmits([
  "game-joined",
  "observe",
  "rejoin",
  "clear-url-game",
]);

const playerName = ref("");
const playerType = ref("human");
const gameType = ref("clue");
const joinGameId = ref("");
const error = ref("");

// Hold'em game creation options
const holdemBuyIn = ref(20);
const holdemAllowRebuys = ref(false);

// URL game state
const urlGameState = ref(null);
const urlGameLoading = ref(false);
const urlGameError = ref("");

// Imported from shared constants
import {
  CHARACTER_COLORS,
  CHARACTER_ABBR,
  CARD_IMAGES,
} from "../constants/clue.js";

function tokenColor(character) {
  const c = CHARACTER_COLORS[character] || { bg: "#444", text: "#fff" };
  return { backgroundColor: c.bg, color: c.text, borderColor: c.bg };
}

function charAbbr(character) {
  return CHARACTER_ABBR[character] || "??";
}

function agentLabel(type) {
  if (type === "agent") return "AI";
  if (type === "llm_agent") return "LLM";
  if (type === "wanderer") return "NPC";
  return type;
}

function particleStyle(n) {
  const x = Math.sin(n * 7.3) * 50 + 50;
  const delay = (n * 1.7) % 12;
  const duration = 8 + (n % 5) * 2;
  const size = 1 + (n % 3);
  return {
    left: `${x}%`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
    width: `${size}px`,
    height: `${size}px`,
  };
}

const urlGameCanJoin = computed(() => {
  return urlGameState.value?.status === "waiting";
});

const urlGameStatusText = computed(() => {
  const status = urlGameState.value?.status;
  if (status === "waiting") return "Awaiting suspects";
  if (status === "playing") return "Investigation in progress";
  if (status === "finished") return "Case closed";
  return "";
});

watch(
  () => props.urlGameId,
  (gid) => {
    if (gid) {
      fetchUrlGame(gid);
    } else {
      urlGameState.value = null;
      urlGameLoading.value = false;
      urlGameError.value = "";
    }
  },
  { immediate: true }
);

async function fetchUrlGame(gid) {
  urlGameLoading.value = true;
  urlGameError.value = "";
  urlGameState.value = null;
  try {
    const endpoint = props.urlGameType === "holdem" ? `/holdem/games/${gid}` : `/games/${gid}`;
    const res = await fetch(endpoint);
    if (!res.ok) {
      urlGameError.value = "Case file not found";
      return;
    }
    const state = await res.json();
    urlGameState.value = state;
    if (state.game_type === "holdem") gameType.value = "holdem";
  } catch (e) {
    urlGameError.value = "Failed to retrieve case: " + e.message;
  } finally {
    urlGameLoading.value = false;
  }
}

async function joinUrlGame() {
  error.value = "";
  if (props.urlGameType === "holdem" || gameType.value === "holdem") {
    await doJoinHoldem(props.urlGameId);
  } else {
    await doJoin(props.urlGameId);
  }
}

function observeUrlGame() {
  emit("observe", { gameId: props.urlGameId, gameType: props.urlGameType });
}

function rejoinAs(player) {
  emit("rejoin", { gameId: props.urlGameId, playerId: player.id, gameType: props.urlGameType });
}

async function createGame() {
  error.value = "";
  try {
    if (gameType.value === "holdem") {
      const buyInCents = Math.round(holdemBuyIn.value * 100);
      const res = await fetch("/holdem/games", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          buy_in: buyInCents,
          allow_rebuys: holdemAllowRebuys.value,
        }),
      });
      const { game_id } = await res.json();
      await doJoinHoldem(game_id);
    } else {
      const res = await fetch("/games", { method: "POST" });
      const { game_id } = await res.json();
      await doJoin(game_id);
    }
  } catch (e) {
    error.value = "Failed to open case: " + e.message;
  }
}

async function joinGame() {
  error.value = "";
  if (gameType.value === "holdem") {
    await doJoinHoldem(joinGameId.value.trim().toUpperCase());
  } else {
    await doJoin(joinGameId.value.trim().toUpperCase());
  }
}

async function doJoin(gameId) {
  try {
    const res = await fetch(`/games/${gameId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_name: playerName.value,
        player_type: playerType.value,
      }),
    });
    if (!res.ok) {
      const data = await res.json();
      error.value = data.detail ?? "Failed to join";
      return;
    }
    const { player_id } = await res.json();
    const stateRes = await fetch(`/games/${gameId}`);
    const state = await stateRes.json();
    emit("game-joined", { gameId, playerId: player_id, state });
  } catch (e) {
    error.value = "Error: " + e.message;
  }
}

async function doJoinHoldem(gameId) {
  try {
    const res = await fetch(`/holdem/games/${gameId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: playerName.value }),
    });
    if (!res.ok) {
      const data = await res.json();
      error.value = data.detail ?? "Failed to join";
      return;
    }
    const { player_id } = await res.json();
    const stateRes = await fetch(`/holdem/games/${gameId}`);
    const state = await stateRes.json();
    emit("game-joined", { gameId, playerId: player_id, state, gameType: "holdem" });
  } catch (e) {
    error.value = "Error: " + e.message;
  }
}

async function observeGame() {
  error.value = "";
  const gid = joinGameId.value.trim().toUpperCase();
  try {
    const res = await fetch(`/games/${gid}`);
    if (!res.ok) {
      error.value = "Case file not found";
      return;
    }
    emit("observe", { gameId: gid });
  } catch (e) {
    error.value = "Error: " + e.message;
  }
}
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap");

.lobby {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  font-family: "Crimson Text", Georgia, serif;
  background: #1c1812;
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
  opacity: 0.035;
  background: radial-gradient(ellipse at 30% 20%, #d4a849 0%, transparent 60%),
    radial-gradient(ellipse at 70% 80%, #8b2a2a 0%, transparent 50%);
  animation: fog-drift 20s ease-in-out infinite alternate;
}

.fog-2 {
  opacity: 0.025;
  background: radial-gradient(ellipse at 60% 40%, #d4a849 0%, transparent 55%),
    radial-gradient(ellipse at 20% 70%, #4a1a2a 0%, transparent 45%);
  animation-delay: -10s;
  animation-direction: alternate-reverse;
}

@keyframes fog-drift {
  0% {
    transform: translate(0, 0) scale(1);
  }
  100% {
    transform: translate(40px, -20px) scale(1.1);
  }
}

.vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at center, transparent 40%, #1c1812 85%);
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
  background: rgba(212, 168, 73, 0.25);
  animation: float-up linear infinite;
  opacity: 0;
}

@keyframes float-up {
  0% {
    transform: translateY(0) translateX(0);
    opacity: 0;
  }
  10% {
    opacity: 0.6;
  }
  90% {
    opacity: 0.2;
  }
  100% {
    transform: translateY(-100vh) translateX(30px);
    opacity: 0;
  }
}

/* === Content === */
.lobby-content {
  position: relative;
  z-index: 2;
  max-width: 660px;
  margin: 0 auto;
  padding: 2rem 1.25rem 3rem;
}

/* === Chandelier === */
.chandelier {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 1rem;
}

.chain {
  width: 1px;
  height: 40px;
  background: linear-gradient(to bottom, transparent, #d4a849);
}

.light-fixture {
  position: relative;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d4a849;
}

.glow {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(212, 168, 73, 0.15),
    transparent 70%
  );
  animation: pulse-glow 4s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%,
  100% {
    opacity: 0.7;
    transform: translate(-50%, -50%) scale(1);
  }
  50% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1.15);
  }
}

/* === Hero === */
.hero {
  text-align: center;
  margin-bottom: 2.5rem;
}

.title-frame {
  position: relative;
  display: inline-block;
  padding: 1.5rem 3rem 1.2rem;
}

.frame-corner {
  position: absolute;
  width: 24px;
  height: 24px;
  border-color: #d4a849;
  opacity: 0.4;
}

.frame-corner.tl {
  top: 0;
  left: 0;
  border-top: 1.5px solid;
  border-left: 1.5px solid;
}
.frame-corner.tr {
  top: 0;
  right: 0;
  border-top: 1.5px solid;
  border-right: 1.5px solid;
}
.frame-corner.bl {
  bottom: 0;
  left: 0;
  border-bottom: 1.5px solid;
  border-left: 1.5px solid;
}
.frame-corner.br {
  bottom: 0;
  right: 0;
  border-bottom: 1.5px solid;
  border-right: 1.5px solid;
}

.title {
  font-family: "Playfair Display", Georgia, serif;
  font-size: 4.5rem;
  font-weight: 900;
  letter-spacing: 0.35em;
  color: #d4a849;
  text-shadow: 0 0 40px rgba(212, 168, 73, 0.2), 0 2px 0 #a07830;
  line-height: 1;
  margin-right: -0.35em; /* compensate letter-spacing */
  animation: title-appear 1.2s ease-out;
}

@keyframes title-appear {
  0% {
    opacity: 0;
    transform: translateY(-10px);
    letter-spacing: 0.6em;
  }
  100% {
    opacity: 1;
    transform: translateY(0);
    letter-spacing: 0.35em;
  }
}

.tagline {
  font-family: "Crimson Text", Georgia, serif;
  font-style: italic;
  font-size: 1.05rem;
  color: #8a7e6b;
  margin-top: 0.6rem;
  letter-spacing: 0.08em;
  animation: fade-in 1.5s ease-out 0.3s both;
}

@keyframes fade-in {
  0% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
}

.weapon-icons {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 1.25rem;
  animation: fade-in 2s ease-out 0.6s both;
}

.weapon-icon {
  font-size: 1.1rem;
  filter: grayscale(0.8) brightness(0.5);
  transition: filter 0.3s;
}

.weapon-icon:hover {
  filter: grayscale(0) brightness(1);
}

.divider-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #4a3f2e;
}

/* === Cards (panels) === */
.lobby-grid {
  display: grid;
  gap: 1.25rem;
  animation: fade-in 1s ease-out 0.4s both;
}

@media (min-width: 580px) {
  .lobby-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.card {
  position: relative;
  border-radius: 8px;
  background: linear-gradient(
    135deg,
    rgba(30, 24, 16, 0.95) 0%,
    rgba(18, 14, 10, 0.97) 100%
  );
  border: 1px solid rgba(212, 168, 73, 0.12);
  overflow: hidden;
  transition: border-color 0.4s, box-shadow 0.4s;
  animation: card-appear 0.6s ease-out both;
}

.card:nth-child(2) {
  animation-delay: 0.15s;
}

@keyframes card-appear {
  0% {
    opacity: 0;
    transform: translateY(16px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

.card:hover {
  border-color: rgba(212, 168, 73, 0.25);
  box-shadow: 0 8px 40px rgba(212, 168, 73, 0.06);
}

.card-inner {
  position: relative;
  z-index: 1;
  padding: 1.75rem 1.5rem 1.5rem;
}

.card-decoration {
  position: absolute;
  bottom: -10px;
  right: -10px;
  width: 120px;
  height: 120px;
  color: #d4a849;
  pointer-events: none;
}

.card-header {
  margin-bottom: 0.75rem;
}

.card-label {
  display: inline-block;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #d4a849;
  opacity: 0.7;
  margin-bottom: 0.3rem;
}

.card-header h2 {
  font-family: "Playfair Display", Georgia, serif;
  font-size: 1.35rem;
  font-weight: 700;
  color: #e8dcc8;
  letter-spacing: 0.03em;
}

.card-desc {
  color: #7a7060;
  font-size: 0.9rem;
  line-height: 1.55;
  margin-bottom: 1.25rem;
}

/* === Status badge === */
.status-badge {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  color: #8a7e6b;
  margin-bottom: 1.25rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-badge.waiting .status-dot {
  background: #d4a849;
  box-shadow: 0 0 8px rgba(212, 168, 73, 0.5);
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-badge.playing .status-dot {
  background: #4caf50;
  box-shadow: 0 0 8px rgba(76, 175, 80, 0.5);
}

.status-badge.finished .status-dot {
  background: #666;
}

@keyframes pulse-dot {
  0%,
  100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}

.player-count {
  margin-left: auto;
  font-size: 0.8rem;
  opacity: 0.7;
}

/* === Forms === */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.input-wrapper {
  position: relative;
}

.input-wrapper input,
.select-wrapper select {
  display: block;
  width: 100%;
  padding: 0.65rem 0.9rem;
  border: 1px solid rgba(212, 168, 73, 0.15);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  color: #e8dcc8;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.95rem;
  transition: border-color 0.3s, background 0.3s, box-shadow 0.3s;
  outline: none;
}

.input-wrapper input::placeholder {
  color: #5a5040;
  font-style: italic;
}

.input-wrapper input:focus,
.select-wrapper select:focus {
  border-color: rgba(212, 168, 73, 0.4);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 3px rgba(212, 168, 73, 0.06);
}

.select-wrapper {
  position: relative;
}

.select-wrapper select {
  appearance: none;
  cursor: pointer;
  padding-right: 2rem;
}

.select-wrapper::after {
  content: "\25BE";
  position: absolute;
  right: 0.9rem;
  top: 50%;
  transform: translateY(-50%);
  color: #5a5040;
  pointer-events: none;
  font-size: 0.8rem;
}

/* === Buttons === */
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.7rem 1.5rem;
  border: none;
  border-radius: 5px;
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all 0.3s;
  position: relative;
  overflow: hidden;
}

.btn-primary::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), transparent);
  opacity: 0;
  transition: opacity 0.3s;
}

.btn-primary:hover:not(:disabled)::before {
  opacity: 1;
}

.btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 20px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0);
}

.btn-primary:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.65rem 1.25rem;
  border: 1px solid rgba(212, 168, 73, 0.2);
  border-radius: 5px;
  background: transparent;
  color: #8a7e6b;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-secondary:hover:not(:disabled) {
  border-color: rgba(212, 168, 73, 0.4);
  color: #d4a849;
  background: rgba(212, 168, 73, 0.05);
}

.btn-secondary:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-secondary.full-width {
  width: 100%;
}

.btn-icon {
  font-size: 0.85rem;
}

.btn-ghost {
  display: inline-block;
  margin-top: 1rem;
  padding: 0.4rem 0;
  background: none;
  border: none;
  color: #5a5040;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.85rem;
  cursor: pointer;
  transition: color 0.2s;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.btn-ghost:hover {
  color: #8a7e6b;
}

.btn-row {
  display: flex;
  gap: 0.5rem;
}

.btn-row .btn-primary {
  flex: 1;
}

/* === Suspect list === */
.section-label {
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #8a7e6b;
  margin-bottom: 0.75rem;
}

.suspect-list {
  list-style: none;
  margin-bottom: 1rem;
}

.suspect-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
  margin-bottom: 0.25rem;
}

.suspect-item:hover {
  background: rgba(212, 168, 73, 0.04);
  border-color: rgba(212, 168, 73, 0.2);
}

.suspect-item.eliminated {
  opacity: 0.4;
}

.suspect-token {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  font-family: "Crimson Text", Georgia, serif;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  flex-shrink: 0;
  overflow: hidden;
}

.suspect-token.has-portrait {
  background: none !important;
  border: 2px solid;
  border-color: inherit;
}

.suspect-portrait {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
  border-radius: 50%;
  display: block;
}

.suspect-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  text-align: left;
  min-width: 0;
}

.suspect-name {
  color: #e8dcc8;
  font-size: 0.9rem;
  font-weight: 600;
}

.suspect-character {
  color: #6a6050;
  font-size: 0.75rem;
  font-style: italic;
}

.badge {
  font-size: 0.65rem;
  padding: 0.2rem 0.5rem;
  border-radius: 3px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  flex-shrink: 0;
}

.badge-eliminated {
  background: rgba(139, 42, 42, 0.2);
  color: #c45050;
}

.badge-agent {
  background: rgba(212, 168, 73, 0.12);
  color: #d4a849;
}

.badge-human {
  background: rgba(255, 255, 255, 0.05);
  color: #6a6050;
}

/* === Details/accordion === */
.new-player-details {
  margin-top: 0.75rem;
}

.new-player-details summary {
  color: #5a5040;
  font-size: 0.85rem;
  font-style: italic;
  cursor: pointer;
  text-align: left;
  transition: color 0.2s;
}

.new-player-details summary:hover {
  color: #8a7e6b;
}

.new-player-details .form-group {
  margin-top: 0.75rem;
}

/* === Loading === */
.loading-text {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: #8a7e6b;
  font-style: italic;
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 1.5px solid rgba(212, 168, 73, 0.2);
  border-top-color: #d4a849;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
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
}

.error-global {
  text-align: center;
  margin-top: 1.25rem;
  animation: fade-in 0.3s ease-out;
}

/* === Footer === */
.lobby-footer {
  margin-top: 3rem;
  text-align: center;
  animation: fade-in 2s ease-out 1s both;
}

.footer-line {
  width: 60px;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(212, 168, 73, 0.2),
    transparent
  );
  margin: 0 auto 1rem;
}

.lobby-footer p {
  color: #3a3528;
  font-style: italic;
  font-size: 0.85rem;
  letter-spacing: 0.03em;
}

/* === Hold'em Buy-in === */
.holdem-buyin-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.input-label {
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #8a7e6b;
}

.dollar-input {
  position: relative;
  display: flex;
  align-items: center;
}

.dollar-sign {
  position: absolute;
  left: 0.75rem;
  color: #8a7e6b;
  font-size: 0.95rem;
  pointer-events: none;
}

.dollar-input input {
  display: block;
  width: 100%;
  padding: 0.65rem 0.9rem 0.65rem 1.6rem;
  border: 1px solid rgba(212, 168, 73, 0.15);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  color: #e8dcc8;
  font-family: "Crimson Text", Georgia, serif;
  font-size: 0.95rem;
  transition: border-color 0.3s, background 0.3s, box-shadow 0.3s;
  outline: none;
  -moz-appearance: textfield;
}

.dollar-input input::-webkit-outer-spin-button,
.dollar-input input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.dollar-input input:focus {
  border-color: rgba(212, 168, 73, 0.4);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 3px rgba(212, 168, 73, 0.06);
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem 0;
}

.checkbox-row input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #d4a849;
  cursor: pointer;
}

.checkbox-label {
  font-size: 0.9rem;
  color: #8a7e6b;
}

/* === Game Type Selector === */
.game-type-selector {
  display: flex;
  gap: 0.75rem;
  justify-content: center;
  margin-bottom: 1.5rem;
  animation: fade-in 0.8s ease-out 0.3s both;
}

.game-type-btn {
  flex: 1;
  max-width: 200px;
  background: linear-gradient(135deg, rgba(30, 24, 16, 0.95), rgba(18, 14, 10, 0.97));
  border: 1.5px solid rgba(212, 168, 73, 0.12);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.3s;
  font-family: 'Crimson Text', Georgia, serif;
}

.game-type-btn:hover {
  border-color: rgba(212, 168, 73, 0.3);
  box-shadow: 0 4px 20px rgba(212, 168, 73, 0.06);
}

.game-type-btn.active {
  border-color: rgba(212, 168, 73, 0.5);
  background: linear-gradient(135deg, rgba(40, 32, 20, 0.95), rgba(25, 20, 14, 0.97));
  box-shadow: 0 4px 20px rgba(212, 168, 73, 0.1);
}

.game-type-icon {
  font-size: 1.5rem;
}

.game-type-label {
  font-size: 0.85rem;
  color: #6a6050;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.game-type-btn.active .game-type-label {
  color: #d4a849;
}

/* === Responsive === */
@media (max-width: 579px) {
  .title {
    font-size: 3rem;
  }

  .title-frame {
    padding: 1rem 2rem 0.8rem;
  }

  .card-inner {
    padding: 1.5rem 1.25rem 1.25rem;
  }
}
</style>
