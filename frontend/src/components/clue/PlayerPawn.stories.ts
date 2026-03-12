import type { Meta, StoryObj } from '@storybook/vue3-vite'
import PlayerPawn from './PlayerPawn.vue'
import { SUSPECTS } from '../../constants/clue'

const meta: Meta<typeof PlayerPawn> = {
  title: 'Clue/PlayerPawn',
  component: PlayerPawn,
  argTypes: {
    character: {
      control: 'select',
      options: [...SUSPECTS]
    },
    size: { control: 'text' },
    wanderer: { control: 'boolean' }
  },
  args: {
    character: 'Miss Scarlett',
    wanderer: false
  }
}

export default meta
type Story = StoryObj<typeof PlayerPawn>

export const MissScarlett: Story = {
  args: { character: 'Miss Scarlett' }
}

export const ColonelMustard: Story = {
  args: { character: 'Colonel Mustard' }
}

export const MrsWhite: Story = {
  args: { character: 'Mrs. White' }
}

export const ReverendGreen: Story = {
  args: { character: 'Reverend Green' }
}

export const MrsPeacock: Story = {
  args: { character: 'Mrs. Peacock' }
}

export const ProfessorPlum: Story = {
  args: { character: 'Professor Plum' }
}

/** Semi-transparent wanderer / NPC token */
export const Wanderer: Story = {
  args: { character: 'Mrs. Peacock', wanderer: true }
}

/** All six suspects displayed side by side at default size */
export const AllSuspects: Story = {
  render: () => ({
    components: { PlayerPawn },
    template: `
      <div style="display: flex; gap: 12px; align-items: center; padding: 20px; background: var(--bg-page, #252018); border-radius: 8px;">
        <PlayerPawn v-for="c in characters" :key="c" :character="c" />
      </div>
    `,
    setup() {
      return { characters: [...SUSPECTS] }
    }
  })
}

/** Size comparison: small (16px), default (20px), medium (28px), large (40px) */
export const Sizes: Story = {
  render: () => ({
    components: { PlayerPawn },
    template: `
      <div style="display: flex; gap: 20px; align-items: center; padding: 24px; background: var(--bg-page, #252018); border-radius: 8px;">
        <div v-for="size in sizes" :key="size.label" style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
          <PlayerPawn character="Miss Scarlett" :size="size.px" />
          <span style="color: var(--text-secondary, #9a8e7a); font-size: 11px;">{{ size.label }}</span>
        </div>
      </div>
    `,
    setup() {
      return {
        sizes: [
          { label: '16px', px: '16px' },
          { label: '20px (default)', px: '20px' },
          { label: '28px', px: '28px' },
          { label: '40px', px: '40px' }
        ]
      }
    }
  })
}
