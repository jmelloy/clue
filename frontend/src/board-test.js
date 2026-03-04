import { createApp, h } from 'vue'
import BoardMap from './components/BoardMap.vue'

// Mock game state with players in various positions
const mockGameState = {
  players: [
    { id: 'p1', name: 'Alice', character: 'Miss Scarlett', type: 'human' },
    { id: 'p2', name: 'Bob', character: 'Colonel Mustard', type: 'human' },
    { id: 'p3', name: 'Carol', character: 'Mrs. White', type: 'human' },
    { id: 'p4', name: 'Dave', character: 'Reverend Green', type: 'agent' },
    { id: 'p5', name: 'Eve', character: 'Mrs. Peacock', type: 'agent' },
    { id: 'p6', name: 'Frank', character: 'Professor Plum', type: 'wanderer' },
  ],
  current_room: {
    p1: 'Study',
    p3: 'Kitchen',
    p4: 'Ballroom',
  },
  player_positions: {
    p2: [7, 23],
    p5: [5, 0],
    p6: [12, 8],
  },
  whose_turn: 'p1',
}

const app = createApp({
  render() {
    return h(BoardMap, {
      gameState: mockGameState,
      playerId: 'p1',
      selectedRoom: null,
      selectable: false,
      reachableRooms: [],
      reachablePositions: [],
      boardData: null,
    })
  }
})

app.mount('#app')
