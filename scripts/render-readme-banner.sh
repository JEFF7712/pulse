#!/usr/bin/env bash
# Regenerate docs/assets/readme-pulse-banner.png
#
# Headless Chrome clips <pre> ASCII when the viewport is only ~140px tall. We capture a
# tall frame, then scripts/crop_readme_banner.py finds green pixels and centers on 920×N.
#
# Requires: google-chrome, ffmpeg (optional scale for HiDPI), Pillow (nix-shell below).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML="file://${ROOT}/docs/assets/readme-pulse-hero-shoot.html"
OUT="${ROOT}/docs/assets/readme-pulse-banner.png"
TMP="${OUT}.tmp.png"

google-chrome --headless=new --disable-gpu --no-sandbox \
  --force-device-scale-factor=1 \
  --window-size=920,480 --hide-scrollbars \
  --screenshot="$TMP" "$HTML"

# Normalize HiDPI captures to logical width 920 before bbox crop
W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$TMP")
NORM="${TMP}.norm.png"
if [[ "${W:-0}" != "920" ]]; then
  ffmpeg -y -i "$TMP" -vf "scale=920:-1:flags=lanczos" -frames:v 1 "$NORM" >/dev/null 2>&1
else
  cp "$TMP" "$NORM"
fi

if python3 -c "import PIL" 2>/dev/null; then
  python3 "${ROOT}/scripts/crop_readme_banner.py" "${NORM}" "${OUT}"
else
  nix-shell -p python313Packages.pillow --run "python3 ${ROOT}/scripts/crop_readme_banner.py \"${NORM}\" \"${OUT}\""
fi

rm -f "$TMP" "$NORM"
echo "Done: $OUT ($(wc -c < "$OUT") bytes)"
