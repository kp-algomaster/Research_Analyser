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
  --collect-all webview \
  --hidden-import webview \
  --hidden-import webview.platforms.cocoa \
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
#   Finder set position = CENTRE of icon image (100 pt icons).
#   Left icon centre : {135, 140}  → left well  (65,70)→(205,250)
#   Right icon centre: {405, 140}  → right well (335,70)→(475,250)
#   Arrow            : x 225–315, y 140
#   Text             : y 270, 287
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
    # Finder set position uses CENTRE of the icon IMAGE (confirmed from
    # screenshots).  Icon centres: left=(135,140), right=(405,140).
    # Icon image: cx±50 pt.  Label below icon: cy+55 → cy+90 (≈35 pt).
    # Wells: 20 pt padding around the full icon+label bounding box.
    R = 14                                   # corner radius
    LX1, LY1, LX2, LY2 = 65,  70, 205, 250 # left well  (140 × 180 pt)
    RX1, RY1, RX2, RY2 = 335, 70, 475, 250 # right well (140 × 180 pt)
    MID_Y = 140                              # == icon centre y

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
    d.text((W//2, 270), 'Drag to Applications to install',
           fill=(155, 165, 178), anchor='mm', **kw(f1))
    d.text((W//2, 287), 'Then open from your Applications folder',
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
# Detach with a retry + force fallback so "Resource busy" doesn't abort the build
hdiutil detach "$MOUNT_DIR" 2>/dev/null \
  || { sleep 3; hdiutil detach "$MOUNT_DIR" -force; }
sleep 2

# ── Convert to compressed read-only DMG ───────────────────────────────────────
hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$TMP_DMG"
rm -rf "$STAGE_DIR"

echo "Built app: $APP_PATH"
echo "Built dmg: $DMG_PATH"
