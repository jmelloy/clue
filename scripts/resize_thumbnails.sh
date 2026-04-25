#!/usr/bin/env bash
set -euo pipefail

IMAGE_ROOT="frontend/public/images"
THUMB_SIZE="320x320"
THUMB_QUALITY="90"

if command -v magick >/dev/null 2>&1; then
  IMAGEMAGICK_CMD=(magick)
elif command -v convert >/dev/null 2>&1; then
  # Ubuntu runners often provide ImageMagick 6 with `convert` but no `magick` shim.
  IMAGEMAGICK_CMD=(convert)
else
  echo "ImageMagick not found. Install ImageMagick to generate thumbnails." >&2
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
  ext="${filename##*.}"
  thumb_dir="$dir/thumbnails"
  thumb_path="$thumb_dir/$filename"

  mkdir -p "$thumb_dir"

  tmp_thumb=$(mktemp "$thumb_dir/.thumb-${filename%.*}.XXXXXX.${ext}")
  "${IMAGEMAGICK_CMD[@]}" "$img" \
    -strip \
    -resize "$THUMB_SIZE" \
    -quality "$THUMB_QUALITY" \
    -define png:exclude-chunk=date,time \
    "$tmp_thumb"

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
