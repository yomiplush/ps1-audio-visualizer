"""
Runtime hook: ensure glfw3.dll / portaudio can be found inside PyInstaller onefile.
Must run before `import glfw`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepend_path(p: Path) -> None:
    if not p.is_dir():
        return
    s = str(p)
    # Windows DLL search
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(s)
        except OSError:
            pass
    os.environ["PATH"] = s + os.pathsep + os.environ.get("PATH", "")


# PyInstaller extracts to sys._MEIPASS
meipass = getattr(sys, "_MEIPASS", None)
if meipass:
    root = Path(meipass)
    _prepend_path(root)
    for sub in ("glfw", "sounddevice", "pyarrow", "_sounddevice_data", "glfw.libs"):
        _prepend_path(root / sub)
    # any nested glfw folders
    try:
        for d in root.rglob("glfw*"):
            if d.is_dir():
                _prepend_path(d)
    except OSError:
        pass
