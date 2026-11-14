#!/bin/bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
ICONSET="$ROOT/App/.build/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  /usr/bin/sips -z "$size" "$size" "$ROOT/App/Assets/AppIcon.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  /usr/bin/sips -z "$double" "$double" "$ROOT/App/Assets/AppIcon.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
/usr/bin/iconutil --convert icns "$ICONSET" --output "$ROOT/App/.build/AppIcon.icns"
echo "Generated macOS icon: $ROOT/App/.build/AppIcon.icns"
