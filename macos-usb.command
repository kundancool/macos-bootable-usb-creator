#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is required. Install it from https://www.python.org/downloads/macos/' >&2
  exit 1
fi
exec python3 "$SCRIPT_DIR/engine/macos_usb.py" all "$@"
