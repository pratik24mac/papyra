#!/usr/bin/env bash
# Build a plain, Finder-free DMG from the built .app (Tauri's create-dmg needs Finder automation,
# which fails on CI and when run from a non-interactive shell).
# Usage: tools/make_dmg_macos.sh [path/to/Papyra.app] [out.dmg]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:-$ROOT/apps/desktop/src-tauri/target/release/bundle/macos/Papyra.app}"
VERSION=$(python3 -c "import json;print(json.load(open('$ROOT/apps/desktop/src-tauri/tauri.conf.json'))['version'])")
ARCH=$(uname -m); [ "$ARCH" = "arm64" ] && ARCH=aarch64
OUT="${2:-$ROOT/apps/desktop/src-tauri/target/release/bundle/dmg/Papyra_${VERSION}_${ARCH}.dmg}"
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"; ln -s /Applications "$STAGE/Applications"
mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
hdiutil create -quiet -volname "Papyra" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "$OUT ($(du -h "$OUT" | cut -f1))"
