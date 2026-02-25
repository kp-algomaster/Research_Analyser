#!/usr/bin/env zsh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d ".venv312" ]]; then
  echo "Missing .venv312. Create it first: python3.12 -m venv .venv312"
  exit 1
fi

source .venv312/bin/activate

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
  --osx-bundle-identifier "com.research.analyser" \
  --add-data "app.py:." \
  --add-data "config.yaml:." \
  --add-data "monkeyocr.py:." \
  --add-data "research_analyser:research_analyser" \
  --add-data ".streamlit:.streamlit" \
  --add-data "packaging/python312.tar.gz:." \
  --collect-all webview \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  packaging/macos_launcher.py

# Clean up the staging copy (the cache stays in packaging/python_cache/)
rm -f "packaging/python312.tar.gz"

APP_PATH="$DIST_DIR/${APP_NAME}.app"
TMP_DMG="$DIST_DIR/${APP_NAME}-tmp.dmg"
DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"

# ── Stage drag-to-install layout ──────────────────────────────────────────────
STAGE_DIR="$DIST_DIR/dmg_stage"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/.background"

cp -r "$APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

# Generate background image — Ollama-style: clean white, thin curved arrow, no wells.
# Canvas: 1080×640 px saved at 144 dpi → displays at 540×320 pt in Finder (Retina-sharp).
# Window bounds {200,100,740,420} = 540×320 pt.
# Icon centres (pt): left=(135,140), right=(405,140)  → (2× px): (270,280), (810,280).
BG_PATH="$STAGE_DIR/.background/background.png"
python3 -c "
import struct, zlib, math
bg = '$BG_PATH'
W, H = 1080, 640   # 2x canvas; dpi=(144,144) makes Finder render at 540x320 pt
try:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new('RGB', (W, H), (255, 255, 255))
    d   = ImageDraw.Draw(img)

    # ── Thin curved arrow (Ollama-style) ──────────────────────────────────────
    # Cubic bezier: starts right of left icon, arcs up, ends left of right icon.
    # All coords in 2x pixels.  Icon centres: left=(270,280), right=(810,280).
    def bez(t, p0, p1, p2, p3):
        mt = 1 - t
        return (mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0],
                mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1])

    P0 = (410, 292)   # start — right of left icon
    P1 = (510, 195)   # ctrl1  — pull curve upward
    P2 = (600, 200)   # ctrl2  — keep arc high
    P3 = (680, 290)   # end   — left of right icon

    STEPS = 400
    pts = [(round(bez(i/STEPS, P0, P1, P2, P3)[0]),
            round(bez(i/STEPS, P0, P1, P2, P3)[1])) for i in range(STEPS+1)]

    INK = (36, 36, 36)   # near-black
    SW  = 7              # stroke width in 2x px (≈3.5 pt)
    try:
        d.line(pts, fill=INK, width=SW, joint='curve')
    except TypeError:
        d.line(pts, fill=INK, width=SW)

    # Arrowhead — V-shape aligned to tangent at P3 (direction P2→P3)
    tx = P3[0] - P2[0]; ty = P3[1] - P2[1]
    tl = math.sqrt(tx*tx + ty*ty)
    tx /= tl; ty /= tl
    ang = math.atan2(ty, tx)
    L = 38; A = math.radians(25)
    w0 = (P3[0] - L*math.cos(ang - A), P3[1] - L*math.sin(ang - A))
    w1 = (P3[0] - L*math.cos(ang + A), P3[1] - L*math.sin(ang + A))
    d.line([w0, P3], fill=INK, width=SW)
    d.line([P3, w1], fill=INK, width=SW)

    img.save(bg, dpi=(144, 144))
    print('  Background: OK (2x Retina, Ollama-style)')

except Exception as _e:
    print(f'  Pillow failed ({_e}); using stdlib fallback')
    try:
        rows = bytearray()
        for y in range(H):
            rows += b'\x00'
            for x in range(W):
                rows += bytes([255, 255, 255])
        compressed = zlib.compress(bytes(rows), 9)
        def chunk(t, d):
            crc = zlib.crc32(t+d) & 0xFFFFFFFF
            return struct.pack('>I', len(d)) + t + d + struct.pack('>I', crc)
        ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
        open(bg, 'wb').write(
            b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', compressed)
            + chunk(b'IEND', b''))
        print('  Background: stdlib fallback (plain white)')
    except Exception as _e2:
        print(f'  Background skipped: {_e2}')
" 2>&1 || true

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

# Build the background AppleScript clause only if the image was created
if [[ -f "$BG_PATH" ]]; then
  BG_SCRIPT='set background picture of icon view options of container window to file ".background:background.png"'
else
  BG_SCRIPT=''
fi

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
    ${BG_SCRIPT}
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
