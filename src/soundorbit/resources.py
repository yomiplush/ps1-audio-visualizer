"""GPU / メモリ負荷の監視と自動スロットル・パージ。"""

from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass, field
from typing import Optional


def _read_rss_mb() -> float:
    """自プロセスの RSS (MiB)。/proc が無ければ 0。"""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # kB
                    parts = line.split()
                    return float(parts[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _read_mem_available_mb() -> float:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 4096.0


@dataclass
class ResourceState:
    rss_mb: float = 0.0
    baseline_rss_mb: float = 0.0
    soft_limit_mb: float = 0.0
    hard_limit_mb: float = 0.0
    throttle: float = 1.0  # 1.0=通常, 0.5=半減 など（FPS・粒子）
    trails_allowed: bool = True
    param_update_scale: float = 1.0
    last_purge_ago: float = 999.0
    purge_count: int = 0
    note: str = ""


@dataclass
class ResourceGuardian:
    """
    メモリを監視し、閾値超過前にパージ / GPU 負荷を下げる。

    - soft: 粒子クリア・GC・残像バッファ初期化・更新頻度低下
    - hard: さらに trails オフ、FPS を強く落とす
    - 持続的な RSS 上昇（リーク疑い）でも hard 寄りに落とす
    """

    check_interval: float = 1.0
    # ベースラインからの許容増分
    soft_delta_mb: float = 180.0
    hard_delta_mb: float = 320.0
    # 絶対上限（小さめマシン向け）
    soft_abs_mb: float = 700.0
    hard_abs_mb: float = 950.0
    min_purge_interval: float = 8.0

    _baseline: float = 0.0
    _last_check: float = 0.0
    _last_purge: float = 0.0
    _purge_count: int = 0
    _throttle: float = 1.0
    _trails_allowed: bool = True
    _param_scale: float = 1.0
    _note: str = "OK"
    _armed: bool = False
    _rss_samples: list = field(default_factory=list)
    _growth_streak: int = 0

    def arm(self) -> None:
        """起動直後のベースラインを記録。"""
        rss = _read_rss_mb()
        self._baseline = max(rss, 80.0)
        self._last_check = time.monotonic()
        self._armed = True
        self._rss_samples = [(self._last_check, rss)]
        self._growth_streak = 0
        self._note = f"baseline {self._baseline:.0f}MB"

    def state(self) -> ResourceState:
        now = time.monotonic()
        return ResourceState(
            rss_mb=_read_rss_mb(),
            baseline_rss_mb=self._baseline,
            soft_limit_mb=min(self._baseline + self.soft_delta_mb, self.soft_abs_mb),
            hard_limit_mb=min(self._baseline + self.hard_delta_mb, self.hard_abs_mb),
            throttle=self._throttle,
            trails_allowed=self._trails_allowed,
            param_update_scale=self._param_scale,
            last_purge_ago=now - self._last_purge if self._last_purge else 999.0,
            purge_count=self._purge_count,
            note=self._note,
        )

    def _growth_mb_per_min(self) -> float:
        if len(self._rss_samples) < 3:
            return 0.0
        t0, r0 = self._rss_samples[0]
        t1, r1 = self._rss_samples[-1]
        dt = max(1e-3, t1 - t0)
        return (r1 - r0) * (60.0 / dt)

    def tick(self) -> tuple[bool, ResourceState]:
        """
        定期チェック。戻り値: (purge_すべきか, 状態)
        """
        now = time.monotonic()
        if not self._armed:
            self.arm()
        if now - self._last_check < self.check_interval:
            return False, self.state()
        self._last_check = now

        rss = _read_rss_mb()
        avail = _read_mem_available_mb()
        soft = min(self._baseline + self.soft_delta_mb, self.soft_abs_mb)
        hard = min(self._baseline + self.hard_delta_mb, self.hard_abs_mb)

        self._rss_samples.append((now, rss))
        if len(self._rss_samples) > 30:
            self._rss_samples = self._rss_samples[-30:]
        growth = self._growth_mb_per_min()
        if growth > 50.0 and rss > self._baseline + 50:
            self._growth_streak += 1
        else:
            self._growth_streak = max(0, self._growth_streak - 1)
        leak_suspect = self._growth_streak >= 4

        # システム全体が逼迫している場合も抑制
        system_tight = avail < 512.0

        need_purge = False
        if rss >= hard or (system_tight and rss > self._baseline + 80) or leak_suspect:
            self._throttle = 0.45
            self._trails_allowed = False
            self._param_scale = 0.35
            tag = "LEAK" if leak_suspect else "HARD"
            self._note = f"{tag} rss={rss:.0f}MB grow={growth:.0f}MB/m"
            need_purge = True
        elif rss >= soft:
            self._throttle = 0.65
            self._trails_allowed = True
            self._param_scale = 0.55
            self._note = f"SOFT rss={rss:.0f}MB"
            need_purge = True
        else:
            # 余裕があればゆっくり回復
            self._throttle = min(1.0, self._throttle + 0.05)
            if rss < soft * 0.85:
                self._trails_allowed = True
                self._param_scale = min(1.0, self._param_scale + 0.1)
            self._note = f"OK rss={rss:.0f}MB"

        if need_purge and (now - self._last_purge) >= self.min_purge_interval:
            self._last_purge = now
            self._purge_count += 1
            return True, self.state()
        return False, self.state()

    def run_python_purge(self) -> None:
        """Python ヒープ側の解放。"""
        gc.collect(2)


def eco_bias_enabled() -> bool:
    """環境変数 SOUNDORBIT_ECO=0 で無効化可。デフォルト ON。"""
    v = os.environ.get("SOUNDORBIT_ECO", "1").strip().lower()
    return v not in ("0", "false", "off", "no")
