# Research Analyser — Windows build script
# Produces: dist\ResearchAnalyser\ResearchAnalyser.exe  (portable folder)
#           dist\ResearchAnalyser-Windows.zip            (distributable archive)
#
# Prerequisites:
#   • Python 3.12 installed and on PATH  (python.org/downloads)
#   • Virtual environment: python -m venv .venv312
#   • Packages installed: pip install -r requirements.txt
#   • WebView2 Runtime on the target machine (ships with Windows 11 / Edge;
#     installer: https://developer.microsoft.com/en-us/microsoft-edge/webview2/)
#
# Run from repo root (PowerShell):
#   .\scripts\build_windows_exe.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

# ── Activate virtual environment ──────────────────────────────────────────────
$VenvActivate = ".venv312\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Error "Missing .venv312. Create it first: python -m venv .venv312"
    exit 1
}
& $VenvActivate

# ── Install build tools ───────────────────────────────────────────────────────
python -m pip install --upgrade pip
python -m pip install pyinstaller

$AppName = "ResearchAnalyser"
$DistDir = "dist"
$BuildDir = "build"

# ── Clean previous build ──────────────────────────────────────────────────────
foreach ($dir in @($DistDir, $BuildDir)) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
if (Test-Path "$AppName.spec") { Remove-Item "$AppName.spec" }

# Remove stale bytecode caches
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory |
    Where-Object { $_.FullName -notmatch "\\.venv" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── PyInstaller ───────────────────────────────────────────────────────────────
# Note: --add-data uses semicolons (;) on Windows, not colons (:)
pyinstaller `
    --noconfirm `
    --log-level WARN `
    --windowed `
    --name $AppName `
    --add-data "app.py;." `
    --add-data "config.yaml;." `
    --add-data "monkeyocr.py;." `
    --add-data "research_analyser;research_analyser" `
    --collect-all webview `
    --collect-all streamlit `
    --collect-all altair `
    --collect-all pydeck `
    --collect-data pandas `
    --copy-metadata pandas `
    --collect-all langgraph `
    --collect-all langchain `
    --collect-all langchain_openai `
    --collect-all langchain_community `
    --collect-all langchain_core `
    --collect-all knowledge_storm `
    --collect-all dspy `
    --collect-all litellm `
    --copy-metadata pydantic `
    --copy-metadata pydantic-settings `
    --copy-metadata pydantic-core `
    --copy-metadata tavily-python `
    --copy-metadata httpx `
    --copy-metadata aiohttp `
    --copy-metadata rich `
    --copy-metadata click `
    --copy-metadata knowledge-storm `
    --copy-metadata dspy-ai `
    --copy-metadata litellm `
    --hidden-import webview `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import langgraph `
    --hidden-import langgraph.graph `
    --hidden-import langchain_openai `
    --hidden-import langchain_community `
    --hidden-import langchain_core `
    --hidden-import tavily `
    --hidden-import sklearn `
    --hidden-import sklearn.utils `
    --hidden-import tiktoken `
    --hidden-import tiktoken_ext `
    --hidden-import tiktoken_ext.openai_public `
    --hidden-import dspy `
    --hidden-import dspy.predict `
    --hidden-import dspy.retrieve `
    --hidden-import knowledge_storm `
    --hidden-import knowledge_storm.lm `
    --hidden-import knowledge_storm.rm `
    --hidden-import litellm `
    --hidden-import litellm.utils `
    --exclude-module pandas.tests `
    --exclude-module numpy.tests `
    --exclude-module scipy.tests `
    --exclude-module matplotlib.tests `
    --exclude-module sklearn.tests `
    packaging\windows_launcher.py

# ── Create distributable ZIP ──────────────────────────────────────────────────
$ZipPath = "$DistDir\$AppName-Windows.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath }
Compress-Archive -Path "$DistDir\$AppName" -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "Build complete!"
Write-Host "  Portable folder : $DistDir\$AppName\$AppName.exe"
Write-Host "  Distributable   : $ZipPath"
Write-Host ""
Write-Host "To create a proper installer, install NSIS (nsis.sourceforge.io)"
Write-Host "and run: makensis packaging\installer.nsi"
