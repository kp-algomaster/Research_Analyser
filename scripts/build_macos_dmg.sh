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
DIST_DIR="dist"
BUILD_DIR="build"

rm -rf "$DIST_DIR" "$BUILD_DIR" "${APP_NAME}.spec"

# Remove stale bytecode caches so PyInstaller bundles freshly compiled .pyc files
find . -type d -name "__pycache__" -not -path "./.venv*" -exec rm -rf {} + 2>/dev/null || true

pyinstaller \
  --noconfirm \
  --log-level WARN \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "com.research.analyser" \
  --add-data "app.py:." \
  --add-data "config.yaml:." \
  --add-data "monkeyocr.py:." \
  --add-data "research_analyser:research_analyser" \
  --collect-all webview \
  --collect-all streamlit \
  --collect-all altair \
  --collect-all pydeck \
  --collect-data pandas \
  --copy-metadata pandas \
  --collect-all langgraph \
  --collect-all langchain \
  --collect-all langchain_openai \
  --collect-all langchain_community \
  --collect-all langchain_core \
  --collect-all knowledge_storm \
  --collect-all dspy \
  --collect-all litellm \
  --copy-metadata pydantic \
  --copy-metadata pydantic-settings \
  --copy-metadata pydantic-core \
  --copy-metadata tavily-python \
  --copy-metadata httpx \
  --copy-metadata aiohttp \
  --copy-metadata rich \
  --copy-metadata click \
  --copy-metadata knowledge-storm \
  --copy-metadata dspy-ai \
  --copy-metadata litellm \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
  --hidden-import langgraph \
  --hidden-import langgraph.graph \
  --hidden-import langchain_openai \
  --hidden-import langchain_community \
  --hidden-import langchain_core \
  --hidden-import tavily \
  --hidden-import sklearn \
  --hidden-import sklearn.utils \
  --hidden-import tiktoken \
  --hidden-import tiktoken_ext \
  --hidden-import tiktoken_ext.openai_public \
  --hidden-import dspy \
  --hidden-import dspy.predict \
  --hidden-import dspy.retrieve \
  --hidden-import knowledge_storm \
  --hidden-import knowledge_storm.lm \
  --hidden-import knowledge_storm.rm \
  --hidden-import litellm \
  --hidden-import litellm.utils \
  --exclude-module pandas.tests \
  --exclude-module numpy.tests \
  --exclude-module scipy.tests \
  --exclude-module matplotlib.tests \
  --exclude-module sklearn.tests \
  packaging/macos_launcher.py

APP_PATH="$DIST_DIR/${APP_NAME}.app"
TMP_DMG="$DIST_DIR/${APP_NAME}-tmp.dmg"
DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"

# ── Stage drag-to-install layout ──────────────────────────────────────────────
STAGE_DIR="$DIST_DIR/dmg_stage"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/.background"

cp -r "$APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

# Generate background image (Pillow preferred; stdlib PNG fallback)
BG_PATH="$STAGE_DIR/.background/background.png"
python3 -c "
import sys, struct, zlib
bg = '$BG_PATH'
W, H = 540, 320
try:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (W, H), (13, 17, 23))
    d = ImageDraw.Draw(img)
    # Subtle radial-glow hint at centre
    for r in range(80, 0, -4):
        alpha = int(18 * (1 - r / 80))
        d.ellipse([(W//2 - r, H//2 - 30 - r), (W//2 + r, H//2 - 30 + r)],
                  fill=(56, 139, 253))
    # Arrow shaft + head between icon positions (app=140, apps=400, y=155)
    d.line([(220, 155), (308, 155)], fill=(88, 166, 255), width=3)
    d.polygon([(308, 145), (328, 155), (308, 165)], fill=(88, 166, 255))
    # Instructions label
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 14)
        font_sm = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 12)
    except Exception:
        font = font_sm = None
    kw = lambda f: {'font': f} if f else {}
    d.text((270, 218), 'Drag to Applications to install', fill=(139, 148, 158),
           anchor='mm', **kw(font))
    d.text((270, 238), 'Then open from your Applications folder', fill=(68, 78, 90),
           anchor='mm', **kw(font_sm))
    img.save(bg)
    print('  Background: Pillow')
except Exception as _e1:
    # stdlib-only fallback: solid dark PNG, no text
    try:
        rows = bytearray()
        for y in range(H):
            rows += b'\x00'
            for x in range(W):
                rows += bytes([13, 17, 23])
        compressed = zlib.compress(bytes(rows), 9)
        def chunk(tag, data):
            crc = zlib.crc32(tag + data) & 0xFFFFFFFF
            return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)
        ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
               + chunk(b'IDAT', compressed) + chunk(b'IEND', b''))
        open(bg, 'wb').write(png)
        print('  Background: stdlib fallback (no text)')
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
MOUNT_DIR="/Volumes/$APP_NAME"
hdiutil attach "$TMP_DMG" -readwrite -noverify -noautoopen -mountpoint "$MOUNT_DIR"
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
    set position of item "${APP_NAME}.app" of container window to {140, 155}
    set position of item "Applications" of container window to {400, 155}
    close
    open
    update without registering applications
    delay 2
  end tell
end tell
APPLESCRIPT

sync
hdiutil detach "$MOUNT_DIR"
sleep 2

# ── Convert to compressed read-only DMG ───────────────────────────────────────
hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$TMP_DMG"
rm -rf "$STAGE_DIR"

echo "Built app: $APP_PATH"
echo "Built dmg: $DMG_PATH"
