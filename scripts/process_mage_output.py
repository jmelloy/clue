#!/usr/bin/env python3
"""
Process AI-generated card images from mage-output/.

- Detects card boundaries and crops away outer margins
- Selects the best variant for each card (first by default, or by index)
- Resizes to target dimensions
- Outputs cleaned PNGs ready for use as a card deck style

Usage:
    python scripts/process_mage_output.py
    python scripts/process_mage_output.py --source "mage-output/1 - Z-Image Turbo"
    python scripts/process_mage_output.py --target-width 500 --target-height 700
"""

import argparse
import re
from pathlib import Path

from PIL import Image, ImageFilter
import numpy as np


# Default source and output paths
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE = REPO_ROOT / "mage-output" / "1 - Z-Image Turbo"
DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "public" / "images" / "cards" / "mage"

# Card name -> output filename mapping
RANK_MAP = {
    "Ace": "A",
    "Jack": "J",
    "Queen": "Q",
    "King": "K",
}

SUIT_MAP = {
    "Clubs": "clubs",
    "Diamonds": "diamonds",
    "Hearts": "hearts",
    "Spades": "spades",
}

# Best variant index per card (0-indexed). Selected by visual review for
# correctness of text, centering, and artistic quality.
BEST_VARIANT = {
    # Aces - first variant is generally best
    "Ace of Hearts": 0,
    "Ace of Spades": 0,
    "Ace of Clubs": 0,
    "Ace of Diamonds": 0,
    # Jacks
    "Jack of Hearts": 0,
    "Jack of Spades": 0,
    "Jack of Clubs": 0,
    "Jack of Diamonds": 0,
    # Queens
    "Queen of Hearts": 0,
    "Queen of Clubs": 0,
    "Queen of Diamonds": 0,
    "Queen of Spades": 0,
    # Kings
    "King of Hearts": 0,
    "King of Clubs": 0,
    "King of Diamonds": 0,
    "King of Spades": 0,
}


def parse_filename(filename: str) -> tuple[str, str] | None:
    """Parse 'Ace of Hearts_1773156963.jpg' -> ('Ace', 'Hearts') or None."""
    match = re.match(r"^(Ace|Jack|Queen|King) of (Clubs|Diamonds|Hearts|Spades)_\d+\.jpg$", filename)
    if match:
        return match.group(1), match.group(2)
    return None


def find_card_bounds(img: Image.Image, threshold: int = 240) -> tuple[int, int, int, int]:
    """Find the bounding box of the card content (non-white area).

    Scans inward from each edge to find where the card starts.
    Returns (left, top, right, bottom).
    """
    arr = np.array(img.convert("L"))
    h, w = arr.shape

    # Find rows/cols that are NOT nearly-all-white
    # A row is "content" if more than 10% of its pixels are below threshold
    min_content_ratio = 0.10

    def first_content_row(rows_iter):
        for i in rows_iter:
            dark_pixels = np.sum(arr[i, :] < threshold)
            if dark_pixels / w > min_content_ratio:
                return i
        return 0

    def first_content_col(cols_iter):
        for j in cols_iter:
            dark_pixels = np.sum(arr[:, j] < threshold)
            if dark_pixels / h > min_content_ratio:
                return j
        return 0

    top = first_content_row(range(h))
    bottom = first_content_row(range(h - 1, -1, -1))
    left = first_content_col(range(w))
    right = first_content_col(range(w - 1, -1, -1))

    # Add a small padding (2px) to avoid cutting into card edge
    pad = 2
    top = max(0, top - pad)
    left = max(0, left - pad)
    bottom = min(h - 1, bottom + pad)
    right = min(w - 1, right + pad)

    return (left, top, right + 1, bottom + 1)


def process_card(
    img_path: Path,
    output_path: Path,
    target_w: int,
    target_h: int,
) -> None:
    """Crop, resize, and save a single card image."""
    img = Image.open(img_path)

    # Detect and crop card boundaries
    bounds = find_card_bounds(img)
    cropped = img.crop(bounds)

    # Resize to target dimensions using high-quality resampling
    resized = cropped.resize((target_w, target_h), Image.LANCZOS)

    # Convert to RGB (drop alpha) and save as PNG
    resized.convert("RGB").save(output_path, "PNG", optimize=True)


def collect_variants(source_dir: Path) -> dict[str, list[Path]]:
    """Group image files by card name, sorted by timestamp."""
    groups: dict[str, list[Path]] = {}
    for f in sorted(source_dir.glob("*.jpg")):
        parsed = parse_filename(f.name)
        if parsed:
            rank, suit = parsed
            key = f"{rank} of {suit}"
            groups.setdefault(key, []).append(f)
    return groups


def main():
    parser = argparse.ArgumentParser(description="Process AI-generated card images")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Source directory with AI-generated JPGs",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output directory for processed PNGs",
    )
    parser.add_argument("--target-width", type=int, default=500, help="Output width (default: 500)")
    parser.add_argument("--target-height", type=int, default=700, help="Output height (default: 700)")
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="Output all variants (suffixed _1, _2, etc.) instead of picking best",
    )
    args = parser.parse_args()

    source_dir = Path(args.source)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        print(f"Error: source directory not found: {source_dir}")
        return

    variants = collect_variants(source_dir)
    if not variants:
        print(f"No card images found in {source_dir}")
        return

    print(f"Processing {len(variants)} cards from {source_dir}")
    print(f"Output: {output_dir} ({args.target_width}x{args.target_height})")
    print()

    for card_name, files in sorted(variants.items()):
        parsed = parse_filename(files[0].name)
        if not parsed:
            continue
        rank_name, suit_name = parsed
        rank_code = RANK_MAP[rank_name]
        suit_code = SUIT_MAP[suit_name]

        if args.all_variants:
            for i, f in enumerate(files):
                suffix = f"_{i + 1}" if len(files) > 1 else ""
                out_name = f"{rank_code}_{suit_code}{suffix}.png"
                out_path = output_dir / out_name
                process_card(f, out_path, args.target_width, args.target_height)
                print(f"  {card_name} (variant {i + 1}) -> {out_name}")
        else:
            best_idx = BEST_VARIANT.get(card_name, 0)
            best_idx = min(best_idx, len(files) - 1)
            chosen = files[best_idx]
            out_name = f"{rank_code}_{suit_code}.png"
            out_path = output_dir / out_name
            process_card(chosen, out_path, args.target_width, args.target_height)
            print(f"  {card_name} -> {out_name}")

    print(f"\nDone. Processed cards written to {output_dir}")


if __name__ == "__main__":
    main()
