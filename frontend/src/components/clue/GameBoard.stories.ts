import type { Meta, StoryObj } from '@storybook/vue3-vite'
import GameBoard from './GameBoard.vue'

// ── Shared test data ──

const players = [
  { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
  { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
  { id: 'p3', name: 'Agent-1', character: 'Mrs. White', type: 'agent', active: true },
  { id: 'p4', name: 'Agent-2', character: 'Reverend Green', type: 'agent', active: true },
  { id: 'p5', name: 'Diana', character: 'Mrs. Peacock', type: 'human', active: true },
  { id: 'p6', name: 'GPT-4', character: 'Professor Plum', type: 'llm_agent', active: true }
]

const playerPositions: Record<string, [number, number]> = {
  p1: [0, 16],  // Scarlett start
  p2: [7, 23],  // Mustard start
  p3: [24, 14], // White start
  p4: [24, 9],  // Green start
  p5: [5, 0],   // Peacock start (using Plum's start pos)
  p6: [18, 0]   // Plum start (using Peacock's start pos)
}

const midGamePositions: Record<string, [number, number]> = {
  p1: [2, 3],   // Study
  p2: [8, 10],  // center area
  p3: [14, 3],  // Billiard Room
  p4: [21, 10], // Ballroom
  p5: [10, 19], // Dining Room
  p6: [2, 19]   // Lounge
}

const baseGameState = {
  game_id: 'CLUE-4821',
  status: 'playing' as const,
  players,
  whose_turn: 'p1',
  turn_number: 1,
  current_room: {} as Record<string, string>,
  player_positions: playerPositions,
  suggestions_this_turn: [],
  winner: null,
  dice_rolled: false,
  moved: false,
  last_roll: null,
  pending_show_card: null,
  was_moved_by_suggestion: {},
  weapon_positions: {
    Candlestick: 'Kitchen',
    Knife: 'Study',
    'Lead Pipe': 'Library',
    Revolver: 'Ballroom',
    Rope: 'Conservatory',
    Wrench: 'Dining Room'
  },
  agent_trace_enabled: false
}

const midGameState = {
  ...baseGameState,
  turn_number: 12,
  player_positions: midGamePositions,
  current_room: {
    p1: 'Study',
    p3: 'Billiard Room',
    p4: 'Ballroom',
    p5: 'Dining Room',
    p6: 'Lounge'
  },
  dice_rolled: true,
  moved: true,
  last_roll: [4, 3],
  suggestions_this_turn: [
    {
      suspect: 'Colonel Mustard',
      weapon: 'Knife',
      room: 'Study',
      suggested_by: 'p1',
      pending_show_by: null
    }
  ]
}

const now = new Date()
function ts(secondsAgo: number) {
  return new Date(now.getTime() - secondsAgo * 1000).toISOString()
}

const chatMessages = [
  { type: 'chat_message', player_id: null, text: 'Alice rolled a 6 and moved to the Study.', timestamp: ts(320) },
  { type: 'chat_message', player_id: null, text: 'Alice suggests it was Colonel Mustard with the Knife in the Study.', timestamp: ts(310) },
  { type: 'chat_message', player_id: null, text: 'Bob showed a card to Alice.', timestamp: ts(305) },
  { type: 'chat_message', player_id: null, text: 'Bob rolled a 4 and moved to the Library.', timestamp: ts(240) },
  { type: 'chat_message', player_id: null, text: 'Bob suggests it was Mrs. White with the Revolver in the Library.', timestamp: ts(230) },
  { type: 'chat_message', player_id: null, text: 'No one could disprove the suggestion.', timestamp: ts(228) },
  { type: 'chat_message', player_id: 'p1', text: 'Alice: I think I know who did it!', timestamp: ts(180) },
  { type: 'chat_message', player_id: null, text: 'Agent-1 rolled a 3 and used the secret passage to the Study.', timestamp: ts(120) },
  { type: 'chat_message', player_id: null, text: 'Agent-1 suggests it was Professor Plum with the Rope in the Study.', timestamp: ts(115) },
  { type: 'chat_message', player_id: null, text: 'Diana showed a card to Agent-1.', timestamp: ts(110) },
  { type: 'chat_message', player_id: 'p2', text: 'Bob: Hmm, interesting move there.', timestamp: ts(80) },
  { type: 'chat_message', player_id: null, text: 'Diana rolled a 5 and moved to the Dining Room.', timestamp: ts(60) },
  { type: 'chat_message', player_id: null, text: 'GPT-4 rolled a 7 and moved to the Lounge.', timestamp: ts(30) }
]

const yourCards = ['Miss Scarlett', 'Knife', 'Library']

// ── Meta ──

const meta: Meta<typeof GameBoard> = {
  title: 'Clue/GameBoard',
  component: GameBoard,
  parameters: {
    layout: 'fullscreen'
  },
  argTypes: {
    gameId: { control: 'text' },
    playerId: { control: 'text' },
    gameState: { control: 'object' },
    yourCards: { control: 'object' },
    availableActions: { control: 'object' },
    chatMessages: { control: 'object' },
    isObserver: { control: 'boolean' },
    reachableRooms: { control: 'object' },
    savedNotes: { control: 'object' }
  },
  args: {
    gameId: 'CLUE-4821',
    playerId: 'p1',
    gameState: midGameState,
    yourCards,
    availableActions: ['suggest', 'accuse', 'end_turn'],
    chatMessages,
    isObserver: false,
    reachableRooms: [],
    reachablePositions: [],
    savedNotes: null,
    showCardRequest: undefined,
    cardShown: undefined,
    autoEndTimer: undefined,
    agentDebugData: {},
    observerPlayerState: undefined,
    suggestionTracking: null
  }
}

export default meta
type Story = StoryObj<typeof GameBoard>

// ═══════════════════════════════════════════════════════════════════
// Size class stories — test the layout at specific viewport widths
// ═══════════════════════════════════════════════════════════════════

/** Desktop: 1920×1080 — typical external monitor */
export const Desktop1080p: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1920, height: 1080 } }
  }
}

/** Laptop: 1440×900 — common MacBook / Windows laptop */
export const Laptop1440: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1440, height: 900 } }
  }
}

/** Small laptop: 1366×768 — most common laptop resolution worldwide */
export const Laptop1366: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1366, height: 768 } }
  }
}

/** Tablet landscape: 1024×768 — iPad classic */
export const TabletLandscape: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1024, height: 768 } }
  }
}

/** Tablet portrait: 768×1024 — iPad portrait (stacked layout) */
export const TabletPortrait: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 768, height: 1024 } }
  }
}

/** Mobile: 390×844 — iPhone 14 / modern phone */
export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 390, height: 844 } }
  }
}

/** Small mobile: 320×568 — iPhone SE / compact phone */
export const MobileSmall: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 320, height: 568 } }
  }
}

// ═══════════════════════════════════════════════════════════════════
// Game state stories
// ═══════════════════════════════════════════════════════════════════

/** Early game — dice not yet rolled, all players at starting positions */
export const EarlyGame: Story = {
  args: {
    gameState: {
      ...baseGameState,
      turn_number: 1,
      dice_rolled: false,
      moved: false,
      last_roll: null
    },
    yourCards,
    availableActions: ['roll']
  }
}

/** Player's turn — dice rolled, must choose a room to move to */
export const RolledDice: Story = {
  args: {
    gameState: {
      ...midGameState,
      dice_rolled: true,
      moved: false,
      last_roll: [5, 3]
    },
    availableActions: ['move'],
    reachableRooms: ['Hall', 'Kitchen', 'Library']
  }
}

/** Player can make a suggestion after moving into a room */
export const CanSuggest: Story = {
  args: {
    gameState: {
      ...midGameState,
      dice_rolled: true,
      moved: true,
      last_roll: [4, 2]
    },
    availableActions: ['suggest', 'accuse', 'end_turn']
  }
}

/** Player has been shown a card after making a suggestion */
export const CardShown: Story = {
  args: {
    gameState: midGameState,
    availableActions: ['accuse', 'end_turn'],
    cardShown: {
      card: 'Colonel Mustard',
      by: 'p2',
      suspect: 'Colonel Mustard',
      weapon: 'Knife',
      room: 'Study'
    }
  }
}

/** Player must choose which card to show to the suggesting player */
export const MustShowCard: Story = {
  args: {
    gameState: {
      ...midGameState,
      whose_turn: 'p2'
    },
    availableActions: ['show_card'],
    showCardRequest: {
      suggestingPlayerId: 'p2',
      suspect: 'Miss Scarlett',
      weapon: 'Knife',
      room: 'Library',
      matching_cards: ['Miss Scarlett', 'Knife', 'Library']
    }
  }
}

/** Waiting for another player's turn */
export const WaitingForTurn: Story = {
  args: {
    gameState: {
      ...midGameState,
      whose_turn: 'p2'
    },
    availableActions: []
  }
}

/** Observer view — watching without participating */
export const Observer: Story = {
  args: {
    playerId: 'observer-xyz',
    isObserver: true,
    gameState: midGameState,
    yourCards: [],
    availableActions: []
  }
}

/** Game over — winner declared with solution revealed */
export const GameOver: Story = {
  args: {
    gameState: {
      ...midGameState,
      status: 'finished',
      winner: 'p1',
      solution: {
        suspect: 'Professor Plum',
        weapon: 'Rope',
        room: 'Conservatory'
      }
    },
    availableActions: [],
    chatMessages: [
      ...chatMessages,
      { type: 'chat_message', player_id: null, text: 'Alice accuses Professor Plum with the Rope in the Conservatory!', timestamp: ts(10) },
      { type: 'chat_message', player_id: null, text: 'Alice is correct! The case is solved!', timestamp: ts(5) }
    ]
  }
}

/** Player eliminated after a wrong accusation */
export const Eliminated: Story = {
  args: {
    gameState: {
      ...midGameState,
      players: players.map((p) =>
        p.id === 'p1' ? { ...p, active: false } : p
      ),
      whose_turn: 'p2'
    },
    availableActions: []
  }
}

/** With detective notes partially filled in */
export const WithNotes: Story = {
  args: {
    gameState: midGameState,
    availableActions: ['suggest', 'accuse', 'end_turn'],
    savedNotes: {
      notes: {
        'Miss Scarlett': 'have',
        'Colonel Mustard': 'no',
        'Mrs. White': 'maybe',
        'Reverend Green': 'no',
        'Mrs. Peacock': 'seen',
        'Professor Plum': '',
        Knife: 'have',
        Candlestick: 'no',
        'Lead Pipe': 'seen',
        Revolver: 'no',
        Rope: '',
        Wrench: 'no',
        Library: 'have',
        Kitchen: 'no',
        Ballroom: '',
        Conservatory: 'no',
        'Billiard Room': 'no',
        Study: 'no',
        Hall: 'no',
        Lounge: 'no',
        'Dining Room': 'no'
      },
      shownBy: {
        'Mrs. Peacock': 'Bob',
        'Lead Pipe': 'Agent-1'
      }
    }
  }
}

/** Six players with wanderer — full lobby, dense board */
export const FullGame: Story = {
  args: {
    gameState: {
      ...midGameState,
      players: [
        ...players,
        { id: 'w1', name: 'Ghost', character: 'Mrs. White', type: 'wanderer', active: true }
      ],
      player_positions: {
        ...midGamePositions,
        w1: [15, 15]
      }
    }
  }
}

/** Auto-end timer counting down */
export const AutoEndTimer: Story = {
  args: {
    gameState: {
      ...midGameState,
      whose_turn: 'p1'
    },
    availableActions: ['end_turn'],
    autoEndTimer: {
      playerId: 'p1',
      seconds: 15,
      startedAt: Date.now() - 5000
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// Layout-specific: laptop height constraint tests
// ═══════════════════════════════════════════════════════════════════

/** Laptop 1440×900 with notes open — tests the height constraint fix */
export const Laptop1440WithNotes: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1440, height: 900 } }
  },
  args: {
    gameState: midGameState,
    availableActions: ['suggest', 'accuse', 'end_turn'],
    savedNotes: {
      notes: {
        'Miss Scarlett': 'have',
        'Colonel Mustard': 'no',
        'Mrs. White': 'maybe',
        'Reverend Green': 'no',
        'Mrs. Peacock': 'seen',
        'Professor Plum': '',
        Knife: 'have',
        Candlestick: 'no',
        'Lead Pipe': 'seen',
        Revolver: 'no',
        Rope: '',
        Wrench: 'no',
        Library: 'have',
        Kitchen: 'no',
        Ballroom: '',
        Conservatory: 'no',
        'Billiard Room': 'no',
        Study: 'no',
        Hall: 'no',
        Lounge: 'no',
        'Dining Room': 'no'
      },
      shownBy: { 'Mrs. Peacock': 'Bob' }
    }
  }
}

/** 1366×768 with full game state — most constrained common laptop */
export const Laptop1366FullState: Story = {
  parameters: {
    viewport: { defaultViewport: { width: 1366, height: 768 } }
  },
  args: {
    gameState: {
      ...midGameState,
      last_roll: [5, 3],
      dice_rolled: true,
      moved: true
    },
    availableActions: ['suggest', 'accuse', 'end_turn'],
    chatMessages,
    savedNotes: {
      notes: {
        'Miss Scarlett': 'have',
        'Colonel Mustard': 'no',
        Knife: 'have',
        Library: 'have'
      },
      shownBy: {}
    }
  }
}
