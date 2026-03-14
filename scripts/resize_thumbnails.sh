#!/usr/bin/env bash
set -euo pipefail

IMAGE_ROOT="frontend/public/images"
THUMB_SIZE="320x320"
THUMB_QUALITY="90"

if ! command -v magick >/dev/null 2>&1; then
  echo "ImageMagick 'magick' not found. Install ImageMagick to generate thumbnails." >&2
  exit 1
fi

if [ ! -d "$IMAGE_ROOT" ]; then
  echo "Image directory not found: $IMAGE_ROOT" >&2
  exit 1
fi

updated=0

while IFS= read -r -d '' img; do
  dir=$(dirname "$img")
  filename=$(basename "$img")
  thumb_dir="$dir/thumbnails"
  thumb_path="$thumb_dir/$filename"

  mkdir -p "$thumb_dir"

  # Skip regeneration when the thumbnail is already current for this source image.
  if [ -f "$thumb_path" ] && [ ! "$img" -nt "$thumb_path" ]; then
    continue
  fi

  tmp_thumb=$(mktemp "$thumb_dir/.thumb-${filename}.XXXXXX")
  magick "$img" -resize "$THUMB_SIZE" -quality "$THUMB_QUALITY" "$tmp_thumb"

  if [ -f "$thumb_path" ] && cmp -s "$tmp_thumb" "$thumb_path"; then
    rm -f "$tmp_thumb"
    continue
  fi

  mv "$tmp_thumb" "$thumb_path"
  updated=1
  echo "Updated thumbnail: $thumb_path"
done < <(find "$IMAGE_ROOT" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) ! -path "*/thumbnails/*" -print0)

if [ "$updated" -eq 0 ]; then
  echo "Thumbnails already up to date."
fi
