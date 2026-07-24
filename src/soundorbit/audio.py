"""PipeWire / PulseAudio モニターからシステム再生音を取得し FFT する。"""

from __future__ import annotations

import math
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


SAMPLE_RATE = 48_000
CHANNELS = 2
FFT_SIZE = 2048
BANDS = 96
# 読み取りチャンク（float32 ステレオ）
CHUNK_FRAMES = 1024


@dataclass
class AudioAnalysis:
    """可視化向けに整形したスペクトルとエネルギー指標。"""

    spectrum: np.ndarray = field(default_factory=lambda: np.zeros(BANDS, dtype=np.float32))
    waveform: np.ndarray = field(default_factory=lambda: np.zeros(256, dtype=np.float32))
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    rms: float = 0.0
    peak: float = 0.0
    beat: float = 0.0  # 0..1 のビートパルス
    ready: bool = False
    error: Optional[str] = None
    source_name: str = ""


class SystemAudioCapture:
    """
    デフォルトシンクの .monitor を parec で読み取り、
    別スレッドで FFT / バンド集約を行う。
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        bands: int = BANDS,
        fft_size: int = FFT_SIZE,
    ) -> None:
        self.sample_rate = sample_rate
        self.bands = bands
        self.fft_size = fft_size

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None

        self._ring = np.zeros(fft_size * 4, dtype=np.float32)
        self._ring_pos = 0
        self._analysis = AudioAnalysis(
            spectrum=np.zeros(bands, dtype=np.float32),
            waveform=np.zeros(256, dtype=np.float32),
        )

        # 平滑化用
        self._smooth = np.zeros(bands, dtype=np.float32)
        self._env_bass = 0.0
        self._env_mid = 0.0
        self._env_treble = 0.0
        self._env_rms = 0.0
        self._beat_env = 0.0
        self._prev_bass = 0.0

        # ログ周波数ビン境界
        self._band_edges = self._make_band_edges(bands, fft_size, sample_rate)
        self._window = np.hanning(fft_size).astype(np.float32)

    @staticmethod
    def _make_band_edges(bands: int, fft_size: int, sample_rate: int) -> np.ndarray:
        """20Hz〜Nyquist を対数分割したビン境界。"""
        n_bins = fft_size // 2
        f_min, f_max = 30.0, sample_rate * 0.48
        edges_hz = np.geomspace(f_min, f_max, bands + 1)
        hz_per_bin = sample_rate / fft_size
        edges = np.clip(edges_hz / hz_per_bin, 1, n_bins - 1).astype(np.int32)
        # 単調増加を保証
        for i in range(1, len(edges)):
            if edges[i] <= edges[i - 1]:
                edges[i] = min(edges[i - 1] + 1, n_bins - 1)
        return edges

    @staticmethod
    def default_monitor_name() -> str:
        try:
            sink = subprocess.check_output(
                ["pactl", "get-default-sink"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if sink:
                return f"{sink}.monitor"
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        return ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="soundorbit-audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if proc is not None:
            try:
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass
            self._proc = None

    def snapshot(self) -> AudioAnalysis:
        with self._lock:
            a = self._analysis
            return AudioAnalysis(
                spectrum=a.spectrum.copy(),
                waveform=a.waveform.copy(),
                bass=a.bass,
                mid=a.mid,
                treble=a.treble,
                rms=a.rms,
                peak=a.peak,
                beat=a.beat,
                ready=a.ready,
                error=a.error,
                source_name=a.source_name,
            )

    def _spawn_parec(self, device: str) -> subprocess.Popen:
        if not shutil.which("parec"):
            raise RuntimeError("parec が見つかりません（pipewire-pulse / libpulse を確認）")
        # float32le ステレオ raw
        cmd = [
            "parec",
            "--device", device,
            "--format=float32le",
            f"--channels={CHANNELS}",
            f"--rate={self.sample_rate}",
            "--latency-msec=30",
            "--raw",
        ]
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=CHUNK_FRAMES * CHANNELS * 4,
        )

    def _run(self) -> None:
        device = self.default_monitor_name()
        if not device:
            with self._lock:
                self._analysis.error = "デフォルト出力デバイスを取得できません"
            return

        with self._lock:
            self._analysis.source_name = device
            self._analysis.error = None

        try:
            self._proc = self._spawn_parec(device)
        except Exception as exc:
            with self._lock:
                self._analysis.error = str(exc)
            return

        assert self._proc.stdout is not None
        bytes_per_chunk = CHUNK_FRAMES * CHANNELS * 4  # float32

        while not self._stop.is_set():
            try:
                raw = self._proc.stdout.read(bytes_per_chunk)
            except Exception as exc:
                with self._lock:
                    self._analysis.error = f"読み取りエラー: {exc}"
                break

            if not raw:
                # プロセス終了 or デバイス変更
                if self._stop.is_set():
                    break
                # 再接続を試みる
                time.sleep(0.3)
                if self._stop.is_set():
                    break
                device = self.default_monitor_name() or device
                try:
                    if self._proc:
                        self._proc.kill()
                    self._proc = self._spawn_parec(device)
                    with self._lock:
                        self._analysis.source_name = device
                        self._analysis.error = None
                    assert self._proc.stdout is not None
                except Exception as exc:
                    with self._lock:
                        self._analysis.error = f"再接続失敗: {exc}"
                    time.sleep(1.0)
                continue

            if len(raw) < 8:
                continue

            # incomplete frame を切り捨て
            n_floats = (len(raw) // 4) // CHANNELS * CHANNELS
            samples = np.frombuffer(raw, dtype=np.float32, count=n_floats)
            if CHANNELS == 2:
                mono = samples.reshape(-1, 2).mean(axis=1)
            else:
                mono = samples

            self._push_samples(mono)
            self._analyze()

        # 終了処理
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    def _push_samples(self, mono: np.ndarray) -> None:
        n = mono.shape[0]
        ring = self._ring
        pos = self._ring_pos
        capacity = ring.shape[0]
        if n >= capacity:
            ring[:] = mono[-capacity:]
            self._ring_pos = 0
            return
        end = pos + n
        if end <= capacity:
            ring[pos:end] = mono
        else:
            first = capacity - pos
            ring[pos:] = mono[:first]
            ring[: end - capacity] = mono[first:]
        self._ring_pos = end % capacity

    def _latest_block(self) -> np.ndarray:
        """リングから最新 fft_size サンプルを取り出す。"""
        n = self.fft_size
        ring = self._ring
        pos = self._ring_pos
        capacity = ring.shape[0]
        start = (pos - n) % capacity
        if start + n <= capacity:
            return ring[start : start + n].copy()
        first = capacity - start
        out = np.empty(n, dtype=np.float32)
        out[:first] = ring[start:]
        out[first:] = ring[: n - first]
        return out

    def _analyze(self) -> None:
        block = self._latest_block()
        peak = float(np.max(np.abs(block))) if block.size else 0.0
        rms = float(np.sqrt(np.mean(block * block))) if block.size else 0.0

        # 波形ダウンサンプル（表示用）
        wave_n = 256
        step = max(1, block.shape[0] // wave_n)
        wave = block[::step][:wave_n]
        if wave.shape[0] < wave_n:
            wave = np.pad(wave, (0, wave_n - wave.shape[0]))

        # FFT
        windowed = block * self._window
        spectrum = np.abs(np.fft.rfft(windowed))
        # 振幅 → dB っぽい圧縮
        spectrum = np.log1p(spectrum * 8.0).astype(np.float32)

        bands = self.bands
        edges = self._band_edges
        band_vals = np.zeros(bands, dtype=np.float32)
        for i in range(bands):
            lo, hi = int(edges[i]), int(edges[i + 1])
            if hi <= lo:
                hi = lo + 1
            band_vals[i] = float(np.mean(spectrum[lo:hi]))

        # 正規化（相対）
        mx = float(np.max(band_vals)) if band_vals.size else 0.0
        if mx > 1e-6:
            band_vals = band_vals / (mx * 0.85 + 1e-6)
        band_vals = np.clip(band_vals, 0.0, 1.5)

        # アタック速め / リリース遅め
        attack, release = 0.55, 0.18
        for i in range(bands):
            target = band_vals[i]
            coeff = attack if target > self._smooth[i] else release
            self._smooth[i] += (target - self._smooth[i]) * coeff

        # 帯域エネルギー
        b = bands
        bass_raw = float(np.mean(self._smooth[: max(1, b // 8)]))
        mid_raw = float(np.mean(self._smooth[b // 8 : b // 2]))
        treble_raw = float(np.mean(self._smooth[b // 2 :]))

        def env(prev: float, raw: float, atk: float = 0.6, rel: float = 0.12) -> float:
            c = atk if raw > prev else rel
            return prev + (raw - prev) * c

        self._env_bass = env(self._env_bass, bass_raw)
        self._env_mid = env(self._env_mid, mid_raw)
        self._env_treble = env(self._env_treble, treble_raw)
        self._env_rms = env(self._env_rms, min(1.0, rms * 4.0), 0.5, 0.15)

        # 単純ビート: バスの立ち上がり
        delta = max(0.0, self._env_bass - self._prev_bass)
        self._prev_bass = self._env_bass
        if delta > 0.045 and self._env_bass > 0.12:
            self._beat_env = min(1.0, self._beat_env + delta * 6.0)
        self._beat_env *= 0.88

        with self._lock:
            self._analysis.spectrum = self._smooth.copy()
            self._analysis.waveform = wave.astype(np.float32)
            self._analysis.bass = self._env_bass
            self._analysis.mid = self._env_mid
            self._analysis.treble = self._env_treble
            self._analysis.rms = self._env_rms
            self._analysis.peak = peak
            self._analysis.beat = self._beat_env
            self._analysis.ready = True
