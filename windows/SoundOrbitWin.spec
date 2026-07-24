# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SoundOrbit Windows
# Bundles glfw3.dll / PortAudio so the onefile exe works without system GLFW.
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_all

block_cipher = None
root = Path(SPECPATH)

# Collect native libs shipped by pip packages
binaries = []
datas = []
hiddenimports = [
    "numpy",
    "OpenGL",
    "OpenGL.GL",
    "OpenGL.platform",
    "OpenGL.platform.win32",
    "OpenGL.GL.shaders",
    "glfw",
    "sounddevice",
    "sound_orbit_win",
    "sound_orbit_win.app",
    "sound_orbit_win.audio",
    "sound_orbit_win.renderer",
    "sound_orbit_win.math3d",
    "cffi",
    "_cffi_backend",
]

# glfw ships glfw3.dll under site-packages/glfw/
try:
    binaries += collect_dynamic_libs("glfw")
    datas += collect_data_files("glfw")
except Exception as exc:
    print("warn: collect glfw libs:", exc)

try:
    binaries += collect_dynamic_libs("sounddevice")
    datas += collect_data_files("sounddevice")
except Exception as exc:
    print("warn: collect sounddevice libs:", exc)

# Fallback: walk package dirs for *.dll
def _add_dlls_from_package(pkg_name: str) -> None:
    try:
        mod = __import__(pkg_name)
        base = Path(mod.__file__).resolve().parent
        for dll in base.rglob("*.dll"):
            # (src, dest_dir_relative_to_bundle_root)
            rel_parent = str(dll.parent.relative_to(base.parent)) if base.parent in dll.parents else pkg_name
            binaries.append((str(dll), rel_parent.replace("\\", "/")))
            # also put next to exe root for glfw loader
            binaries.append((str(dll), "."))
    except Exception as exc:
        print(f"warn: scan {pkg_name} dlls:", exc)

_add_dlls_from_package("glfw")
_add_dlls_from_package("sounddevice")

# Deduplicate by basename+dest
seen = set()
uniq = []
for src, dest in binaries:
    key = (Path(src).name, dest)
    if key in seen:
        continue
    seen.add(key)
    uniq.append((src, dest))
binaries = uniq

a = Analysis(
    [str(root / "run_soundorbit.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(root / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(root / "hooks" / "rthook_glfw_path.py")],
    excludes=["tkinter", "matplotlib", "gi", "cairo", "PyQt5", "PySide6"],
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
    # UPX sometimes breaks DLL loading on Windows — keep off
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
