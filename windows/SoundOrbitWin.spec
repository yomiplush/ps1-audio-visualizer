# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SoundOrbit Windows
import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "run_soundorbit.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "numpy",
        "OpenGL",
        "OpenGL.GL",
        "OpenGL.platform.win32",
        "glfw",
        "sounddevice",
        "sound_orbit_win",
        "sound_orbit_win.app",
        "sound_orbit_win.audio",
        "sound_orbit_win.renderer",
        "sound_orbit_win.math3d",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "gi", "cairo"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SoundOrbit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # show console for audio/GL diagnostics; set False for pure GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
