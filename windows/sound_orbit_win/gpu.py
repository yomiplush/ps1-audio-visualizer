"""Windows GPU detection + vendor-specific quality / driver hints."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GpuAdapter:
    name: str
    vendor: str  # NVIDIA | AMD | INTEL | UNKNOWN
    is_integrated: bool


@dataclass
class GpuProfile:
    """Runtime knobs chosen from detected GPUs."""

    primary: str
    adapters: list[GpuAdapter] = field(default_factory=list)
    detail: str = ""
    is_integrated: bool = False
    # Render quality
    internal_w: int = 240
    internal_h: int = 180
    particle_count: int = 400
    particle_emit_scale: float = 0.55
    trail_decay: float = 0.78
    trail_scene_gain: float = 0.28
    trail_mix: float = 0.32
    crt_barrel: float = 0.09
    crt_scanline: float = 0.92
    crt_vignette: float = 0.42
    exposure: float = 0.88
    vsync: bool = True
    note: str = ""


def _classify_name(name: str) -> tuple[str, bool]:
    low = name.lower()
    # NVIDIA discrete first
    if re.search(r"nvidia|geforce|rtx|gtx|quadro|tesla", low):
        return "NVIDIA", False
    # AMD
    if re.search(r"amd|radeon|rx \d|ati ", low):
        # APU names often include "Graphics" without RX
        igpu = bool(re.search(r"graphics|vega \d|ryzen|athlon|radeon\(tm\) graphics", low)) and not re.search(
            r"\brx\b|radeon pro|radeon vii|xt\b", low
        )
        return "AMD", igpu
    # Intel
    if re.search(r"intel", low):
        igpu = bool(re.search(r"uhd|hd graphics|iris|xe graphics|arc", low))
        # Arc is discrete-ish but still treat as capable
        if re.search(r"\barc\b", low):
            return "INTEL", False
        return "INTEL", True
    return "UNKNOWN", True


def _query_wmi_names() -> list[str]:
    names: list[str] = []
    # PowerShell CIM (Windows 10/11)
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -ExpandProperty Name"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in out.splitlines():
            s = line.strip()
            if s:
                names.append(s)
        if names:
            return names
    except Exception:
        pass

    # Fallback WMIC (deprecated but still present on many systems)
    try:
        out = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in out.splitlines():
            s = line.strip()
            if not s or s.lower() == "name":
                continue
            names.append(s)
    except Exception:
        pass
    return names


def detect_adapters() -> list[GpuAdapter]:
    override = (os.environ.get("SOUNDORBIT_GPU") or "").strip().upper()
    names = _query_wmi_names()
    adapters: list[GpuAdapter] = []
    for name in names:
        vendor, igpu = _classify_name(name)
        if override in ("NVIDIA", "AMD", "INTEL") and vendor != override:
            # still list all; primary selection uses override later
            pass
        adapters.append(GpuAdapter(name=name, vendor=vendor, is_integrated=igpu))
    if not adapters:
        adapters.append(GpuAdapter(name="unknown", vendor="UNKNOWN", is_integrated=True))
    return adapters


def pick_primary(adapters: list[GpuAdapter]) -> GpuAdapter:
    override = (os.environ.get("SOUNDORBIT_GPU") or "auto").strip().upper()
    if override in ("NVIDIA", "AMD", "INTEL"):
        for a in adapters:
            if a.vendor == override:
                return a

    # Prefer discrete: NVIDIA > AMD dGPU > Intel Arc > AMD iGPU > Intel iGPU
    def score(a: GpuAdapter) -> int:
        s = 0
        if a.vendor == "NVIDIA":
            s += 100
        elif a.vendor == "AMD":
            s += 80 if not a.is_integrated else 40
        elif a.vendor == "INTEL":
            s += 70 if not a.is_integrated else 20
        if not a.is_integrated:
            s += 10
        return s

    return max(adapters, key=score)


def build_profile(adapters: Optional[list[GpuAdapter]] = None) -> GpuProfile:
    adapters = adapters or detect_adapters()
    primary = pick_primary(adapters)
    names = ", ".join(a.name for a in adapters)

    # Defaults (balanced)
    p = GpuProfile(
        primary=primary.vendor,
        adapters=list(adapters),
        detail=names,
        is_integrated=primary.is_integrated,
        note=f"primary={primary.vendor} ({primary.name})",
    )

    if primary.vendor == "NVIDIA":
        # Discrete NVIDIA: higher quality, full effects
        if not primary.is_integrated:
            p.internal_w, p.internal_h = 320, 240
            p.particle_count = 520
            p.particle_emit_scale = 0.70
            p.trail_mix = 0.36
            p.trail_decay = 0.80
            p.note += " | NVIDIA dGPU profile"
        else:
            p.note += " | NVIDIA profile"
        # Driver hints (harmless on pure NVIDIA desktops)
        os.environ.setdefault("__GL_THREADED_OPTIMIZATIONS", "1")
        os.environ.setdefault("__GL_SHADER_DISK_CACHE", "1")

    elif primary.vendor == "AMD":
        if primary.is_integrated:
            # Ryzen iGPU / Vega graphics — keep ECO-ish
            p.internal_w, p.internal_h = 240, 180
            p.particle_count = 320
            p.particle_emit_scale = 0.45
            p.trail_mix = 0.28
            p.crt_scanline = 0.85
            p.note += " | AMD iGPU / APU profile (ECO)"
        else:
            p.internal_w, p.internal_h = 320, 240
            p.particle_count = 480
            p.particle_emit_scale = 0.65
            p.trail_mix = 0.34
            p.note += " | AMD dGPU profile"

    elif primary.vendor == "INTEL":
        if primary.is_integrated:
            # HD / UHD / Iris — lighter load (user had HD 620)
            p.internal_w, p.internal_h = 200, 150
            p.particle_count = 220
            p.particle_emit_scale = 0.32
            p.trail_mix = 0.22
            p.trail_decay = 0.72
            p.crt_scanline = 0.80
            p.crt_barrel = 0.07
            p.exposure = 0.90
            p.note += " | Intel iGPU profile (ECO)"
        else:
            # Arc
            p.internal_w, p.internal_h = 288, 216
            p.particle_count = 420
            p.particle_emit_scale = 0.55
            p.note += " | Intel Arc profile"
    else:
        p.note += " | generic profile"

    # Hybrid warning string
    vendors = {a.vendor for a in adapters if a.vendor != "UNKNOWN"}
    if len(vendors) > 1:
        p.note += f" | hybrid {sorted(vendors)}"
        # Prefer high-performance GPU request flags via env for child processes / drivers
        if "NVIDIA" in vendors:
            os.environ.setdefault("SHIM_MCCOMPAT", "0x800000001")  # best-effort; may be ignored
        p.note += " (Windows may still pick iGPU; set Graphics Settings → High performance if needed)"

    # Manual quality override
    q = (os.environ.get("SOUNDORBIT_QUALITY") or "").strip().lower()
    if q == "low":
        p.internal_w, p.internal_h = 160, 120
        p.particle_count = 120
        p.particle_emit_scale = 0.22
        p.trail_mix = 0.15
    elif q == "high":
        p.internal_w, p.internal_h = 320, 240
        p.particle_count = max(p.particle_count, 500)
        p.particle_emit_scale = max(p.particle_emit_scale, 0.7)
    elif q == "ultra":
        p.internal_w, p.internal_h = 400, 300
        p.particle_count = 650
        p.particle_emit_scale = 0.85
        p.trail_mix = 0.40

    return p


def apply_windows_gpu_env(profile: GpuProfile) -> None:
    """
    Best-effort env before creating the GL context.
    True Optimus export symbols need a native DLL; env alone is partial.
    """
    if profile.primary == "NVIDIA":
        # Encourage high-performance path on hybrid laptops when driver honors it
        os.environ.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")  # ignored on pure Win often
        os.environ.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")  # mainly Linux; harmless if unused
    elif profile.primary == "AMD":
        os.environ.setdefault("AMD_ADAPTER_INDEX", "0")
    # Intel: no special env required


def describe_profile(profile: GpuProfile) -> str:
    lines = [
        f"GPU primary: {profile.primary}",
        f"Adapters: {profile.detail}",
        f"Profile: {profile.note}",
        f"Internal: {profile.internal_w}x{profile.internal_h}  particles={profile.particle_count}",
    ]
    return "\n".join(lines)
