#!/usr/bin/env python3
"""
Crop AI-generated playing card images to the card frame.

Per image:
    1. Detect the card frame border and crop to it (keeping the frame)
    2. If a frame is not confidently detected, crop to the center object bounds

Usage:
        python scripts/clean_cards.py mage-output/ --output mage-output/cleaned
        python scripts/clean_cards.py mage-output/ --dry-run
"""

import argparse
from collections import deque
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# White threshold for transparency conversion.
WHITE_THRESHOLD = 245

# Distance-from-white threshold for frameless foreground detection.
FOREGROUND_DELTA = 18


# ---------------------------------------------------------------------------
# Frame detection (for images with visible rectangular border)
# ---------------------------------------------------------------------------


def _is_dark(r, g, b, threshold=128):
    return min(r, g, b) < threshold or (r + g + b) < 600


def find_frame_rect(img):
    """Find the card frame border via pixel-density scanning.

    Returns (left, top, right, bottom) if confidently found, else None.
    """
    width, height = img.size
    pixels = img.load()
    step = 2

    cx_start, cx_end = width // 5, width * 4 // 5
    cy_start, cy_end = height // 5, height * 4 // 5
    cx_total = len(range(cx_start, cx_end, step))
    cy_total = len(range(cy_start, cy_end, step))

    def row_density(y):
        dark = sum(
            1 for x in range(cx_start, cx_end, step) if _is_dark(*pixels[x, y][:3])
        )
        return dark / cx_total

    def col_density(x):
        dark = sum(
            1 for y in range(cy_start, cy_end, step) if _is_dark(*pixels[x, y][:3])
        )
        return dark / cy_total

    skip = 5

    def _scan(scan_range, density_fn, threshold):
        for i in scan_range:
            if density_fn(i) > threshold:
                return i
        return None

    top = _scan(range(skip, height // 3), row_density, 0.9)
    bottom = _scan(range(height - 1 - skip, height * 2 // 3, -1), row_density, 0.9)
    left = _scan(range(skip, width // 3), col_density, 0.9)
    right = _scan(range(width - 1 - skip, width * 2 // 3, -1), col_density, 0.9)

    # Fallback with lower threshold
    if any(v is None for v in [top, bottom, left, right]):
        if top is None:
            top = _scan(range(skip, height // 3), row_density, 0.7)
        if bottom is None:
            bottom = _scan(
                range(height - 1 - skip, height * 2 // 3, -1), row_density, 0.7
            )
        if left is None:
            left = _scan(range(skip, width // 3), col_density, 0.7)
        if right is None:
            right = _scan(range(width - 1 - skip, width * 2 // 3, -1), col_density, 0.7)

    if top is None or bottom is None or left is None or right is None:
        return None

    # Expand outward to find outer edge of border
    if top is not None:
        for y in range(top, max(0, top - 30), -1):
            if row_density(y) < 0.5:
                top = y + 1
                break
    if bottom is not None:
        for y in range(bottom, min(height - 1, bottom + 30)):
            if row_density(y) < 0.5:
                bottom = y - 1
                break
    if left is not None:
        for x in range(left, max(0, left - 30), -1):
            if col_density(x) < 0.5:
                left = x + 1
                break
    if right is not None:
        for x in range(right, min(width - 1, right + 30)):
            if col_density(x) < 0.5:
                right = x - 1
                break

    # Symmetry sanity check
    min_margin = 30
    mt, mb = top, height - 1 - bottom
    ml, mr = left, width - 1 - right
    if ml < min_margin and mr > min_margin * 2:
        left = width - 1 - right
    elif mr < min_margin and ml > min_margin * 2:
        right = width - 1 - left
    if mt < min_margin and mb > min_margin * 2:
        top = height - 1 - bottom
    elif mb < min_margin and mt > min_margin * 2:
        bottom = height - 1 - top

    if right <= left or bottom <= top:
        return None

    frame_w = right - left + 1
    frame_h = bottom - top + 1
    if frame_w < width * 0.45 or frame_h < height * 0.45:
        return None

    # Border confidence check: all four edges should still look dark-heavy.
    if (
        row_density(top) < 0.55
        or row_density(bottom) < 0.55
        or col_density(left) < 0.55
        or col_density(right) < 0.55
    ):
        return None

    return left, top, right, bottom


# ---------------------------------------------------------------------------
# Center-object fallback detection
# ---------------------------------------------------------------------------


def find_center_object_bounds(img, threshold=WHITE_THRESHOLD, pad=2):
    """Find the central foreground object bounds as fallback crop.

    Returns PIL-style crop box (left, top, right, bottom).
    """
    arr = np.array(img.convert("RGB"), dtype=np.int16)
    h, w, _ = arr.shape

    # Treat anything meaningfully darker or more colorful than white as foreground.
    distance_from_white = 255 - arr.min(axis=2)
    channel_spread = arr.max(axis=2) - arr.min(axis=2)
    mask = (distance_from_white >= FOREGROUND_DELTA) | (
        (distance_from_white >= FOREGROUND_DELTA // 2) & (channel_spread >= 10)
    )

    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        gray = np.array(img.convert("L"))
        ys, xs = np.where(gray < threshold)
        if len(xs) == 0 or len(ys) == 0:
            return 0, 0, w, h
        left = max(0, int(xs.min()) - pad)
        top = max(0, int(ys.min()) - pad)
        right = min(w, int(xs.max()) + 1 + pad)
        bottom = min(h, int(ys.max()) + 1 + pad)
        return left, top, right, bottom

    center_x = w / 2
    center_y = h / 2
    inner_left = w * 0.18
    inner_right = w * 0.82
    inner_top = h * 0.14
    inner_bottom = h * 0.86
    min_area = max(12, int(w * h * 0.00015))
    large_area = max(40, int(w * h * 0.0025))

    visited = np.zeros((h, w), dtype=bool)
    kept_components = []

    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue

        queue = deque([(start_x, start_y)])
        visited[start_y, start_x] = True
        component_pixels = []
        min_x = max_x = start_x
        min_y = max_y = start_y
        touches_edge = (
            start_x == 0 or start_x == w - 1 or start_y == 0 or start_y == h - 1
        )

        while queue:
            x, y = queue.popleft()
            component_pixels.append((x, y))
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            if x == 0 or x == w - 1 or y == 0 or y == h - 1:
                touches_edge = True
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((nx, ny))

        area = len(component_pixels)
        if area < min_area:
            continue
        if touches_edge and area < large_area:
            continue

        center_component_x = (min_x + max_x) / 2
        center_component_y = (min_y + max_y) / 2
        intersects_inner = not (
            max_x < inner_left
            or min_x > inner_right
            or max_y < inner_top
            or min_y > inner_bottom
        )
        near_center = (
            abs(center_component_x - center_x) <= w * 0.22
            and abs(center_component_y - center_y) <= h * 0.28
        )

        if intersects_inner or near_center or area >= large_area:
            kept_components.append(component_pixels)

    if not kept_components:
        left = max(0, int(xs.min()) - pad)
        top = max(0, int(ys.min()) - pad)
        right = min(w, int(xs.max()) + 1 + pad)
        bottom = min(h, int(ys.max()) + 1 + pad)
        return left, top, right, bottom

    filtered_mask = np.zeros((h, w), dtype=bool)
    for component in kept_components:
        for x, y in component:
            filtered_mask[y, x] = True

    row_counts = filtered_mask.sum(axis=1)
    col_counts = filtered_mask.sum(axis=0)
    row_threshold = max(2, int(w * 0.006))
    col_threshold = max(2, int(h * 0.006))

    active_rows = np.where(row_counts >= row_threshold)[0]
    active_cols = np.where(col_counts >= col_threshold)[0]

    if len(active_rows) == 0 or len(active_cols) == 0:
        active_y, active_x = np.where(filtered_mask)
        if len(active_x) == 0 or len(active_y) == 0:
            return 0, 0, w, h
        left = max(0, int(active_x.min()) - pad)
        top = max(0, int(active_y.min()) - pad)
        right = min(w, int(active_x.max()) + 1 + pad)
        bottom = min(h, int(active_y.max()) + 1 + pad)
        return left, top, right, bottom

    left = max(0, int(active_cols[0]) - pad)
    top = max(0, int(active_rows[0]) - pad)
    right = min(w, int(active_cols[-1]) + 1 + pad)
    bottom = min(h, int(active_rows[-1]) + 1 + pad)
    return left, top, right, bottom


def make_white_transparent(img, threshold=WHITE_THRESHOLD):
    """Convert white and near-white pixels to transparent."""
    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    white = (
        (arr[:, :, 0] >= threshold)
        & (arr[:, :, 1] >= threshold)
        & (arr[:, :, 2] >= threshold)
    )
    arr[white, 3] = 0
    return Image.fromarray(arr)


# ---------------------------------------------------------------------------
# Single-card processing pipeline
# ---------------------------------------------------------------------------


def process_card(filepath, dry_run=False):
    """Crop to frame if found, otherwise crop to center object bounds."""
    img = Image.open(filepath).convert("RGB")
    frame_rect = find_frame_rect(img)
    w, h = img.size

    if dry_run:
        print(f"  [DRY RUN] Would process {Path(filepath).name}")
        return None

    if frame_rect is not None:
        left, top, right, bottom = frame_rect
        print(f"  Frame crop: ({left}, {top}) -> ({right}, {bottom})")
        print(
            f"  Image: {w}x{h}, margins: T={top} B={h-bottom-1} L={left} R={w-right-1}"
        )
        cropped = img.crop((left, top, right + 1, bottom + 1))
        return make_white_transparent(cropped)

    left, top, right, bottom = find_center_object_bounds(img)
    print(f"  Fallback center-object crop: ({left}, {top}) -> ({right-1}, {bottom-1})")
    cropped = img.crop((left, top, right, bottom))
    return make_white_transparent(cropped)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Crop AI-generated card images to frame (or center object fallback)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("path", help="Path to a card image or directory of images")
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for cropped PNGs (default: save alongside source)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument(
        "--pattern",
        default="*.jpg",
        help="Glob pattern for directory mode (default: *.jpg)",
    )
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    out_dir = None
    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Single file mode
    if target.is_file():
        print(f"[1/1] {target}")
        result = process_card(target, dry_run=args.dry_run)
        if result is not None:
            stem = target.stem
            out_path = (
                (out_dir / f"{stem}.png") if out_dir else target.with_suffix(".png")
            )
            result.save(out_path, "PNG", optimize=True)
            print(f"  Saved: {out_path}")
        return

    # Directory mode — process all matching files and preserve source stems.
    files = sorted(target.rglob(args.pattern))
    if not files:
        print(f"No {args.pattern} files found in {target}")
        sys.exit(1)

    print(f"Processing {len(files)} file(s) from {target}")
    if out_dir:
        print(f"Output: {out_dir}")

    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f}")

        try:
            result = process_card(f, dry_run=args.dry_run)
            if result is not None:
                out_path = (
                    (out_dir / f"{f.stem}.png") if out_dir else f.with_suffix(".png")
                )
                result.save(out_path, "PNG", optimize=True)
                print(f"  Saved: {out_path}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\nDone. Processed {len(files)} file(s).")


if __name__ == "__main__":
    main()
