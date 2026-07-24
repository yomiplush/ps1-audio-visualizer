"""Windows WASAPI loopback capture + FFT analysis (system audio)."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

SAMPLE_RATE = 48_000
CHANNELS = 2
FFT_SIZE = 2048
BANDS = 96
CHUNK_FRAMES = 1024


@dataclass
class AudioAnalysis:
    spectrum: np.ndarray = field(default_factory=lambda: np.zeros(BANDS, dtype=np.float32))
    waveform: np.ndarray = field(default_factory=lambda: np.zeros(256, dtype=np.float32))
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    rms: float = 0.0
    peak: float = 0.0
    beat: float = 0.0
    ready: bool = False
    error: Optional[str] = None
    source_name: str = ""


class SystemAudioCapture:
    """
    Capture default output (what you hear) via WASAPI loopback (sounddevice).
    Falls back to default input if loopback is unavailable.
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
        self._stream = None

        self._ring = np.zeros(fft_size * 4, dtype=np.float32)
        self._ring_pos = 0
        self._analysis = AudioAnalysis(
            spectrum=np.zeros(bands, dtype=np.float32),
            waveform=np.zeros(256, dtype=np.float32),
        )
        self._smooth = np.zeros(bands, dtype=np.float32)
        self._env_bass = 0.0
        self._env_mid = 0.0
        self._env_treble = 0.0
        self._env_rms = 0.0
        self._beat_env = 0.0
        self._prev_bass = 0.0
        self._band_edges = self._make_band_edges(bands, fft_size, sample_rate)
        self._window = np.hanning(fft_size).astype(np.float32)

    @staticmethod
    def _make_band_edges(bands: int, fft_size: int, sample_rate: int) -> np.ndarray:
        n_bins = fft_size // 2
        f_min, f_max = 30.0, sample_rate * 0.48
        edges_hz = np.geomspace(f_min, f_max, bands + 1)
        hz_per_bin = sample_rate / fft_size
        edges = np.clip(edges_hz / hz_per_bin, 1, n_bins - 1).astype(np.int32)
        for i in range(1, len(edges)):
            if edges[i] <= edges[i - 1]:
                edges[i] = min(edges[i - 1] + 1, n_bins - 1)
        return edges

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="soundorbit-wasapi", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        stream = self._stream
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

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

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            with self._lock:
                self._analysis.error = f"sounddevice import failed: {exc}"
            return

        device = None
        name = "default-output-loopback"
        try:
            # Prefer WASAPI loopback of default output
            wasapi = None
            try:
                wasapi = sd.WasapiSettings(loopback=True)
            except Exception:
                wasapi = None

            if wasapi is not None:
                try:
                    default_out = sd.default.device[1] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
                    dev = sd.query_devices(default_out)
                    name = f"loopback:{dev.get('name', default_out)}"
                    self._stream = sd.InputStream(
                        samplerate=self.sample_rate,
                        channels=CHANNELS,
                        dtype="float32",
                        blocksize=CHUNK_FRAMES,
                        device=default_out,
                        extra_settings=wasapi,
                        callback=self._callback,
                    )
                    device = default_out
                except Exception as exc:
                    # Fall back to default input
                    with self._lock:
                        self._analysis.error = f"WASAPI loopback failed ({exc}); trying default input"
                    self._stream = None

            if self._stream is None:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=min(2, sd.query_devices(kind="input")["max_input_channels"] or 1),
                    dtype="float32",
                    blocksize=CHUNK_FRAMES,
                    callback=self._callback,
                )
                name = "default-input"

            with self._lock:
                self._analysis.source_name = name
                if device is not None or name == "default-input":
                    # clear soft error if we recovered
                    if self._analysis.error and "trying default input" in (self._analysis.error or ""):
                        pass
                    else:
                        self._analysis.error = None

            self._stream.start()
            while not self._stop.is_set():
                time.sleep(0.05)
                self._analyze()
        except Exception as exc:
            with self._lock:
                self._analysis.error = str(exc)
        finally:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            pass
        data = np.asarray(indata, dtype=np.float32)
        if data.ndim == 2:
            mono = data.mean(axis=1)
        else:
            mono = data.reshape(-1)
        self._push_samples(mono)

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

        wave_n = 256
        step = max(1, block.shape[0] // wave_n)
        wave = block[::step][:wave_n]
        if wave.shape[0] < wave_n:
            wave = np.pad(wave, (0, wave_n - wave.shape[0]))

        windowed = block * self._window
        spectrum = np.abs(np.fft.rfft(windowed))
        spectrum = np.log1p(spectrum * 8.0).astype(np.float32)

        bands = self.bands
        edges = self._band_edges
        band_vals = np.zeros(bands, dtype=np.float32)
        for i in range(bands):
            lo, hi = int(edges[i]), int(edges[i + 1])
            if hi <= lo:
                hi = lo + 1
            band_vals[i] = float(np.mean(spectrum[lo:hi]))

        mx = float(np.max(band_vals)) if band_vals.size else 0.0
        if mx > 1e-6:
            band_vals = band_vals / (mx * 0.85 + 1e-6)
        band_vals = np.clip(band_vals, 0.0, 1.5)

        attack, release = 0.55, 0.18
        for i in range(bands):
            target = band_vals[i]
            coeff = attack if target > self._smooth[i] else release
            self._smooth[i] += (target - self._smooth[i]) * coeff

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
