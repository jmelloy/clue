<template>
  <div class="game-board">
    <!-- Header -->
    <header class="game-header">
      <div class="header-left">
        <h1>CLUE</h1>
        <span class="game-id-label">Case {{ gameId }}</span>
      </div>
      <div class="header-center">
        <div v-if="gameState?.status === 'finished'" class="status-banner winner">
          Case Closed! {{ winnerName }} wins!
          <div v-if="gameState.solution" class="solution-detail">
            <span class="highlight-suspect">{{ gameState.solution.suspect }}</span>
            with the
            <span class="highlight-weapon">{{ gameState.solution.weapon }}</span>
            in the
            <span class="highlight-room">{{ gameState.solution.room }}</span>
          </div>
        </div>
        <div v-else-if="isMyTurn" class="status-banner my-turn">
          Your turn! (Turn {{ gameState?.turn_number }})
        </div>
        <div v-else class="status-banner waiting">
          {{ currentPlayerName }}'s turn (Turn {{ gameState?.turn_number }})
          <span v-if="countdown !== null && !timerForMe" class="header-timer">- auto-end in {{ countdown }}s</span>
        </div>
      </div>
      <div class="header-right">
        <div v-if="isObserver" class="observer-badge">Observer</div>
        <div v-if="gameState?.last_roll" class="dice-display" title="Last dice roll">
          <span class="dice" v-for="(die, idx) in gameState.last_roll" :key="idx">{{ die }}</span>
        </div>
        <ThemeSwitcher />
      </div>
    </header>

    <!-- Main content: Board + Sidebar -->
    <div class="main-layout">
      <!-- Left: Board Map + Players -->
      <div class="board-column">
        <div class="board-map-wrapper">
          <BoardMap :game-state="gameState" :player-id="playerId" :selected-room="targetRoom" :selectable="canMove"
            :reachable-rooms="reachableRooms" :reachable-positions="reachablePositions" @select-room="onRoomSelected"
            @select-position="onPositionSelected" />
          <!-- Winning cards tossed on the board -->
          <div v-if="gameState?.status === 'finished' && gameState?.solution" class="board-tossed-cards">
            <div class="tossed-card tossed-card-1">
              <div class="tossed-card-inner card-suspect">
                <div class="tossed-card-image-frame">
                  <img v-if="hasCardImage(gameState.solution.suspect)" :src="cardImageUrl(gameState.solution.suspect)" :alt="gameState.solution.suspect" />
                  <div v-else class="tossed-card-icon">{{ cardIcon(gameState.solution.suspect) }}</div>
                </div>
                <div class="tossed-card-name">{{ gameState.solution.suspect }}</div>
              </div>
            </div>
            <div class="tossed-card tossed-card-2">
              <div class="tossed-card-inner card-weapon">
                <div class="tossed-card-image-frame">
                  <img v-if="hasCardImage(gameState.solution.weapon)" :src="cardImageUrl(gameState.solution.weapon)" :alt="gameState.solution.weapon" />
                  <div v-else class="tossed-card-icon">{{ cardIcon(gameState.solution.weapon) }}</div>
                </div>
                <div class="tossed-card-name">{{ gameState.solution.weapon }}</div>
              </div>
            </div>
            <div class="tossed-card tossed-card-3">
              <div class="tossed-card-inner card-room">
                <div class="tossed-card-image-frame">
                  <img v-if="hasCardImage(gameState.solution.room)" :src="cardImageUrl(gameState.solution.room)" :alt="gameState.solution.room" />
                  <div v-else class="tossed-card-icon">{{ cardIcon(gameState.solution.room) }}</div>
                </div>
                <div class="tossed-card-name">{{ gameState.solution.room }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Player Legend -->
        <div class="player-legend">
          <div v-for="p in gameState?.players" :key="p.id" class="legend-item" :class="{
            active: gameState?.whose_turn === p.id,
            eliminated: !p.active,
            'is-me': p.id === playerId,
            'wanderer-legend': p.type === 'wanderer',
            'observer-clickable': isObserver,
            'observer-selected': isObserver && observerPlayerState?.playerId === p.id
          }" @click.stop="onLegendClick(p)">
            <PlayerPawn :character="p.character" :wanderer="p.type === 'wanderer'" />
            <span class="legend-name">{{ p.name }}</span>
            <span v-if="p.type !== 'wanderer' && p.character !== p.name" class="legend-character">{{ p.character }}</span>
            <span v-if="gameState?.current_room?.[p.id]" class="legend-room">{{
              gameState.current_room[p.id]
              }}</span>
            <span v-if="!p.active" class="legend-status">eliminated</span>
            <span v-if="p.type === 'wanderer'" class="legend-wanderer-label">wandering</span>
            <span v-else-if="gameState?.whose_turn === p.id" class="legend-turn">turn</span>
            <!-- Shown cards popup -->
            <div v-if="shownCardsPlayerId === p.id && shownCardsForPlayer.length" class="shown-cards-popup" @click.stop>
              <div class="shown-cards-title">Cards shown to you:</div>
              <div class="shown-cards-hand">
                <div v-for="card in shownCardsForPlayer" :key="card" class="hand-card" :class="cardCategory(card)">
                  <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card" class="card-thumb" />
                  <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                  <span class="card-label">{{ card }}</span>
                </div>
              </div>
            </div>
            <div v-if="shownCardsPlayerId === p.id && !shownCardsForPlayer.length" class="shown-cards-popup"
              @click.stop>
              <div class="shown-cards-title">No cards shown to you</div>
            </div>
          </div>
        </div>

      </div>

      <!-- Right: Sidebar -->
      <div class="sidebar-column">
        <!-- Your Cards -->
        <section v-if="!isObserver" class="sidebar-panel cards-panel">
          <h2 class="panel-header collapsible-header" @click="cardsCollapsed = !cardsCollapsed">
            <span>Your Cards</span>
            <span class="collapse-indicator" :class="{ collapsed: cardsCollapsed }">&#9660;</span>
          </h2>
          <div v-if="!cardsCollapsed">
            <div v-if="!yourCards.length" class="no-cards">No cards dealt yet</div>
            <div v-else class="card-hand">
              <div v-for="card in suspectCards" :key="card" class="hand-card card-suspect card-with-image"
                @click="showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card" class="card-thumb" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
              <div v-for="card in weaponCards" :key="card" class="hand-card card-weapon"
                :class="{ 'card-with-image': hasCardImage(card) }"
                @click="hasCardImage(card) && showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card"
                  class="card-thumb card-thumb-weapon" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
              <div v-for="card in roomCards" :key="card" class="hand-card card-room card-with-image"
                @click="showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card"
                  class="card-thumb card-thumb-room" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Card Shown notification (sidebar hint) -->
        <section v-if="cardShown" class="sidebar-panel shown-card-panel">
          <div class="shown-card-notice">
            <span class="shown-card-icon">&#128065;</span>
            <div>
              <div v-if="cardShown.suspect" class="shown-card-suggestion">
                You suggested:
                <span class="highlight-suspect">{{ cardShown.suspect }}</span>,
                <span class="highlight-weapon">{{ cardShown.weapon }}</span>,
                <span class="highlight-room">{{ cardShown.room }}</span>
              </div>
              <template v-if="cardShown.card">
                <strong>{{ playerName(cardShown.by) }}</strong> showed you:
                <span class="shown-card-name">{{ cardShown.card }}</span>
              </template>
              <template v-else>
                No one could show a card.
              </template>
            </div>
            <button class="dismiss-btn" @click="$emit('dismiss-card-shown')">&times;</button>
          </div>
        </section>

        <!-- Show Card Request (must respond) -->
        <section v-if="showCardRequest" class="sidebar-panel show-card-request-panel">
          <h2 class="panel-header">You Must Show a Card</h2>
          <p class="show-card-desc">
            <strong>{{ playerName(showCardRequest.suggestingPlayerId) }}</strong>
            suggested:
            <span class="highlight-suspect">{{ showCardRequest.suspect }}</span>
            with the
            <span class="highlight-weapon">{{ showCardRequest.weapon }}</span>
            in the
            <span class="highlight-room">{{ showCardRequest.room }}</span>
          </p>
          <p class="show-card-prompt">Choose a card to reveal:</p>
          <div class="show-card-options">
            <button v-for="card in matchingCards" :key="card" class="show-card-btn" :class="cardCategory(card)"
              @click="doShowCard(card)">
              <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card" class="show-card-thumb"
                :class="'show-card-thumb-' + cardCategory(card).replace('card-', '')" />
              <span v-else class="card-icon">{{ cardIcon(card) }}</span>
              {{ card }}
            </button>
          </div>
        </section>

        <!-- Actions -->
        <section v-if="isMyTurn && !showCardRequest && gameState?.status === 'playing' && !isObserver"
          class="sidebar-panel actions-panel">
          <h2 class="panel-header">Actions</h2>

          <!-- Secret Passage -->
          <div v-if="canSecretPassage" class="action-group">
            <h3>Secret Passage</h3>
            <p class="action-hint">You're in {{ myCurrentRoom }} — take the secret passage?</p>
            <button class="action-btn passage-btn" @click="doSecretPassage">
              Use Passage to {{ passageDestination }}
            </button>
          </div>

          <!-- Roll Dice -->
          <div v-if="canRoll" class="action-group">
            <h3>Roll Dice</h3>
            <button class="action-btn roll-btn" @click="doRoll">Roll Dice</button>
          </div>

          <!-- Move (choose room after rolling) -->
          <div v-if="canMove" class="action-group">
            <h3>
              Move (rolled
              {{gameState?.last_roll?.reduce((a, b) => a + b, 0)}})
            </h3>
            <p class="action-hint">
              Click a highlighted room on the board or select below:
              <span v-if="reachableRooms.length" class="reachable-count">{{ reachableRooms.length }} room{{
                reachableRooms.length !== 1 ? 's' : ''
              }}
                reachable</span>
            </p>
            <select v-model="targetRoom" class="action-select">
              <option value="">-- Choose a room --</option>
              <option v-for="room in ROOMS" :key="room" :value="room"
                :class="{ 'reachable-option': reachableRooms.includes(room) }">
                {{ room }}{{ reachableRooms.includes(room) ? ' ✓' : '' }}
              </option>
            </select>
            <button class="action-btn move-btn" :disabled="!targetRoom" @click="doMove">
              Move{{ targetRoom ? ' to ' + targetRoom : '' }}
            </button>
          </div>

          <!-- Suggest -->
          <div v-if="canSuggest" class="action-group">
            <h3>
              Suggest (in <span class="highlight-room">{{ myCurrentRoom }}</span>)
            </h3>
            <select v-model="suggestSuspect" class="action-select">
              <option value="">-- Suspect --</option>
              <option v-for="s in SUSPECTS" :key="s" :value="s">{{ s }}</option>
            </select>
            <select v-model="suggestWeapon" class="action-select">
              <option value="">-- Weapon --</option>
              <option v-for="w in WEAPONS" :key="w" :value="w">{{ w }}</option>
            </select>
            <button class="action-btn suggest-btn" :disabled="!suggestSuspect || !suggestWeapon" @click="doSuggest">
              Make Suggestion
            </button>
          </div>

          <!-- Accuse -->
          <div v-if="canAccuse" class="action-group accuse-group">
            <button v-if="!showAccuseForm" class="action-btn toggle-accuse-btn" @click="showAccuseForm = true">
              Make Final Accusation...
            </button>
            <div v-if="showAccuseForm" class="accuse-form">
              <h3>Final Accusation</h3>
              <p class="action-warning">
                Warning: A wrong accusation eliminates you from the game!
              </p>
              <select v-model="accuseSuspect" class="action-select">
                <option value="">-- Suspect --</option>
                <option v-for="s in SUSPECTS" :key="s" :value="s">
                  {{ s }}
                </option>
              </select>
              <select v-model="accuseWeapon" class="action-select">
                <option value="">-- Weapon --</option>
                <option v-for="w in WEAPONS" :key="w" :value="w">
                  {{ w }}
                </option>
              </select>
              <select v-model="accuseRoom" class="action-select">
                <option value="">-- Room --</option>
                <option v-for="r in ROOMS" :key="r" :value="r">{{ r }}</option>
              </select>
              <div class="accuse-buttons">
                <button class="action-btn accuse-btn" :disabled="!accuseSuspect || !accuseWeapon || !accuseRoom"
                  @click="doAccuse">
                  Accuse!
                </button>
                <button class="action-btn cancel-btn" @click="showAccuseForm = false">
                  Cancel
                </button>
              </div>
            </div>
          </div>

          <!-- End Turn -->
          <div v-if="canEndTurn" class="action-group">
            <div v-if="timerForMe" class="auto-end-timer">
              <div class="timer-bar">
                <div class="timer-bar-fill" :style="{
                  width: (countdown / (props.autoEndTimer?.seconds || 15)) * 100 + '%'
                }"></div>
              </div>
              <span class="timer-text">Auto-ending turn in {{ countdown }}s</span>
            </div>
            <button class="action-btn end-turn-btn" @click="doEndTurn">End Turn</button>
          </div>
        </section>

        <!-- Waiting message when not your turn -->
        <section v-if="!isMyTurn && !showCardRequest && gameState?.status === 'playing' && !isObserver"
          class="sidebar-panel waiting-panel">
          <div class="waiting-message">
            Waiting for <strong>{{ currentPlayerName }}</strong>'s turn...
          </div>
        </section>

        <!-- Detective Notes -->
        <section v-if="!isObserver" class="sidebar-panel notes-panel">
          <DetectiveNotes ref="notesRef" :your-cards="yourCards" :saved-notes="savedNotes"
            @notes-changed="onNotesChanged" />
        </section>

        <!-- Observer: Selected Player Info -->
        <template v-if="isObserver">
          <section v-if="!observerPlayerState" class="sidebar-panel observer-hint-panel">
            <div class="observer-hint">
              Click a player below the board to inspect their cards and debug info.
            </div>
          </section>

          <section v-if="observerPlayerState" class="sidebar-panel cards-panel">
            <h2 class="panel-header">{{ observerSelectedPlayerName }}'s Cards</h2>
            <div v-if="!observerCards.length" class="no-cards">No cards</div>
            <div v-else class="card-hand">
              <div v-for="card in observerSuspectCards" :key="card" class="hand-card card-suspect card-with-image"
                @click="showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card" class="card-thumb" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
              <div v-for="card in observerWeaponCards" :key="card" class="hand-card card-weapon"
                :class="{ 'card-with-image': hasCardImage(card) }"
                @click="hasCardImage(card) && showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card"
                  class="card-thumb card-thumb-weapon" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
              <div v-for="card in observerRoomCards" :key="card" class="hand-card card-room card-with-image"
                @click="showCardPreview(card)">
                <img v-if="hasCardImage(card)" :src="cardImageUrl(card)" :alt="card"
                  class="card-thumb card-thumb-room" />
                <span v-else class="card-icon">{{ cardIcon(card) }}</span>
                <span class="card-label">{{ card }}</span>
              </div>
            </div>
          </section>

          <section v-if="observerSelectedDebug" class="sidebar-panel">
            <AgentDebugPanel :agent-debug-data="{
              [observerPlayerState.playerId]: observerSelectedDebug
            }" :players="gameState?.players" :game-state="gameState" />
          </section>
        </template>
      </div>

      <!-- Chat (at bottom of responsive stack) -->
      <section class="sidebar-panel chat-panel-wrapper">
        <h2 class="panel-header">Chat &amp; Game Log</h2>
        <ChatPanel
          :messages="chatMessages"
          :players="gameState?.players"
          @send-message="$emit('send-chat', $event)"
        />
      </section>
    </div>
    <Teleport to="body">
      <div v-if="cardShown && !cardShownDismissedOnce" class="card-shown-overlay" @click="dismissCardShownOverlay">
        <div class="card-shown-banner" @click.stop>
          <div class="card-shown-banner-label">{{ cardShown.card ? 'Card Revealed' : 'No One Could Show' }}</div>
          <div v-if="cardShown.suspect" class="card-shown-banner-suggestion">
            You suggested:
            <span class="highlight-suspect">{{ cardShown.suspect }}</span>
            with the
            <span class="highlight-weapon">{{ cardShown.weapon }}</span>
            in the
            <span class="highlight-room">{{ cardShown.room }}</span>
          </div>
          <div v-if="cardShown.card" class="card-shown-banner-from">{{ playerName(cardShown.by) }} showed you:</div>
          <div v-if="cardShown.card" class="card-shown-banner-card physical-card" :class="cardCategory(cardShown.card)">
            <div class="physical-card-header">
              <span class="physical-card-icon">{{ cardIcon(cardShown.card) }}</span>
              <span class="physical-card-title">{{ cardShown.card }}</span>
            </div>
            <div class="physical-card-image-frame">
              <img v-if="hasCardImage(cardShown.card)" :src="cardImageUrl(cardShown.card)" :alt="cardShown.card" class="physical-card-image" />
              <div v-else class="physical-card-icon-fallback">{{ cardIcon(cardShown.card) }}</div>
            </div>
            <div class="physical-card-footer">
              <span class="physical-card-title">{{ cardShown.card }}</span>
              <span class="physical-card-icon">{{ cardIcon(cardShown.card) }}</span>
            </div>
          </div>
          <div v-else class="card-shown-banner-noshow">No one could disprove your suggestion!</div>
          <button class="card-shown-banner-dismiss" @click="dismissCardShownOverlay">Got it</button>
        </div>
      </div>
    </Teleport>

    <!-- Game Over Winner Overlay -->
    <Teleport to="body">
      <div v-if="showGameOverOverlay" class="game-over-overlay" @click="showGameOverOverlay = false">
        <div class="game-over-banner" @click.stop>
          <div class="game-over-trophy">&#127942;</div>
          <div class="game-over-title">Case Closed!</div>
          <div class="game-over-winner">{{ winnerName }} wins!</div>
          <div class="game-over-cards" v-if="gameState?.solution">
            <div class="game-over-card physical-card card-suspect">
              <div class="physical-card-header">
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.suspect) }}</span>
                <span class="physical-card-title">{{ gameState.solution.suspect }}</span>
              </div>
              <div class="physical-card-image-frame">
                <img v-if="hasCardImage(gameState.solution.suspect)" :src="cardImageUrl(gameState.solution.suspect)" :alt="gameState.solution.suspect" class="physical-card-image" />
                <div v-else class="physical-card-icon-fallback">{{ cardIcon(gameState.solution.suspect) }}</div>
              </div>
              <div class="physical-card-footer">
                <span class="physical-card-title">{{ gameState.solution.suspect }}</span>
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.suspect) }}</span>
              </div>
            </div>
            <div class="game-over-card physical-card card-weapon">
              <div class="physical-card-header">
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.weapon) }}</span>
                <span class="physical-card-title">{{ gameState.solution.weapon }}</span>
              </div>
              <div class="physical-card-image-frame">
                <img v-if="hasCardImage(gameState.solution.weapon)" :src="cardImageUrl(gameState.solution.weapon)" :alt="gameState.solution.weapon" class="physical-card-image" />
                <div v-else class="physical-card-icon-fallback">{{ cardIcon(gameState.solution.weapon) }}</div>
              </div>
              <div class="physical-card-footer">
                <span class="physical-card-title">{{ gameState.solution.weapon }}</span>
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.weapon) }}</span>
              </div>
            </div>
            <div class="game-over-card physical-card card-room">
              <div class="physical-card-header">
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.room) }}</span>
                <span class="physical-card-title">{{ gameState.solution.room }}</span>
              </div>
              <div class="physical-card-image-frame">
                <img v-if="hasCardImage(gameState.solution.room)" :src="cardImageUrl(gameState.solution.room)" :alt="gameState.solution.room" class="physical-card-image" />
                <div v-else class="physical-card-icon-fallback">{{ cardIcon(gameState.solution.room) }}</div>
              </div>
              <div class="physical-card-footer">
                <span class="physical-card-title">{{ gameState.solution.room }}</span>
                <span class="physical-card-icon">{{ cardIcon(gameState.solution.room) }}</span>
              </div>
            </div>
          </div>
          <button class="game-over-dismiss" @click="showGameOverOverlay = false">Continue</button>
        </div>
      </div>
    </Teleport>

    <!-- Card Preview Overlay -->
    <Teleport to="body">
      <div v-if="previewCard && hasCardImage(previewCard)" class="card-preview-overlay" @click="closePreview">
        <div class="card-preview-frame" :class="cardCategory(previewCard)" @click.stop>
          <div class="card-preview-header">
            <span class="card-preview-icon">{{ cardIcon(previewCard) }}</span>
            <span class="card-preview-name">{{ previewCard }}</span>
          </div>
          <div class="card-preview-image-area">
            <div class="card-preview-image-frame">
              <img :src="cardImageUrl(previewCard)" :alt="previewCard" class="card-preview-image" />
            </div>
          </div>
          <div class="card-preview-footer">
            <span class="card-preview-name">{{ previewCard }}</span>
            <span class="card-preview-icon">{{ cardIcon(previewCard) }}</span>
          </div>
          <button class="card-preview-close" @click="closePreview">&times;</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import BoardMap from './BoardMap.vue'
import ChatPanel from './ChatPanel.vue'
import DetectiveNotes from './DetectiveNotes.vue'
import AgentDebugPanel from './AgentDebugPanel.vue'
import ThemeSwitcher from '../common/ThemeSwitcher.vue'
import PlayerPawn from './PlayerPawn.vue'
import { useTheme } from '../../composables/useTheme'
import {
  SUSPECTS,
  WEAPONS,
  ROOMS,
  CARD_ICONS,
  CARD_IMAGES,
  cardIcon,
  hasCardImage as _hasCardImage,
  cardImageUrl as _cardImageUrl,
} from '../../constants/clue'

const { theme } = useTheme()
const hasCardImage = (card) => _hasCardImage(card, theme.value)
const cardImageUrl = (card) => _cardImageUrl(card, theme.value)

const props = defineProps({
  gameId: String,
  playerId: String,
  gameState: Object,
  yourCards: { type: Array, default: () => [] },
  availableActions: { type: Array, default: () => [] },
  showCardRequest: Object,
  cardShown: Object,
  chatMessages: { type: Array, default: () => [] },
  isObserver: { type: Boolean, default: false },
  autoEndTimer: { type: Object, default: null },
  reachableRooms: { type: Array, default: () => [] },
  reachablePositions: { type: Array, default: () => [] },
  savedNotes: { type: Object, default: null },
  agentDebugData: { type: Object, default: () => ({}) },
  observerPlayerState: { type: Object, default: null }
})

const emit = defineEmits(['action', 'send-chat', 'dismiss-card-shown', 'select-player'])

const notesRef = ref(null)

// Form state
const targetRoom = ref('')
const suggestSuspect = ref('')
const suggestWeapon = ref('')
const accuseSuspect = ref('')
const accuseWeapon = ref('')
const accuseRoom = ref('')
const showAccuseForm = ref(false)
const cardsCollapsed = ref(false)

// Auto-end timer countdown
const countdown = ref(null)
let countdownInterval = null

function clearCountdown() {
  if (countdownInterval) {
    clearInterval(countdownInterval)
    countdownInterval = null
  }
  countdown.value = null
}

watch(
  () => props.autoEndTimer,
  (timer) => {
    clearCountdown()
    if (timer && timer.seconds > 0) {
      const updateCountdown = () => {
        const elapsed = (Date.now() - timer.startedAt) / 1000
        const remaining = Math.max(0, Math.ceil(timer.seconds - elapsed))
        countdown.value = remaining
        if (remaining <= 0) clearCountdown()
      }
      updateCountdown()
      countdownInterval = setInterval(updateCountdown, 1000)
    }
  },
  { immediate: true }
)

onUnmounted(() => clearCountdown())

const timerForMe = computed(
  () => countdown.value !== null && props.autoEndTimer?.playerId === props.playerId
)

// Computed
const isMyTurn = computed(() => props.gameState?.whose_turn === props.playerId)
const myCurrentRoom = computed(() => props.gameState?.current_room?.[props.playerId] ?? null)

const canSecretPassage = computed(() => props.availableActions.includes('secret_passage'))
const canRoll = computed(() => props.availableActions.includes('roll'))
const canMove = computed(() => props.availableActions.includes('move'))
const canSuggest = computed(() => props.availableActions.includes('suggest'))
const canAccuse = computed(() => props.availableActions.includes('accuse'))
const canEndTurn = computed(() => props.availableActions.includes('end_turn'))

const SECRET_PASSAGES = {
  Study: 'Kitchen',
  Kitchen: 'Study',
  Lounge: 'Conservatory',
  Conservatory: 'Lounge'
}
const passageDestination = computed(() => SECRET_PASSAGES[myCurrentRoom.value] ?? '?')

const currentPlayerName = computed(() => {
  return playerName(props.gameState?.whose_turn)
})

const winnerName = computed(() => {
  return playerName(props.gameState?.winner)
})

const suspectCards = computed(() => props.yourCards.filter((c) => SUSPECTS.includes(c)))
const weaponCards = computed(() => props.yourCards.filter((c) => WEAPONS.includes(c)))
const roomCards = computed(() => props.yourCards.filter((c) => ROOMS.includes(c)))

// Observer selected player computeds
const observerCards = computed(() => props.observerPlayerState?.your_cards ?? [])
const observerSuspectCards = computed(() =>
  observerCards.value.filter((c) => SUSPECTS.includes(c))
)
const observerWeaponCards = computed(() => observerCards.value.filter((c) => WEAPONS.includes(c)))
const observerRoomCards = computed(() => observerCards.value.filter((c) => ROOMS.includes(c)))
const observerSelectedPlayerName = computed(() => {
  if (!props.observerPlayerState) return ''
  return playerName(props.observerPlayerState.playerId)
})
const observerSelectedDebug = computed(() => {
  if (!props.observerPlayerState) return null
  return props.agentDebugData?.[props.observerPlayerState.playerId] ?? null
})

const matchingCards = computed(() => {
  if (!props.showCardRequest) return []
  const suggestion = [
    props.showCardRequest.suspect,
    props.showCardRequest.weapon,
    props.showCardRequest.room
  ]
  return props.yourCards.filter((c) => suggestion.includes(c))
})

function playerName(pid) {
  if (!pid) return '?'
  const p = props.gameState?.players?.find((pl) => pl.id === pid)
  return p ? p.name : pid
}


function cardCategory(card) {
  if (SUSPECTS.includes(card)) return 'card-suspect'
  if (WEAPONS.includes(card)) return 'card-weapon'
  if (ROOMS.includes(card)) return 'card-room'
  return ''
}

// Per-card emoji icons

// Shown cards popup state
const shownCardsPlayerId = ref(null)
const shownCardsForPlayer = computed(() => {
  if (!shownCardsPlayerId.value || !notesRef.value) return []
  const pName = playerName(shownCardsPlayerId.value)
  return notesRef.value.getCardsShownBy(pName)
})

function onLegendClick(player) {
  if (props.isObserver) {
    emit('select-player', player.id)
    return
  }
  // Toggle shown cards popup for this player
  if (shownCardsPlayerId.value === player.id) {
    shownCardsPlayerId.value = null
  } else {
    shownCardsPlayerId.value = player.id
  }
}

// Card shown overlay state
const cardShownDismissedOnce = ref(false)

function dismissCardShownOverlay() {
  cardShownDismissedOnce.value = true
}

// Game over overlay state
const showGameOverOverlay = ref(false)

// Card preview state
const previewCard = ref(null)

function showCardPreview(card) {
  previewCard.value = previewCard.value === card ? null : card
}

function closePreview() {
  previewCard.value = null
}

// Actions
function onRoomSelected(room) {
  if (canMove.value) {
    targetRoom.value = room
    emit('action', { type: 'move', room })
    targetRoom.value = ''
  }
}

function onPositionSelected(position) {
  if (canMove.value) {
    emit('action', { type: 'move', position })
  }
}

function doSecretPassage() {
  emit('action', { type: 'secret_passage' })
}

function doRoll() {
  emit('action', { type: 'roll' })
}

function doMove() {
  emit('action', { type: 'move', room: targetRoom.value })
  targetRoom.value = ''
}

function doSuggest() {
  emit('action', {
    type: 'suggest',
    suspect: suggestSuspect.value,
    weapon: suggestWeapon.value,
    room: myCurrentRoom.value
  })
  suggestSuspect.value = ''
  suggestWeapon.value = ''
}

function doShowCard(card) {
  emit('action', { type: 'show_card', card })
}

function doAccuse() {
  emit('action', {
    type: 'accuse',
    suspect: accuseSuspect.value,
    weapon: accuseWeapon.value,
    room: accuseRoom.value
  })
  showAccuseForm.value = false
}

function doEndTurn() {
  emit('action', { type: 'end_turn' })
}

// Debounced save of detective notes to backend
let saveNotesTimer = null
function onNotesChanged(notesData) {
  if (saveNotesTimer) clearTimeout(saveNotesTimer)
  saveNotesTimer = setTimeout(() => {
    fetch(`/api/clue/games/${props.gameId}/notes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: props.playerId, notes: notesData })
    }).catch(() => { })
  }, 500)
}

// Close shown cards popup when clicking outside
function onDocClick() {
  shownCardsPlayerId.value = null
}
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  if (saveNotesTimer) clearTimeout(saveNotesTimer)
})

// Auto-mark shown cards in detective notes + reset overlay
watch(
  () => props.cardShown,
  (shown) => {
    if (shown) {
      cardShownDismissedOnce.value = false
      if (shown.card && notesRef.value) {
        notesRef.value.markCard(shown.card, 'seen', playerName(shown.by))
      }
    }
  }
)

// Trigger game over overlay when game finishes
watch(
  () => props.gameState?.status,
  (status) => {
    if (status === 'finished') {
      showGameOverOverlay.value = true
    }
  }
)

// Reset accuse form on turn change
watch(
  () => props.gameState?.whose_turn,
  () => {
    showAccuseForm.value = false
  }
)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.game-board {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  font-family: 'Crimson Text', Georgia, serif;
}

/* Header */
.game-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-panel);
  border: 1px solid var(--border-panel);
  border-radius: 8px;
  padding: 0.6rem 1.2rem;
  gap: 1rem;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.header-left h1 {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.5rem;
  font-weight: 900;
  color: var(--accent);
  letter-spacing: 0.15em;
  margin: 0;
  text-shadow: 0 0 20px var(--accent-glow);
}

.game-id-label {
  font-size: 0.7rem;
  color: var(--text-dim);
  letter-spacing: 0.08em;
}

.header-center {
  flex: 1;
  text-align: center;
}

.status-banner {
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.3rem 1rem;
  border-radius: 20px;
  display: inline-block;
  letter-spacing: 0.02em;
}

.status-banner.my-turn {
  background: var(--accent-bg);
  color: var(--accent);
  border: 1px solid var(--accent-border-hover);
}

.status-banner.waiting {
  color: var(--text-muted);
}

.status-banner.winner {
  background: rgba(46, 160, 80, 0.15);
  color: #4caf50;
  border: 1px solid rgba(46, 160, 80, 0.25);
}

.solution-detail {
  font-size: 0.85rem;
  font-weight: normal;
  margin-top: 0.2rem;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.observer-badge {
  background: var(--accent-bg);
  color: var(--accent);
  font-size: 0.65rem;
  padding: 0.2rem 0.6rem;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.dice-display {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.dice {
  background: var(--accent);
  color: var(--accent-text);
  width: 28px;
  height: 28px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.95rem;
  font-family: 'Playfair Display', Georgia, serif;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

/* Main layout */
.main-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 0.75rem;
  min-height: 400px;
  align-items: start;
}

/* Board column */
.board-column {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/* Player legend */
.player-legend {
  background: var(--bg-panel);
  border: 1px solid var(--border-panel);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  transition: border-color 0.2s;
  position: relative;
  cursor: pointer;
}

.legend-item.active {
  border-color: rgba(212, 168, 73, 0.3);
  background: rgba(212, 168, 73, 0.06);
}

.legend-item.eliminated {
  opacity: 0.35;
}

.legend-item.is-me {
  border-color: rgba(212, 168, 73, 0.15);
}

.legend-item.observer-clickable {
  cursor: pointer;
}

.legend-item.observer-clickable:hover {
  border-color: rgba(142, 68, 173, 0.4);
  background: rgba(142, 68, 173, 0.08);
}

.legend-item.observer-selected {
  border-color: rgba(142, 68, 173, 0.6);
  background: rgba(142, 68, 173, 0.12);
}

.observer-hint {
  font-size: 0.8rem;
  color: #778;
  font-style: italic;
  text-align: center;
  padding: 0.5rem;
}


.legend-name {
  font-weight: 600;
  color: var(--text-primary);
}

.legend-character {
  color: var(--text-dim);
  font-style: italic;
}

.legend-room {
  color: var(--accent);
  font-size: 0.7rem;
}

.legend-status {
  color: var(--error);
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.legend-turn {
  background: var(--accent);
  color: var(--accent-text);
  font-size: 0.6rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.wanderer-legend {
  opacity: 0.5;
}


.legend-wanderer-label {
  color: var(--text-faint);
  font-size: 0.6rem;
  font-style: italic;
}

/* Shown cards popup */
.shown-cards-popup {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  background: var(--bg-panel-solid);
  border: 1px solid var(--accent-border-hover);
  border-radius: 4px;
  padding: 0.4rem 0.6rem;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}

.shown-cards-title {
  color: var(--accent);
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.3rem;
}

.shown-cards-hand {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

/* Sidebar */
.sidebar-column {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.sidebar-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-panel);
  border-radius: 6px;
  padding: 0.8rem;
}

/* Panel headers and collapsible headers are in styles/components.css */

/* Cards */
.card-hand {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.hand-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  padding: 4px;
  border-radius: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  border: 1.5px solid #c8b88a;
  width: 80px;
  box-sizing: border-box;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2), 0 1px 2px rgba(0, 0, 0, 0.1);
  position: relative;
  overflow: hidden;
  background: #f5f0e1;
}

.card-suspect {
  border-color: #b8848a;
  color: #6b1a2a;
}

.card-weapon {
  border-color: #8a9cb8;
  color: #1a3a5b;
}

.card-room {
  border-color: #8ab89a;
  color: #1a5b3a;
}


.card-group {
  margin-bottom: 0.5rem;
}

.card-group:last-child {
  margin-bottom: 0;
}

.card-group-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 0.25rem;
  font-weight: 600;
}

.card-group-suspect {
  color: #d4888a;
}

.card-group-weapon {
  color: #7aa8d4;
}

.card-group-room {
  color: #7ac89a;
}

[data-theme="light"] .card-group-suspect {
  color: #9b1b30;
}

[data-theme="light"] .card-group-weapon {
  color: #1a3a6b;
}

[data-theme="light"] .card-group-room {
  color: #1a6b3c;
}

.card-icon {
  font-size: 1.4rem;
  margin: 0.3rem 0;
  filter: none;
}

.card-label {
  white-space: nowrap;
  text-align: center;
  font-size: 0.65rem;
  line-height: 1.15;
  word-break: break-word;
  white-space: normal;
  font-family: 'Playfair Display', Georgia, serif;
  font-weight: 700;
  color: #3a3020;
}

.no-cards {
  color: var(--text-faint);
  font-style: italic;
  font-size: 0.85rem;
}

/* Card shown notification */
.shown-card-panel {
  border-color: rgba(26, 58, 107, 0.4);
  background: linear-gradient(135deg, rgba(26, 58, 107, 0.15), var(--bg-panel-solid));
}

.shown-card-notice {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  color: var(--text-primary);
}

.shown-card-icon {
  font-size: 1.3rem;
  flex-shrink: 0;
}

.shown-card-name {
  color: #7aa8d4;
  font-weight: bold;
}

[data-theme="light"] .shown-card-name {
  color: #1a3a6b;
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0;
  margin-left: auto;
  transition: color 0.2s;
}

.dismiss-btn:hover {
  color: var(--text-primary);
}

/* Show card request */
.show-card-request-panel {
  border: 1.5px solid rgba(155, 27, 48, 0.6);
  background: linear-gradient(135deg, rgba(155, 27, 48, 0.1), var(--bg-panel-solid));
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {

  0%,
  100% {
    border-color: rgba(155, 27, 48, 0.6);
  }

  50% {
    border-color: rgba(155, 27, 48, 0.9);
    box-shadow: 0 0 12px rgba(155, 27, 48, 0.15);
  }
}

.show-card-desc {
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
  color: var(--text-primary);
}

/* Card type color highlights */
.highlight-suspect {
  color: #d4888a;
  font-weight: bold;
}

.highlight-weapon {
  color: #7aa8d4;
  font-weight: bold;
}

.highlight-room {
  color: #7ac89a;
  font-weight: bold;
}

[data-theme="light"] .highlight-suspect {
  color: #9b1b30;
}

[data-theme="light"] .highlight-weapon {
  color: #1a3a6b;
}

[data-theme="light"] .highlight-room {
  color: #1a6b3c;
}

.show-card-prompt {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

.show-card-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.show-card-btn {
  color: #e8dcc8;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: #9b1b30;
}

.show-card-btn:hover {
  filter: brightness(1.15);
  transform: translateY(-1px);
}

.show-card-btn.card-suspect {
  background: #9b1b30;
  color: #e8dcc8;
}

.show-card-btn.card-weapon {
  background: #1a3a6b;
  color: #e8dcc8;
}

.show-card-btn.card-room {
  background: #1a6b3c;
  color: #e8dcc8;
}

[data-theme="light"] .show-card-btn.card-suspect,
[data-theme="vintage"] .show-card-btn.card-suspect {
  background: rgba(155, 27, 48, 0.12);
  color: #7a1525;
  border: 1.5px solid rgba(155, 27, 48, 0.4);
}

[data-theme="light"] .show-card-btn.card-weapon,
[data-theme="vintage"] .show-card-btn.card-weapon {
  background: rgba(26, 58, 107, 0.12);
  color: #1a3a6b;
  border: 1.5px solid rgba(26, 58, 107, 0.4);
}

[data-theme="light"] .show-card-btn.card-room,
[data-theme="vintage"] .show-card-btn.card-room {
  background: rgba(26, 107, 60, 0.12);
  color: #145430;
  border: 1.5px solid rgba(26, 107, 60, 0.4);
}

/* Actions */
.action-group {
  margin-bottom: 0.75rem;
}

.action-group h3 {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 0.3rem;
  font-weight: 600;
}

.action-hint {
  font-size: 0.75rem;
  color: var(--text-dim);
  margin-bottom: 0.3rem;
}

.reachable-count {
  display: inline-block;
  color: #4caf50;
  font-weight: bold;
  margin-left: 0.3rem;
}

.action-select {
  display: block;
  width: 100%;
  margin-bottom: 0.35rem;
  padding: 0.45rem 0.6rem;
  border-radius: 4px;
  border: 1px solid var(--accent-border);
  background: var(--bg-input);
  color: var(--text-primary);
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.85rem;
  appearance: none;
  cursor: pointer;
  transition: border-color 0.2s;
}

.action-select:focus {
  border-color: var(--accent-border-focus);
  outline: none;
  box-shadow: 0 0 0 2px var(--accent-bg);
}

.action-btn {
  display: block;
  width: 100%;
  padding: 0.55rem 0.75rem;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  font-family: 'Crimson Text', Georgia, serif;
  transition: all 0.25s;
  letter-spacing: 0.02em;
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.passage-btn {
  background: linear-gradient(135deg, #5c2d82, #4a2268);
  color: #f0e8f8;
}

.passage-btn:hover {
  box-shadow: 0 3px 12px rgba(92, 45, 130, 0.2);
  transform: translateY(-1px);
}

.roll-btn {
  background: linear-gradient(135deg, var(--accent), var(--accent-dark));
  color: var(--accent-text);
}

.roll-btn:hover {
  box-shadow: 0 3px 12px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.move-btn {
  background: linear-gradient(135deg, var(--accent), var(--accent-dark));
  color: var(--accent-text);
}

.move-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(212, 168, 73, 0.25);
  transform: translateY(-1px);
}

.suggest-btn {
  background: linear-gradient(135deg, #1a3a6b, #153058);
  color: #e8f0f8;
}

.suggest-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(26, 58, 107, 0.3);
  transform: translateY(-1px);
}

.toggle-accuse-btn {
  background: transparent;
  border: 1px solid rgba(155, 27, 48, 0.2);
  color: var(--text-muted);
  font-weight: normal;
}

.toggle-accuse-btn:hover {
  border-color: rgba(155, 27, 48, 0.5);
  color: var(--error);
}

.action-warning {
  font-size: 0.75rem;
  color: var(--error);
  margin-bottom: 0.4rem;
  font-style: italic;
}

.accuse-buttons {
  display: flex;
  gap: 0.4rem;
}

.accuse-btn {
  background: linear-gradient(135deg, #9b1b30, #7a1525);
  color: #f8e8e8;
  flex: 1;
}

.accuse-btn:not(:disabled):hover {
  box-shadow: 0 3px 12px rgba(155, 27, 48, 0.25);
  transform: translateY(-1px);
}

.cancel-btn {
  background: var(--bg-input);
  color: var(--text-muted);
  flex: 0;
  white-space: nowrap;
}

.cancel-btn:hover {
  background: var(--bg-input-focus);
  color: var(--text-secondary);
}

.end-turn-btn {
  background: linear-gradient(135deg, #1a6b3c, #14562e);
  color: #e8f8ee;
}

.end-turn-btn:hover {
  box-shadow: 0 3px 12px rgba(26, 107, 60, 0.2);
  transform: translateY(-1px);
}

.auto-end-timer {
  margin-bottom: 0.4rem;
}

.timer-bar {
  height: 3px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.25rem;
}

.timer-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 1s linear;
}

.timer-text {
  font-size: 0.75rem;
  color: var(--accent);
  font-weight: 600;
}

.header-timer {
  font-size: 0.85rem;
  color: var(--accent);
}

/* Waiting message */
.waiting-panel {
  text-align: center;
}

.waiting-message {
  padding: 0.5rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  font-style: italic;
}

/* Notes panel */
.notes-panel {
  max-height: 300px;
  overflow-y: auto;
}

/* Chat */
.chat-panel-wrapper {
  min-height: 200px;
  grid-column: 1;
}

/* Card thumbnails in hand */
.card-with-image {
  cursor: pointer;
  transition: all 0.25s ease;
  position: relative;
}

.card-with-image:hover {
  border-color: #a8984a;
  transform: translateY(-4px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25), 0 0 8px rgba(168, 152, 74, 0.15);
}

.card-thumb {
  width: 64px;
  height: 52px;
  border-radius: 4px;
  object-fit: cover;
  object-position: center 15%;
  border: 1.5px solid #b8a878;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  background: #e8e0cc;
}

.card-thumb-room {
  border-radius: 4px;
  object-position: center center;
}

.card-thumb-weapon {
  border-radius: 4px;
  object-position: center center;
  border-color: #8a9cb8;
}

.show-card-thumb {
  width: 24px;
  height: 24px;
  object-fit: cover;
  flex-shrink: 0;
}

.card-with-image:hover .card-thumb {
  border-color: #a8984a;
  box-shadow: 0 0 4px rgba(168, 152, 74, 0.2);
}

.show-card-thumb.show-card-thumb-suspect {
  border-radius: 50%;
  object-position: center 15%;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.show-card-thumb.show-card-thumb-room {
  border-radius: 4px;
  object-position: center center;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.show-card-thumb.show-card-thumb-weapon {
  border-radius: 4px;
  object-position: center center;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

/* ================================ */
/* Physical Card Style (shared)     */
/* ================================ */
.physical-card {
  background: #f5f0e1;
  border: 2px solid #c8b88a;
  border-radius: 10px;
  padding: 8px 8px 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25), 0 1px 3px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.physical-card-header,
.physical-card-footer {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  width: 100%;
  box-sizing: border-box;
}

.physical-card-header {
  justify-content: flex-start;
}

.physical-card-footer {
  justify-content: flex-end;
}

.physical-card-icon {
  font-size: 0.85rem;
  flex-shrink: 0;
}

.physical-card-title {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 0.8rem;
  font-weight: 700;
  color: #3a3020;
  letter-spacing: 0.03em;
  text-align: center;
  line-height: 1.1;
}

.physical-card-image-frame {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid #b8a878;
  background: #e8e0cc;
  display: flex;
  align-items: center;
  justify-content: center;
}

.physical-card.card-suspect .physical-card-image-frame {
  border-radius: 50%;
  aspect-ratio: 1;
  width: 75%;
  border-color: #8a4a50;
}

.physical-card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.physical-card.card-suspect .physical-card-image {
  object-position: center 15%;
}

.physical-card-icon-fallback {
  font-size: 2.5rem;
}

/* Category accent colors on physical cards */
.physical-card.card-suspect { border-color: #b8848a; }
.physical-card.card-weapon { border-color: #8a9cb8; }
.physical-card.card-room { border-color: #8ab89a; }

.physical-card.card-suspect .physical-card-title { color: #6b1a2a; }
.physical-card.card-weapon .physical-card-title { color: #1a3a5b; }
.physical-card.card-room .physical-card-title { color: #1a5b3a; }

/* ================================ */
/* Card Preview Overlay             */
/* ================================ */
.card-preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.card-preview-frame {
  position: relative;
  width: min(260px, 70vw);
  aspect-ratio: 57 / 89;
  background: #f5f0e1;
  border: 3px solid #c8b88a;
  border-radius: 14px;
  padding: 14px 14px 10px;
  box-shadow: 0 0 30px rgba(0, 0, 0, 0.2), 0 20px 60px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  animation: cardReveal 0.3s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  box-sizing: border-box;
}

.card-preview-frame.card-suspect { border-color: #b8848a; }
.card-preview-frame.card-weapon { border-color: #8a9cb8; }
.card-preview-frame.card-room { border-color: #8ab89a; }

@keyframes cardReveal {
  from { opacity: 0; transform: scale(0.85) rotateY(15deg); }
  to { opacity: 1; transform: scale(1) rotateY(0); }
}

.card-preview-header,
.card-preview-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  width: 100%;
  box-sizing: border-box;
}

.card-preview-header {
  justify-content: flex-start;
}

.card-preview-footer {
  justify-content: flex-end;
}

.card-preview-image-area {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.card-preview-icon {
  font-size: 1.1rem;
  flex-shrink: 0;
}

.card-preview-name {
  font-family: 'Playfair Display', Georgia, serif;
  color: #3a3020;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: center;
}

.card-preview-frame.card-suspect .card-preview-name { color: #6b1a2a; }
.card-preview-frame.card-weapon .card-preview-name { color: #1a3a5b; }
.card-preview-frame.card-room .card-preview-name { color: #1a5b3a; }

.card-preview-image-frame {
  width: 100%;
  max-height: 100%;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid #b8a878;
  background: #e8e0cc;
}

.card-preview-frame.card-suspect .card-preview-image-frame {
  border-radius: 50%;
  width: 90%;
  aspect-ratio: 1;
  border-color: #8a4a50;
}

.card-preview-image {
  width: 100%;
  display: block;
}

.card-preview-frame.card-weapon .card-preview-image {
  height: 100%;
  object-fit: cover;
  object-position: center center;
}

.card-preview-frame.card-suspect .card-preview-image {
  height: 100%;
  object-fit: cover;
  object-position: center 15%;
}

.card-preview-close {
  position: absolute;
  top: -10px;
  right: -10px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid #c8b88a;
  background: #f5f0e1;
  color: #6b5a3a;
  font-size: 1.1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  line-height: 1;
}

.card-preview-close:hover {
  background: #6b5a3a;
  color: #f5f0e1;
  border-color: #6b5a3a;
}

/* ================================ */
/* Card Shown Banner Overlay        */
/* ================================ */
.card-shown-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  animation: fadeIn 0.25s ease;
}

.card-shown-banner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem 2.5rem;
  background: linear-gradient(145deg, #2a2018, #1a1408);
  border: 2px solid rgba(212, 168, 73, 0.4);
  border-radius: 16px;
  box-shadow: 0 0 40px rgba(212, 168, 73, 0.12), 0 30px 80px rgba(0, 0, 0, 0.6);
  animation: bannerSlideIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes bannerSlideIn {
  from { opacity: 0; transform: translateY(30px) scale(0.9); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.card-shown-banner-label {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: #d4a849;
  background: rgba(212, 168, 73, 0.1);
  padding: 0.25rem 1rem;
  border-radius: 20px;
  border: 1px solid rgba(212, 168, 73, 0.2);
}

.card-shown-banner-suggestion {
  font-size: 0.9rem;
  color: #c8bca8;
  margin-bottom: 0.25rem;
}

.card-shown-banner-noshow {
  font-size: 1.1rem;
  font-weight: 700;
  color: #d4a849;
  padding: 1rem;
}

.card-shown-banner-from {
  font-size: 1rem;
  color: #c8bca8;
}

.shown-card-suggestion {
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

.card-shown-banner-card {
  animation: cardReveal 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 0.15s both;
}

.card-shown-banner-card.physical-card {
  width: min(180px, 50vw);
}

.card-shown-banner-card.physical-card .physical-card-image-frame {
  height: 130px;
}

.card-shown-banner-card.physical-card.card-suspect .physical-card-image-frame {
  height: 130px;
  width: 65%;
}

.card-shown-banner-dismiss {
  margin-top: 0.25rem;
  padding: 0.5rem 2rem;
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
  border: none;
  border-radius: 6px;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.03em;
}

.card-shown-banner-dismiss:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(212, 168, 73, 0.3);
}

/* ================================ */
/* Game Over Winner Overlay         */
/* ================================ */
.game-over-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10001;
  animation: fadeIn 0.3s ease;
}

.game-over-banner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 2.5rem 3rem;
  background: linear-gradient(145deg, #2a2018 0%, #1a1408 50%, #221a0e 100%);
  border: 2px solid rgba(212, 168, 73, 0.5);
  border-radius: 20px;
  box-shadow: 0 0 60px rgba(212, 168, 73, 0.15), 0 40px 100px rgba(0, 0, 0, 0.7);
  animation: bannerSlideIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
  max-width: 90vw;
}

[data-theme="light"] .game-over-banner,
[data-theme="vintage"] .game-over-banner {
  background: linear-gradient(145deg, var(--bg-panel-solid) 0%, var(--bg-page) 100%);
  border-color: var(--accent-border-hover);
  box-shadow: 0 0 40px var(--accent-glow), 0 20px 60px rgba(0, 0, 0, 0.2);
}

.game-over-trophy {
  font-size: 3rem;
  animation: trophyBounce 0.6s ease 0.3s both;
}

@keyframes trophyBounce {
  0% { transform: scale(0); opacity: 0; }
  60% { transform: scale(1.3); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}

.game-over-title {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.8rem;
  font-weight: 900;
  color: #d4a849;
  letter-spacing: 0.08em;
  text-shadow: 0 0 30px rgba(212, 168, 73, 0.2);
}

.game-over-winner {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.2rem;
  font-weight: 700;
  color: #e8dcc8;
  margin-bottom: 0.5rem;
}

[data-theme="light"] .game-over-winner,
[data-theme="vintage"] .game-over-winner {
  color: var(--text-primary);
}

.game-over-cards {
  display: flex;
  gap: 1.25rem;
  flex-wrap: wrap;
  justify-content: center;
}

.game-over-card.physical-card {
  width: 150px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 1px 3px rgba(0, 0, 0, 0.2);
}

.game-over-card.physical-card .physical-card-image-frame {
  height: 100px;
}

.game-over-card.physical-card.card-suspect .physical-card-image-frame {
  height: 100px;
  width: 65%;
}

.game-over-card:nth-child(1) { animation: cardFlipIn 0.5s ease 0.3s both; }
.game-over-card:nth-child(2) { animation: cardFlipIn 0.5s ease 0.5s both; }
.game-over-card:nth-child(3) { animation: cardFlipIn 0.5s ease 0.7s both; }

@keyframes cardFlipIn {
  0% { opacity: 0; transform: perspective(400px) rotateY(90deg) scale(0.8); }
  100% { opacity: 1; transform: perspective(400px) rotateY(0) scale(1); }
}

.game-over-dismiss {
  margin-top: 0.75rem;
  padding: 0.6rem 2.5rem;
  background: linear-gradient(135deg, #d4a849, #b8912e);
  color: #1a1008;
  border: none;
  border-radius: 8px;
  font-family: 'Crimson Text', Georgia, serif;
  font-size: 1rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.04em;
}

.game-over-dismiss:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(212, 168, 73, 0.35);
}

/* ================================ */
/* Tossed Cards on Board (win)      */
/* ================================ */
.board-map-wrapper {
  position: relative;
}

.board-tossed-cards {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  pointer-events: none;
  z-index: 50;
}

.tossed-card {
  pointer-events: auto;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.6));
}

.tossed-card-inner {
  background: #f5f0e1;
  border: 2px solid #c8b88a;
  border-radius: 8px;
  padding: 6px;
  width: 110px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.tossed-card-inner.card-suspect { border-color: #b8848a; }
.tossed-card-inner.card-weapon { border-color: #8a9cb8; }
.tossed-card-inner.card-room { border-color: #8ab89a; }

.tossed-card-image-frame {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 4px;
  overflow: hidden;
  border: 1.5px solid #b8a878;
  background: #e8e0cc;
}

.tossed-card-inner.card-suspect .tossed-card-image-frame {
  border-radius: 50%;
  aspect-ratio: 1;
  width: 75%;
  border-color: #8a4a50;
}

.tossed-card-image-frame img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tossed-card-inner.card-suspect .tossed-card-image-frame img {
  object-position: center 15%;
}

.tossed-card-icon {
  font-size: 2rem;
  padding: 10px;
}

.tossed-card-name {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 0.65rem;
  font-weight: 700;
  color: #3a3020;
  text-align: center;
  padding: 3px 4px 2px;
  line-height: 1.1;
}

.tossed-card-inner.card-suspect .tossed-card-name { color: #6b1a2a; }
.tossed-card-inner.card-weapon .tossed-card-name { color: #1a3a5b; }
.tossed-card-inner.card-room .tossed-card-name { color: #1a5b3a; }

/* Tossed card positions - scattered look */
.tossed-card-1 {
  animation: tossCard1 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) 0.2s both;
}

.tossed-card-2 {
  animation: tossCard2 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) 0.4s both;
}

.tossed-card-3 {
  animation: tossCard3 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) 0.6s both;
}

@keyframes tossCard1 {
  0% { opacity: 0; transform: translateY(-80px) rotate(-30deg) scale(0.5); }
  100% { opacity: 1; transform: translateY(0) rotate(-8deg) scale(1); }
}

@keyframes tossCard2 {
  0% { opacity: 0; transform: translateY(-80px) rotate(20deg) scale(0.5); }
  100% { opacity: 1; transform: translateY(0) rotate(3deg) scale(1); }
}

@keyframes tossCard3 {
  0% { opacity: 0; transform: translateY(-80px) rotate(40deg) scale(0.5); }
  100% { opacity: 1; transform: translateY(0) rotate(11deg) scale(1); }
}

/* Responsive */
@media (max-width: 900px) {
  .main-layout {
    grid-template-columns: 1fr;
  }

  .game-header {
    flex-wrap: wrap;
  }

  .header-center {
    order: 3;
    flex-basis: 100%;
  }

  .sidebar-column {
    max-width: 100%;
  }
}

@media (max-width: 500px) {
  .game-header {
    padding: 0.4rem 0.6rem;
    gap: 0.5rem;
  }

  .header-left h1 {
    font-size: 1.1rem;
  }

  .header-left {
    gap: 0.35rem;
  }

  .header-right {
    gap: 0.4rem;
  }

  .status-banner {
    font-size: 0.82rem;
    padding: 0.25rem 0.6rem;
  }

  .dice {
    width: 24px;
    height: 24px;
    font-size: 0.8rem;
  }

  .hand-card {
    width: 68px;
    font-size: 0.65rem;
  }

  .physical-card-image-frame {
    height: 50px;
  }

  .sidebar-panel {
    padding: 0.5rem;
  }

  .game-over-cards {
    gap: 0.75rem;
  }
  .game-over-card.physical-card {
    width: 100px;
  }
  .game-over-card-frame {
    width: 85px;
    height: 65px;
  }
  .game-over-banner {
    padding: 1.5rem 1.5rem;
  }

  .legend-name,
  .legend-character {
    display: none;
  }
}

@media (max-width: 390px) {
  .header-left h1 {
    font-size: 1rem;
    letter-spacing: 0.1em;
  }

  .game-id-label {
    display: none;
  }

  .hand-card {
    width: 60px;
    font-size: 0.6rem;
  }

  .card-hand {
    gap: 0.3rem;
  }

  .status-banner {
    font-size: 0.75rem;
    padding: 0.2rem 0.5rem;
  }
}
</style>
