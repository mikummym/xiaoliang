# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 整个 assets 目录随包收入，sounds/poke 下的 wav 音效随之进 bundle（main.py 走 assets_dir()/"sounds"/"poke"）。
    datas=[('assets', 'assets')],
    # sound.py 里 QtMultimedia / QtTextToSpeech 为惰性 import，PyInstaller 静态分析可能漏收，此处显式列出保打包不缺插件。
    hiddenimports=['PySide6.QtMultimedia', 'PySide6.QtTextToSpeech'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# onefile 形态：binaries 与 datas 并入 EXE，不再走 COLLECT，分发为单一 dist\xiaoliang.exe。
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='xiaoliang',
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
