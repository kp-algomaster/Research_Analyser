#!/usr/bin/env zsh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d ".venv312" ]]; then
  echo "Missing .venv312. Create it first: python3 -m venv .venv312"
  exit 1
fi

source .venv312/bin/activate

if [[ -n "${SKIP_SSL_VERIFICATION:-}" ]]; then
  echo "Note: SKIP_SSL_VERIFICATION is a runtime setting for API calls;"
  echo "      it is not required for DMG packaging and is ignored by this build script."
fi

python -m pip install --upgrade pip
python -m pip install pyinstaller

APP_NAME="ResearchAnalyser"

# ── Bundle a self-contained Python 3.12 interpreter ───────────────────────────
# We use python-build-standalone (indygreg) "install_only" tarballs.
# They are fully self-contained: no system Python is required at all.
# The tarball is bundled inside the .app via PyInstaller --add-data and
# extracted by the launcher to ~/.researchanalyser/python312/ on first run.
#
# The download is cached in packaging/python_cache/ so rebuilds are fast.
# ──────────────────────────────────────────────────────────────────────────────
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
  PY_ARCH="aarch64-apple-darwin"
else
  PY_ARCH="x86_64-apple-darwin"
fi

PY_CACHE_DIR="packaging/python_cache"
mkdir -p "$PY_CACHE_DIR"
PY_CACHE="$PY_CACHE_DIR/python312_${ARCH}.tar.gz"

if [[ ! -f "$PY_CACHE" ]]; then
  echo "  Fetching latest python-build-standalone release info…"
  # Query GitHub API for the latest release; extract the matching asset URL.
  # Note: python3 -c uses a double-quoted shell string so ${PY_ARCH} expands.
  RELEASE_JSON=$(curl -fsSL \
    -H "User-Agent: research-analyser-build" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/indygreg/python-build-standalone/releases/latest")
  PY_URL=$(echo "$RELEASE_JSON" | python3 -c "
import sys, json
raw = sys.stdin.read()
data = json.JSONDecoder(strict=False).decode(raw)
for a in data.get('assets', []):
    n = a['name']
    if ('cpython-3.12' in n and '${PY_ARCH}' in n
            and 'install_only' in n and n.endswith('.tar.gz')):
        print(a['browser_download_url'])
        break
")
  if [[ -z "$PY_URL" ]]; then
    echo "  ERROR: Could not find a Python 3.12 ${PY_ARCH} install_only asset." >&2
    echo "         Check https://github.com/indygreg/python-build-standalone/releases" >&2
    exit 1
  fi
  echo "  Downloading: $PY_URL"
  curl -fL --progress-bar -o "$PY_CACHE" "$PY_URL"
  echo "  Cached to: $PY_CACHE ($(du -sh "$PY_CACHE" | cut -f1))"
else
  echo "  Using cached Python 3.12 tarball: $PY_CACHE ($(du -sh "$PY_CACHE" | cut -f1))"
fi

# Symlink/copy into a predictable name that PyInstaller --add-data will pick up
cp "$PY_CACHE" "packaging/python312.tar.gz"
echo "  Bundled Python 3.12 ready."
# (Cleaned up after PyInstaller below)
DIST_DIR="dist"
BUILD_DIR="build"

rm -rf "$DIST_DIR" "$BUILD_DIR" "${APP_NAME}.spec"

# Remove stale bytecode caches so PyInstaller bundles freshly compiled .pyc files
find . -type d -name "__pycache__" -not -path "./.venv*" -exec rm -rf {} + 2>/dev/null || true

# ── Generate custom app icon ───────────────────────────────────────────────────
echo "Generating app icon…"
python3 packaging/make_icon.py

# ── Bundle beautiful-mermaid Node.js renderer ──────────────────────────────────
echo "Bundling beautiful-mermaid renderer…"
(cd packaging/beautiful_mermaid && npm install --silent && npm run build --silent)

# ── PyInstaller: LIGHTWEIGHT bundle ───────────────────────────────────────────
# Heavy ML/data deps (torch, streamlit, langchain, scipy, …) are NOT bundled.
# They are installed into ~/.researchanalyser/venv by the launcher on first run.
# This keeps the .app at ~80-150 MB instead of 3+ GB.
pyinstaller \
  --noconfirm \
  --log-level WARN \
  --windowed \
  --strip \
  --name "$APP_NAME" \
  --icon "packaging/icon.icns" \
  --osx-bundle-identifier "com.research.analyser" \
  --add-data "app.py:." \
  --add-data "config.yaml:." \
  --add-data "monkeyocr.py:." \
  --add-data "research_analyser:research_analyser" \
  --add-data ".streamlit:.streamlit" \
  --add-data "packaging/python312.tar.gz:." \
  --add-data "packaging/beautiful_mermaid/render.bundle.mjs:packaging/beautiful_mermaid" \
  --collect-all webview \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  packaging/macos_launcher.py

# Clean up the staging copy (the cache stays in packaging/python_cache/)
rm -f "packaging/python312.tar.gz"

APP_PATH="$DIST_DIR/${APP_NAME}.app"

# ── Ad-hoc Sign the App Bundle ────────────────────────────────────────────────
echo "Ad-hoc signing the app bundle to prevent Gatekeeper issues on local machine..."
codesign --force --deep --sign - "$APP_PATH"

TMP_DMG="$DIST_DIR/${APP_NAME}-tmp.dmg"
DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"

# ── Stage drag-to-install layout ──────────────────────────────────────────────
STAGE_DIR="$DIST_DIR/dmg_stage"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

cp -r "$APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

# ── Writable DMG from staged directory ────────────────────────────────────────
rm -f "$TMP_DMG" "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDRW \
  "$TMP_DMG"

# Mount for Finder window / icon customisation
# Capture the /dev/diskXsY device so we detach by device, not by mount-point
# name (which can be ambiguous when stale mounts linger from earlier builds).
MOUNT_DIR="/Volumes/$APP_NAME"
ATTACH_OUT=$(hdiutil attach "$TMP_DMG" -readwrite -noverify -noautoopen -mountpoint "$MOUNT_DIR")
# Extract the first /dev/diskN entry from the attach output
ATTACH_DEV=$(echo "$ATTACH_OUT" | awk '/\/dev\/disk/{print $1; exit}')
echo "  Attached as $ATTACH_DEV → $MOUNT_DIR"
sleep 3

osascript <<APPLESCRIPT
tell application "Finder"
  tell disk "$APP_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {200, 100, 740, 420}
    set the icon size of the icon view options of container window to 100
    set the arrangement of the icon view options of container window to not arranged
    set position of item "${APP_NAME}.app" of container window to {135, 140}
    set position of item "Applications" of container window to {405, 140}

    close
    open
    update without registering applications
    delay 2
  end tell
end tell
APPLESCRIPT

sync
# Remove filesystem/event metadata folders from the mounted image so they don't
# appear as extra icons in the DMG window.
rm -rf "$MOUNT_DIR/.fseventsd" "$MOUNT_DIR/.Trashes" "$MOUNT_DIR/.hidden" "$MOUNT_DIR/.background" 2>/dev/null || true

# Detach by the exact device captured at attach time (not mount-point name,
# which can be ambiguous when stale mounts from prior builds still linger).
hdiutil detach "$ATTACH_DEV" 2>/dev/null \
  || { sleep 3; hdiutil detach "$ATTACH_DEV" -force; }
sleep 2

# ── Convert to compressed read-only DMG ───────────────────────────────────────
hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$TMP_DMG"
rm -rf "$STAGE_DIR"

echo "Built app: $APP_PATH"
echo "Built dmg: $DMG_PATH"
