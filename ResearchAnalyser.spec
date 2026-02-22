# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import copy_metadata

datas = [('app.py', '.'), ('config.yaml', '.'), ('monkeyocr.py', '.'), ('research_analyser', 'research_analyser')]
binaries = []
hiddenimports = ['langgraph', 'langgraph.graph', 'langchain_openai', 'langchain_community', 'langchain_core', 'tavily', 'sklearn', 'sklearn.utils', 'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public']
datas += collect_data_files('pandas')
datas += copy_metadata('pandas')
datas += copy_metadata('pydantic')
datas += copy_metadata('pydantic-settings')
datas += copy_metadata('pydantic-core')
datas += copy_metadata('tavily-python')
datas += copy_metadata('httpx')
datas += copy_metadata('aiohttp')
datas += copy_metadata('rich')
datas += copy_metadata('click')
tmp_ret = collect_all('streamlit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('altair')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydeck')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('langgraph')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('langchain')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('langchain_openai')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('langchain_community')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('langchain_core')
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
    excludes=['pandas.tests', 'numpy.tests', 'scipy.tests', 'matplotlib.tests', 'sklearn.tests'],
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
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ResearchAnalyser',
)
app = BUNDLE(
    coll,
    name='ResearchAnalyser.app',
    icon=None,
    bundle_identifier='com.research.analyser',
)
