#!/bin/bash
# Assemble and ad-hoc-sign a self-contained "USDZ Forge.app".
#
# The app bundles a relocatable CPython 3.14 (python-build-standalone) with
# usd-core (OpenUSD 26.5) + the ported Apple usdzconvert engine in Resources/engine.
# Nothing on the recipient's Mac is required beyond macOS 13+ on Apple Silicon.
#
# IMPORTANT: we assemble + sign in /private/tmp, NOT under ~/Documents. The project
# lives in an iCloud-synced folder, and iCloud/FileProvider injects xattrs that
# codesign rejects ("resource fork, Finder information, or similar detritus"). The
# final deliverable is a clean .zip copied back into dist/.
#
# Ad-hoc signing lets it run locally via right-click -> Open. For frictionless
# distribution, re-sign with a Developer ID identity and notarize (see JOURNAL.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="/private/tmp/usdzforge-build"
APP="$BUILD/USDZ Forge.app"
BIN="$ROOT/.build/release/USDZForge"
ENGINE="$ROOT/engine"

echo "==> Fresh bundle in /private/tmp (avoids iCloud xattr breakage)"
rm -rf "$BUILD"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources/engine"

echo "==> App binary + Info.plist"
ditto --norsrc --noextattr "$BIN" "$APP/Contents/MacOS/USDZForge"
cp "$ROOT/packaging/Info.plist" "$APP/Contents/Info.plist"
cp "$ROOT/packaging/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"

echo "==> Bundle engine: standalone python + native scripts"
ditto --norsrc --noextattr "$ENGINE/python" "$APP/Contents/Resources/engine/python"
ditto --norsrc --noextattr "$ENGINE/native" "$APP/Contents/Resources/engine/native"

echo "==> Strip caches to shrink bundle"
find "$APP/Contents/Resources/engine" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$APP/Contents/Resources/engine" -name "*.pyc" -delete 2>/dev/null || true

echo "==> Strip extended attributes"
xattr -cr "$APP"

echo "==> Sign inside-out (ad-hoc)"
find "$APP/Contents/Resources/engine/python" \( -name "*.dylib" -o -name "*.so" \) -type f -print0 \
  | xargs -0 -I{} codesign --force --timestamp=none -s - {}
find "$APP/Contents/Resources/engine/python/bin" -type f -perm +111 -print0 \
  | xargs -0 -I{} codesign --force --timestamp=none -s - {} 2>/dev/null || true
codesign --force --timestamp=none -s - "$APP/Contents/MacOS/USDZForge"
codesign --force --timestamp=none -s - "$APP"

echo "==> Verify signature"
codesign -vv "$APP"

echo "==> Emit clean deliverable zip"
mkdir -p "$ROOT/dist"
rm -f "$ROOT/dist/USDZ-Forge.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ROOT/dist/USDZ-Forge.zip"

du -sh "$APP"
echo ""
echo "Signed app: $APP"
echo "Deliverable: $ROOT/dist/USDZ-Forge.zip"
echo "First launch on another Mac: unzip, then right-click -> Open."
