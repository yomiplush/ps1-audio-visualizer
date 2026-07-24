"""OpenGL / GPU environment helpers + auto-fix re-exec for SoundOrbit."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GpuInfo:
    vendors: tuple[str, ...]  # AMD, NVIDIA, INTEL, UNKNOWN
    primary: str
    detail: str

    @property
    def label(self) -> str:
        if not self.vendors or self.vendors == ("UNKNOWN",):
            return "GPU: 不明"
        return f"GPU: {', '.join(self.vendors)}"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    p = Path(base) / "sound-orbit"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def detect_gpu() -> GpuInfo:
    found: list[str] = []
    details: list[str] = []

    try:
        out = subprocess.check_output(
            ["lspci"], text=True, stderr=subprocess.DEVNULL, timeout=2.0
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        out = ""

    for line in out.splitlines():
        if not re.search(r"VGA|3D|Display", line, re.I):
            continue
        details.append(line.strip())
        low = line.lower()
        if re.search(r"nvidia|geforce|quadro|\brtx\b|\bgtx\b", low):
            found.append("NVIDIA")
        if re.search(r"amd|ati |radeon|advanced micro devices", low):
            found.append("AMD")
        if re.search(r"intel", low):
            found.append("INTEL")

    try:
        import glob

        for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
            vendor = _read(f"{card}/device/vendor").lower()
            driver_link = os.path.realpath(f"{card}/device/driver")
            driver = os.path.basename(driver_link) if os.path.exists(driver_link) else ""
            if vendor == "0x1002" or driver in ("amdgpu", "radeon"):
                found.append("AMD")
            if vendor == "0x10de" or driver.startswith("nvidia"):
                found.append("NVIDIA")
            if vendor == "0x8086" or driver in ("i915", "xe"):
                found.append("INTEL")
    except OSError:
        pass

    if os.path.exists("/dev/nvidia0"):
        found.append("NVIDIA")

    ordered: list[str] = []
    for v in found:
        if v not in ordered:
            ordered.append(v)
    if not ordered:
        ordered = ["UNKNOWN"]

    if "NVIDIA" in ordered:
        primary = "NVIDIA"
    elif "AMD" in ordered:
        primary = "AMD"
    elif "INTEL" in ordered:
        primary = "INTEL"
    else:
        primary = "UNKNOWN"

    return GpuInfo(
        vendors=tuple(ordered),
        primary=primary,
        detail="; ".join(details[:3]) if details else primary,
    )


def detect_shell() -> str:
    """Return 'fish' | 'bash' | 'zsh' | 'sh' for user-facing command hints."""
    # fish sets this
    if os.environ.get("fish_pid") or os.environ.get("FISH_VERSION"):
        return "fish"
    shell = os.environ.get("SHELL", "")
    base = os.path.basename(shell)
    if base in ("fish", "bash", "zsh", "sh", "dash"):
        return base if base != "dash" else "sh"
    # parent process name
    try:
        ppid = os.getppid()
        comm = Path(f"/proc/{ppid}/comm").read_text(encoding="utf-8").strip()
        if comm in ("fish", "bash", "zsh"):
            return comm
    except OSError:
        pass
    return "bash"


def _cmd_export(shell: str, assignments: list[tuple[str, str]], run: str) -> str:
    if shell == "fish":
        parts = [f"set -x {k} {v}" for k, v in assignments]
        return "; ".join(parts + [run])
    # bash/zsh/sh
    exports = " ".join(f"{k}={v}" for k, v in assignments)
    return f"{exports} {run}"


def gl_mode_sequence(gpu: Optional[GpuInfo] = None) -> list[str]:
    """Ordered auto-fix modes (first success wins)."""
    gpu = gpu or detect_gpu()
    session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if gpu.primary == "NVIDIA":
        if session == "wayland":
            return [
                "nvidia-x11",   # proprietary + X11 (most common fix)
                "x11-clean",    # X11 without forcing vendor
                "nvidia-egl",   # nvidia vendor, leave display
                "default",
                "software",
            ]
        return [
            "nvidia-x11",
            "x11-clean",
            "nvidia-egl",
            "default",
            "software",
        ]
    if gpu.primary in ("AMD", "INTEL"):
        return ["default", "x11-clean", "software"]
    return ["default", "x11-clean", "software"]


def apply_gl_mode(mode: str) -> None:
    """Mutate os.environ for a named GL mode."""
    # Clear auto-managed keys first
    for k in (
        "GDK_BACKEND",
        "__GLX_VENDOR_LIBRARY_NAME",
        "LIBGL_ALWAYS_SOFTWARE",
        "GALLIUM_DRIVER",
        "__EGL_VENDOR_LIBRARY_FILENAMES",
        "GBM_BACKEND",
    ):
        os.environ.pop(k, None)

    mode = (mode or "default").strip().lower()
    os.environ["SOUNDORBIT_GL_MODE"] = mode

    if mode in ("nvidia-x11", "x11", "x11-clean"):
        os.environ["GDK_BACKEND"] = "x11"
    if mode == "nvidia-x11":
        os.environ["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        os.environ["__GL_THREADED_OPTIMIZATIONS"] = "1"
    elif mode == "nvidia-egl":
        os.environ["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        os.environ["__GL_THREADED_OPTIMIZATIONS"] = "1"
        # Prefer explicit EGL vendor file if present
        for candidate in (
            "/usr/share/glvnd/egl_vendor.d/10_nvidia.json",
            "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
        ):
            if os.path.isfile(candidate) and "nvidia" in candidate:
                os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"] = candidate
                break
    elif mode == "wayland":
        os.environ["GDK_BACKEND"] = "wayland"
    elif mode in ("software", "llvmpipe"):
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
        os.environ["GALLIUM_DRIVER"] = "llvmpipe"
        os.environ["GDK_BACKEND"] = os.environ.get("GDK_BACKEND") or "x11"
    elif mode == "default":
        pass

    # Never leave a stale nvidia vendor when not in nvidia-* modes
    if not mode.startswith("nvidia") and mode != "default":
        os.environ.pop("__GLX_VENDOR_LIBRARY_NAME", None)


def apply_runtime_gl_env(gpu: Optional[GpuInfo] = None) -> None:
    """
    Apply saved successful mode, or SOUNDORBIT_GL / SOUNDORBIT_GL_MODE.
    Does NOT force nvidia vendor by default (that breaks many setups).
    """
    gpu = gpu or detect_gpu()
    explicit = (
        os.environ.get("SOUNDORBIT_GL_MODE")
        or os.environ.get("SOUNDORBIT_GL")
        or ""
    ).strip().lower()
    if explicit and explicit not in ("auto", ""):
        apply_gl_mode(explicit)
        return

    success_path = data_dir() / "gl_mode.ok"
    if success_path.is_file():
        try:
            saved = success_path.read_text(encoding="utf-8").strip()
            if saved:
                apply_gl_mode(saved)
                return
        except OSError:
            pass

    # Soft defaults only — no forced __GLX_VENDOR_LIBRARY_NAME
    if gpu.primary == "NVIDIA":
        os.environ.setdefault("__GL_THREADED_OPTIMIZATIONS", "1")
        session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
        if session == "wayland" and not os.environ.get("GDK_BACKEND"):
            # Most reliable first guess for NVIDIA+Wayland
            os.environ["GDK_BACKEND"] = "x11"
            os.environ["SOUNDORBIT_GL_MODE"] = "x11-clean"


def mark_gl_success() -> None:
    mode = os.environ.get("SOUNDORBIT_GL_MODE") or "default"
    try:
        (data_dir() / "gl_mode.ok").write_text(mode + "\n", encoding="utf-8")
        (data_dir() / "gl_attempt").unlink(missing_ok=True)
    except OSError:
        pass


def _attempt_index() -> int:
    try:
        return int((data_dir() / "gl_attempt").read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _set_attempt_index(i: int) -> None:
    try:
        (data_dir() / "gl_attempt").write_text(str(i) + "\n", encoding="utf-8")
    except OSError:
        pass


def next_autofix_mode(gpu: Optional[GpuInfo] = None) -> Optional[str]:
    """Return next GL mode to try, or None if exhausted."""
    gpu = gpu or detect_gpu()
    modes = gl_mode_sequence(gpu)
    # Skip modes already forced if current mode is in list
    current = (os.environ.get("SOUNDORBIT_GL_MODE") or "default").strip().lower()
    idx = _attempt_index()
    # Advance past current if present
    if idx == 0 and current in modes:
        try:
            idx = modes.index(current) + 1
        except ValueError:
            idx = 0
    if idx >= len(modes):
        return None
    mode = modes[idx]
    _set_attempt_index(idx + 1)
    return mode


def reexec_with_gl_mode(mode: str) -> None:
    """Replace current process with same launcher + new GL mode env."""
    env = os.environ.copy()
    # Clear managed keys then set mode (mirror apply_gl_mode without touching os.environ forever)
    for k in (
        "GDK_BACKEND",
        "__GLX_VENDOR_LIBRARY_NAME",
        "LIBGL_ALWAYS_SOFTWARE",
        "GALLIUM_DRIVER",
        "__EGL_VENDOR_LIBRARY_FILENAMES",
        "GBM_BACKEND",
    ):
        env.pop(k, None)

    m = (mode or "default").strip().lower()
    env["SOUNDORBIT_GL_MODE"] = m
    env["SOUNDORBIT_GL_AUTOFIX"] = "1"
    if m in ("nvidia-x11", "x11", "x11-clean"):
        env["GDK_BACKEND"] = "x11"
    if m == "nvidia-x11":
        env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        env["__GL_THREADED_OPTIMIZATIONS"] = "1"
    elif m == "nvidia-egl":
        env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        env["__GL_THREADED_OPTIMIZATIONS"] = "1"
    elif m == "wayland":
        env["GDK_BACKEND"] = "wayland"
    elif m in ("software", "llvmpipe"):
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        env["GALLIUM_DRIVER"] = "llvmpipe"
        env["GDK_BACKEND"] = env.get("GDK_BACKEND") or "x11"

    print(f"==> SoundOrbit auto-fix: re-launch mode={mode}", file=sys.stderr)

    appimage = env.get("APPIMAGE")
    if appimage and os.path.isfile(appimage):
        os.execve(appimage, [appimage], env)

    argv0 = os.path.abspath(sys.argv[0]) if sys.argv else ""
    if argv0 and os.path.isfile(argv0) and os.access(argv0, os.X_OK):
        os.execve(argv0, [argv0, *sys.argv[1:]], env)

    os.execve(sys.executable, [sys.executable, *sys.argv], env)


def try_gl_autofix(gpu: Optional[GpuInfo] = None) -> bool:
    """
    If another GL mode remains, re-exec into it (does not return on success path).
    Returns False if no more modes (caller should show final error UI).
    """
    if os.environ.get("SOUNDORBIT_GL_NO_AUTOFIX") == "1":
        return False
    mode = next_autofix_mode(gpu)
    if not mode:
        return False
    reexec_with_gl_mode(mode)
    return True  # unreachable if exec works


def _app_launch_path() -> str:
    """Best path to re-run: AppImage path, else ./SoundOrbit-*.AppImage."""
    appimage = os.environ.get("APPIMAGE") or ""
    if appimage and os.path.isfile(appimage):
        return appimage
    # Menu launcher
    local = os.path.expanduser("~/.local/bin/sound-orbit")
    if os.path.isfile(local):
        return local
    return "./SoundOrbit-*.AppImage"


def _sh_quote(path: str) -> str:
    if not path or any(c in path for c in " \t'\"$`\\*?"):
        return "'" + path.replace("'", "'\"'\"'") + "'"
    return path


def clipboard_fix_commands(gpu: Optional[GpuInfo] = None, *, soft: bool = False) -> str:
    """
    Single paste-ready block for the user's shell (fish or bash/zsh).
    No comments that break paste — only executable lines.
    """
    gpu = gpu or detect_gpu()
    shell = detect_shell()
    run = _sh_quote(_app_launch_path())
    lines: list[str] = []

    # packages first (one line)
    if command_exists_pacman():
        pkgs = [
            "gtk4",
            "libadwaita",
            "python-gobject",
            "python-opengl",
            "mesa",
            "libepoxy",
            "libglvnd",
            "pipewire-pulse",
        ]
        if "NVIDIA" in gpu.vendors:
            pkgs += ["nvidia-utils", "egl-wayland"]
        if "AMD" in gpu.vendors:
            pkgs += ["vulkan-radeon", "mesa-utils"]
        if "INTEL" in gpu.vendors:
            pkgs += ["vulkan-intel", "intel-media-driver"]
        # unique preserve order
        upkgs: list[str] = []
        for p in pkgs:
            if p not in upkgs:
                upkgs.append(p)
        lines.append("sudo pacman -S --needed " + " ".join(upkgs))

    if shell == "fish":
        if soft:
            lines.append(f"set -x LIBGL_ALWAYS_SOFTWARE 1; set -x GALLIUM_DRIVER llvmpipe; set -x GDK_BACKEND x11; {run}")
        elif "NVIDIA" in gpu.vendors:
            lines.append(f"set -x GDK_BACKEND x11; set -x __GLX_VENDOR_LIBRARY_NAME nvidia; {run}")
        else:
            lines.append(f"set -x GDK_BACKEND x11; {run}")
    else:
        if soft:
            lines.append(f"LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe GDK_BACKEND=x11 {run}")
        elif "NVIDIA" in gpu.vendors:
            lines.append(f"GDK_BACKEND=x11 __GLX_VENDOR_LIBRARY_NAME=nvidia {run}")
        else:
            lines.append(f"GDK_BACKEND=x11 {run}")

    return "\n".join(lines) + "\n"


def command_exists_pacman() -> bool:
    from shutil import which

    return which("pacman") is not None


def gl_failure_hints(gpu: Optional[GpuInfo] = None) -> str:
    """Shell-aware recovery tips (fish vs bash). Prefer auto-fix first."""
    gpu = gpu or detect_gpu()
    shell = detect_shell()
    cmd = clipboard_fix_commands(gpu, soft=False).rstrip()
    soft = clipboard_fix_commands(gpu, soft=True).rstrip()

    lines = [
        "OpenGL コンテキストを作成できませんでした。",
        f"{gpu.label}  ·  {gpu.detail[:80]}",
        f"検出シェル: {shell}",
        "",
        "【ターミナルにコピーして貼り付け → Enter】",
        "",
        "■ 推奨（そのまま1ブロック貼り付け）:",
        cmd,
        "",
        "■ まだダメならソフトウェア描画:",
        soft,
        "",
    ]
    return "\n".join(lines)
