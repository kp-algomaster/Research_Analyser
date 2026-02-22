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
  --copy-metadata pydantic \
  --copy-metadata pydantic-settings \
  --copy-metadata pydantic-core \
  --copy-metadata tavily-python \
  --copy-metadata httpx \
  --copy-metadata aiohttp \
  --copy-metadata rich \
  --copy-metadata click \
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
  --exclude-module pandas.tests \
  --exclude-module numpy.tests \
  --exclude-module scipy.tests \
  --exclude-module matplotlib.tests \
  --exclude-module sklearn.tests \
  packaging/macos_launcher.py

DMG_PATH="$DIST_DIR/${APP_NAME}.dmg"
APP_PATH="$DIST_DIR/${APP_NAME}.app"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Built app: $APP_PATH"
echo "Built dmg: $DMG_PATH"
