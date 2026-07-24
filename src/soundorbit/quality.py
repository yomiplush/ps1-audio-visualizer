"""PC スペック自動検出 → 描画品質プロファイル。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QualityProfile:
    """描画・更新の負荷をまとめたプリセット。"""

    key: str
    label: str
    score: int
    # 描画密度
    particle_count: int
    orb_stacks: int
    orb_slices: int
    ring_segments: int
    ring_radii: tuple[float, ...]
    grid_half: int
    grid_spacing: float
    # ポストプロセス
    trails: bool
    rgb_shift: bool
    fbo_scale: float  # オフスクリーン解像度倍率 (0.5–1.0)
    # 残像・色収差のベース（白飛びしにくい値）
    trail_decay: float
    trail_scene_gain: float
    trail_mix: float
    aberration: float
    # 更新
    target_fps: int
    particle_emit_scale: float
    # 検出メモ（UI 表示用）
    reason: str = ""


# キー → 固定プリセット（score は検出時の参考表示用）
_PRESETS: dict[str, QualityProfile] = {
    # ※ GPU 発熱を抑えるため全体的に控えめ（ECO 既定）
    "low": QualityProfile(
        key="low",
        label="低",
        score=0,
        particle_count=120,
        orb_stacks=10,
        orb_slices=14,
        ring_segments=72,
        ring_radii=(2.0, 4.5),
        grid_half=8,
        grid_spacing=1.0,
        trails=False,
        rgb_shift=False,
        fbo_scale=0.45,
        trail_decay=0.65,
        trail_scene_gain=0.20,
        trail_mix=0.24,
        aberration=0.0,
        target_fps=20,
        particle_emit_scale=0.22,
    ),
    "medium": QualityProfile(
        key="medium",
        label="中",
        score=40,
        particle_count=280,
        orb_stacks=14,
        orb_slices=18,
        ring_segments=120,
        ring_radii=(2.0, 4.0, 5.5),
        grid_half=12,
        grid_spacing=0.85,
        trails=True,
        rgb_shift=False,
        fbo_scale=0.55,
        trail_decay=0.70,
        trail_scene_gain=0.24,
        trail_mix=0.28,
        aberration=0.0,
        target_fps=24,
        particle_emit_scale=0.40,
    ),
    "high": QualityProfile(
        key="high",
        label="高",
        score=70,
        particle_count=420,
        orb_stacks=16,
        orb_slices=22,
        ring_segments=160,
        ring_radii=(2.0, 4.0, 5.5),
        grid_half=14,
        grid_spacing=0.8,
        trails=True,
        rgb_shift=True,
        fbo_scale=0.65,
        trail_decay=0.72,
        trail_scene_gain=0.26,
        trail_mix=0.30,
        aberration=0.0010,
        target_fps=30,
        particle_emit_scale=0.55,
    ),
    "ultra": QualityProfile(
        key="ultra",
        label="最高",
        score=90,
        particle_count=600,
        orb_stacks=20,
        orb_slices=28,
        ring_segments=200,
        ring_radii=(2.0, 3.5, 5.0, 6.2),
        grid_half=16,
        grid_spacing=0.75,
        trails=True,
        rgb_shift=True,
        fbo_scale=0.75,
        trail_decay=0.74,
        trail_scene_gain=0.28,
        trail_mix=0.32,
        aberration=0.0012,
        target_fps=36,
        particle_emit_scale=0.70,
    ),
}


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def _cpu_logical() -> int:
    return max(1, os.cpu_count() or 1)


def _ram_gb() -> float:
    # /proc/meminfo MemTotal: kB
    text = _read_text("/proc/meminfo")
    m = re.search(r"MemTotal:\s+(\d+)", text)
    if m:
        return int(m.group(1)) / (1024.0 * 1024.0)
    return 8.0


def _run(cmd: list[str], timeout: float = 1.5) -> str:
    try:
        return subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""


@dataclass
class _GpuInfo:
    name: str
    vram_mb: int
    is_integrated: bool
    accelerated: bool


def _gpu_info() -> _GpuInfo:
    name = ""
    vram_mb = 0
    is_igpu = False
    accelerated = True

    # glxinfo が最も詳しい（あれば）
    if shutil.which("glxinfo"):
        out = _run(["glxinfo", "-B"])
        for line in out.splitlines():
            low = line.lower()
            if "device:" in low and not name:
                name = line.split(":", 1)[-1].strip()
            if "video memory:" in low:
                m = re.search(r"(\d+)\s*MB", line, re.I)
                if m:
                    vram_mb = int(m.group(1))
            if "accelerated:" in low:
                accelerated = "yes" in low

    if not name and shutil.which("lspci"):
        out = _run(["lspci"])
        for line in out.splitlines():
            if re.search(r"VGA|3D|Display", line, re.I):
                name = line.split(":", 2)[-1].strip() if ":" in line else line
                break

    # DRM 経由のざっくり推定
    if not name:
        for card in ("card0", "card1"):
            vendor = _read_text(f"/sys/class/drm/{card}/device/vendor").strip()
            device = _read_text(f"/sys/class/drm/{card}/device/device").strip()
            if vendor:
                name = f"DRM {vendor}:{device}"
                break

    low = name.lower()
    # 内蔵 GPU っぽいキーワード
    igpu_kw = (
        "renoir", "raphael", "phoenix", "rembrandt", "raven", "picasso",
        "vega", "graphics", "uhd", "iris", "xe graphics", "radeon graphics",
        "apple", "adreno", "mali", "llvmpipe", "softpipe", "swrast",
    )
    # 明確な dGPU
    dgpu_kw = (
        "geforce", "rtx", "gtx", "quadro", "radeon rx", "radeon pro w",
        "arc a", "tesla", "instinct",
    )
    if any(k in low for k in dgpu_kw):
        is_igpu = False
    elif any(k in low for k in igpu_kw) or "unified memory: yes" in _run(["glxinfo", "-B"]).lower():
        is_igpu = True
    elif vram_mb and vram_mb <= 2048:
        is_igpu = True

    if "llvmpipe" in low or "softpipe" in low or "swrast" in low:
        accelerated = False
        is_igpu = True
        vram_mb = vram_mb or 256

    return _GpuInfo(
        name=name or "unknown",
        vram_mb=vram_mb,
        is_integrated=is_igpu,
        accelerated=accelerated,
    )


def _on_battery() -> bool:
    """ノートでバッテリ駆動中なら True（検出できなければ False）。"""
    power = "/sys/class/power_supply"
    try:
        for name in os.listdir(power):
            base = os.path.join(power, name)
            t = _read_text(os.path.join(base, "type")).strip().lower()
            if t != "battery":
                continue
            status = _read_text(os.path.join(base, "status")).strip().lower()
            # Discharging のみ省エネ寄り
            if status == "discharging":
                return True
    except OSError:
        pass
    return False


def detect_system() -> dict:
    """検出生データ（デバッグ・表示用）。"""
    gpu = _gpu_info()
    return {
        "cpu_logical": _cpu_logical(),
        "ram_gb": round(_ram_gb(), 1),
        "gpu_name": gpu.name,
        "gpu_vram_mb": gpu.vram_mb,
        "gpu_integrated": gpu.is_integrated,
        "gpu_accelerated": gpu.accelerated,
        "on_battery": _on_battery(),
    }


def score_system(info: Optional[dict] = None) -> tuple[int, list[str]]:
    """0–100 程度のスコアと理由リスト。"""
    info = info or detect_system()
    score = 0
    reasons: list[str] = []

    cpu = int(info["cpu_logical"])
    if cpu <= 2:
        score += 5
        reasons.append(f"CPU {cpu}スレッド")
    elif cpu <= 4:
        score += 15
        reasons.append(f"CPU {cpu}スレッド")
    elif cpu <= 8:
        score += 28
        reasons.append(f"CPU {cpu}スレッド")
    elif cpu <= 12:
        score += 36
        reasons.append(f"CPU {cpu}スレッド")
    else:
        score += 42
        reasons.append(f"CPU {cpu}スレッド")

    ram = float(info["ram_gb"])
    if ram < 6:
        score += 4
        reasons.append(f"RAM {ram:.0f}GB")
    elif ram < 12:
        score += 12
        reasons.append(f"RAM {ram:.0f}GB")
    elif ram < 20:
        score += 18
        reasons.append(f"RAM {ram:.0f}GB")
    else:
        score += 24
        reasons.append(f"RAM {ram:.0f}GB")

    if not info["gpu_accelerated"]:
        score = min(score, 25)
        reasons.append("ソフトウェア描画")
    elif info["gpu_integrated"]:
        vram = int(info["gpu_vram_mb"] or 0)
        if vram and vram < 1024:
            score += 8
        elif vram and vram < 2048:
            score += 14
        else:
            score += 18
        reasons.append("内蔵GPU")
        # iGPU は上限を少し抑える
        score = min(score, 78)
    else:
        vram = int(info["gpu_vram_mb"] or 0)
        if vram >= 8000:
            score += 34
            reasons.append(f"dGPU VRAM {vram}MB")
        elif vram >= 4000:
            score += 28
            reasons.append(f"dGPU VRAM {vram}MB")
        elif vram >= 2000:
            score += 22
            reasons.append(f"dGPU VRAM {vram}MB")
        else:
            score += 18
            reasons.append("dGPU")

    if info.get("on_battery"):
        score = max(0, score - 12)
        reasons.append("バッテリ駆動")

    return int(score), reasons


def profile_for_score(score: int) -> str:
    if score < 35:
        return "low"
    if score < 55:
        return "medium"
    if score < 80:
        return "high"
    return "ultra"


def detect_quality(override: Optional[str] = None) -> QualityProfile:
    """
    スペックから品質を決める。
    override: "low"|"medium"|"high"|"ultra"|"auto"|None
    環境変数 SOUNDORBIT_QUALITY も参照。
    """
    env = (override or os.environ.get("SOUNDORBIT_QUALITY") or "auto").strip().lower()
    if env in _PRESETS:
        p = _PRESETS[env]
        return QualityProfile(**{**p.__dict__, "reason": f"手動/環境変数: {env}"})

    info = detect_system()
    score, reasons = score_system(info)
    key = profile_for_score(score)

    # GPU 発熱対策: 既定で 1 段落とす / iGPU は ultra 禁止
    try:
        from soundorbit.resources import eco_bias_enabled
        eco = eco_bias_enabled()
    except Exception:
        eco = True
    if eco:
        order = ["low", "medium", "high", "ultra"]
        idx = order.index(key) if key in order else 1
        # 常に 1 段省エネ寄り
        idx = max(0, idx - 1)
        if info.get("gpu_integrated"):
            idx = min(idx, order.index("high") - 1)  # medium まで
            reasons = list(reasons) + ["ECO/iGPU"]
        else:
            reasons = list(reasons) + ["ECO"]
        key = order[idx]

    base = _PRESETS[key]
    reason = f"自動 score={score} → {base.label}（{', '.join(reasons)}）"
    # frozen dataclass: 新しいインスタンスで reason だけ差し替え
    return QualityProfile(
        key=base.key,
        label=base.label,
        score=score,
        particle_count=base.particle_count,
        orb_stacks=base.orb_stacks,
        orb_slices=base.orb_slices,
        ring_segments=base.ring_segments,
        ring_radii=base.ring_radii,
        grid_half=base.grid_half,
        grid_spacing=base.grid_spacing,
        trails=base.trails,
        rgb_shift=base.rgb_shift,
        fbo_scale=base.fbo_scale,
        trail_decay=base.trail_decay,
        trail_scene_gain=base.trail_scene_gain,
        trail_mix=base.trail_mix,
        aberration=base.aberration,
        target_fps=base.target_fps,
        particle_emit_scale=base.particle_emit_scale,
        reason=reason,
    )


def cycle_quality(current_key: str) -> QualityProfile:
    order = ["low", "medium", "high", "ultra"]
    try:
        i = order.index(current_key)
    except ValueError:
        i = 1
    nxt = order[(i + 1) % len(order)]
    p = _PRESETS[nxt]
    return QualityProfile(**{**p.__dict__, "reason": f"手動切替: {p.label}"})
