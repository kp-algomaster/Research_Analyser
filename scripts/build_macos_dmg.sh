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
# Layout (540×320 canvas, window bounds {200,100,740,420}):
#   Left well  : x 40–230, y 45–240  → icon top-left AppleScript {85, 75}
#   Right well : x 310–500, y 45–240 → icon top-left AppleScript {355, 75}
#   Arrow      : x 238–302, y 142    (centred between wells)
#   Text       : y 264, 281
BG_PATH="$STAGE_DIR/.background/background.png"
python3 -c "
import struct, zlib
bg = '$BG_PATH'
W, H = 540, 320
try:
    from PIL import Image, ImageDraw, ImageFont

    # ── Canvas: dark vertical gradient ───────────────────────────────────────
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=(int(10 + t*8), int(13 + t*6), int(19 + t*11)))

    # ── Well geometry ─────────────────────────────────────────────────────────
    # Icon top-left set to {85,75} and {355,75} in AppleScript (100 pt icons).
    # Icon image: x+0..+100, y+0..+100.  Label (≈30 pt): y+104..+134.
    # Wells add 18–22 pt padding on each side around that bounding box.
    R = 14                                   # corner radius
    LX1, LY1, LX2, LY2 = 62,  55, 212, 218 # left well  (150 × 163 pt)
    RX1, RY1, RX2, RY2 = 332, 55, 482, 218 # right well (150 × 163 pt)
    MID_Y = 128                              # vertical centre of icon image

    # Fake drop-shadow: darker rect offset by 2 px
    SHADOW = (6, 8, 12)
    for bx1, by1, bx2, by2 in [(LX1, LY1, LX2, LY2), (RX1, RY1, RX2, RY2)]:
        d.rounded_rectangle([bx1+2, by1+3, bx2+2, by2+3],
                            radius=R, fill=SHADOW)

    # Well backgrounds
    FILL    = (20, 25, 33)
    BORDER  = (33, 40, 52)
    HILITE  = (38, 46, 60)   # top-edge inner highlight
    for bx1, by1, bx2, by2 in [(LX1, LY1, LX2, LY2), (RX1, RY1, RX2, RY2)]:
        d.rounded_rectangle([bx1, by1, bx2, by2],
                            radius=R, fill=FILL, outline=BORDER, width=1)
        # 1-px inner highlight along the top edge
        d.line([(bx1+R, by1+1), (bx2-R, by1+1)], fill=HILITE, width=1)

    # ── Arrow (shaft + head) ──────────────────────────────────────────────────
    AX0, AX1 = LX2 + 20, RX1 - 20          # gap on each side of the wells
    HEAD = 12                               # arrowhead length
    d.line([(AX0, MID_Y), (AX1 - HEAD, MID_Y)],
           fill=(52, 120, 230), width=2)
    d.polygon([(AX1-HEAD, MID_Y-7), (AX1, MID_Y), (AX1-HEAD, MID_Y+7)],
              fill=(80, 150, 255))

    # ── Text ──────────────────────────────────────────────────────────────────
    try:
        f1 = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 13)
        f2 = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 11)
    except Exception:
        f1 = f2 = None
    kw = lambda f: {'font': f} if f else {}
    d.text((W//2, 248), 'Drag to Applications to install',
           fill=(155, 165, 178), anchor='mm', **kw(f1))
    d.text((W//2, 265), 'Then open from your Applications folder',
           fill=(65, 75, 92), anchor='mm', **kw(f2))

    img.save(bg)
    print('  Background: OK')

except Exception as _e:
    print(f'  Pillow failed ({_e}); using stdlib fallback')
    try:
        rows = bytearray()
        for y in range(H):
            rows += b'\x00'
            for x in range(W):
                rows += bytes([13, 17, 23])
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
    set position of item "${APP_NAME}.app" of container window to {85, 75}
    set position of item "Applications" of container window to {355, 75}
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
