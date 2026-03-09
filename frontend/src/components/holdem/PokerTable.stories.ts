import type { Meta, StoryObj } from '@storybook/vue3-vite'
import PokerTable from './PokerTable.vue'

const basePlayers = [
  { id: 'p1', name: 'You', chips: 1480, current_bet: 0, folded: false, all_in: false },
  { id: 'p2', name: 'Alice', chips: 950, current_bet: 0, folded: false, all_in: false },
  { id: 'p3', name: 'Bob', chips: 2200, current_bet: 0, folded: false, all_in: false },
  { id: 'p4', name: 'Charlie', chips: 600, current_bet: 0, folded: false, all_in: false },
  { id: 'p5', name: 'Diana', chips: 1800, current_bet: 0, folded: false, all_in: false },
  { id: 'p6', name: 'Eve', chips: 1100, current_bet: 0, folded: false, all_in: false }
]

function withBets(players: typeof basePlayers, bets: Record<string, number>) {
  return players.map(p => ({ ...p, current_bet: bets[p.id] ?? 0 }))
}

function withFolded(players: typeof basePlayers, folded: string[]) {
  return players.map(p => ({ ...p, folded: folded.includes(p.id) }))
}

const meta: Meta<typeof PokerTable> = {
  title: 'Holdem/PokerTable',
  component: PokerTable,
  parameters: {
    layout: 'fullscreen'
  },
  argTypes: {
    gameId: { control: 'text' },
    playerId: { control: 'text' },
    isObserver: { control: 'boolean' }
  },
  args: {
    gameId: 'DEMO-1234',
    playerId: 'p1',
    isObserver: false,
    yourCards: [
      { rank: 'A', suit: 'hearts' },
      { rank: 'K', suit: 'hearts' }
    ],
    availableActions: [],
    chatMessages: []
  }
}

export default meta
type Story = StoryObj<typeof PokerTable>

/** Pre-flop: blinds posted, waiting for action */
export const PreFlop: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 7,
      small_blind: 10,
      big_blind: 20,
      pot: 30,
      betting_round: 'preflop',
      dealer_index: 0,
      whose_turn: 'p3',
      current_bet: 20,
      community_cards: [],
      players: withBets(basePlayers, { p2: 10, p3: 20 })
    }
  }
}

/** Flop dealt with active betting */
export const Flop: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 12,
      small_blind: 10,
      big_blind: 20,
      pot: 180,
      betting_round: 'flop',
      dealer_index: 2,
      whose_turn: 'p1',
      current_bet: 40,
      community_cards: [
        { rank: 'Q', suit: 'hearts' },
        { rank: '7', suit: 'clubs' },
        { rank: '2', suit: 'diamonds' }
      ],
      players: withBets(
        withFolded(basePlayers, ['p4']),
        { p1: 20, p2: 40, p3: 40, p5: 40, p6: 0 }
      )
    },
    availableActions: ['fold', 'call', 'raise']
  }
}

/** Turn card with bigger pot */
export const Turn: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 12,
      small_blind: 10,
      big_blind: 20,
      pot: 420,
      betting_round: 'turn',
      dealer_index: 2,
      whose_turn: 'p1',
      current_bet: 0,
      community_cards: [
        { rank: 'Q', suit: 'hearts' },
        { rank: '7', suit: 'clubs' },
        { rank: '2', suit: 'diamonds' },
        { rank: 'J', suit: 'hearts' }
      ],
      players: withFolded(basePlayers, ['p4', 'p6'])
    },
    availableActions: ['check', 'bet']
  }
}

/** River with all 5 community cards */
export const River: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 12,
      small_blind: 10,
      big_blind: 20,
      pot: 860,
      betting_round: 'river',
      dealer_index: 2,
      whose_turn: 'p5',
      current_bet: 100,
      community_cards: [
        { rank: 'Q', suit: 'hearts' },
        { rank: '7', suit: 'clubs' },
        { rank: '2', suit: 'diamonds' },
        { rank: 'J', suit: 'hearts' },
        { rank: '10', suit: 'hearts' }
      ],
      players: withBets(
        withFolded(basePlayers, ['p4', 'p6', 'p2']),
        { p1: 100, p3: 100, p5: 0 }
      )
    }
  }
}

/** All-in showdown */
export const AllIn: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 3,
      small_blind: 25,
      big_blind: 50,
      pot: 3200,
      betting_round: 'flop',
      dealer_index: 0,
      whose_turn: null,
      current_bet: 600,
      community_cards: [
        { rank: 'A', suit: 'spades' },
        { rank: 'K', suit: 'diamonds' },
        { rank: '9', suit: 'clubs' }
      ],
      players: basePlayers.map((p, i) => ({
        ...p,
        folded: i > 2,
        all_in: i <= 2,
        current_bet: i <= 2 ? 600 : 0,
        chips: i <= 2 ? 0 : p.chips
      }))
    }
  }
}

/** Heads-up (2 players) */
export const HeadsUp: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 22,
      small_blind: 50,
      big_blind: 100,
      pot: 300,
      betting_round: 'flop',
      dealer_index: 0,
      whose_turn: 'p1',
      current_bet: 100,
      community_cards: [
        { rank: '5', suit: 'spades' },
        { rank: '8', suit: 'hearts' },
        { rank: 'J', suit: 'diamonds' }
      ],
      players: [
        { id: 'p1', name: 'You', chips: 2400, current_bet: 100, folded: false, all_in: false },
        { id: 'p2', name: 'Alice', chips: 2600, current_bet: 200, folded: false, all_in: false }
      ]
    },
    yourCards: [
      { rank: 'J', suit: 'clubs' },
      { rank: 'J', suit: 'spades' }
    ],
    availableActions: ['fold', 'call', 'raise']
  }
}

/** Spectator view (no hole cards, no actions) */
export const Spectator: Story = {
  args: {
    isObserver: true,
    playerId: 'spectator',
    yourCards: [],
    gameState: {
      status: 'playing',
      hand_number: 5,
      small_blind: 10,
      big_blind: 20,
      pot: 240,
      betting_round: 'turn',
      dealer_index: 1,
      whose_turn: 'p3',
      current_bet: 40,
      community_cards: [
        { rank: '3', suit: 'hearts' },
        { rank: '9', suit: 'spades' },
        { rank: 'K', suit: 'clubs' },
        { rank: '6', suit: 'diamonds' }
      ],
      players: withBets(
        withFolded(basePlayers, ['p1', 'p5']),
        { p2: 40, p3: 0, p4: 40, p6: 40 }
      )
    }
  }
}

/** Waiting for next hand */
export const WaitingForHand: Story = {
  args: {
    gameState: {
      status: 'playing',
      hand_number: 0,
      small_blind: 10,
      big_blind: 20,
      pot: 0,
      betting_round: null,
      dealer_index: 0,
      whose_turn: null,
      current_bet: 0,
      community_cards: [],
      players: basePlayers
    },
    yourCards: []
  }
}
