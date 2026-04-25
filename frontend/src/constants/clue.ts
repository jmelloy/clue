// Shared Clue game constants — single source of truth

import type { CharacterColor } from '../types'

export const SUSPECTS = [
  'Miss Scarlett',
  'Colonel Mustard',
  'Mrs. White',
  'Reverend Green',
  'Mrs. Peacock',
  'Professor Plum'
] as const

export const WEAPONS = ['Candlestick', 'Knife', 'Lead Pipe', 'Revolver', 'Rope', 'Wrench'] as const

export const ROOMS = [
  'Kitchen',
  'Ballroom',
  'Conservatory',
  'Billiard Room',
  'Library',
  'Study',
  'Hall',
  'Lounge',
  'Dining Room'
] as const

export type Suspect = (typeof SUSPECTS)[number]
export type Weapon = (typeof WEAPONS)[number]
export type Room = (typeof ROOMS)[number]
export type ClueCard = Suspect | Weapon | Room

export const CHARACTER_COLORS: Record<string, CharacterColor> = {
  'Miss Scarlett': { bg: '#c0392b', text: '#fff' },
  'Colonel Mustard': { bg: '#e8b812', text: '#1a1a2e' },
  'Mrs. White': { bg: '#e8e8e8', text: '#1a1a2e', name: '#9e9e9e' },
  'Reverend Green': { bg: '#1a9e3f', text: '#fff' },
  'Mrs. Peacock': { bg: '#1a5fb4', text: '#fff' },
  'Professor Plum': { bg: '#7b2d8e', text: '#fff' }
}

export const CHARACTER_ABBR: Record<string, string> = {
  'Miss Scarlett': 'Sc',
  'Colonel Mustard': 'Mu',
  'Mrs. White': 'Wh',
  'Reverend Green': 'Gr',
  'Mrs. Peacock': 'Pe',
  'Professor Plum': 'Pl'
}

export const CARD_ICONS: Record<string, string> = {
  // Suspects
  'Miss Scarlett': '\u{1F48B}', // 💋
  'Colonel Mustard': '\u{1F396}', // 🎖️
  'Mrs. White': '\u{1F9F9}', // 🧹
  'Reverend Green': '\u{26EA}', // ⛪
  'Mrs. Peacock': '\u{1F99A}', // 🦚
  'Professor Plum': '\u{1F393}', // 🎓
  // Weapons
  Candlestick: '\u{1F56F}', // 🕯️
  Knife: '\u{1F5E1}', // 🗡️
  'Lead Pipe': '\u{1F529}', // 🔩
  Revolver: '\u{1F52B}', // 🔫
  Rope: '\u{1FAA2}', // 🪢
  Wrench: '\u{1F527}', // 🔧
  // Rooms
  Kitchen: '\u{1F373}', // 🍳
  Ballroom: '\u{1F483}', // 💃
  Conservatory: '\u{1FAB4}', // 🪴
  'Billiard Room': '\u{1F3B1}', // 🎱
  Library: '\u{1F4DA}', // 📚
  Study: '\u{1F50D}', // 🔍
  Hall: '\u{1F6AA}', // 🚪
  Lounge: '\u{1F6CB}', // 🛋️
  'Dining Room': '\u{1F37D}' // 🍽️
}

export const CARD_IMAGES: Record<string, string> = {
  // Suspects
  'Miss Scarlett': '/images/clue/default/suspects/thumbnails/MissScarlett.jpg',
  'Colonel Mustard': '/images/clue/default/suspects/thumbnails/ColonelMustard.jpg',
  'Mrs. White': '/images/clue/default/suspects/thumbnails/MrsWhite.jpg',
  'Reverend Green': '/images/clue/default/suspects/thumbnails/MrGreen.jpg',
  'Mrs. Peacock': '/images/clue/default/suspects/thumbnails/MrsPeacock.jpg',
  'Professor Plum': '/images/clue/default/suspects/thumbnails/ProfessorPlum.jpg',
  // Weapons
  Candlestick: '/images/clue/default/weapons/thumbnails/Candlestick.jpg',
  Knife: '/images/clue/default/weapons/thumbnails/Knife.jpg',
  'Lead Pipe': '/images/clue/default/weapons/thumbnails/LeadPipe.jpg',
  Revolver: '/images/clue/default/weapons/thumbnails/Revolver.jpg',
  Rope: '/images/clue/default/weapons/thumbnails/Rope.jpg',
  Wrench: '/images/clue/default/weapons/thumbnails/Wrench.jpg',
  // Rooms
  Kitchen: '/images/clue/default/rooms/thumbnails/Kitchen.jpg',
  Ballroom: '/images/clue/default/rooms/thumbnails/BallRoom.jpg',
  Conservatory: '/images/clue/default/rooms/thumbnails/Conservatory.jpg',
  'Billiard Room': '/images/clue/default/rooms/thumbnails/BilliardRoom.jpg',
  Library: '/images/clue/default/rooms/thumbnails/Library.jpg',
  Study: '/images/clue/default/rooms/thumbnails/Study.jpg',
  Hall: '/images/clue/default/rooms/thumbnails/Hall.jpg',
  Lounge: '/images/clue/default/rooms/thumbnails/Lounge.jpg',
  'Dining Room': '/images/clue/default/rooms/thumbnails/DiningRoom.jpg'
}

// Per-theme card image overrides — keyed by theme name, each a partial map of card name -> image URL.
// Falls back to CARD_IMAGES for any card not listed under the active theme.
export const THEME_CARD_IMAGES: Record<string, Record<string, string>> = {
  vintage: {
    Kitchen: '/images/clue/vintage/kitchen.png',
    Ballroom: '/images/clue/vintage/ballroom.png',
    Conservatory: '/images/clue/vintage/conservatory.png',
    'Billiard Room': '/images/clue/vintage/billiard_room.png',
    Library: '/images/clue/vintage/library.png',
    Study: '/images/clue/vintage/study.png',
    Hall: '/images/clue/vintage/hall.png',
    Lounge: '/images/clue/vintage/lounge.png',
    'Dining Room': '/images/clue/vintage/dining_room.png'
  },
  flirtatious: {
    'Miss Scarlett': '/images/clue/flirtatious/thumbnails/MissScarlett.jpg',
    'Colonel Mustard': '/images/clue/flirtatious/thumbnails/ColonelMustard.jpg',
    'Mrs. White': '/images/clue/flirtatious/thumbnails/MrsWhite.jpg',
    'Reverend Green': '/images/clue/flirtatious/thumbnails/ReverendGreen.jpg',
    'Mrs. Peacock': '/images/clue/flirtatious/thumbnails/MrsPeacock.jpg',
    'Professor Plum': '/images/clue/flirtatious/thumbnails/ProfessorPlum.jpg'
  }
}

export interface ImageVariant {
  id: string
  label: string
  description: string
  suspects: Record<string, string>
  weapons: Record<string, string>
  rooms: Record<string, string>
  board: string
}

export const IMAGE_VARIANTS: ImageVariant[] = [
  {
    id: 'default',
    label: 'Default',
    description: 'Classic Clue artwork',
    suspects: {
      'Miss Scarlett': '/images/clue/default/suspects/MissScarlett.jpg',
      'Colonel Mustard': '/images/clue/default/suspects/ColonelMustard.jpg',
      'Mrs. White': '/images/clue/default/suspects/MrsWhite.jpg',
      'Reverend Green': '/images/clue/default/suspects/MrGreen.jpg',
      'Mrs. Peacock': '/images/clue/default/suspects/MrsPeacock.jpg',
      'Professor Plum': '/images/clue/default/suspects/ProfessorPlum.jpg'
    },
    weapons: {
      Candlestick: '/images/clue/default/weapons/Candlestick.jpg',
      Knife: '/images/clue/default/weapons/Knife.jpg',
      'Lead Pipe': '/images/clue/default/weapons/LeadPipe.jpg',
      Revolver: '/images/clue/default/weapons/Revolver.jpg',
      Rope: '/images/clue/default/weapons/Rope.jpg',
      Wrench: '/images/clue/default/weapons/Wrench.jpg'
    },
    rooms: {
      Kitchen: '/images/clue/default/rooms/Kitchen.jpg',
      Ballroom: '/images/clue/default/rooms/BallRoom.jpg',
      Conservatory: '/images/clue/default/rooms/Conservatory.jpg',
      'Billiard Room': '/images/clue/default/rooms/BilliardRoom.jpg',
      Library: '/images/clue/default/rooms/Library.jpg',
      Study: '/images/clue/default/rooms/Study.jpg',
      Hall: '/images/clue/default/rooms/Hall.jpg',
      Lounge: '/images/clue/default/rooms/Lounge.jpg',
      'Dining Room': '/images/clue/default/rooms/DiningRoom.jpg'
    },
    board: '/images/clue/default/board.png'
  },
  {
    id: 'vintage',
    label: 'Vintage',
    description: 'Vintage room illustrations — suspects & weapons use Default',
    suspects: {
      'Miss Scarlett': '/images/clue/default/suspects/MissScarlett.jpg',
      'Colonel Mustard': '/images/clue/default/suspects/ColonelMustard.jpg',
      'Mrs. White': '/images/clue/default/suspects/MrsWhite.jpg',
      'Reverend Green': '/images/clue/default/suspects/MrGreen.jpg',
      'Mrs. Peacock': '/images/clue/default/suspects/MrsPeacock.jpg',
      'Professor Plum': '/images/clue/default/suspects/ProfessorPlum.jpg'
    },
    weapons: {
      Candlestick: '/images/clue/default/weapons/Candlestick.jpg',
      Knife: '/images/clue/default/weapons/Knife.jpg',
      'Lead Pipe': '/images/clue/default/weapons/LeadPipe.jpg',
      Revolver: '/images/clue/default/weapons/Revolver.jpg',
      Rope: '/images/clue/default/weapons/Rope.jpg',
      Wrench: '/images/clue/default/weapons/Wrench.jpg'
    },
    rooms: {
      Kitchen: '/images/clue/vintage/kitchen.png',
      Ballroom: '/images/clue/vintage/ballroom.png',
      Conservatory: '/images/clue/vintage/conservatory.png',
      'Billiard Room': '/images/clue/vintage/billiard_room.png',
      Library: '/images/clue/vintage/library.png',
      Study: '/images/clue/vintage/study.png',
      Hall: '/images/clue/vintage/hall.png',
      Lounge: '/images/clue/vintage/lounge.png',
      'Dining Room': '/images/clue/vintage/dining_room.png'
    },
    board: '/images/clue/default/board.png'
  },
  {
    id: 'flirtatious',
    label: 'Flirtatious',
    description: 'Alternate suspect portraits — rooms & weapons use Default',
    suspects: {
      'Miss Scarlett': '/images/clue/flirtatious/MissScarlett.jpg',
      'Colonel Mustard': '/images/clue/flirtatious/ColonelMustard.jpg',
      'Mrs. White': '/images/clue/flirtatious/MrsWhite.jpg',
      'Reverend Green': '/images/clue/flirtatious/ReverendGreen.jpg',
      'Mrs. Peacock': '/images/clue/flirtatious/MrsPeacock.jpg',
      'Professor Plum': '/images/clue/flirtatious/ProfessorPlum.jpg'
    },
    weapons: {
      Candlestick: '/images/clue/default/weapons/Candlestick.jpg',
      Knife: '/images/clue/default/weapons/Knife.jpg',
      'Lead Pipe': '/images/clue/default/weapons/LeadPipe.jpg',
      Revolver: '/images/clue/default/weapons/Revolver.jpg',
      Rope: '/images/clue/default/weapons/Rope.jpg',
      Wrench: '/images/clue/default/weapons/Wrench.jpg'
    },
    rooms: {
      Kitchen: '/images/clue/default/rooms/Kitchen.jpg',
      Ballroom: '/images/clue/default/rooms/BallRoom.jpg',
      Conservatory: '/images/clue/default/rooms/Conservatory.jpg',
      'Billiard Room': '/images/clue/default/rooms/BilliardRoom.jpg',
      Library: '/images/clue/default/rooms/Library.jpg',
      Study: '/images/clue/default/rooms/Study.jpg',
      Hall: '/images/clue/default/rooms/Hall.jpg',
      Lounge: '/images/clue/default/rooms/Lounge.jpg',
      'Dining Room': '/images/clue/default/rooms/DiningRoom.jpg'
    },
    board: '/images/clue/default/board.png'
  }
]

export function cardIcon(card: string): string {
  return CARD_ICONS[card] || '\u{1F0CF}'
}

export function hasCardImage(card: string, theme?: string): boolean {
  const overrides = theme ? THEME_CARD_IMAGES[theme] : undefined
  if (overrides?.[card]) return true
  return !!CARD_IMAGES[card]
}

export function cardImageUrl(card: string, theme?: string): string {
  const overrides = theme ? THEME_CARD_IMAGES[theme] : undefined
  return overrides?.[card] || CARD_IMAGES[card] || ''
}

/** Returns the abbreviation for a character name (e.g. "Sc" for "Miss Scarlett"). */
export function abbr(character: string): string {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? '?'
}

/** Returns the `{ bg, text }` color pair for a character. Falls back to a neutral gray. */
export function characterColors(character: string): CharacterColor {
  return CHARACTER_COLORS[character] ?? { bg: '#666', text: '#fff' }
}
