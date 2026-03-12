import type { Meta, StoryObj } from '@storybook/vue3-vite'
import DetectiveNotes from './DetectiveNotes.vue'

const meta: Meta<typeof DetectiveNotes> = {
  title: 'Clue/DetectiveNotes',
  component: DetectiveNotes,
  parameters: {
    layout: 'centered'
  },
  decorators: [
    () => ({
      template: `
        <div style="background: var(--bg-panel-solid, #2a2318); padding: 16px; border-radius: 8px; width: 260px; min-height: 400px;">
          <story />
        </div>
      `
    })
  ],
  argTypes: {
    yourCards: { control: 'object' },
    savedNotes: { control: 'object' }
  },
  args: {
    yourCards: [],
    savedNotes: null
  }
}

export default meta
type Story = StoryObj<typeof DetectiveNotes>

/** Blank slate — no cards held, no notes taken yet */
export const Empty: Story = {
  args: {
    yourCards: [],
    savedNotes: null
  }
}

/** Player holds three cards — auto-marked with ✓ */
export const WithCardsInHand: Story = {
  args: {
    yourCards: ['Miss Scarlett', 'Knife', 'Library'],
    savedNotes: null
  }
}

/** Mixed states: have, seen (with source), eliminated, and suspected */
export const MixedStates: Story = {
  args: {
    yourCards: ['Colonel Mustard', 'Revolver'],
    savedNotes: {
      notes: {
        'Miss Scarlett': 'no',
        'Colonel Mustard': 'have',
        'Mrs. White': 'maybe',
        'Reverend Green': 'no',
        'Mrs. Peacock': 'seen',
        'Professor Plum': 'no',
        Revolver: 'have',
        Knife: 'seen',
        Rope: 'no',
        Candlestick: 'maybe',
        'Lead Pipe': 'no',
        Wrench: 'no',
        Kitchen: 'no',
        Library: 'seen',
        Study: 'no',
        Ballroom: 'maybe',
        Conservatory: 'no',
        'Billiard Room': 'no',
        Hall: 'no',
        Lounge: 'no',
        'Dining Room': 'no'
      },
      shownBy: {
        'Mrs. Peacock': 'Alice',
        Knife: 'Bob',
        Library: 'Alice'
      }
    }
  }
}

/** Detective has almost everything eliminated — close to solving the case */
export const NearSolution: Story = {
  args: {
    yourCards: ['Miss Scarlett', 'Candlestick', 'Kitchen'],
    savedNotes: {
      notes: {
        'Miss Scarlett': 'have',
        'Colonel Mustard': 'no',
        'Mrs. White': 'no',
        'Reverend Green': 'no',
        'Mrs. Peacock': 'no',
        'Professor Plum': 'maybe',
        Candlestick: 'have',
        Knife: 'no',
        'Lead Pipe': 'no',
        Revolver: 'no',
        Rope: 'no',
        Wrench: 'maybe',
        Kitchen: 'have',
        Ballroom: 'no',
        Conservatory: 'no',
        'Billiard Room': 'no',
        Library: 'no',
        Study: 'no',
        Hall: 'no',
        Lounge: 'no',
        'Dining Room': 'no'
      },
      shownBy: {}
    }
  }
}

/** All cards seen or eliminated — notes fully filled in */
export const FullyInvestigated: Story = {
  args: {
    yourCards: ['Miss Scarlett', 'Candlestick', 'Kitchen'],
    savedNotes: {
      notes: {
        'Miss Scarlett': 'have',
        'Colonel Mustard': 'no',
        'Mrs. White': 'seen',
        'Reverend Green': 'no',
        'Mrs. Peacock': 'no',
        'Professor Plum': 'no',
        Candlestick: 'have',
        Knife: 'no',
        'Lead Pipe': 'seen',
        Revolver: 'no',
        Rope: 'seen',
        Wrench: 'no',
        Kitchen: 'have',
        Ballroom: 'no',
        Conservatory: 'seen',
        'Billiard Room': 'no',
        Library: 'no',
        Study: 'no',
        Hall: 'no',
        Lounge: 'seen',
        'Dining Room': 'no'
      },
      shownBy: {
        'Mrs. White': 'Bob',
        'Lead Pipe': 'Alice',
        Rope: 'Charlie',
        Conservatory: 'Bob',
        Lounge: 'Alice'
      }
    }
  }
}
