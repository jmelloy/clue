<template>
  <div id="clue-app">
    <ThemeSwitcher class="global-theme-switcher" />
    <Lobby
      v-if="!gameId"
      :url-game-id="urlGameId"
      :url-game-type="currentGameType"
      @game-joined="onGameJoined"
      @observe="onObserve"
      @rejoin="onRejoin"
      @clear-url-game="urlGameId = null"
    />

    <!-- Clue game views -->
    <template v-else-if="currentGameType === 'clue'">
      <WaitingRoom
        v-if="gameStatus === 'waiting'"
        :game-id="gameId"
        :player-id="playerId"
        :players="players"
        @game-started="onGameStarted"
        @leave-game="leaveGame"
      />
      <GameBoard
        v-else
        :game-id="gameId"
        :player-id="playerId"
        :game-state="gameState"
        :board-data="boardData"
        :your-cards="yourCards"
        :available-actions="availableActions"
        :show-card-request="showCardRequest"
        :card-shown="cardShown"
        :chat-messages="chatMessages"
        :is-observer="isObserver"
        :auto-end-timer="autoEndTimer"
        :auto-show-card-timer="autoShowCardTimer"
        :reachable-rooms="reachableRooms"
        :reachable-positions="reachablePositions"
        :saved-notes="savedNotes"
        :agent-debug-data="agentDebugData"
        :observer-player-state="observerPlayerState"
        @action="sendAction"
        @send-chat="sendChat"
        @dismiss-card-shown="cardShown = null"
        @select-player="onObserverSelectPlayer"
      />
    </template>

    <!-- Texas Hold'em views -->
    <template v-else-if="currentGameType === 'holdem'">
      <PokerWaitingRoom
        v-if="gameStatus === 'waiting'"
        :game-id="gameId"
        :player-id="playerId"
        :players="players"
        @game-started="onGameStarted"
        @leave-game="leaveGame"
      />
      <PokerTable
        v-else
        ref="pokerTableRef"
        :game-id="gameId"
        :player-id="playerId"
        :game-state="gameState"
        :your-cards="yourCards"
        :available-actions="availableActions"
        :chat-messages="chatMessages"
        :is-observer="isObserver"
        @action="sendHoldemAction"
        @send-chat="sendHoldemChat"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import Lobby from "./components/Lobby.vue";
import WaitingRoom from "./components/WaitingRoom.vue";
import GameBoard from "./components/GameBoard.vue";
import PokerWaitingRoom from "./components/PokerWaitingRoom.vue";
import PokerTable from "./components/PokerTable.vue";
import ThemeSwitcher from "./components/ThemeSwitcher.vue";
import { useTheme } from "./composables/useTheme.js";

// Initialize theme on app load
useTheme();

const gameId = ref(null);
const playerId = ref(null);
const gameState = ref(null);
const yourCards = ref([]);
const availableActions = ref([]);
const showCardRequest = ref(null);
const cardShown = ref(null);
const chatMessages = ref([]);
const isObserver = ref(false);
const urlGameId = ref(null);
const autoEndTimer = ref(null);
const autoShowCardTimer = ref(null);
const reachableRooms = ref([]);
const reachablePositions = ref([]);
const savedNotes = ref(null);
const boardData = ref(null);
const agentDebugData = ref({});
const observerPlayerState = ref(null);
const currentGameType = ref("clue"); // 'clue' or 'holdem'
const pokerTableRef = ref(null);

const gameStatus = computed(() => gameState.value?.status ?? "waiting");
const players = computed(() => gameState.value?.players ?? []);

let ws = null;
let reconnectTimer = null;

// --- URL routing ---

function parseGameIdFromUrl() {
  // Check holdem route first
  const holdemMatch = window.location.pathname.match(/^\/holdem\/([A-Za-z0-9]+)/);
  if (holdemMatch) return { gameId: holdemMatch[1].toUpperCase(), gameType: "holdem" };
  // Check clue route
  const clueMatch = window.location.pathname.match(/^\/game\/([A-Za-z0-9]+)/);
  if (clueMatch) return { gameId: clueMatch[1].toUpperCase(), gameType: "clue" };
  return null;
}

function pushGameUrl(gid) {
  const prefix = currentGameType.value === "holdem" ? "/holdem" : "/game";
  const url = `${prefix}/${gid}`;
  if (window.location.pathname !== url) {
    window.history.pushState({ gameId: gid, gameType: currentGameType.value }, "", url);
  }
}

function pushLobbyUrl() {
  if (window.location.pathname !== "/") {
    window.history.pushState({}, "", "/");
  }
}

function onPopState() {
  const parsed = parseGameIdFromUrl();
  if (parsed && gameId.value && parsed.gameId === gameId.value) {
    return;
  }
  if (!parsed) {
    leaveGame();
  } else if (parsed.gameId !== gameId.value) {
    resetState();
    currentGameType.value = parsed.gameType;
    urlGameId.value = parsed.gameId;
  }
}

onMounted(async () => {
  window.addEventListener("popstate", onPopState);
  const parsed = parseGameIdFromUrl();
  if (parsed) {
    currentGameType.value = parsed.gameType;
    urlGameId.value = parsed.gameId;
  }
  try {
    const res = await fetch("/board");
    if (res.ok) boardData.value = await res.json();
  } catch (_) {
    /* fall back to hardcoded board data */
  }
});

onUnmounted(() => {
  window.removeEventListener("popstate", onPopState);
});

// --- WebSocket ---

function connectWS() {
  if (!gameId.value || !playerId.value) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const wsPath = currentGameType.value === "holdem"
    ? `/ws/holdem/${gameId.value}/${playerId.value}`
    : `/ws/${gameId.value}/${playerId.value}`;
  ws = new WebSocket(`${proto}://${location.host}${wsPath}`);

  ws.onopen = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onclose = () => {
    // Auto-reconnect after 3 seconds
    if (gameId.value && playerId.value) {
      reconnectTimer = setTimeout(connectWS, 3000);
    }
  };

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (currentGameType.value === "holdem") {
        handleHoldemMessage(msg);
      } else {
        handleMessage(msg);
      }
    } catch (e) {
      // ignore non-JSON messages
    }
  };
}

function handleMessage(msg) {
  switch (msg.type) {
    case "game_state":
      if (msg.state) {
        gameState.value = msg.state;
        if (msg.state.your_cards) yourCards.value = msg.state.your_cards;
        if (msg.state.available_actions)
          availableActions.value = msg.state.available_actions;
        // Restore detective notes on reconnect
        if (msg.state.detective_notes)
          savedNotes.value = msg.state.detective_notes;
        // Restore showCardRequest from pending_show_card on reconnect
        const pending = msg.state.pending_show_card;
        if (pending && pending.player_id === playerId.value) {
          showCardRequest.value = {
            suggestingPlayerId: pending.suggesting_player_id,
            suspect: pending.suspect,
            weapon: pending.weapon,
            room: pending.room,
          };
        } else {
          showCardRequest.value = null;
        }
      } else {
        // Partial update: merge individual fields
        const { type: _type, ...fields } = msg;
        gameState.value = { ...gameState.value, ...fields };
      }
      autoEndTimer.value = null;
      autoShowCardTimer.value = null;
      reachableRooms.value = [];
      reachablePositions.value = [];
      // Update position/room in debug data for all players
      if (gameState.value) {
        const updated = { ...agentDebugData.value };
        for (const pid of Object.keys(updated)) {
          updated[pid] = {
            ...updated[pid],
            position: gameState.value.player_positions?.[pid] ?? null,
            room: gameState.value.current_room?.[pid] ?? null,
          };
        }
        agentDebugData.value = updated;
      }
      break;

    case "player_joined":
      if (gameState.value) {
        gameState.value = { ...gameState.value, players: msg.players };
      }
      break;

    case "game_started":
      if (msg.your_cards) yourCards.value = msg.your_cards;
      if (msg.available_actions) availableActions.value = msg.available_actions;
      if (msg.state) {
        // Broadcast with full state object — use it directly
        gameState.value = msg.state;
      } else if (gameState.value) {
        // Individual per-player message with top-level fields
        gameState.value = {
          ...gameState.value,
          status: "playing",
          whose_turn: msg.whose_turn,
        };
      }
      break;

    case "your_turn":
      if (msg.available_actions) availableActions.value = msg.available_actions;
      if (msg.reachable_rooms) reachableRooms.value = msg.reachable_rooms;
      if (msg.reachable_positions)
        reachablePositions.value = msg.reachable_positions;
      showCardRequest.value = null;
      autoEndTimer.value = null;
      break;

    case "auto_end_timer":
      autoEndTimer.value = {
        playerId: msg.player_id,
        seconds: msg.seconds,
        startedAt: Date.now(),
      };
      break;

    case "auto_show_card_timer":
      autoShowCardTimer.value = {
        playerId: msg.player_id,
        seconds: msg.seconds,
        startedAt: Date.now(),
      };
      break;

    case "show_card_request":
      showCardRequest.value = {
        suggestingPlayerId: msg.suggesting_player_id,
        suspect: msg.suspect,
        weapon: msg.weapon,
        room: msg.room,
      };
      if (msg.available_actions) availableActions.value = msg.available_actions;
      break;

    case "dice_rolled":
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          last_roll: msg.last_roll,
          dice_rolled: true,
        };
      }
      if (msg.reachable_rooms) reachableRooms.value = msg.reachable_rooms;
      break;

    case "player_moved":
      if (gameState.value) {
        const rooms = {
          ...gameState.value.current_room,
          [msg.player_id]: msg.room,
        };
        const positions = { ...(gameState.value.player_positions || {}) };
        if (msg.position) positions[msg.player_id] = msg.position;
        const updates = {
          current_room: rooms,
          player_positions: positions,
          moved: true,
        };
        gameState.value = { ...gameState.value, ...updates };
      }
      // Clear reachable highlights after movement
      reachableRooms.value = [];
      reachablePositions.value = [];
      // Update debug data for moved player
      if (agentDebugData.value[msg.player_id]) {
        agentDebugData.value = {
          ...agentDebugData.value,
          [msg.player_id]: {
            ...agentDebugData.value[msg.player_id],
            position: msg.position ?? null,
            room: msg.room ?? null,
          },
        };
      }
      break;

    case "suggestion_made":
      if (gameState.value) {
        const suggUpdate = {
          suggestions_this_turn: [
            ...(gameState.value.suggestions_this_turn ?? []),
            {
              suspect: msg.suspect,
              weapon: msg.weapon,
              room: msg.room,
              suggested_by: msg.player_id,
            },
          ],
        };
        // Update player positions if a suspect player was moved
        if (msg.player_positions)
          suggUpdate.player_positions = msg.player_positions;
        gameState.value = { ...gameState.value, ...suggUpdate };
      }
      break;

    case "card_shown":
      cardShown.value = { card: msg.card, by: msg.shown_by };
      if (msg.available_actions) availableActions.value = msg.available_actions;
      showCardRequest.value = null;
      autoShowCardTimer.value = null;
      break;

    case "card_shown_public":
      // A card was shown between two players (we don't see which card)
      // Clear any pending show card state
      showCardRequest.value = null;
      autoShowCardTimer.value = null;
      break;

    case "accusation_made":
      if (gameState.value && !msg.correct) {
        // Mark the player as eliminated
        const updatedPlayers = gameState.value.players.map((p) =>
          p.id === msg.player_id ? { ...p, active: false } : p
        );
        gameState.value = { ...gameState.value, players: updatedPlayers };
      }
      break;

    case "game_over":
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          status: "finished",
          winner: msg.winner,
          solution: msg.solution,
        };
      }
      availableActions.value = [];
      autoEndTimer.value = null;
      autoShowCardTimer.value = null;
      break;

    case "chat_message":
      chatMessages.value = [...chatMessages.value, msg];
      break;

    case "agent_debug":
      if (msg.player_id) {
        agentDebugData.value = {
          ...agentDebugData.value,
          [msg.player_id]: msg,
        };
      }
      break;

    case "pong":
      // keep-alive response, no action needed
      break;
  }
}

// --- Game lifecycle ---

function resetState() {
  if (ws) {
    ws.onclose = null; // prevent reconnect
    ws.close();
    ws = null;
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  gameId.value = null;
  playerId.value = null;
  gameState.value = null;
  yourCards.value = [];
  availableActions.value = [];
  showCardRequest.value = null;
  cardShown.value = null;
  chatMessages.value = [];
  isObserver.value = false;
  autoEndTimer.value = null;
  autoShowCardTimer.value = null;
  reachableRooms.value = [];
  reachablePositions.value = [];
  savedNotes.value = null;
  agentDebugData.value = {};
  observerPlayerState.value = null;
  currentGameType.value = "clue";
}

function leaveGame() {
  resetState();
  urlGameId.value = null;
  pushLobbyUrl();
}

function onGameJoined({ gameId: gid, playerId: pid, state, gameType: gType }) {
  if (gType) currentGameType.value = gType;
  gameId.value = gid;
  playerId.value = pid;
  gameState.value = state;
  isObserver.value = false;
  urlGameId.value = null;
  pushGameUrl(gid);
  connectWS();
  if (currentGameType.value === "holdem") {
    loadHoldemChat(gid);
  } else {
    loadChat(gid);
  }
}

function onObserve({ gameId: gid, gameType: gType }) {
  if (gType) currentGameType.value = gType;
  gameId.value = gid;
  // Generate a random observer ID for WS connection
  playerId.value = "OBS_" + Math.random().toString(36).substring(2, 10);
  isObserver.value = true;
  urlGameId.value = null;

  // Fetch current state
  const endpoint = currentGameType.value === "holdem" ? `/holdem/games/${gid}` : `/games/${gid}`;
  fetch(endpoint)
    .then((r) => r.json())
    .then((state) => {
      gameState.value = state;
    })
    .catch(() => {});

  // Fetch initial agent debug data (Clue only)
  if (currentGameType.value === "clue") loadAgentDebug(gid);

  pushGameUrl(gid);
  connectWS();
  if (currentGameType.value === "holdem") {
    loadHoldemChat(gid);
  } else {
    loadChat(gid);
  }
}

function onRejoin({ gameId: gid, playerId: pid, gameType: gType }) {
  if (gType) currentGameType.value = gType;
  gameId.value = gid;
  playerId.value = pid;
  isObserver.value = false;
  urlGameId.value = null;

  // Fetch current state
  const endpoint = currentGameType.value === "holdem" ? `/holdem/games/${gid}` : `/games/${gid}`;
  fetch(endpoint)
    .then((r) => r.json())
    .then((state) => {
      gameState.value = state;
    })
    .catch(() => {});

  pushGameUrl(gid);
  connectWS(); // WS will send player-specific state (cards, actions)
  if (currentGameType.value === "holdem") {
    loadHoldemChat(gid);
  } else {
    loadChat(gid);
  }
}

function loadChat(gid) {
  fetch(`/games/${gid}/chat`)
    .then((r) => r.json())
    .then((data) => {
      chatMessages.value = data.messages ?? [];
    })
    .catch(() => {});
}

function loadAgentDebug(gid) {
  fetch(`/games/${gid}/agent_debug`)
    .then((r) => r.json())
    .then((data) => {
      if (data.agents) {
        const debugMap = {};
        for (const agent of data.agents) {
          debugMap[agent.player_id] = agent;
        }
        agentDebugData.value = debugMap;
      }
    })
    .catch(() => {});
}

function onObserverSelectPlayer(pid) {
  if (!isObserver.value || !gameId.value) return;
  fetch(`/games/${gameId.value}/player/${pid}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data) {
        observerPlayerState.value = {
          playerId: pid,
          your_cards: data.your_cards || [],
          available_actions: data.available_actions || [],
          detective_notes: data.detective_notes || null,
        };
      }
    })
    .catch(() => {});
}

function onGameStarted(state) {
  gameState.value = { ...gameState.value, ...state, status: "playing" };
}

async function sendAction(action) {
  const res = await fetch(`/games/${gameId.value}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: playerId.value, action }),
  });
  if (res.ok) {
    const result = await res.json();
    if (result.available_actions)
      availableActions.value = result.available_actions;
    // Refresh full state to stay in sync
    try {
      const stateRes = await fetch(`/games/${gameId.value}`);
      if (stateRes.ok) {
        const freshState = await stateRes.json();
        gameState.value = freshState;
      }
    } catch (e) {
      // rely on WS updates
    }
  }
}

async function sendChat(text) {
  await fetch(`/games/${gameId.value}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: playerId.value, text }),
  });
}

// --- Texas Hold'em ---

function handleHoldemMessage(msg) {
  switch (msg.type) {
    case "game_state":
      if (msg.state) {
        gameState.value = msg.state;
        if (msg.state.your_cards) yourCards.value = msg.state.your_cards;
        if (msg.state.available_actions) availableActions.value = msg.state.available_actions;
      }
      break;

    case "player_joined":
      if (gameState.value) {
        gameState.value = { ...gameState.value, players: msg.players };
      }
      break;

    case "game_started":
      if (msg.your_cards) yourCards.value = msg.your_cards;
      if (msg.available_actions) availableActions.value = msg.available_actions;
      if (msg.state) {
        gameState.value = msg.state;
      } else if (gameState.value) {
        gameState.value = { ...gameState.value, status: "playing", whose_turn: msg.whose_turn };
      }
      break;

    case "your_turn":
      if (msg.available_actions) availableActions.value = msg.available_actions;
      break;

    case "player_action":
      refreshHoldemState();
      break;

    case "community_cards":
      if (gameState.value) {
        gameState.value = {
          ...gameState.value,
          community_cards: msg.cards,
          betting_round: msg.betting_round,
        };
      }
      break;

    case "showdown":
      if (pokerTableRef.value) {
        pokerTableRef.value.onShowdown(msg);
      }
      refreshHoldemState();
      break;

    case "new_hand":
      refreshHoldemState();
      break;

    case "game_over":
      if (gameState.value) {
        gameState.value = { ...gameState.value, status: "finished", winner: msg.winner };
      }
      availableActions.value = [];
      break;

    case "chat_message":
      chatMessages.value = [...chatMessages.value, msg];
      break;

    case "pong":
      break;
  }
}

async function refreshHoldemState() {
  if (!gameId.value || !playerId.value) return;
  try {
    const res = await fetch(`/holdem/games/${gameId.value}/player/${playerId.value}`);
    if (res.ok) {
      const state = await res.json();
      gameState.value = state;
      if (state.your_cards) yourCards.value = state.your_cards;
      if (state.available_actions) availableActions.value = state.available_actions;
    }
  } catch (_) { /* rely on WS */ }
}

async function sendHoldemAction(action) {
  const res = await fetch(`/holdem/games/${gameId.value}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: playerId.value, action }),
  });
  if (res.ok) {
    const result = await res.json();
    if (result.available_actions) availableActions.value = result.available_actions;
    await refreshHoldemState();
  }
}

async function sendHoldemChat(text) {
  await fetch(`/holdem/games/${gameId.value}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_id: playerId.value, text }),
  });
}

function loadHoldemChat(gid) {
  fetch(`/holdem/games/${gid}/chat`)
    .then((r) => r.json())
    .then((data) => { chatMessages.value = data.messages ?? []; })
    .catch(() => {});
}

// Keep-alive ping every 30 seconds
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ping" }));
  }
}, 30000);
</script>

<style>
/* ═══ Theme CSS Variables ═══ */

/* Dark theme (default) */
:root,
[data-theme="dark"] {
  --bg-body: #1c1812;
  --bg-panel: rgba(30, 24, 16, 0.95);
  --bg-panel-solid: #1e1810;
  --bg-panel-hover: rgba(40, 32, 20, 0.95);
  --bg-input: rgba(255, 255, 255, 0.03);
  --bg-input-focus: rgba(255, 255, 255, 0.05);

  --text-primary: #e8dcc8;
  --text-secondary: #8a7e6b;
  --text-muted: #5a5040;
  --text-faint: #3a3528;

  --accent: #d4a849;
  --accent-dim: #b8912e;
  --accent-bg: rgba(212, 168, 73, 0.15);
  --accent-glow: rgba(212, 168, 73, 0.2);
  --accent-border: rgba(212, 168, 73, 0.12);

  --border-subtle: rgba(212, 168, 73, 0.12);
  --border-hover: rgba(212, 168, 73, 0.25);
  --border-focus: rgba(212, 168, 73, 0.4);

  --error-text: #c45050;
  --error-bg: rgba(139, 42, 42, 0.1);
  --error-border: rgba(139, 42, 42, 0.2);

  --success: #4caf50;

  /* Board */
  --board-bg: #1a1510;
  --board-border: #8b1a1a;
  --board-grid-line: #15110c;
  --hallway-color: #c8b88a;
  --hallway-border: rgba(160, 140, 100, 0.4);
  --room-bg: #1a1610;
  --room-filter: saturate(0.35) brightness(0.9);
  --wall-bg: #2a2a1e;
  --center-bg: #3a2e1e;
  --center-border: rgba(80, 65, 40, 0.3);
  --door-color: #e8be4a;
  --room-label-color: #f0e0b0;
  --room-label-bg: rgba(0, 0, 0, 0.45);
  --secret-passage-color: #c8a060;

  /* Panel chrome */
  --panel-gradient: linear-gradient(135deg, rgba(30, 24, 16, 0.95) 0%, rgba(18, 14, 10, 0.97) 100%);

  /* Fog/atmosphere */
  --fog-color-1: #d4a849;
  --fog-color-2: #8b2a2a;
  --vignette-color: #1c1812;
  --particle-color: rgba(212, 168, 73, 0.25);

  /* Chat */
  --chat-border: rgba(212, 168, 73, 0.04);
  --chat-system: #6a6050;
}

/* Light theme */
[data-theme="light"] {
  --bg-body: #f5f0e8;
  --bg-panel: rgba(255, 255, 255, 0.92);
  --bg-panel-solid: #faf8f4;
  --bg-panel-hover: rgba(255, 255, 255, 0.97);
  --bg-input: rgba(0, 0, 0, 0.04);
  --bg-input-focus: rgba(0, 0, 0, 0.06);

  --text-primary: #2c2418;
  --text-secondary: #6b5f4e;
  --text-muted: #9a8e7c;
  --text-faint: #c4b8a4;

  --accent: #b08830;
  --accent-dim: #977425;
  --accent-bg: rgba(176, 136, 48, 0.12);
  --accent-glow: rgba(176, 136, 48, 0.15);
  --accent-border: rgba(176, 136, 48, 0.2);

  --border-subtle: rgba(0, 0, 0, 0.1);
  --border-hover: rgba(176, 136, 48, 0.35);
  --border-focus: rgba(176, 136, 48, 0.5);

  --error-text: #b33030;
  --error-bg: rgba(179, 48, 48, 0.08);
  --error-border: rgba(179, 48, 48, 0.15);

  --success: #2e8b40;

  /* Board */
  --board-bg: #e8e0d0;
  --board-border: #a03030;
  --board-grid-line: #d8d0c0;
  --hallway-color: #d8c890;
  --hallway-border: rgba(160, 140, 100, 0.3);
  --room-bg: #e0d8c8;
  --room-filter: saturate(0.55) brightness(1.1);
  --wall-bg: #e0d8ca;
  --center-bg: #d8ceb8;
  --center-border: rgba(120, 100, 70, 0.2);
  --door-color: #c09820;
  --room-label-color: #4a3e28;
  --room-label-bg: rgba(255, 255, 255, 0.7);
  --secret-passage-color: #8a6a30;

  /* Panel chrome */
  --panel-gradient: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 248, 244, 0.97) 100%);

  /* Fog/atmosphere */
  --fog-color-1: #d4a849;
  --fog-color-2: #c08060;
  --vignette-color: #f5f0e8;
  --particle-color: rgba(176, 136, 48, 0.15);

  /* Chat */
  --chat-border: rgba(0, 0, 0, 0.06);
  --chat-system: #8a7e6b;
}

/* Vintage theme */
[data-theme="vintage"] {
  --bg-body: #2a2010;
  --bg-panel: rgba(42, 32, 16, 0.95);
  --bg-panel-solid: #2a2010;
  --bg-panel-hover: rgba(50, 38, 20, 0.95);
  --bg-input: rgba(255, 255, 255, 0.04);
  --bg-input-focus: rgba(255, 255, 255, 0.07);

  --text-primary: #e8d8b0;
  --text-secondary: #a09070;
  --text-muted: #70603a;
  --text-faint: #4a3e28;

  --accent: #c8952a;
  --accent-dim: #a07820;
  --accent-bg: rgba(200, 149, 42, 0.15);
  --accent-glow: rgba(200, 149, 42, 0.25);
  --accent-border: rgba(200, 149, 42, 0.15);

  --border-subtle: rgba(200, 149, 42, 0.12);
  --border-hover: rgba(200, 149, 42, 0.3);
  --border-focus: rgba(200, 149, 42, 0.45);

  --error-text: #c45050;
  --error-bg: rgba(139, 42, 42, 0.12);
  --error-border: rgba(139, 42, 42, 0.25);

  --success: #4caf50;

  /* Board — vintage uses board.jpg as background */
  --board-bg: #1a1408;
  --board-border: #6b1515;
  --board-grid-line: transparent;
  --hallway-color: transparent;
  --hallway-border: rgba(160, 140, 100, 0.15);
  --room-bg: transparent;
  --room-filter: saturate(0.3) brightness(0.85) sepia(0.3);
  --wall-bg: transparent;
  --center-bg: transparent;
  --center-border: transparent;
  --door-color: #e8be4a;
  --room-label-color: #f0e0b0;
  --room-label-bg: rgba(0, 0, 0, 0.55);
  --secret-passage-color: #c8a060;

  /* Panel chrome */
  --panel-gradient: linear-gradient(135deg, rgba(42, 32, 16, 0.96) 0%, rgba(28, 20, 10, 0.98) 100%);

  /* Fog/atmosphere */
  --fog-color-1: #c89530;
  --fog-color-2: #6b2020;
  --vignette-color: #2a2010;
  --particle-color: rgba(200, 149, 42, 0.2);

  /* Chat */
  --chat-border: rgba(200, 149, 42, 0.05);
  --chat-system: #7a6a4a;
}

/* ═══ Base Styles ═══ */

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
body {
  font-family: "Georgia", serif;
  background: var(--bg-body);
  color: var(--text-primary);
  min-height: 100vh;
  transition: background-color 0.3s ease, color 0.3s ease;
}
#clue-app {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0.75rem;
  position: relative;
}
.global-theme-switcher {
  position: fixed;
  top: 0.5rem;
  right: 0.75rem;
  z-index: 1000;
}
</style>
