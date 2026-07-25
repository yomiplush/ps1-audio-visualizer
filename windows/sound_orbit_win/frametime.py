"""PS1-style frame timing (Windows) — low hard-capped FPS."""

from __future__ import annotations

import os
from typing import Optional

PS1_FPS_DEFAULT = 18
PS1_FPS_MIN = 12
PS1_FPS_MAX = 24


def ps1_lock_enabled() -> bool:
    v = (os.environ.get("SOUNDORBIT_PS1_FPS") or "1").strip().lower()
    return v not in ("0", "off", "false", "no")


def ps1_target_fps(quality_fps: Optional[float] = None) -> int:
    raw = (os.environ.get("SOUNDORBIT_FPS") or "").strip()
    if raw:
        try:
            return int(max(10, min(30, float(raw))))
        except ValueError:
            pass

    q = int(quality_fps) if quality_fps is not None else PS1_FPS_DEFAULT
    if not ps1_lock_enabled():
        return max(PS1_FPS_MIN, min(60, q))

    capped = min(q, PS1_FPS_MAX)
    if capped >= 30:
        capped = 20
    elif capped >= 24:
        capped = 18
    elif capped >= 20:
        capped = 18
    else:
        capped = max(PS1_FPS_MIN, min(capped, 16))
    return int(max(PS1_FPS_MIN, min(PS1_FPS_MAX, capped)))


def fixed_dt(fps: float) -> float:
    return 1.0 / max(PS1_FPS_MIN, float(fps))
