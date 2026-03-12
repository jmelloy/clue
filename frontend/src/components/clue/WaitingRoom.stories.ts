import type { Meta, StoryObj } from '@storybook/vue3-vite'
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
  }
}

/** Two human players — minimum needed to start the game */
export const TwoPlayers: Story = {
  args: {
    players: [
      { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
      { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true }
    ]
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
  }
}
