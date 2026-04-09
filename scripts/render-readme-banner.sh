#!/usr/bin/env bash
# Regenerate docs/assets/readme-pulse-banner.png (full-bleed #050505, no letterboxing).
# Requires: google-chrome (headless), ffmpeg.
#
# On HiDPI, Chrome often screenshots 2x (e.g. 920x264). Cropping a fixed height then
# kept only the top half of the banner. We always scale to exactly 920x132 instead.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML="file://${ROOT}/docs/assets/readme-pulse-hero-shoot.html"
OUT="${ROOT}/docs/assets/readme-pulse-banner.png"
TMP="${OUT}.tmp.png"

google-chrome --headless=new --disable-gpu --no-sandbox \
  --force-device-scale-factor=1 \
  --window-size=920,132 --hide-scrollbars \
  --screenshot="$TMP" "$HTML"

# Normalize to logical size (handles 920x132, 1840x264, 920x264, etc.)
ffmpeg -y -i "$TMP" -vf "scale=920:132:flags=lanczos" -frames:v 1 "$OUT" >/dev/null 2>&1
rm -f "$TMP"
echo "Wrote $OUT ($(wc -c < "$OUT") bytes)"
