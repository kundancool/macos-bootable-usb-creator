#!/bin/bash
# Build locally. No downloads or USB operations are performed by this script.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
CONFIG="release"
UNIVERSAL=0
case "${1:-}" in
  --debug) CONFIG="debug" ;;
  --universal) UNIVERSAL=1 ;;
  --help|-h) echo 'Usage: scripts/build-app.sh [--debug|--universal]'; exit 0 ;;
  '') ;;
  *) echo 'Unknown build option' >&2; exit 1 ;;
esac
export CLANG_MODULE_CACHE_PATH="$ROOT/App/.build/current/module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$ROOT/App/.build/current/module-cache"
ARGS=(--package-path "$ROOT/App" --scratch-path "$ROOT/App/.build/current/package" --disable-sandbox -c "$CONFIG")
if [ "$UNIVERSAL" -eq 1 ]; then ARGS+=(--arch arm64 --arch x86_64); fi
/usr/bin/swift build "${ARGS[@]}"
BIN_DIR="$(/usr/bin/swift build "${ARGS[@]}" --show-bin-path)"
mkdir -p "$ROOT/dist"
BUILD_DIR="$(mktemp -d "$ROOT/dist/.app-build.XXXXXX")"
trap '/bin/rm -rf "$BUILD_DIR"' EXIT
APP="$BUILD_DIR/macOS Bootable USB Creator.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/backend"
"$ROOT/scripts/make-icon.sh"
cp "$ROOT/App/.build/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
cp "$BIN_DIR/MacOSBootableUSBCreator" "$APP/Contents/MacOS/MacOSBootableUSBCreator"
cp "$ROOT/App/Info.plist" "$APP/Contents/Info.plist"
cp "$ROOT/engine/"*.py "$APP/Contents/Resources/backend/"
cp "$ROOT/README.md" "$ROOT/CREDITS.md" "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$APP/Contents/Resources/"
cp "$ROOT/CHANGELOG.md" "$ROOT/CONTRIBUTING.md" "$ROOT/SECURITY.md" "$APP/Contents/Resources/"
mkdir -p "$APP/Contents/Resources/docs"
cp "$ROOT/docs/"*.md "$APP/Contents/Resources/docs/"
/usr/bin/codesign --force --sign "${CODESIGN_IDENTITY:--}" "$APP"
/usr/bin/codesign --verify --strict "$APP"
OUTPUT="$ROOT/dist/macOS Bootable USB Creator.app"
if [ -e "$OUTPUT" ]; then
  mkdir -p "$ROOT/work/previous-builds"
  mv "$OUTPUT" "$ROOT/work/previous-builds/app-$(date +%Y%m%d-%H%M%S)-$$.app"
fi
mv "$APP" "$OUTPUT"
echo "Built: $OUTPUT"
echo 'This local build is ad hoc signed unless CODESIGN_IDENTITY is set. Public distribution requires your own signing/notarization setup.'
