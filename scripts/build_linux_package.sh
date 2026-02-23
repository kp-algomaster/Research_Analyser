#!/usr/bin/env bash
# Research Analyser — Linux build script
# Produces: dist/ResearchAnalyser/          (PyInstaller onedir bundle)
#           dist/ResearchAnalyser.AppImage  (self-contained, runs on most distros)
#           dist/ResearchAnalyser.deb       (Debian/Ubuntu installer, requires fpm)
#
# Prerequisites:
#   • Python 3.12:  sudo apt install python3.12 python3.12-venv  (Debian/Ubuntu)
#                   sudo dnf install python3.12                    (Fedora/RHEL)
#   • Virtual environment already created: python3.12 -m venv .venv312
#   • Packages installed: pip install -r requirements.txt
#   • For AppImage:
#       wget https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage
#       chmod +x appimagetool-x86_64.AppImage
#       sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool
#   • For .deb (optional):
#       sudo apt install ruby-dev && sudo gem install fpm
#   • Native webview system libraries (installed on the target machine):
#       sudo apt install gir1.2-webkit2-4.0 python3-gi   (Debian/Ubuntu)
#       sudo dnf install webkit2gtk4.0 python3-gobject    (Fedora/RHEL)
#
# Run from repo root:
#   ./scripts/build_linux_package.sh [--appimage] [--deb] [--all]
#
# Without flags, only the raw onedir bundle is produced.

set -euo pipefail
cd "$(dirname "$0")/.."

# ── Parse flags ───────────────────────────────────────────────────────────────
BUILD_APPIMAGE=false
BUILD_DEB=false
for arg in "$@"; do
  case $arg in
    --appimage) BUILD_APPIMAGE=true ;;
    --deb)      BUILD_DEB=true ;;
    --all)      BUILD_APPIMAGE=true; BUILD_DEB=true ;;
  esac
done

# ── Activate virtual environment ──────────────────────────────────────────────
if [[ ! -d ".venv312" ]]; then
  echo "Missing .venv312. Create it first: python3.12 -m venv .venv312"
  exit 1
fi
source .venv312/bin/activate

python -m pip install --upgrade pip
python -m pip install pyinstaller

APP_NAME="ResearchAnalyser"
APP_VERSION="1.0.0"
DIST_DIR="dist"
BUILD_DIR="build"

# ── Clean previous build ──────────────────────────────────────────────────────
rm -rf "$DIST_DIR" "$BUILD_DIR" "${APP_NAME}.spec"

# Remove stale bytecode caches
find . -type d -name "__pycache__" -not -path "./.venv*" -exec rm -rf {} + 2>/dev/null || true

# ── PyInstaller (onedir, no window flag — Linux needs a terminal or .desktop) ─
pyinstaller \
  --noconfirm \
  --log-level WARN \
  --name "$APP_NAME" \
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
  --hidden-import webview.platforms.gtk \
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
  packaging/linux_launcher.py

echo "PyInstaller bundle: $DIST_DIR/$APP_NAME/"

# ── AppImage ──────────────────────────────────────────────────────────────────
if [[ "$BUILD_APPIMAGE" == "true" ]]; then
  if ! command -v appimagetool &>/dev/null; then
    echo "appimagetool not found. Install it:"
    echo "  wget https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage"
    echo "  chmod +x appimagetool-x86_64.AppImage && sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool"
    exit 1
  fi

  APPDIR="$DIST_DIR/${APP_NAME}.AppDir"
  rm -rf "$APPDIR"
  mkdir -p "$APPDIR/usr/bin"

  # Copy PyInstaller bundle into AppDir
  cp -r "$DIST_DIR/$APP_NAME"/* "$APPDIR/usr/bin/"

  # AppRun entry point
  cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/ResearchAnalyser" "$@"
APPRUN
  chmod +x "$APPDIR/AppRun"

  # .desktop file
  cat > "$APPDIR/ResearchAnalyser.desktop" <<DESKTOP
[Desktop Entry]
Name=Research Analyser
Exec=ResearchAnalyser
Icon=ResearchAnalyser
Type=Application
Categories=Science;Education;
Comment=AI-powered research paper analysis
DESKTOP

  # Placeholder icon (replace with a real PNG if available)
  if [[ -f "packaging/icon.png" ]]; then
    cp packaging/icon.png "$APPDIR/ResearchAnalyser.png"
  else
    # Create a minimal 64x64 placeholder PNG using Python
    python3 -c "
import struct, zlib
def png_1px(r,g,b):
    raw = bytes([0,r,g,b,255])
    compressed = zlib.compress(raw)
    def chunk(t,d): l=len(d); return struct.pack('>I',l)+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
        + chunk(b'IDAT', compressed)
        + chunk(b'IEND', b''))
open('$APPDIR/ResearchAnalyser.png','wb').write(png_1px(30,90,160))
"
  fi

  APPIMAGE_PATH="$DIST_DIR/${APP_NAME}.AppImage"
  ARCH=x86_64 appimagetool "$APPDIR" "$APPIMAGE_PATH"
  chmod +x "$APPIMAGE_PATH"
  echo "AppImage: $APPIMAGE_PATH"
fi

# ── .deb package ──────────────────────────────────────────────────────────────
if [[ "$BUILD_DEB" == "true" ]]; then
  if ! command -v fpm &>/dev/null; then
    echo "fpm not found. Install it: sudo gem install fpm"
    exit 1
  fi

  DEB_PATH="$DIST_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"

  fpm \
    --input-type dir \
    --output-type deb \
    --name "research-analyser" \
    --version "$APP_VERSION" \
    --architecture amd64 \
    --description "AI-powered research paper analysis tool" \
    --url "https://github.com/kp-algomaster/Research_Analyser" \
    --maintainer "Research Analyser Team" \
    --depends "gir1.2-webkit2-4.0" \
    --depends "python3-gi" \
    --package "$DEB_PATH" \
    "$DIST_DIR/$APP_NAME/=/opt/ResearchAnalyser/" \
    packaging/research-analyser.desktop=/usr/share/applications/research-analyser.desktop

  echo ".deb package: $DEB_PATH"
fi

echo ""
echo "Build complete!"
echo "  Bundle    : $DIST_DIR/$APP_NAME/$APP_NAME"
[[ "$BUILD_APPIMAGE" == "true" ]] && echo "  AppImage  : $DIST_DIR/${APP_NAME}.AppImage"
[[ "$BUILD_DEB"      == "true" ]] && echo "  .deb      : $DIST_DIR/${APP_NAME}_${APP_VERSION}_amd64.deb"
