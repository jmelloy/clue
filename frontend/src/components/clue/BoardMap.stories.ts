import type { Meta, StoryObj } from '@storybook/vue3-vite'
import BoardMap from './BoardMap.vue'

// ── Shared test data ──

const players = [
  { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
  { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
  { id: 'p3', name: 'Agent-1', character: 'Mrs. White', type: 'agent', active: true },
  { id: 'p4', name: 'Agent-2', character: 'Reverend Green', type: 'agent', active: true },
  { id: 'p5', name: 'Diana', character: 'Mrs. Peacock', type: 'human', active: true },
  { id: 'p6', name: 'GPT-4', character: 'Professor Plum', type: 'llm_agent', active: true }
]

const startPositions: Record<string, [number, number]> = {
  p1: [0, 16],
  p2: [7, 23],
  p3: [24, 14],
  p4: [24, 9],
  p5: [5, 0],
  p6: [18, 0]
}

const midGamePositions: Record<string, [number, number]> = {
  p1: [2, 3],   // Study
  p2: [8, 10],  // hallway
  p3: [14, 3],  // Billiard Room
  p4: [21, 10], // Ballroom
  p5: [10, 19], // Dining Room
  p6: [2, 19]   // Lounge
}

const baseState = {
  game_id: 'CLUE-4821',
  status: 'playing' as const,
  players,
  whose_turn: 'p1',
  turn_number: 1,
  current_room: {} as Record<string, string>,
  player_positions: startPositions,
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

// ── Meta ──

const meta: Meta<typeof BoardMap> = {
  title: 'Clue/BoardMap',
  component: BoardMap,
  parameters: {
    layout: 'centered'
  },
  argTypes: {
    gameState: { control: 'object' },
    playerId: { control: 'text' },
    selectable: { control: 'boolean' },
    reachableRooms: { control: 'object' },
    reachablePositions: { control: 'object' }
  },
  args: {
    gameState: baseState,
    playerId: 'p1',
    selectedRoom: '',
    selectable: false,
    reachableRooms: [],
    reachablePositions: []
  }
}

export default meta
type Story = StoryObj<typeof BoardMap>

// ═══════════════════════════════════════════════════════════════════
// Board at different container sizes
// ═══════════════════════════════════════════════════════════════════

/** Default: board at natural size */
export const Default: Story = {}

/** Small container: 400px — simulates tight sidebar or small screen */
export const Small400px: Story = {
  decorators: [
    () => ({
      template: '<div style="width: 400px;"><story /></div>'
    })
  ]
}

/** Medium container: 550px — typical laptop board column */
export const Medium550px: Story = {
  decorators: [
    () => ({
      template: '<div style="width: 550px;"><story /></div>'
    })
  ]
}

/** Large container: 690px — max width on desktop */
export const Large690px: Story = {
  decorators: [
    () => ({
      template: '<div style="width: 690px;"><story /></div>'
    })
  ]
}

// ═══════════════════════════════════════════════════════════════════
// Game state variants
// ═══════════════════════════════════════════════════════════════════

/** All players at starting positions */
export const StartPositions: Story = {
  args: {
    gameState: baseState
  }
}

/** Mid-game: players scattered in rooms and hallways */
export const MidGame: Story = {
  args: {
    gameState: {
      ...baseState,
      turn_number: 12,
      player_positions: midGamePositions,
      current_room: {
        p1: 'Study',
        p3: 'Billiard Room',
        p4: 'Ballroom',
        p5: 'Dining Room',
        p6: 'Lounge'
      }
    }
  }
}

/** Multiple players in same room — tests token stacking */
export const CrowdedRoom: Story = {
  args: {
    gameState: {
      ...baseState,
      player_positions: {
        p1: [2, 3],   // Study
        p2: [2, 4],   // Study
        p3: [3, 3],   // Study
        p4: [3, 4],   // Study
        p5: [10, 19], // Dining Room
        p6: [10, 20]  // Dining Room
      },
      current_room: {
        p1: 'Study',
        p2: 'Study',
        p3: 'Study',
        p4: 'Study',
        p5: 'Dining Room',
        p6: 'Dining Room'
      }
    }
  }
}

/** Interactive: rooms are selectable, some reachable */
export const SelectableRooms: Story = {
  args: {
    gameState: {
      ...baseState,
      player_positions: midGamePositions,
      current_room: { p1: 'Study' },
      dice_rolled: true,
      last_roll: [5, 3]
    },
    selectable: true,
    reachableRooms: ['Hall', 'Kitchen', 'Library']
  }
}

/** Weapons displayed in rooms */
export const WithWeapons: Story = {
  args: {
    gameState: {
      ...baseState,
      player_positions: midGamePositions,
      current_room: {
        p1: 'Study',
        p3: 'Billiard Room'
      },
      weapon_positions: {
        Candlestick: 'Kitchen',
        Knife: 'Study',
        'Lead Pipe': 'Library',
        Revolver: 'Ballroom',
        Rope: 'Conservatory',
        Wrench: 'Dining Room'
      }
    }
  }
}

/** Game over state */
export const GameOver: Story = {
  args: {
    gameState: {
      ...baseState,
      status: 'finished',
      winner: 'p1',
      player_positions: midGamePositions,
      current_room: { p1: 'Study' }
    }
  }
}
