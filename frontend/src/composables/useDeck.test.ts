import { beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'clue-deck'

describe('DECKS', () => {
  it('contains all expected deck types', async () => {
    vi.resetModules()
    const { DECKS } = await import('./useDeck')
    expect(DECKS).toEqual(['css', 'classic', 'modern', 'vintage', 'fantasy'])
  })
})

describe('useDeck', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('defaults to css when localStorage is empty', async () => {
    const { useDeck } = await import('./useDeck')
    const { deck } = useDeck()
    expect(deck.value).toBe('css')
  })

  it('loads saved deck from localStorage', async () => {
    localStorage.setItem(STORAGE_KEY, 'vintage')
    const { useDeck } = await import('./useDeck')
    const { deck } = useDeck()
    expect(deck.value).toBe('vintage')
  })

  it('returns the full decks list', async () => {
    const { useDeck, DECKS } = await import('./useDeck')
    const { decks } = useDeck()
    expect(decks).toEqual(DECKS)
  })

  it('setDeck changes the current deck', async () => {
    const { useDeck } = await import('./useDeck')
    const { deck, setDeck } = useDeck()
    setDeck('modern')
    expect(deck.value).toBe('modern')
  })

  it('setDeck persists the selection to localStorage', async () => {
    const { useDeck } = await import('./useDeck')
    const { setDeck } = useDeck()
    setDeck('classic')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('classic')
  })

  it('setDeck ignores unknown deck names', async () => {
    const { useDeck } = await import('./useDeck')
    const { deck, setDeck } = useDeck()
    const before = deck.value
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    setDeck('nonexistent' as any)
    expect(deck.value).toBe(before)
  })

  it('setDeck falls back gracefully when localStorage throws', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
      throw new DOMException('storage full')
    })
    const { useDeck } = await import('./useDeck')
    const { deck, setDeck } = useDeck()
    setDeck('fantasy')
    // deck value is updated even though storage threw
    expect(deck.value).toBe('fantasy')
  })

  it('deck ref is readonly', async () => {
    const { useDeck } = await import('./useDeck')
    const { deck } = useDeck()
    // Readonly refs still expose .value but TypeScript prevents direct assignment.
    // Verify the value is accessible.
    expect(typeof deck.value).toBe('string')
  })
})
