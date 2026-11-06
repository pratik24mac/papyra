#!/usr/bin/env bash
# Sign every Mach-O file in the staged backend with a Developer ID (hardened runtime), so the
# notarised app bundle passes Gatekeeper. Usage: tools/sign_backend_macos.sh "Developer ID Application: Name (TEAMID)"
set -euo pipefail
IDENTITY="${1:?signing identity required}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/apps/desktop/src-tauri/resources/backend"
ENT="$(cd "$(dirname "$0")/.." && pwd)/apps/desktop/src-tauri/entitlements.plist"
find "$DIR" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) -print0 | while IFS= read -r -d '' f; do
  if file "$f" | grep -q "Mach-O"; then
    codesign --force --timestamp --options runtime --entitlements "$ENT" --sign "$IDENTITY" "$f"
  fi
done
echo "signed backend in $DIR"
