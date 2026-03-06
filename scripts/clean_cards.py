#!/usr/bin/env python3
"""
Clean up AI-generated playing card images.

- Detects the inner rectangular frame border
- Whites out everything outside the frame
- Optionally removes stray suit symbols inside the frame

Usage:
    # Clean a single image
    python scripts/clean_cards.py path/to/card.jpg

    # Clean all cards in a directory (recursive)
    python scripts/clean_cards.py mage-output/

    # Preview without saving (dry run)
    python scripts/clean_cards.py mage-output/ --dry-run

    # Save cleaned versions with suffix instead of overwriting
    python scripts/clean_cards.py mage-output/ --suffix _clean

    # Also remove stray suit pips inside the frame
    python scripts/clean_cards.py mage-output/ --remove-pips
"""

import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw


def is_dark(r, g, b, threshold=128):
    """Check if a pixel is 'dark' (part of artwork, not white background)."""
    return min(r, g, b) < threshold or (r + g + b) < 600


def find_frame_rect(img):
    """Find the inner rectangular frame border.

    Strategy: The frame border is a thin line of dark pixels that spans almost
    the entire width/height of the image. We check the center 60% of each
    row/column - a frame border line will have nearly 100% dark pixels there.

    We skip the very edge pixels (0-5) to avoid image boundary artifacts,
    and require >0.9 density to distinguish the solid frame line from the
    figure artwork (which is typically 0.5-0.6 density).
    """
    width, height = img.size
    pixels = img.load()
    step = 2  # sample every 2nd pixel for speed

    # Center bands for checking (middle 60% of image)
    cx_start, cx_end = width // 5, width * 4 // 5
    cy_start, cy_end = height // 5, height * 4 // 5
    cx_total = len(range(cx_start, cx_end, step))
    cy_total = len(range(cy_start, cy_end, step))

    def row_center_density(y):
        dark = sum(1 for x in range(cx_start, cx_end, step) if is_dark(*pixels[x, y][:3]))
        return dark / cx_total

    def col_center_density(x):
        dark = sum(1 for y in range(cy_start, cy_end, step) if is_dark(*pixels[x, y][:3]))
        return dark / cy_total

    density_threshold = 0.9
    skip_edge = 5  # skip first/last 5 pixels to avoid boundary artifacts

    # Find top frame line: first row (after edge skip) with >0.9 center density
    top = None
    for y in range(skip_edge, height // 3):
        if row_center_density(y) > density_threshold:
            top = y
            break

    # Find bottom frame line: last such row
    bottom = None
    for y in range(height - 1 - skip_edge, height * 2 // 3, -1):
        if row_center_density(y) > density_threshold:
            bottom = y
            break

    # Find left frame line
    left = None
    for x in range(skip_edge, width // 3):
        if col_center_density(x) > density_threshold:
            left = x
            break

    # Find right frame line
    right = None
    for x in range(width - 1 - skip_edge, width * 2 // 3, -1):
        if col_center_density(x) > density_threshold:
            right = x
            break

    if any(v is None for v in [top, bottom, left, right]):
        print(f"  Warning: Could not detect all frame edges (t={top}, b={bottom}, l={left}, r={right})")
        # Fall back to scanning with lower threshold
        density_threshold = 0.7
        if top is None:
            for y in range(skip_edge, height // 3):
                if row_center_density(y) > density_threshold:
                    top = y
                    break
        if bottom is None:
            for y in range(height - 1 - skip_edge, height * 2 // 3, -1):
                if row_center_density(y) > density_threshold:
                    bottom = y
                    break
        if left is None:
            for x in range(skip_edge, width // 3):
                if col_center_density(x) > density_threshold:
                    left = x
                    break
        if right is None:
            for x in range(width - 1 - skip_edge, width * 2 // 3, -1):
                if col_center_density(x) > density_threshold:
                    right = x
                    break

    # Now expand to find the outer edge of the border (it's several pixels thick)
    # Walk outward from detected line until density drops
    if top is not None:
        for y in range(top, max(0, top - 30), -1):
            if row_center_density(y) < 0.5:
                top = y + 1
                break

    if bottom is not None:
        for y in range(bottom, min(height - 1, bottom + 30)):
            if row_center_density(y) < 0.5:
                bottom = y - 1
                break

    if left is not None:
        for x in range(left, max(0, left - 30), -1):
            if col_center_density(x) < 0.5:
                left = x + 1
                break

    if right is not None:
        for x in range(right, min(width - 1, right + 30)):
            if col_center_density(x) < 0.5:
                right = x - 1
                break

    # Default to full image if detection completely fails
    top = top or 0
    bottom = bottom or (height - 1)
    left = left or 0
    right = right or (width - 1)

    # Sanity check: frame should be roughly centered. If one edge is
    # suspiciously close to the image boundary while its opposite isn't,
    # it's likely a misdetection (e.g. a thick vertical line in the artwork).
    min_expected_margin = 30  # cards typically have at least this much margin
    margin_top, margin_bottom = top, height - 1 - bottom
    margin_left, margin_right = left, width - 1 - right

    # Check horizontal symmetry
    if margin_left < min_expected_margin and margin_right > min_expected_margin * 2:
        # Left edge seems wrong - estimate from right
        left = width - 1 - right  # mirror the right margin
        print(f"  Corrected left edge: {left} (was too close to boundary)")
    elif margin_right < min_expected_margin and margin_left > min_expected_margin * 2:
        right = width - 1 - left
        print(f"  Corrected right edge: {right} (was too close to boundary)")

    # Check vertical symmetry
    if margin_top < min_expected_margin and margin_bottom > min_expected_margin * 2:
        top = height - 1 - bottom
        print(f"  Corrected top edge: {top} (was too close to boundary)")
    elif margin_bottom < min_expected_margin and margin_top > min_expected_margin * 2:
        bottom = height - 1 - top
        print(f"  Corrected bottom edge: {bottom} (was too close to boundary)")

    return left, top, right, bottom


def white_out_outside_frame(img, frame_rect):
    """White out everything outside the frame rectangle."""
    width, height = img.size
    left, top, right, bottom = frame_rect
    draw = ImageDraw.Draw(img)

    # Top strip
    if top > 0:
        draw.rectangle([0, 0, width - 1, top - 1], fill=(255, 255, 255))
    # Bottom strip
    if bottom < height - 1:
        draw.rectangle([0, bottom + 1, width - 1, height - 1], fill=(255, 255, 255))
    # Left strip (between top and bottom)
    if left > 0:
        draw.rectangle([0, top, left - 1, bottom], fill=(255, 255, 255))
    # Right strip (between top and bottom)
    if right < width - 1:
        draw.rectangle([right + 1, top, width - 1, bottom], fill=(255, 255, 255))

    return img


def detect_suit_color(img, frame_rect):
    """Determine if the card uses red or black suit from frame border color."""
    pixels = img.load()
    left, top, right, bottom = frame_rect

    red_count = 0
    black_count = 0
    # Sample along the top border
    for x in range(left, right, 4):
        for y_off in range(-2, 3):
            y = top + y_off
            if 0 <= y < img.size[1]:
                r, g, b = pixels[x, y][:3]
                if r > 150 and g < 100 and b < 100:
                    red_count += 1
                elif r < 80 and g < 80 and b < 80:
                    black_count += 1

    return "red" if red_count > black_count else "black"


def detect_and_remove_pips(img, frame_rect, max_pip_size=4000, min_pip_size=50):
    """Remove stray suit symbols (pips) from inside the frame margins.

    Strategy: Find all dark/colored blobs in the margin area (near corners/edges).
    Only remove blobs that are ISOLATED (not connected to the central figure).
    A blob is considered isolated if it doesn't touch the central figure zone.

    Args:
        max_pip_size: maximum pixel count for a blob to be considered a removable pip
        min_pip_size: minimum pixel count (ignore tiny specks)
    """
    width, height = img.size
    left, top, right, bottom = frame_rect
    pixels = img.load()

    suit_color = detect_suit_color(img, frame_rect)

    def is_dark_or_colored(r, g, b):
        """Match any non-white pixel (artwork of any color)."""
        return (r + g + b) < 680 and min(r, g, b) < 200

    # Define zones: corner rectangles where stray pips typically appear
    frame_w = right - left
    frame_h = bottom - top
    corner_w = frame_w // 4
    corner_h = frame_h // 5

    corner_zones = [
        # (x1, y1, x2, y2) for each corner zone inside the frame
        (left + 3, top + 3, left + corner_w, top + corner_h),           # top-left
        (right - corner_w, top + 3, right - 3, top + corner_h),         # top-right
        (left + 3, bottom - corner_h, left + corner_w, bottom - 3),     # bottom-left
        (right - corner_w, bottom - corner_h, right - 3, bottom - 3),   # bottom-right
    ]

    # Central figure zone - blobs touching this are part of the main artwork
    fig_margin_x = frame_w // 4
    fig_margin_y = frame_h // 5
    fig_left = left + fig_margin_x
    fig_right = right - fig_margin_x
    fig_top = top + fig_margin_y
    fig_bottom = bottom - fig_margin_y

    def flood_find_blob(start_x, start_y, max_pixels=6000):
        """Find all connected dark pixels from a starting point.
        Returns (set of pixels, touches_figure_zone)."""
        stack = [(start_x, start_y)]
        visited = set()
        touches_figure = False

        while stack and len(visited) < max_pixels:
            x, y = stack.pop()
            if (x, y) in visited:
                continue
            if not (left + 1 <= x <= right - 1 and top + 1 <= y <= bottom - 1):
                continue
            r, g, b = pixels[x, y][:3]
            if not is_dark_or_colored(r, g, b):
                continue

            visited.add((x, y))

            # Check if this pixel is in the central figure zone
            if fig_left <= x <= fig_right and fig_top <= y <= fig_bottom:
                touches_figure = True

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited:
                    stack.append((nx, ny))

        return visited, touches_figure

    removed = 0
    already_visited = set()
    step = 3

    for zx1, zy1, zx2, zy2 in corner_zones:
        for y in range(zy1, zy2, step):
            for x in range(zx1, zx2, step):
                if (x, y) in already_visited:
                    continue

                r, g, b = pixels[x, y][:3]
                if not is_dark_or_colored(r, g, b):
                    continue

                blob, touches_figure = flood_find_blob(x, y, max_pixels=max_pip_size + 100)
                already_visited.update(blob)

                # Only remove if: isolated from figure, right size range
                if not touches_figure and min_pip_size <= len(blob) <= max_pip_size:
                    for bx, by in blob:
                        pixels[bx, by] = (255, 255, 255)
                    removed += 1

    return img, removed


def clean_card(filepath, suffix="", dry_run=False, remove_pips=False):
    """Clean a single card image."""
    path = Path(filepath)
    img = Image.open(path).convert("RGB")

    frame_rect = find_frame_rect(img)
    left, top, right, bottom = frame_rect
    width, height = img.size

    print(f"  Frame: ({left}, {top}) -> ({right}, {bottom})")
    print(f"  Image: {width}x{height}, margins: T={top} B={height-bottom-1} L={left} R={width-right-1}")

    if dry_run:
        print(f"  [DRY RUN] Would clean {path.name}")
        return

    img = white_out_outside_frame(img, frame_rect)

    if remove_pips:
        img, pip_count = detect_and_remove_pips(img, frame_rect)
        if pip_count > 0:
            print(f"  Removed {pip_count} stray pip region(s)")

    if suffix:
        out_path = path.parent / f"{path.stem}{suffix}{path.suffix}"
    else:
        out_path = path
    img.save(out_path, quality=95)
    print(f"  Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up AI-generated playing card images"
    )
    parser.add_argument("path", help="Path to a card image or directory of card images")
    parser.add_argument("--suffix", default="", help="Suffix for output files (empty = overwrite)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--remove-pips", action="store_true", help="Remove stray suit symbols inside frame")
    parser.add_argument("--pattern", default="*.jpg", help="Glob pattern for directory mode (default: *.jpg)")
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.rglob(args.pattern))
    else:
        print(f"Error: {target} not found")
        sys.exit(1)

    if not files:
        print(f"No {args.pattern} files found in {target}")
        sys.exit(1)

    print(f"Processing {len(files)} file(s)...")
    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f}")
        try:
            clean_card(f, suffix=args.suffix, dry_run=args.dry_run, remove_pips=args.remove_pips)
        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
