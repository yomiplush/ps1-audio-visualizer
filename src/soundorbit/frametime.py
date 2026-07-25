"""PS1-style frame timing — low, hard-capped FPS for chunky polygon motion.

PlayStation 1 titles were typically 30fps (NTSC) or dropped toward 15–20
under load, with no motion interpolation. We lock intentionally low so the
visualizer feels stepped / jagged rather than smooth 60fps.
"""

from __future__ import annotations

import os
from typing import Optional

# Default lock: slightly under 30 so motion reads as "old console"
PS1_FPS_DEFAULT = 18
PS1_FPS_MIN = 12
PS1_FPS_MAX = 24  # never allow silky-smooth rates by default


def ps1_lock_enabled() -> bool:
    """SOUNDORBIT_PS1_FPS=0 disables the PS1 lock (use quality FPS as-is, still capped)."""
    v = (os.environ.get("SOUNDORBIT_PS1_FPS") or "1").strip().lower()
    return v not in ("0", "off", "false", "no")


def ps1_target_fps(quality_fps: Optional[float] = None) -> int:
    """
    Resolve the locked target FPS.

    Priority:
      1. SOUNDORBIT_FPS=<n>  (explicit, 10–30)
      2. PS1 lock on → min(quality, 24) then bias toward ~18
      3. quality target only
    """
    raw = (os.environ.get("SOUNDORBIT_FPS") or "").strip()
    if raw:
        try:
            return int(max(10, min(30, float(raw))))
        except ValueError:
            pass

    q = int(quality_fps) if quality_fps is not None else PS1_FPS_DEFAULT
    if not ps1_lock_enabled():
        return max(PS1_FPS_MIN, min(60, q))

    # PS1 lock: quality can only go so high; default sits around 18
    capped = min(q, PS1_FPS_MAX)
    # Pull high profiles down a bit (30/36 → 20/24 feel)
    if capped >= 30:
        capped = 20
    elif capped >= 24:
        capped = 18
    elif capped >= 20:
        capped = 18
    else:
        capped = max(PS1_FPS_MIN, min(capped, 16))
    return int(max(PS1_FPS_MIN, min(PS1_FPS_MAX, capped)))


def interval_ms_for_fps(fps: float) -> int:
    fps = max(PS1_FPS_MIN, float(fps))
    return max(int(round(1000.0 / fps)), int(round(1000.0 / PS1_FPS_MAX)))


def fixed_dt(fps: float) -> float:
    """Fixed simulation step (seconds) — stepped animation, no sub-frame blend."""
    return 1.0 / max(PS1_FPS_MIN, float(fps))
