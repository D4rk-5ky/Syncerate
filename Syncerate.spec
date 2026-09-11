# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build definition for Syncerate."""

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = sorted(
    set(
        collect_submodules("pexpect")
        + collect_submodules("paho.mqtt")
    )
)

analysis = Analysis(
    ["Syncerate.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Syncerate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
