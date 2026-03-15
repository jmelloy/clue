import type { Meta, StoryObj } from '@storybook/vue3-vite'
import { expect, within } from 'storybook/test'
import WaitingRoom from './WaitingRoom.vue'

const meta: Meta<typeof WaitingRoom> = {
  title: 'Clue/WaitingRoom',
  component: WaitingRoom,
  parameters: {
    layout: 'fullscreen'
  },
  argTypes: {
    gameId: { control: 'text' },
    playerId: { control: 'text' },
    players: { control: 'object' }
  },
  args: {
    gameId: 'CLUE-4821',
    playerId: 'p1'
  }
}

export default meta
type Story = StoryObj<typeof WaitingRoom>

/** Single human player — the host waiting for others to join */
export const SoloHost: Story = {
  args: {
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true }
    ]
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    // Player name is shown
    await expect(canvas.getByText('Alice')).toBeInTheDocument()
    // "you" badge appears for the current player
    await expect(canvas.getByText('you')).toBeInTheDocument()
    // Player count shows 1 out of 6
    await expect(canvas.getByText('1 / 6')).toBeInTheDocument()
  }
}

/** Two human players — minimum needed to start the game */
export const TwoPlayers: Story = {
  args: {
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
      { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true }
    ]
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await expect(canvas.getByText('Alice')).toBeInTheDocument()
    await expect(canvas.getByText('Bob')).toBeInTheDocument()
    await expect(canvas.getByText('2 / 6')).toBeInTheDocument()
  }
}

/** Mixed party: 2 humans + 2 AI agents */
export const MixedParty: Story = {
  args: {
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
      { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
      { id: 'p3', name: 'Agent-1', character: 'Mrs. White', type: 'agent', active: true },
      { id: 'p4', name: 'Agent-2', character: 'Reverend Green', type: 'agent', active: true }
    ]
  }
}

/** Full room — all 6 seats filled (humans, agents, and an LLM agent) */
export const FullRoom: Story = {
  args: {
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
      { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
      { id: 'p3', name: 'Agent-1', character: 'Mrs. White', type: 'agent', active: true },
      { id: 'p4', name: 'Agent-2', character: 'Reverend Green', type: 'agent', active: true },
      { id: 'p5', name: 'GPT-4', character: 'Mrs. Peacock', type: 'llm_agent', active: true },
      { id: 'p6', name: 'Agent-3', character: 'Professor Plum', type: 'agent', active: true }
    ]
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    await expect(canvas.getByText('6 / 6')).toBeInTheDocument()
    // Each player's name is visible
    for (const name of ['Alice', 'Bob', 'Agent-1', 'Agent-2', 'GPT-4', 'Agent-3']) {
      await expect(canvas.getByText(name)).toBeInTheDocument()
    }
  }
}

/** Observer view — no matching player ID, so no "you" badge is shown */
export const ObserverView: Story = {
  args: {
    playerId: 'spectator-xyz',
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
      { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
      { id: 'p3', name: 'Charlie', character: 'Reverend Green', type: 'human', active: true }
    ]
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement)
    // No "you" badge since the spectator's ID doesn't match any player
    await expect(canvas.queryByText('you')).not.toBeInTheDocument()
    await expect(canvas.getByText('3 / 6')).toBeInTheDocument()
  }
}
