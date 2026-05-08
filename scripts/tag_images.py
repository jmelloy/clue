#!/usr/bin/env python3
"""
Tag downloaded/generated images using the room and card prompt markdown files.

Walks an image directory (e.g. ``mage-archive/`` from ``mage_download.py`` or
``mage-output/`` from ``mage_generate.py``) and, for each image, derives tags
from:

- the file name and parent directories
- the JSON sidecar written by ``mage_download.py`` (``{stem}.json``)
- a fuzzy match against the entries parsed from
  ``backend/app/games/clue/room-prompts.md`` and
  ``backend/app/games/holdem/cards.md``

Tags are written to a SQLite database with three tables: ``images``,
``tags``, and ``image_tags``. The script is idempotent — re-running it
updates existing rows instead of duplicating them.

Usage:
    python scripts/tag_images.py mage-archive/
    python scripts/tag_images.py mage-output/ --db images.db
    python scripts/tag_images.py scripts/cards/ --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOMS_MD = REPO_ROOT / "backend/app/games/clue/room-prompts.md"
DEFAULT_CARDS_MD = REPO_ROOT / "backend/app/games/holdem/cards.md"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

# Short rank codes (A_Hearts, K_Spades, ...) → full names
RANK_CODES = {"A": "Ace", "K": "King", "Q": "Queen", "J": "Jack"}
SUITS = {"Hearts", "Diamonds", "Spades", "Clubs"}

# Directory name → deck name (for path hints in scripts/cards/<deck>/...)
DECK_DIR_TO_NAME = {
    "classic": "Classic Deck",
    "vintage": "Vintage Deck",
    "modern": "Modern Deck",
    "web": "Web Deck (Fun)",
    "fantasy": "Fantasy Deck (Fun)",
    "pinup": "Pinup Deck (Fun)",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    sidecar_path TEXT,
    prompt TEXT,
    model TEXT,
    aspect_ratio TEXT,
    dimensions TEXT,
    date_created TEXT,
    uuid TEXT,
    matched_entry TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    UNIQUE(name, category)
);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (image_id, tag_id),
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag_id);
"""


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-_\s]+", "-", text)
    return text.strip("-")


def normalize(text: str) -> str:
    """Aggressive normalization for fuzzy substring comparison."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def parse_prompts_markdown(filepath: Path) -> list[dict]:
    """Parse a prompts markdown file into entries.

    Tracks the most recent ``#`` (h1) and ``##`` (h2) headings so each
    ``###`` (h3) entry inherits both. A new h1 resets h2.

    Returns a list of dicts: ``{source, h1, h2, name, ratio, prompt}``.
    """
    text = filepath.read_text()
    lines = text.split("\n")

    entries: list[dict] = []
    h1: str | None = None
    h2: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]

        m = re.match(r"^#\s+(.+)", line)
        if m:
            h1 = m.group(1).strip()
            h2 = None
            i += 1
            continue

        m = re.match(r"^##\s+(.+)", line)
        if m:
            h2 = m.group(1).strip()
            i += 1
            continue

        m = re.match(r"^###\s+(.+)", line)
        if m:
            name = m.group(1).strip()
            ratio: str | None = None
            prompt_lines: list[str] = []
            i += 1
            while i < len(lines):
                sub = lines[i]
                if re.match(r"^#{1,3}\s+", sub):
                    break
                rm = re.match(r"\*\*Ratio:\*\*\s*(\S+)", sub)
                if rm:
                    ratio = rm.group(1).strip()
                if sub.startswith(">"):
                    prompt_lines.append(sub.lstrip("> ").strip())
                i += 1
            prompt = " ".join(p for p in prompt_lines if p)
            entries.append(
                {
                    "source": filepath.name,
                    "h1": h1,
                    "h2": h2,
                    "name": name,
                    "ratio": ratio,
                    "prompt": prompt,
                }
            )
            continue

        i += 1

    return entries


def build_match_index(entries: list[dict]) -> list[dict]:
    """Augment entries with normalized aliases for fuzzy matching."""
    out = []
    for e in entries:
        # Split the name on em-dash / en-dash / hyphen (with whitespace) to
        # extract base + variant — e.g. "Study — Night" -> ("Study", "Night").
        parts = re.split(r"\s+[—–-]\s+", e["name"])
        base = parts[0].strip()
        variant = parts[1].strip() if len(parts) > 1 else None

        # Build slug aliases for the entry name and base.
        slugs = {
            slugify(e["name"]),
            slugify(base),
            slugify(e["name"].replace(".", "").replace("'", "")),
        }
        # Card short-code alias: "Ace of Hearts" -> "a-hearts"
        m = re.match(r"^(Ace|King|Queen|Jack)\s+of\s+(\w+)$", base)
        if m:
            rank = m.group(1)[0]
            suit = m.group(2)
            slugs.add(f"{rank.lower()}-{suit.lower()}")

        out.append(
            {
                **e,
                "base": base,
                "variant": variant,
                "name_slugs": {s for s in slugs if s},
                "base_norm": normalize(base),
                "variant_norm": normalize(variant) if variant else None,
                "h1_norm": normalize(e["h1"]) if e["h1"] else None,
                "prompt_norm": normalize(e["prompt"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def match_entry(
    image_path: Path,
    root: Path,
    sidecar: dict,
    entries: list[dict],
) -> tuple[dict | None, int]:
    """Return ``(entry, score)`` for the best match, or ``(None, 0)``."""
    stem = image_path.stem
    stem_slug = slugify(stem)
    stem_norm = normalize(stem)

    # Path components above the file (not including the root) — both
    # normalized and slugified for matching against entry name/h1.
    try:
        rel_parts = image_path.relative_to(root).parts[:-1]
    except ValueError:
        rel_parts = ()
    path_text = normalize(" ".join(rel_parts))
    path_slugs = {slugify(p) for p in rel_parts}

    sidecar_prompt_norm = normalize(sidecar.get("prompt", "") or "")

    best: dict | None = None
    best_score = 0
    for e in entries:
        score = 0

        # Filename slug contains the entry slug (strongest filename signal).
        if any(s and s in stem_slug for s in e["name_slugs"]):
            score += 50

        # Base name appears in filename or path.
        if e["base_norm"]:
            if e["base_norm"] in stem_norm:
                score += 25
            if e["base_norm"] in path_text:
                score += 15

        # Variant ("Night", "Day", "Oil Painting", "Flirtatious") appears.
        if e["variant_norm"]:
            if e["variant_norm"] in stem_norm or e["variant_norm"] in path_text:
                score += 20
            elif e["variant_norm"] in sidecar_prompt_norm:
                score += 8
        else:
            # Penalize matching a base-only entry when the file clearly has
            # a variant marker like "night"/"day"/"oil-painting" in the path
            # or stem — those should match a variant entry instead.
            for v in ("night", "day", "oil painting"):
                if v in stem_norm or v in path_text:
                    score -= 15
                    break

        # Section (h1) directory hint: e.g. "Classic Deck" → "classic-deck"
        if e["h1"]:
            h1_slug = slugify(e["h1"])
            if h1_slug in path_slugs:
                score += 25
            # Also match shortened deck dir names like "classic"
            for dirname, deckname in DECK_DIR_TO_NAME.items():
                if deckname == e["h1"] and dirname in path_slugs:
                    score += 25
                    break
            if e["h1_norm"] and e["h1_norm"] in path_text:
                score += 10

        # Sidecar prompt: card name appears verbatim.
        if sidecar_prompt_norm and e["base_norm"]:
            if e["base_norm"] in sidecar_prompt_norm:
                score += 25

        # Sidecar prompt: leading chunk of the markdown prompt is contained.
        # This is the strongest signal because the same prompt text was
        # submitted to mage.space.
        if sidecar_prompt_norm and e["prompt_norm"]:
            head = e["prompt_norm"][:100]
            if head and head in sidecar_prompt_norm:
                score += 70
            else:
                tail = e["prompt_norm"][-80:]
                if tail and tail in sidecar_prompt_norm:
                    score += 40

        if score > best_score:
            best = e
            best_score = score

    return (best, best_score) if best_score >= 35 else (None, best_score)


# ---------------------------------------------------------------------------
# Tag derivation
# ---------------------------------------------------------------------------


def derive_tags(
    entry: dict | None,
    sidecar: dict,
    image_path: Path,
    root: Path,
) -> list[tuple[str, str]]:
    """Return a list of ``(tag_name, category)`` tuples for an image."""
    tags: list[tuple[str, str]] = []

    if entry:
        if entry["h1"]:
            tags.append((entry["h1"], "section"))
        if entry["h2"]:
            tags.append((entry["h2"], "section"))
        tags.append((entry["base"], "subject"))
        if entry["variant"]:
            tags.append((entry["variant"], "variant"))
        if entry["ratio"]:
            tags.append((entry["ratio"], "ratio"))

        src = entry.get("source", "")
        if "room" in src:
            tags.append(("clue", "game"))
        elif "card" in src:
            tags.append(("holdem", "game"))

    # Sidecar metadata
    if sidecar.get("model"):
        tags.append((sidecar["model"], "model"))
    if sidecar.get("aspect_ratio") and not entry:
        tags.append((sidecar["aspect_ratio"], "ratio"))
    if sidecar.get("collection"):
        tags.append((sidecar["collection"], "collection"))

    # Path hints — deck directory and year (mage-archive uses YYYY/...)
    try:
        rel_parts = image_path.relative_to(root).parts
    except ValueError:
        rel_parts = ()

    for part in rel_parts[:-1]:
        if part.lower() in DECK_DIR_TO_NAME:
            tags.append((DECK_DIR_TO_NAME[part.lower()], "section"))
        if re.fullmatch(r"\d{4}", part):
            tags.append((part, "year"))

    # Card short code (A_Hearts, etc.) — emit suit/rank tags even when the
    # full markdown match failed.
    m = re.match(r"^([AKQJ])[_\- ](Hearts|Diamonds|Spades|Clubs)$", image_path.stem)
    if m:
        tags.append((RANK_CODES[m.group(1)], "rank"))
        tags.append((m.group(2), "suit"))
        tags.append(("holdem", "game"))

    # De-duplicate while preserving order
    seen: set[tuple[str, str]] = set()
    unique = []
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
    return unique


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------


def get_or_create_tag(conn: sqlite3.Connection, name: str, category: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
        (name, category),
    )
    row = conn.execute(
        "SELECT id FROM tags WHERE name = ? AND category = ?",
        (name, category),
    ).fetchone()
    return row[0]


def upsert_image(
    conn: sqlite3.Connection,
    image_path: Path,
    sidecar_path: Path | None,
    sidecar: dict,
    matched_entry: str | None,
) -> int:
    conn.execute(
        """
        INSERT INTO images (file_path, file_name, sidecar_path, prompt, model,
                            aspect_ratio, dimensions, date_created, uuid,
                            matched_entry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
            sidecar_path = excluded.sidecar_path,
            prompt = excluded.prompt,
            model = excluded.model,
            aspect_ratio = excluded.aspect_ratio,
            dimensions = excluded.dimensions,
            date_created = excluded.date_created,
            uuid = excluded.uuid,
            matched_entry = excluded.matched_entry
        """,
        (
            str(image_path),
            image_path.name,
            str(sidecar_path) if sidecar_path else None,
            sidecar.get("prompt"),
            sidecar.get("model"),
            sidecar.get("aspect_ratio"),
            sidecar.get("dimensions"),
            sidecar.get("date_created"),
            sidecar.get("uuid"),
            matched_entry,
        ),
    )
    row = conn.execute(
        "SELECT id FROM images WHERE file_path = ?", (str(image_path),)
    ).fetchone()
    return row[0]


def link_tag(conn: sqlite3.Connection, image_id: int, tag_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
        (image_id, tag_id),
    )


# ---------------------------------------------------------------------------
# Walking
# ---------------------------------------------------------------------------


def find_sidecar(image_path: Path) -> Path | None:
    sidecar = image_path.with_suffix(".json")
    return sidecar if sidecar.exists() else None


def load_sidecar(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tag images using room/card prompt markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("path", help="Image directory to scan")
    parser.add_argument(
        "--db",
        default="images.db",
        help="SQLite database path (default: images.db)",
    )
    parser.add_argument(
        "--rooms",
        default=str(DEFAULT_ROOMS_MD),
        help=f"Path to room prompts markdown (default: {DEFAULT_ROOMS_MD})",
    )
    parser.add_argument(
        "--cards",
        default=str(DEFAULT_CARDS_MD),
        help=f"Path to card prompts markdown (default: {DEFAULT_CARDS_MD})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to the database — just print matches",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print the result for every image",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        parser.error(f"Path not found: {root}")

    # Parse markdown sources
    raw_entries: list[dict] = []
    for md in [Path(args.rooms), Path(args.cards)]:
        if md.exists():
            parsed = parse_prompts_markdown(md)
            raw_entries.extend(parsed)
            print(f"Parsed {md}: {len(parsed)} entries")
        else:
            print(f"Warning: {md} not found, skipping")

    entries = build_match_index(raw_entries)
    if not entries:
        parser.error("No prompt entries parsed — provide --rooms / --cards paths")

    # Walk for images
    if root.is_file():
        images = [root] if root.suffix.lower() in IMAGE_EXTS else []
    else:
        images = sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS)

    print(f"Found {len(images)} image(s) under {root}")
    if not images:
        return

    conn: sqlite3.Connection | None = None
    if not args.dry_run:
        conn = sqlite3.connect(args.db)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)

    matched = 0
    unmatched = 0
    for img in images:
        sidecar_path = find_sidecar(img)
        sidecar = load_sidecar(sidecar_path)

        entry, score = match_entry(img, root if root.is_dir() else root.parent,
                                   sidecar, entries)
        tags = derive_tags(
            entry, sidecar, img, root if root.is_dir() else root.parent
        )

        rel = img.relative_to(root) if root.is_dir() else img.name
        if entry:
            matched += 1
            if args.verbose:
                section = entry["h1"] or entry["h2"] or "?"
                print(f"  {rel} -> {entry['name']} [{section}] (score={score})")
        else:
            unmatched += 1
            if args.verbose:
                print(f"  {rel} -> no match (best score={score})")

        if conn:
            image_id = upsert_image(
                conn, img, sidecar_path, sidecar,
                entry["name"] if entry else None,
            )
            for name, category in tags:
                tag_id = get_or_create_tag(conn, name, category)
                link_tag(conn, image_id, tag_id)

    if conn:
        conn.commit()
        # Quick stats
        n_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        n_tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        n_links = conn.execute("SELECT COUNT(*) FROM image_tags").fetchone()[0]
        conn.close()
        print(f"\nWrote to {args.db}: {n_images} images, {n_tags} tags, "
              f"{n_links} image_tags")

    print(f"Matched: {matched}, Unmatched: {unmatched}, Total: {len(images)}")


if __name__ == "__main__":
    main()
