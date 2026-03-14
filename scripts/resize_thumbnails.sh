#!/usr/bin/env bash
set -euo pipefail

IMAGE_ROOT="frontend/public/images"
THUMB_SIZE="320x320"
THUMB_QUALITY="90"

if ! command -v convert >/dev/null 2>&1; then
  echo "ImageMagick 'convert' not found. Install ImageMagick to generate thumbnails." >&2
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

  before_hash=""
  if [ -f "$thumb_path" ]; then
    before_hash=$(shasum -a 256 "$thumb_path" | awk '{print $1}')
  fi

  convert "$img" -resize "$THUMB_SIZE" -quality "$THUMB_QUALITY" "$thumb_path"

  after_hash=$(shasum -a 256 "$thumb_path" | awk '{print $1}')
  if [ "$before_hash" != "$after_hash" ]; then
    updated=1
    echo "Updated thumbnail: $thumb_path"
  fi
done < <(find "$IMAGE_ROOT" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) ! -path "*/thumbnails/*" -print0)

if [ "$updated" -eq 0 ]; then
  echo "Thumbnails already up to date."
fi
