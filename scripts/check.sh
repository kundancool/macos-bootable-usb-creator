#!/bin/bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
for script in ./*.command cli/*.command scripts/*.sh; do /bin/bash -n "$script"; done
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
export CLANG_MODULE_CACHE_PATH="$ROOT/App/.build/current/module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$ROOT/App/.build/current/module-cache"
mkdir -p "$ROOT/App/.build/current"
/usr/bin/swiftc -module-cache-path "$CLANG_MODULE_CACHE_PATH" \
  "$ROOT/App/Sources/MacOSBootableUSBCreator/Support.swift" \
  "$ROOT/App/Tests/SupportChecks/main.swift" -o "$ROOT/App/.build/current/support-checks"
"$ROOT/App/.build/current/support-checks"
