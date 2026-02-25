# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('app.py', '.'), ('config.yaml', '.'), ('monkeyocr.py', '.'), ('research_analyser', 'research_analyser'), ('.streamlit', '.streamlit'), ('packaging/python312.tar.gz', '.'), ('packaging/beautiful_mermaid/render.bundle.mjs', 'packaging/beautiful_mermaid')]
binaries = []
hiddenimports = ['webview', 'webview.platforms.cocoa']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['packaging/macos_launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ResearchAnalyser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['packaging/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='ResearchAnalyser',
)
app = BUNDLE(
    coll,
    name='ResearchAnalyser.app',
    icon='packaging/icon.icns',
    bundle_identifier='com.research.analyser',
)
