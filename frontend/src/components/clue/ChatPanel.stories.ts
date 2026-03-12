import type { Meta, StoryObj } from '@storybook/vue3-vite'
import ChatPanel from './ChatPanel.vue'

const now = new Date()
function ts(secondsAgo: number) {
  return new Date(now.getTime() - secondsAgo * 1000).toISOString()
}

const basePlayers = [
  { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human', active: true },
  { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human', active: true },
  { id: 'p3', name: 'Charlie', character: 'Reverend Green', type: 'agent', active: true },
  { id: 'p4', name: 'Diana', character: 'Mrs. Peacock', type: 'agent', active: true }
]

const sampleMessages = [
  {
    type: 'chat_message',
    player_id: null,
    text: 'Alice rolled a 6 and moved to the Kitchen.',
    timestamp: ts(320)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Alice suggests it was Miss Scarlett with the Knife in the Kitchen.',
    timestamp: ts(310)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Bob showed a card to Alice.',
    timestamp: ts(305)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Bob rolled a 4 and moved to the Library.',
    timestamp: ts(240)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Bob suggests it was Colonel Mustard with the Revolver in the Library.',
    timestamp: ts(230)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'No one could disprove the suggestion.',
    timestamp: ts(228)
  },
  {
    type: 'chat_message',
    player_id: 'p1',
    text: 'Alice: I think I know who did it!',
    timestamp: ts(180)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Charlie rolled a 3 and used the secret passage to the Study.',
    timestamp: ts(120)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Charlie suggests it was Professor Plum with the Rope in the Study.',
    timestamp: ts(115)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Diana showed a card to Charlie.',
    timestamp: ts(110)
  },
  {
    type: 'chat_message',
    player_id: 'p2',
    text: 'Bob: Hmm, interesting move there.',
    timestamp: ts(80)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Diana rolled a 5 and moved to the Ballroom.',
    timestamp: ts(60)
  },
  {
    type: 'chat_message',
    player_id: null,
    text: 'Diana accuses Miss Scarlett with the Knife in the Kitchen!',
    timestamp: ts(30)
  }
]

const meta: Meta<typeof ChatPanel> = {
  title: 'Clue/ChatPanel',
  component: ChatPanel,
  parameters: {
    layout: 'centered'
  },
  decorators: [
    () => ({
      template: `
        <div style="background: var(--bg-panel-solid, #2a2318); padding: 0; border-radius: 8px; width: 340px; height: 480px; display: flex; flex-direction: column;">
          <story />
        </div>
      `
    })
  ],
  argTypes: {
    messages: { control: 'object' },
    players: { control: 'object' }
  },
  args: {
    messages: sampleMessages,
    players: basePlayers
  }
}

export default meta
type Story = StoryObj<typeof ChatPanel>

/** No messages yet — initial empty state */
export const Empty: Story = {
  args: {
    messages: [],
    players: basePlayers
  }
}

/** Game in progress — a mix of moves, suggestions, card shows, and one accusation */
export const ActiveGame: Story = {
  args: {
    messages: sampleMessages,
    players: basePlayers
  }
}

/** Only player chat messages (no game log) */
export const ChatOnly: Story = {
  args: {
    messages: [
      { type: 'chat_message', player_id: 'p1', text: 'Alice: Anyone else suspicious of the Study?', timestamp: ts(200) },
      { type: 'chat_message', player_id: 'p2', text: 'Bob: I have my eye on the Library.', timestamp: ts(160) },
      { type: 'chat_message', player_id: 'p1', text: 'Alice: Interesting...', timestamp: ts(120) },
      { type: 'chat_message', player_id: 'p3', text: 'Charlie: Making my move.', timestamp: ts(60) }
    ],
    players: basePlayers
  }
}

/** Only suggestions and card-show log entries */
export const SuggestionsAndCardShows: Story = {
  args: {
    messages: [
      {
        type: 'chat_message',
        player_id: null,
        text: 'Alice suggests it was Miss Scarlett with the Knife in the Kitchen.',
        timestamp: ts(300)
      },
      {
        type: 'chat_message',
        player_id: null,
        text: 'Bob showed a card to Alice.',
        timestamp: ts(295)
      },
      {
        type: 'chat_message',
        player_id: null,
        text: 'Bob suggests it was Colonel Mustard with the Revolver in the Library.',
        timestamp: ts(200)
      },
      {
        type: 'chat_message',
        player_id: null,
        text: 'No one could disprove the suggestion.',
        timestamp: ts(198)
      },
      {
        type: 'chat_message',
        player_id: null,
        text: 'Charlie showed a card to Bob.',
        timestamp: ts(100)
      }
    ],
    players: basePlayers
  }
}

/** A game ending with a correct accusation */
export const GameOver: Story = {
  args: {
    messages: [
      ...sampleMessages,
      {
        type: 'chat_message',
        player_id: null,
        text: 'Alice accuses Professor Plum with the Rope in the Study!',
        timestamp: ts(10)
      },
      {
        type: 'chat_message',
        player_id: null,
        text: 'Alice is correct! The game is over.',
        timestamp: ts(5)
      }
    ],
    players: basePlayers
  }
}
