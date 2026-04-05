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
  'Miss Scarlett': '/images/clue/suspects/thumbnails/MissScarlett.jpg',
  'Colonel Mustard': '/images/clue/suspects/thumbnails/ColonelMustard.jpg',
  'Mrs. White': '/images/clue/suspects/thumbnails/MrsWhite.jpg',
  'Reverend Green': '/images/clue/suspects/thumbnails/MrGreen.jpg',
  'Mrs. Peacock': '/images/clue/suspects/thumbnails/MrsPeacock.jpg',
  'Professor Plum': '/images/clue/suspects/thumbnails/ProfessorPlum.jpg',
  // Weapons
  Candlestick: '/images/clue/weapons/thumbnails/Candlestick.jpg',
  Knife: '/images/clue/weapons/thumbnails/Knife.jpg',
  'Lead Pipe': '/images/clue/weapons/thumbnails/LeadPipe.jpg',
  Revolver: '/images/clue/weapons/thumbnails/Revolver.jpg',
  Rope: '/images/clue/weapons/thumbnails/Rope.jpg',
  Wrench: '/images/clue/weapons/thumbnails/Wrench.jpg',
  // Rooms
  Kitchen: '/images/clue/rooms/thumbnails/Kitchen.jpg',
  Ballroom: '/images/clue/rooms/thumbnails/BallRoom.jpg',
  Conservatory: '/images/clue/rooms/thumbnails/Conservatory.jpg',
  'Billiard Room': '/images/clue/rooms/thumbnails/BilliardRoom.jpg',
  Library: '/images/clue/rooms/thumbnails/Library.jpg',
  Study: '/images/clue/rooms/thumbnails/Study.jpg',
  Hall: '/images/clue/rooms/thumbnails/Hall.jpg',
  Lounge: '/images/clue/rooms/thumbnails/Lounge.jpg',
  'Dining Room': '/images/clue/rooms/thumbnails/DiningRoom.jpg'
}

// Per-theme card image overrides — keyed by theme name, each a partial map of card name -> image URL.
// Falls back to CARD_IMAGES for any card not listed under the active theme.
//
// Room images support two approaches for light/dark modes:
//   Approach A (separate images): populate both `light` and `dark` entries with
//     dedicated daytime and nighttime room images respectively.
//   Approach B (CSS night filter): populate only `light` with daytime images and
//     rely on the `--board-room-night-filter` CSS variable to darken them in dark mode.
//     In this case, `dark` can be left empty or pointed at the same daytime images.
//
// Daytime room images go in: /images/clue/rooms/day/ and /images/clue/rooms/day/thumbnails/
// Nighttime room images go in: /images/clue/rooms/night/ and /images/clue/rooms/night/thumbnails/
export const THEME_CARD_IMAGES: Record<string, Record<string, string>> = {
  // Light theme — daytime room images (Approach A), or same default images (Approach B)
  // Uncomment when daytime images are generated:
  // light: {
  //   Kitchen: '/images/clue/rooms/day/thumbnails/Kitchen.jpg',
  //   Ballroom: '/images/clue/rooms/day/thumbnails/BallRoom.jpg',
  //   Conservatory: '/images/clue/rooms/day/thumbnails/Conservatory.jpg',
  //   'Billiard Room': '/images/clue/rooms/day/thumbnails/BilliardRoom.jpg',
  //   Library: '/images/clue/rooms/day/thumbnails/Library.jpg',
  //   Study: '/images/clue/rooms/day/thumbnails/Study.jpg',
  //   Hall: '/images/clue/rooms/day/thumbnails/Hall.jpg',
  //   Lounge: '/images/clue/rooms/day/thumbnails/Lounge.jpg',
  //   'Dining Room': '/images/clue/rooms/day/thumbnails/DiningRoom.jpg',
  // },
  // Dark theme — nighttime room images (Approach A only; skip if using Approach B)
  // Uncomment when separate nighttime images are generated:
  // dark: {
  //   Kitchen: '/images/clue/rooms/night/thumbnails/Kitchen.jpg',
  //   Ballroom: '/images/clue/rooms/night/thumbnails/BallRoom.jpg',
  //   Conservatory: '/images/clue/rooms/night/thumbnails/Conservatory.jpg',
  //   'Billiard Room': '/images/clue/rooms/night/thumbnails/BilliardRoom.jpg',
  //   Library: '/images/clue/rooms/night/thumbnails/Library.jpg',
  //   Study: '/images/clue/rooms/night/thumbnails/Study.jpg',
  //   Hall: '/images/clue/rooms/night/thumbnails/Hall.jpg',
  //   Lounge: '/images/clue/rooms/night/thumbnails/Lounge.jpg',
  //   'Dining Room': '/images/clue/rooms/night/thumbnails/DiningRoom.jpg',
  // },
  vintage: {
    Kitchen: '/images/clue/alternates/vintage/kitchen.png',
    Ballroom: '/images/clue/alternates/vintage/ballroom.png',
    Conservatory: '/images/clue/alternates/vintage/conservatory.png',
    'Billiard Room': '/images/clue/alternates/vintage/billiard_room.png',
    Library: '/images/clue/alternates/vintage/library.png',
    Study: '/images/clue/alternates/vintage/study.png',
    Hall: '/images/clue/alternates/vintage/hall.png',
    Lounge: '/images/clue/alternates/vintage/lounge.png',
    'Dining Room': '/images/clue/alternates/vintage/dining_room.png'
  },
  flirtatious: {
    'Miss Scarlett': '/images/clue/alternates/flirtatious/thumbnails/MissScarlett.jpg',
    'Colonel Mustard': '/images/clue/alternates/flirtatious/thumbnails/ColonelMustard.jpg',
    'Mrs. White': '/images/clue/alternates/flirtatious/thumbnails/MrsWhite.jpg',
    'Reverend Green': '/images/clue/alternates/flirtatious/thumbnails/ReverendGreen.jpg',
    'Mrs. Peacock': '/images/clue/alternates/flirtatious/thumbnails/MrsPeacock.jpg',
    'Professor Plum': '/images/clue/alternates/flirtatious/thumbnails/ProfessorPlum.jpg'
  }
}

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
