// Shared Clue game constants — single source of truth

export const SUSPECTS = [
  "Miss Scarlett",
  "Colonel Mustard",
  "Mrs. White",
  "Reverend Green",
  "Mrs. Peacock",
  "Professor Plum",
];

export const WEAPONS = [
  "Candlestick",
  "Knife",
  "Lead Pipe",
  "Revolver",
  "Rope",
  "Wrench",
];

export const ROOMS = [
  "Kitchen",
  "Ballroom",
  "Conservatory",
  "Billiard Room",
  "Library",
  "Study",
  "Hall",
  "Lounge",
  "Dining Room",
];

export const CHARACTER_COLORS = {
  "Miss Scarlett": { bg: "#c0392b", text: "#fff" },
  "Colonel Mustard": { bg: "#e8b812", text: "#1a1a2e" },
  "Mrs. White": { bg: "#e8e8e8", text: "#1a1a2e" },
  "Reverend Green": { bg: "#1a9e3f", text: "#fff" },
  "Mrs. Peacock": { bg: "#1a5fb4", text: "#fff" },
  "Professor Plum": { bg: "#7b2d8e", text: "#fff" },
};

export const CHARACTER_ABBR = {
  "Miss Scarlett": "Sc",
  "Colonel Mustard": "Mu",
  "Mrs. White": "Wh",
  "Reverend Green": "Gr",
  "Mrs. Peacock": "Pe",
  "Professor Plum": "Pl",
};

export const CARD_ICONS = {
  // Suspects
  "Miss Scarlett": "\u{1F48B}", // 💋
  "Colonel Mustard": "\u{1F396}", // 🎖️
  "Mrs. White": "\u{1F9F9}", // 🧹
  "Reverend Green": "\u{26EA}", // ⛪
  "Mrs. Peacock": "\u{1F99A}", // 🦚
  "Professor Plum": "\u{1F393}", // 🎓
  // Weapons
  Candlestick: "\u{1F56F}", // 🕯️
  Knife: "\u{1F5E1}", // 🗡️
  "Lead Pipe": "\u{26CF}", // ⛏
  Revolver: "\u{1F52B}", // 🔫
  Rope: "\u{1FA62}", // 🪢
  Wrench: "\u{1F527}", // 🔧
  // Rooms
  Kitchen: "\u{1F373}", // 🍳
  Ballroom: "\u{1F483}", // 💃
  Conservatory: "\u{1FAB4}", // 🪴
  "Billiard Room": "\u{1F3B1}", // 🎱
  Library: "\u{1F4DA}", // 📚
  Study: "\u{1F50D}", // 🔍
  Hall: "\u{1F6AA}", // 🚪
  Lounge: "\u{1F6CB}", // 🛋️
  "Dining Room": "\u{1F37D}", // 🍽️
};

export const CARD_IMAGES = {
  // Suspects
  "Miss Scarlett": "/images/clue/suspects/MissScarlett.jpg",
  "Colonel Mustard": "/images/clue/suspects/ColonelMustard.jpg",
  "Mrs. White": "/images/clue/suspects/MrsWhite.jpg",
  "Reverend Green": "/images/clue/suspects/MrGreen.jpg",
  "Mrs. Peacock": "/images/clue/suspects/MrsPeacock.jpg",
  "Professor Plum": "/images/clue/suspects/ProfessorPlum.jpg",
  // Weapons
  Candlestick: "/images/clue/weapons/Candlestick.jpg",
  Knife: "/images/clue/weapons/Knife.jpg",
  "Lead Pipe": "/images/clue/weapons/LeadPipe.jpg",
  Revolver: "/images/clue/weapons/Revolver.jpg",
  Rope: "/images/clue/weapons/Rope.jpg",
  Wrench: "/images/clue/weapons/Wrench.jpg",
  // Rooms
  Kitchen: "/images/clue/rooms/Kitchen.jpg",
  Ballroom: "/images/clue/rooms/BallRoom.jpg",
  Conservatory: "/images/clue/rooms/Conservatory.jpg",
  "Billiard Room": "/images/clue/rooms/BilliardRoom.jpg",
  Library: "/images/clue/rooms/Library.jpg",
  Study: "/images/clue/rooms/Study.jpg",
  Hall: "/images/clue/rooms/Hall.jpg",
  Lounge: "/images/clue/rooms/Lounge.jpg",
  "Dining Room": "/images/clue/rooms/DiningRoom.jpg",
};

export function cardIcon(card) {
  return CARD_ICONS[card] || "\u{1F0CF}";
}

export function hasCardImage(card) {
  return !!CARD_IMAGES[card];
}

export function cardImageUrl(card) {
  return CARD_IMAGES[card] || "";
}

/** Returns the abbreviation for a character name (e.g. "Sc" for "Miss Scarlett"). */
export function abbr(character) {
  return CHARACTER_ABBR[character] ?? character?.charAt(0) ?? "?";
}

/** Returns the `{ bg, text }` color pair for a character. Falls back to a neutral gray. */
export function characterColors(character) {
  return CHARACTER_COLORS[character] ?? { bg: "#666", text: "#fff" };
}
