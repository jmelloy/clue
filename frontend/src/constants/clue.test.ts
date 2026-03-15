import { describe, expect, it } from 'vitest'
import {
  CARD_ICONS,
  CARD_IMAGES,
  CHARACTER_ABBR,
  CHARACTER_COLORS,
  ROOMS,
  SUSPECTS,
  WEAPONS,
  abbr,
  cardIcon,
  cardImageUrl,
  characterColors,
  hasCardImage
} from './clue'

describe('constants', () => {
  it('SUSPECTS contains exactly 6 characters', () => {
    expect(SUSPECTS).toHaveLength(6)
    expect(SUSPECTS).toContain('Miss Scarlett')
    expect(SUSPECTS).toContain('Colonel Mustard')
    expect(SUSPECTS).toContain('Mrs. White')
    expect(SUSPECTS).toContain('Reverend Green')
    expect(SUSPECTS).toContain('Mrs. Peacock')
    expect(SUSPECTS).toContain('Professor Plum')
  })

  it('WEAPONS contains exactly 6 weapons', () => {
    expect(WEAPONS).toHaveLength(6)
    expect(WEAPONS).toContain('Candlestick')
    expect(WEAPONS).toContain('Knife')
    expect(WEAPONS).toContain('Lead Pipe')
    expect(WEAPONS).toContain('Revolver')
    expect(WEAPONS).toContain('Rope')
    expect(WEAPONS).toContain('Wrench')
  })

  it('ROOMS contains exactly 9 rooms', () => {
    expect(ROOMS).toHaveLength(9)
    expect(ROOMS).toContain('Kitchen')
    expect(ROOMS).toContain('Ballroom')
    expect(ROOMS).toContain('Conservatory')
    expect(ROOMS).toContain('Study')
  })

  it('CHARACTER_COLORS has an entry for every suspect', () => {
    for (const suspect of SUSPECTS) {
      expect(CHARACTER_COLORS[suspect], `missing color for ${suspect}`).toBeDefined()
      expect(typeof CHARACTER_COLORS[suspect].bg).toBe('string')
      expect(typeof CHARACTER_COLORS[suspect].text).toBe('string')
    }
  })

  it('CHARACTER_ABBR has an entry for every suspect', () => {
    for (const suspect of SUSPECTS) {
      expect(CHARACTER_ABBR[suspect], `missing abbr for ${suspect}`).toBeDefined()
      expect(CHARACTER_ABBR[suspect].length).toBeGreaterThan(0)
    }
  })

  it('CARD_IMAGES has entries for all suspects, weapons, and rooms', () => {
    for (const card of [...SUSPECTS, ...WEAPONS, ...ROOMS]) {
      expect(CARD_IMAGES[card], `missing image for ${card}`).toBeDefined()
    }
  })
})

describe('cardIcon', () => {
  it('returns the correct emoji for a known suspect', () => {
    expect(cardIcon('Miss Scarlett')).toBe('💋')
  })

  it('returns the correct emoji for a known weapon', () => {
    expect(cardIcon('Knife')).toBe(CARD_ICONS['Knife'])
  })

  it('returns the correct emoji for a known room', () => {
    expect(cardIcon('Kitchen')).toBe('🍳')
  })

  it('returns a fallback joker card emoji for an unknown card', () => {
    expect(cardIcon('Unknown Card')).toBe('🃏')
  })
})

describe('hasCardImage', () => {
  it('returns true for a known card', () => {
    expect(hasCardImage('Miss Scarlett')).toBe(true)
  })

  it('returns false for an unknown card', () => {
    expect(hasCardImage('Banana')).toBe(false)
  })

  it('returns true for a known room', () => {
    expect(hasCardImage('Kitchen')).toBe(true)
  })

  it('returns true for a card with a theme override', () => {
    expect(hasCardImage('Kitchen', 'vintage')).toBe(true)
  })

  it('returns true for a card that exists in the base map but not in the theme', () => {
    // Miss Scarlett exists in base but not in vintage theme
    expect(hasCardImage('Miss Scarlett', 'vintage')).toBe(true)
  })
})

describe('cardImageUrl', () => {
  it('returns the correct URL for a known suspect', () => {
    expect(cardImageUrl('Miss Scarlett')).toContain('MissScarlett')
  })

  it('returns the correct URL for a known weapon', () => {
    expect(cardImageUrl('Knife')).toContain('Knife')
  })

  it('returns the theme override URL when a theme is specified', () => {
    const url = cardImageUrl('Kitchen', 'vintage')
    expect(url).toContain('vintage')
    expect(url).toContain('kitchen')
  })

  it('falls back to base URL when theme has no override for the card', () => {
    // Miss Scarlett is not overridden in the vintage theme
    const url = cardImageUrl('Miss Scarlett', 'vintage')
    expect(url).toContain('MissScarlett')
    expect(url).not.toContain('vintage')
  })

  it('returns empty string for an unknown card', () => {
    expect(cardImageUrl('Unknown')).toBe('')
  })
})

describe('abbr', () => {
  it('returns the correct abbreviation for each suspect', () => {
    expect(abbr('Miss Scarlett')).toBe('Sc')
    expect(abbr('Colonel Mustard')).toBe('Mu')
    expect(abbr('Mrs. White')).toBe('Wh')
    expect(abbr('Reverend Green')).toBe('Gr')
    expect(abbr('Mrs. Peacock')).toBe('Pe')
    expect(abbr('Professor Plum')).toBe('Pl')
  })

  it('falls back to the first character for an unknown name', () => {
    expect(abbr('Xena')).toBe('X')
  })

  it('returns an empty string for an empty input', () => {
    expect(abbr('')).toBe('')
  })
})

describe('characterColors', () => {
  it('returns the correct colors for a known character', () => {
    const colors = characterColors('Miss Scarlett')
    expect(colors.bg).toBe('#c0392b')
    expect(colors.text).toBe('#fff')
  })

  it('returns a neutral fallback for an unknown character', () => {
    const colors = characterColors('Nobody')
    expect(colors.bg).toBe('#666')
    expect(colors.text).toBe('#fff')
  })
})
