"""OpenGL / GPU environment helpers for SoundOrbit."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
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

    # DRM
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

    # unique
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


def gl_failure_hints(gpu: Optional[GpuInfo] = None) -> str:
    """Human-readable recovery tips after GL context failure."""
    gpu = gpu or detect_gpu()
    lines = [
        "OpenGL コンテキストを作成できませんでした。",
        f"{gpu.label}  ·  {gpu.detail[:80]}",
        "",
        "試す順:",
        "  1) GDK_BACKEND=x11 ./SoundOrbit-*.AppImage",
        "  2) LIBGL_ALWAYS_SOFTWARE=1 ./SoundOrbit-*.AppImage  (遅いが確実)",
        "  3) 下の GPU 向けパッケージを入れる",
        "",
    ]
    if "AMD" in gpu.vendors:
        lines += [
            "AMD:",
            "  sudo pacman -S --needed mesa libepoxy libglvnd vulkan-radeon mesa-utils",
            "",
        ]
    if "NVIDIA" in gpu.vendors:
        lines += [
            "NVIDIA:",
            "  · プロプライエタリ: カーネルと同世代の nvidia / nvidia-utils",
            "  · Wayland: egl-wayland libglvnd",
            "  · sudo pacman -S --needed nvidia-utils egl-wayland libglvnd libepoxy",
            "  · ハイブリッドは PRIME 設定を確認",
            "",
        ]
    if "INTEL" in gpu.vendors:
        lines += [
            "Intel (UHD / Iris / Arc):",
            "  sudo pacman -S --needed mesa libepoxy libglvnd vulkan-intel intel-media-driver",
            "",
        ]
    if gpu.primary == "UNKNOWN":
        lines += [
            "共通:",
            "  sudo pacman -S --needed mesa libepoxy libglvnd gtk4",
            "",
        ]
    return "\n".join(lines)


def apply_runtime_gl_env(gpu: Optional[GpuInfo] = None) -> None:
    """
    Soft defaults only when user has not set overrides.
    Does not force NVIDIA GBM (that breaks some setups).
    """
    gpu = gpu or detect_gpu()
    # Prefer not to clobber explicit user env
    if gpu.primary == "NVIDIA":
        os.environ.setdefault("__GL_THREADED_OPTIMIZATIONS", "1")
        # Help GLVND pick nvidia when both mesa and nvidia exist
        if os.path.exists("/dev/nvidia0"):
            os.environ.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
    elif gpu.primary in ("AMD", "INTEL"):
        # Clear accidental software override leftovers? No — respect user.
        pass
