import type { Meta, StoryObj } from '@storybook/vue3-vite'
import PlayingCard from './PlayingCard.vue'

const meta: Meta<typeof PlayingCard> = {
  title: 'Cards/PlayingCard',
  component: PlayingCard,
  argTypes: {
    rank: {
      control: 'select',
      options: ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    },
    suit: {
      control: 'select',
      options: ['hearts', 'diamonds', 'clubs', 'spades']
    },
    size: {
      control: 'select',
      options: ['tiny', 'mini', 'small', 'medium', 'large']
    },
    faceDown: { control: 'boolean' }
  },
  args: {
    rank: 'A',
    suit: 'spades',
    size: 'medium',
    faceDown: false
  }
}

export default meta
type Story = StoryObj<typeof PlayingCard>

export const AceOfSpades: Story = {
  args: { rank: 'A', suit: 'spades' }
}

export const KingOfHearts: Story = {
  args: { rank: 'K', suit: 'hearts' }
}

export const QueenOfDiamonds: Story = {
  args: { rank: 'Q', suit: 'diamonds' }
}

export const JackOfClubs: Story = {
  args: { rank: 'J', suit: 'clubs' }
}

export const TenOfSpades: Story = {
  args: { rank: '10', suit: 'spades' }
}

export const FiveOfHearts: Story = {
  args: { rank: '5', suit: 'hearts' }
}

export const FaceDown: Story = {
  args: { faceDown: true }
}

export const Large: Story = {
  args: { rank: 'K', suit: 'hearts', size: 'large' }
}

/** Large cards showing all pip counts */
export const LargeAllRanks: Story = {
  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="display: flex; gap: 12px; flex-wrap: wrap; padding: 20px; background: #1a1a2e; border-radius: 12px;">
        <PlayingCard v-for="rank in ranks" :key="rank" :rank="rank" suit="spades" size="large" />
      </div>
    `,
    setup() {
      const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
      return { ranks }
    }
  })
}

export const Small: Story = {
  args: { rank: 'K', suit: 'spades', size: 'small' }
}

/** All 13 ranks of a single suit */
export const FullSuit: Story = {
  args: {
    suit: 'clubs',
    size: 'medium',
    faceDown: true
  },

  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="display: flex; gap: 8px; flex-wrap: wrap; padding: 20px;">
        <PlayingCard v-for="rank in ranks" :key="rank" :rank="rank" :suit="suit" :size="size" :faceDown="faceDown" />
      </div>
    `,
    setup() {
      const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
      return { ranks }
    }
  })
}

/** One card from each suit */
export const AllSuits: Story = {
  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="display: flex; gap: 8px; padding: 20px;">
        <PlayingCard v-for="suit in suits" :key="suit" rank="A" :suit="suit" />
      </div>
    `,
    setup() {
      const suits = ['hearts', 'diamonds', 'clubs', 'spades']
      return { suits }
    }
  })
}

/** A Texas Hold'em hand: 2 hole cards + 5 community cards */
export const HoldemHand: Story = {
  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="padding: 20px;">
        <div style="margin-bottom: 12px; font-weight: 600; color: #666;">Hole Cards</div>
        <div style="display: flex; gap: 6px; margin-bottom: 24px;">
          <PlayingCard rank="A" suit="hearts" size="medium"
            style="transform: rotate(-4deg);" />
          <PlayingCard rank="K" suit="hearts" size="medium"
            style="transform: rotate(4deg);" />
        </div>
        <div style="margin-bottom: 12px; font-weight: 600; color: #666;">Community Cards</div>
        <div style="display: flex; gap: 8px;">
          <PlayingCard rank="Q" suit="hearts" size="large" />
          <PlayingCard rank="J" suit="hearts" size="large" />
          <PlayingCard rank="10" suit="hearts" size="large" />
          <PlayingCard rank="3" suit="clubs" size="large" />
          <PlayingCard rank="7" suit="spades" size="large" />
        </div>
        <div style="margin-top: 12px; color: #dc2626; font-weight: bold;">Royal Flush!</div>
      </div>
    `
  })
}

/** Mix of face-up and face-down cards */
export const DealInProgress: Story = {
  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="display: flex; gap: 8px; padding: 20px;">
        <PlayingCard rank="9" suit="diamonds" />
        <PlayingCard rank="9" suit="clubs" />
        <PlayingCard rank="4" suit="hearts" />
        <PlayingCard :faceDown="true" />
        <PlayingCard :faceDown="true" />
      </div>
    `
  })
}

/** All five sizes side by side */
export const Sizes: Story = {
  render: () => ({
    components: { PlayingCard },
    template: `
      <div style="display: flex; gap: 16px; align-items: flex-end; padding: 20px;">
        <div v-for="size in sizes" :key="size" style="text-align: center;">
          <PlayingCard rank="A" suit="spades" :size="size" />
          <div style="margin-top: 8px; font-size: 12px; color: #666;">{{ size }}</div>
        </div>
      </div>
    `,
    setup() {
      const sizes = ['tiny', 'mini', 'small', 'medium', 'large']
      return { sizes }
    }
  })
}
