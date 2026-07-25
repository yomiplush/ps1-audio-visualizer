"""Windows resource guardian — CPU / RAM / GPU load control + leak brake.

User-mode apps cannot cause a true BSOD by themselves, but runaway
allocations, driver thrashing, and busy-loops can freeze the desktop or
trip bad GPU drivers. This module:

* monitors process Working Set + system free RAM
* detects sustained memory growth (leak-like)
* throttles FPS / particles / trails before RAM explodes
* lowers process priority under pressure (less CPU contention)
* never busy-spins the main loop
"""

from __future__ import annotations

import gc
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple


# ---------------------------------------------------------------------------
# Windows memory / CPU sampling (ctypes only — no psutil dependency)
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _read_rss_mb() -> float:
    """Process working set (approx RSS) in MiB."""
    if _is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.WinDLL("psapi")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GetCurrentProcess = kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE
            GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
            GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            GetProcessMemoryInfo.restype = wintypes.BOOL

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return float(counters.WorkingSetSize) / (1024.0 * 1024.0)
        except Exception:
            pass
        return 0.0

    # Linux fallback for local testing
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _read_mem_available_mb() -> float:
    if _is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            GlobalMemoryStatusEx = kernel32.GlobalMemoryStatusEx
            GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
            GlobalMemoryStatusEx.restype = wintypes.BOOL
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if GlobalMemoryStatusEx(ctypes.byref(st)):
                return float(st.ullAvailPhys) / (1024.0 * 1024.0)
        except Exception:
            pass
        return 4096.0

    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 4096.0


def _read_mem_load_percent() -> float:
    """0–100 system memory load (Windows) or estimated."""
    if _is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return float(st.dwMemoryLoad)
        except Exception:
            pass
    avail = _read_mem_available_mb()
    # crude estimate
    return max(0.0, min(100.0, 100.0 - (avail / 80.0)))


def set_process_priority_below_normal() -> bool:
    """Lower scheduling priority — reduces CPU contention / heat."""
    if not _is_windows():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        handle = kernel32.GetCurrentProcess()
        return bool(kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS))
    except Exception:
        return False


def set_process_priority_normal() -> bool:
    if not _is_windows():
        return False
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        NORMAL_PRIORITY_CLASS = 0x00000020
        return bool(kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), NORMAL_PRIORITY_CLASS))
    except Exception:
        return False


def trim_working_set() -> None:
    """Ask Windows to release unused pages (best-effort, not a leak fix)."""
    if not _is_windows():
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # EmptyWorkingSet via psapi
        psapi = ctypes.WinDLL("psapi")
        EmptyWorkingSet = getattr(psapi, "EmptyWorkingSet", None)
        if EmptyWorkingSet is not None:
            EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            EmptyWorkingSet.restype = wintypes.BOOL
            EmptyWorkingSet(kernel32.GetCurrentProcess())
            return
        # Fallback: SetProcessWorkingSetSize(-1, -1)
        SetProcessWorkingSetSize = kernel32.SetProcessWorkingSetSize
        SetProcessWorkingSetSize.argtypes = [
            wintypes.HANDLE,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass


def eco_bias_enabled() -> bool:
    v = (os.environ.get("SOUNDORBIT_ECO") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


# ---------------------------------------------------------------------------
# Guardian
# ---------------------------------------------------------------------------

@dataclass
class ResourceState:
    rss_mb: float = 0.0
    baseline_rss_mb: float = 0.0
    soft_limit_mb: float = 0.0
    hard_limit_mb: float = 0.0
    avail_mb: float = 0.0
    mem_load_pct: float = 0.0
    throttle: float = 1.0  # 1.0 normal → 0.35 hard
    trails_allowed: bool = True
    labels_allowed: bool = True
    param_update_scale: float = 1.0
    target_fps: float = 30.0
    last_purge_ago: float = 999.0
    purge_count: int = 0
    leak_suspect: bool = False
    level: str = "OK"  # OK | SOFT | HARD | EMERGENCY
    note: str = ""


class ResourceGuardian:
    """
    Watches RAM growth and system pressure; returns throttle knobs.

    Levels:
      OK         — full features (eco-biased FPS cap)
      SOFT       — cut particles / param rate / FPS
      HARD       — trails off, labels thin, low FPS, priority down
      EMERGENCY  — absolute RAM brake (aggressive purge + min FPS)
    """

    def __init__(
        self,
        *,
        check_interval: float = 0.75,
        soft_delta_mb: float = 140.0,
        hard_delta_mb: float = 240.0,
        # Absolute ceilings (PyInstaller onefile + numpy ~150–250MB baseline)
        soft_abs_mb: float = 520.0,
        hard_abs_mb: float = 680.0,
        emergency_abs_mb: float = 820.0,
        min_purge_interval: float = 6.0,
        base_fps: float = 30.0,
        eco: Optional[bool] = None,
    ) -> None:
        self.check_interval = check_interval
        self.soft_delta_mb = soft_delta_mb
        self.hard_delta_mb = hard_delta_mb
        self.soft_abs_mb = soft_abs_mb
        self.hard_abs_mb = hard_abs_mb
        self.emergency_abs_mb = emergency_abs_mb
        self.min_purge_interval = min_purge_interval
        self.base_fps = float(base_fps)
        self.eco = eco_bias_enabled() if eco is None else bool(eco)

        self._baseline = 0.0
        self._last_check = 0.0
        self._last_purge = 0.0
        self._purge_count = 0
        self._throttle = 0.85 if self.eco else 1.0
        self._trails = True
        self._labels = True
        self._param_scale = 1.0
        self._target_fps = 24.0 if self.eco else self.base_fps
        self._level = "OK"
        self._note = "init"
        self._armed = False
        self._leak_suspect = False
        self._priority_low = False
        # (t, rss) samples for growth detection
        self._rss_hist: Deque[Tuple[float, float]] = deque(maxlen=40)
        # consecutive growth ticks
        self._growth_streak = 0

        # env overrides
        try:
            if os.environ.get("SOUNDORBIT_MEM_SOFT"):
                self.soft_abs_mb = float(os.environ["SOUNDORBIT_MEM_SOFT"])
            if os.environ.get("SOUNDORBIT_MEM_HARD"):
                self.hard_abs_mb = float(os.environ["SOUNDORBIT_MEM_HARD"])
            if os.environ.get("SOUNDORBIT_FPS"):
                self.base_fps = float(os.environ["SOUNDORBIT_FPS"])
                self._target_fps = self.base_fps
        except ValueError:
            pass

    def arm(self) -> None:
        rss = _read_rss_mb()
        # Floor baseline so soft limits aren't absurdly low
        self._baseline = max(rss, 120.0)
        self._last_check = time.monotonic()
        self._armed = True
        self._rss_hist.clear()
        self._rss_hist.append((self._last_check, rss))
        self._note = f"baseline {self._baseline:.0f}MB eco={int(self.eco)}"
        if self.eco:
            set_process_priority_below_normal()
            self._priority_low = True

    def state(self) -> ResourceState:
        now = time.monotonic()
        return ResourceState(
            rss_mb=_read_rss_mb(),
            baseline_rss_mb=self._baseline,
            soft_limit_mb=min(self._baseline + self.soft_delta_mb, self.soft_abs_mb),
            hard_limit_mb=min(self._baseline + self.hard_delta_mb, self.hard_abs_mb),
            avail_mb=_read_mem_available_mb(),
            mem_load_pct=_read_mem_load_percent(),
            throttle=self._throttle,
            trails_allowed=self._trails,
            labels_allowed=self._labels,
            param_update_scale=self._param_scale,
            target_fps=self._target_fps,
            last_purge_ago=now - self._last_purge if self._last_purge else 999.0,
            purge_count=self._purge_count,
            leak_suspect=self._leak_suspect,
            level=self._level,
            note=self._note,
        )

    def _growth_mb_per_min(self) -> float:
        if len(self._rss_hist) < 4:
            return 0.0
        t0, r0 = self._rss_hist[0]
        t1, r1 = self._rss_hist[-1]
        dt = max(1e-3, t1 - t0)
        return (r1 - r0) * (60.0 / dt)

    def tick(self) -> tuple[bool, ResourceState]:
        """Returns (need_purge, state). Call from main loop."""
        now = time.monotonic()
        if not self._armed:
            self.arm()
        if now - self._last_check < self.check_interval:
            return False, self.state()
        self._last_check = now

        rss = _read_rss_mb()
        avail = _read_mem_available_mb()
        load = _read_mem_load_percent()
        self._rss_hist.append((now, rss))
        growth = self._growth_mb_per_min()

        soft = min(self._baseline + self.soft_delta_mb, self.soft_abs_mb)
        hard = min(self._baseline + self.hard_delta_mb, self.hard_abs_mb)
        emergency = self.emergency_abs_mb

        system_tight = avail < 640.0 or load >= 90.0
        system_critical = avail < 320.0 or load >= 95.0

        # Leak-like: steady climb even under load
        if growth > 45.0 and rss > self._baseline + 40:
            self._growth_streak += 1
        else:
            self._growth_streak = max(0, self._growth_streak - 1)
        self._leak_suspect = self._growth_streak >= 4

        need_purge = False
        if rss >= emergency or system_critical or (self._leak_suspect and rss > soft):
            self._level = "EMERGENCY"
            self._throttle = 0.30
            self._trails = False
            self._labels = False
            self._param_scale = 0.20
            self._target_fps = 12.0
            self._note = f"EMERGENCY rss={rss:.0f} avail={avail:.0f} growth={growth:.0f}MB/m"
            need_purge = True
            if not self._priority_low:
                set_process_priority_below_normal()
                self._priority_low = True
        elif rss >= hard or (system_tight and rss > self._baseline + 60) or self._leak_suspect:
            self._level = "HARD"
            self._throttle = 0.45
            self._trails = False
            self._labels = True
            self._param_scale = 0.35
            self._target_fps = 16.0
            self._note = f"HARD rss={rss:.0f} load={load:.0f}% grow={growth:.0f}"
            need_purge = True
            if not self._priority_low:
                set_process_priority_below_normal()
                self._priority_low = True
        elif rss >= soft or system_tight:
            self._level = "SOFT"
            self._throttle = 0.65
            self._trails = True
            self._labels = True
            self._param_scale = 0.55
            self._target_fps = 20.0 if self.eco else 24.0
            self._note = f"SOFT rss={rss:.0f} avail={avail:.0f}"
            need_purge = True
        else:
            # Recover slowly
            self._level = "OK"
            self._throttle = min(1.0 if not self.eco else 0.90, self._throttle + 0.04)
            self._param_scale = min(1.0, self._param_scale + 0.08)
            if rss < soft * 0.82 and not system_tight:
                self._trails = True
                self._labels = True
                self._target_fps = min(self.base_fps if not self.eco else min(28.0, self.base_fps), self._target_fps + 1.5)
            self._note = f"OK rss={rss:.0f} thr={self._throttle:.2f}"
            if self._priority_low and rss < soft * 0.75 and not self.eco:
                set_process_priority_normal()
                self._priority_low = False

        # Always eco-cap FPS a bit on Windows laptops
        if self.eco:
            self._target_fps = min(self._target_fps, 28.0)

        if need_purge and (now - self._last_purge) >= self.min_purge_interval:
            self._last_purge = now
            self._purge_count += 1
            return True, self.state()
        return False, self.state()

    def run_python_purge(self, *, trim: bool = True) -> None:
        """Release Python heap; optionally ask OS to shrink working set."""
        try:
            gc.collect(2)
        except Exception:
            gc.collect()
        if trim and self._level in ("HARD", "EMERGENCY"):
            trim_working_set()


class FramePacer:
    """Cap FPS without busy-spin (sleep remainder of frame budget)."""

    def __init__(self, target_fps: float = 30.0) -> None:
        self.target_fps = max(8.0, float(target_fps))
        self._last = time.perf_counter()
        self._frame = 0
        self.avg_frame_ms = 0.0

    def set_fps(self, fps: float) -> None:
        self.target_fps = max(8.0, min(60.0, float(fps)))

    def end_frame(self) -> float:
        """Sleep until next frame; returns dt seconds since previous end_frame."""
        budget = 1.0 / self.target_fps
        elapsed = time.perf_counter() - self._last
        sleep_t = budget - elapsed
        if sleep_t > 0.001:
            # Never busy-wait; cap sleep if FPS target is very low
            time.sleep(min(sleep_t, 0.12))
        end = time.perf_counter()
        real_dt = end - self._last
        self._last = end
        self._frame += 1
        ms = real_dt * 1000.0
        self.avg_frame_ms = ms if self.avg_frame_ms <= 0 else (self.avg_frame_ms * 0.9 + ms * 0.1)
        return min(0.1, max(1e-4, real_dt))
