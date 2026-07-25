"""GPU / メモリ / 排熱の監視と自動スロットル・パージ。

排熱センサー（hwmon / thermal_zone）を読み、温度が上がるほど
FPS・粒子・残像を自動で落とす。メモリ圧迫時の挙動も併用する。
"""

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


def thermal_enabled() -> bool:
    """SOUNDORBIT_THERMAL=0 で無効。既定 ON。"""
    v = (os.environ.get("SOUNDORBIT_THERMAL") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except OSError:
        return ""


def _read_millic_c(path: str) -> Optional[float]:
    """sysfs temp*_input / thermal_zone temp → °C。"""
    raw = _read_text(path)
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    # millidegree C（通常） or すでに °C
    if v > 200.0:
        v *= 0.001
    # 異常値・未実装センサー（0 や 127 など）を捨てる
    if v < 20.0 or v > 120.0:
        return None
    return v


# hwmon 名の優先度（高いほど CPU/GPU 排熱として信頼）
_HWMON_NAME_SCORE = {
    "amdgpu": 100,
    "nvidia": 100,
    "nouveau": 90,
    "coretemp": 95,
    "k10temp": 95,
    "zenpower": 95,
    "thinkpad": 80,
    "acpitz": 50,
    "nvme": 10,
    "iwlwifi": 5,
    "ath10k": 5,
    "ath11k": 5,
}

# ラベル優先（edge/junction/Tctl/CPU/GPU）
_LABEL_SCORE = {
    "edge": 40,
    "junction": 45,
    "tctl": 35,
    "tdie": 35,
    "cpu": 35,
    "gpu": 40,
    "package id 0": 35,
    "package": 30,
    "composite": 5,
}


def _sensor_score(hwmon_name: str, label: str) -> int:
    name_l = hwmon_name.lower()
    label_l = label.lower()
    score = 0
    for key, sc in _HWMON_NAME_SCORE.items():
        if key in name_l:
            score = max(score, sc)
            break
    else:
        score = 20
    for key, sc in _LABEL_SCORE.items():
        if key in label_l:
            score += sc
            break
    # 無線・SSD は排熱判定から外し気味
    if any(k in name_l for k in ("iwlwifi", "ath", "wifi", "nvme", "ssd")):
        score = min(score, 15)
    if any(k in label_l for k in ("composite", "sensor 2", "pch")):
        score = min(score, score)  # keep
    return score


def read_thermal_c() -> tuple[Optional[float], str]:
    """
    主要センサーの最高温度 (°C) と表示用ラベル。
    見つからなければ (None, "")。
    """
    if not thermal_enabled():
        return None, ""

    best_temp: Optional[float] = None
    best_label = ""
    best_score = -1
    candidates: list[tuple[float, int, str]] = []

    hwmon_root = "/sys/class/hwmon"
    try:
        names = os.listdir(hwmon_root)
    except OSError:
        names = []

    for entry in names:
        base = os.path.join(hwmon_root, entry)
        hname = _read_text(os.path.join(base, "name")) or entry
        try:
            files = os.listdir(base)
        except OSError:
            continue
        for fn in files:
            if not (fn.startswith("temp") and fn.endswith("_input")):
                continue
            temp = _read_millic_c(os.path.join(base, fn))
            if temp is None:
                continue
            prefix = fn[: -len("_input")]
            label = _read_text(os.path.join(base, prefix + "_label")) or prefix
            sc = _sensor_score(hname, label)
            tag = f"{hname}:{label}"
            candidates.append((temp, sc, tag))
            if sc > best_score or (sc == best_score and (best_temp is None or temp > best_temp)):
                best_score = sc
                best_temp = temp
                best_label = tag

    # thermal_zone フォールバック
    tz_root = "/sys/class/thermal"
    try:
        zones = [z for z in os.listdir(tz_root) if z.startswith("thermal_zone")]
    except OSError:
        zones = []
    for z in zones:
        base = os.path.join(tz_root, z)
        ztype = _read_text(os.path.join(base, "type")) or z
        # 無線ゾーンは無視
        if any(k in ztype.lower() for k in ("iwl", "wifi", "ath", "wcn")):
            continue
        temp = _read_millic_c(os.path.join(base, "temp"))
        if temp is None:
            continue
        sc = _sensor_score(ztype, ztype)
        tag = f"tz:{ztype}"
        candidates.append((temp, sc, tag))
        if sc > best_score or (sc == best_score and (best_temp is None or temp > best_temp)):
            best_score = sc
            best_temp = temp
            best_label = tag

    if not candidates:
        return None, ""

    # 高スコア群のうち最高温（CPU/GPU 寄りの複数センサーをカバー）
    # score が 40 未満だけのときは全体最高
    hi = [c for c in candidates if c[1] >= 40]
    pool = hi if hi else candidates
    t_max, _, tag = max(pool, key=lambda c: c[0])
    # 表示は「主センサー」を残しつつ、実際の制御温度は max
    if best_temp is not None and best_label and abs(t_max - best_temp) < 0.5:
        return t_max, best_label
    return t_max, tag if tag else best_label


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# 排熱レベル 0=cool … 4=critical
# しきい値は「上がるとき」。下がるときはヒステリシスで -3°C
_THERMAL_UP = (62.0, 70.0, 78.0, 85.0)  # → level 1,2,3,4
_THERMAL_DOWN = (59.0, 67.0, 75.0, 82.0)


def thermal_level_from_temp(temp_c: float, prev_level: int = 0) -> int:
    """温度 → 0..4。ヒステリシス付き。"""
    level = 0
    for i, thr in enumerate(_THERMAL_UP):
        if temp_c >= thr:
            level = i + 1
    # 回復時: 1段下げるには DOWN 閾値未満が必要
    if level < prev_level:
        # 現在の prev を維持できるか
        keep = prev_level
        while keep > level:
            down_thr = _THERMAL_DOWN[keep - 1]
            if temp_c > down_thr:
                break
            keep -= 1
        level = keep
    return int(max(0, min(4, level)))


def thermal_knobs(level: int) -> tuple[float, bool, float, str]:
    """
    排熱レベル → (throttle, trails_ok, param_scale, tag)
    アプリ起因の発熱を早めに抑える寄り。
    """
    if level <= 0:
        return 1.0, True, 1.0, "cool"
    if level == 1:
        return 0.82, True, 0.80, "warm"
    if level == 2:
        return 0.60, True, 0.55, "hot"
    if level == 3:
        return 0.45, False, 0.35, "vhot"
    return 0.32, False, 0.22, "crit"


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
    # 排熱
    temp_c: Optional[float] = None
    temp_label: str = ""
    heat_level: int = 0  # 0..4
    heat_tag: str = "cool"


@dataclass
class ResourceGuardian:
    """
    メモリ + 排熱を監視し、閾値超過前にパージ / GPU 負荷を下げる。

    - soft: 粒子クリア・GC・残像バッファ初期化・更新頻度低下
    - hard: さらに trails オフ、FPS を強く落とす
    - 持続的な RSS 上昇（リーク疑い）でも hard 寄りに落とす
    - 排熱: 温度に応じて描画を自動で軽くする（メモリと独立に min 合成）
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
    # 排熱
    _temp_c: Optional[float] = None
    _temp_label: str = ""
    _heat_level: int = 0
    _heat_tag: str = "cool"
    # ECO 時は回復上限を少し抑える
    _eco: bool = True

    def arm(self) -> None:
        """起動直後のベースラインを記録。"""
        rss = _read_rss_mb()
        self._baseline = max(rss, 80.0)
        self._last_check = time.monotonic()
        self._armed = True
        self._rss_samples = [(self._last_check, rss)]
        self._growth_streak = 0
        self._eco = eco_bias_enabled()
        # 起動直後から排熱を読む
        t, lab = read_thermal_c()
        self._temp_c = t
        self._temp_label = lab
        if t is not None:
            self._heat_level = thermal_level_from_temp(t, 0)
            thr, trails, pscale, tag = thermal_knobs(self._heat_level)
            self._heat_tag = tag
            if self._eco:
                thr = min(thr, 0.92)
            self._throttle = thr
            self._trails_allowed = trails
            self._param_scale = pscale
            self._note = f"baseline {self._baseline:.0f}MB · {t:.0f}°C {tag}"
        else:
            self._throttle = 0.92 if self._eco else 1.0
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
            temp_c=self._temp_c,
            temp_label=self._temp_label,
            heat_level=self._heat_level,
            heat_tag=self._heat_tag,
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

        system_tight = avail < 512.0

        # --- メモリ側の目標 ---
        mem_throttle = 1.0
        mem_trails = True
        mem_param = 1.0
        need_purge = False
        mem_note = f"rss={rss:.0f}MB"

        if rss >= hard or (system_tight and rss > self._baseline + 80) or leak_suspect:
            mem_throttle = 0.45
            mem_trails = False
            mem_param = 0.35
            tag = "LEAK" if leak_suspect else "HARD"
            mem_note = f"{tag} rss={rss:.0f}MB grow={growth:.0f}MB/m"
            need_purge = True
        elif rss >= soft:
            mem_throttle = 0.65
            mem_trails = True
            mem_param = 0.55
            mem_note = f"SOFT rss={rss:.0f}MB"
            need_purge = True
        else:
            mem_throttle = 1.0
            mem_trails = True
            mem_param = 1.0
            mem_note = f"OK rss={rss:.0f}MB"

        # --- 排熱側 ---
        t, lab = read_thermal_c()
        self._temp_c = t
        self._temp_label = lab
        heat_throttle = 1.0
        heat_trails = True
        heat_param = 1.0
        heat_note = ""

        if t is not None:
            self._heat_level = thermal_level_from_temp(t, self._heat_level)
            heat_throttle, heat_trails, heat_param, self._heat_tag = thermal_knobs(
                self._heat_level
            )
            heat_note = f"{t:.0f}°C {self._heat_tag}"
            # 熱いときはメモリに余裕があってもパージ気味に（残像テクスチャの熱源を減らす）
            if self._heat_level >= 3:
                need_purge = True
        else:
            self._heat_level = 0
            self._heat_tag = "n/a"

        # ECO: 平常時もわずかに抑える
        eco_cap = 0.90 if self._eco else 1.0

        # メモリと排熱で厳しい方を採用
        target_thr = min(mem_throttle, heat_throttle, eco_cap)
        target_trails = mem_trails and heat_trails
        target_param = min(mem_param, heat_param)

        # 熱上昇時は即スロットル、回復時はゆっくり戻す（チラつき防止）
        if target_thr < self._throttle:
            self._throttle = target_thr
        else:
            self._throttle = min(target_thr, self._throttle + 0.04)
        # 残像は熱い側に合わせて即オフ、回復時は target が True なら戻す
        if not target_trails:
            self._trails_allowed = False
        elif target_thr >= 0.75:
            self._trails_allowed = True
        if target_param < self._param_scale:
            self._param_scale = target_param
        else:
            self._param_scale = min(target_param, self._param_scale + 0.08)

        parts = [mem_note]
        if heat_note:
            parts.append(heat_note)
        parts.append(f"thr {self._throttle:.2f}")
        self._note = " · ".join(parts)

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
