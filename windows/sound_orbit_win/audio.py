"""Windows system-playback capture (loopback only) + FFT.

Primary: ``soundcard`` (WASAPI loopback — works with Realtek / Intel / BT / HDMI).
Never opens a microphone. sounddevice mic fallback removed.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

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


def _classify(name: str) -> str:
    low = (name or "").lower()
    if "bluetooth" in low or "hands-free" in low or "a2dp" in low or "bthhf" in low:
        return "bluetooth"
    if "realtek" in low:
        return "realtek"
    if "intel" in low:
        return "intel"
    if "nvidia" in low:
        return "nvidia"
    if "amd" in low or "radeon" in low:
        return "amd"
    if "hdmi" in low or "displayport" in low:
        return "hdmi"
    if "usb" in low:
        return "usb"
    return "other"


def _score_loopback_name(name: str, is_default: bool) -> int:
    low = (name or "").lower()
    s = 0
    if is_default:
        s += 1000
    if any(k in low for k in ("speaker", "headphone", "headset", "realtek")):
        s += 80
    if "bluetooth" in low:
        s += 40
    if "stereo mix" in low or "what u hear" in low:
        s += 30
    # Deprioritize obscure hands-free AG (often wrong endpoint)
    if "hands-free" in low and "speaker" not in low:
        s -= 40
    if "mapper" in low or "primary sound" in low:
        s -= 60
    return s


@dataclass(frozen=True)
class LoopbackMic:
    """A soundcard 'microphone' that is actually a render-device loopback."""

    mic: Any
    name: str
    kind: str
    is_default: bool
    score: int


def list_soundcard_loopbacks() -> list[LoopbackMic]:
    import soundcard as sc

    default_speaker = None
    try:
        default_speaker = sc.default_speaker()
    except Exception:
        pass
    default_name = getattr(default_speaker, "name", None) if default_speaker else None

    out: list[LoopbackMic] = []
    try:
        mics = sc.all_microphones(include_loopback=True)
    except TypeError:
        # very old soundcard
        mics = sc.all_microphones()

    for mic in mics:
        name = str(getattr(mic, "name", "") or "")
        # Prefer explicit loopback flag when present
        is_loop = bool(getattr(mic, "isloopback", False))
        # soundcard names loopbacks often as same as speaker name when include_loopback=True
        # Non-loopback pure mics: skip if clearly mic-only
        if not is_loop:
            low = name.lower()
            # Without isloopback attribute, include_loopback=True still returns loopbacks;
            # pure mics usually contain these:
            if any(
                k in low
                for k in (
                    "microphone",
                    "mic array",
                    "webcam",
                    "camera",
                    "internal mic",
                    "external mic",
                )
            ) and "loopback" not in low:
                # Might still be a misnamed loopback; only skip if not matching any speaker
                try:
                    speakers = [s.name for s in sc.all_speakers()]
                    if name not in speakers and not any(name in s or s in name for s in speakers):
                        continue
                except Exception:
                    continue

        is_default = False
        if default_name:
            if name == default_name or default_name in name or name in default_name:
                is_default = True
        kind = _classify(name)
        score = _score_loopback_name(name, is_default)
        if is_loop:
            score += 100
        out.append(LoopbackMic(mic=mic, name=name, kind=kind, is_default=is_default, score=score))

    # If nothing marked loopback, try mapping each speaker to a mic via get_microphone(..., include_loopback=True)
    if not out or all(not getattr(m.mic, "isloopback", False) for m in out):
        try:
            for sp in sc.all_speakers():
                try:
                    mic = sc.get_microphone(id=str(sp.id), include_loopback=True)
                except Exception:
                    try:
                        mic = sc.get_microphone(id=str(sp.name), include_loopback=True)
                    except Exception:
                        continue
                name = str(getattr(mic, "name", sp.name) or sp.name)
                is_default = bool(
                    default_speaker is not None
                    and (sp.id == getattr(default_speaker, "id", None) or sp.name == default_name)
                )
                kind = _classify(name)
                score = _score_loopback_name(name, is_default) + 150
                out.append(
                    LoopbackMic(
                        mic=mic, name=name, kind=kind, is_default=is_default, score=score
                    )
                )
        except Exception as exc:
            print(f"speaker→loopback map failed: {exc}", file=sys.stderr)

    # Dedupe by name keeping highest score
    best: dict[str, LoopbackMic] = {}
    for m in out:
        key = m.name.strip().lower()
        if key not in best or m.score > best[key].score:
            best[key] = m
    ranked = sorted(best.values(), key=lambda m: (-m.score, m.name))
    return ranked


def _log_loopbacks(cands: list[LoopbackMic]) -> None:
    print("==> Playback loopback candidates (mic excluded):", file=sys.stderr)
    for m in cands[:30]:
        mark = "*" if m.is_default else " "
        loop = "loop" if getattr(m.mic, "isloopback", False) else "map"
        print(
            f"  {mark} {m.kind:10} score={m.score:4} [{loop}] {m.name}",
            file=sys.stderr,
        )


class SystemAudioCapture:
    """
    Capture system playback via WASAPI loopback (soundcard).

    - Detects Realtek / Intel HD / Bluetooth / HDMI / USB outputs
    - Prefers Windows default speaker loopback
    - Never opens a real microphone
    - Rebinds when default speaker changes
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
        self._active_name: str = ""

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
        self._thread = threading.Thread(target=self._run, name="soundorbit-loopback", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
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

    def _record_loop(self, mic: Any, name: str, kind: str) -> None:
        """Blocking record until stop or error."""
        rates = [self.sample_rate, 48000, 44100, 96000]
        last_err: Optional[Exception] = None
        for rate in rates:
            if self._stop.is_set():
                return
            try:
                # channels: try stereo then mono
                for ch in (2, 1):
                    if self._stop.is_set():
                        return
                    try:
                        with mic.recorder(samplerate=rate, channels=ch, blocksize=CHUNK_FRAMES) as rec:
                            self.sample_rate = rate
                            self._band_edges = self._make_band_edges(self.bands, self.fft_size, rate)
                            self._window = np.hanning(self.fft_size).astype(np.float32)
                            self._active_name = name
                            with self._lock:
                                self._analysis.source_name = f"loopback:{kind}:{name}"
                                self._analysis.error = None
                            print(
                                f"==> Loopback OK: {kind} — {name} @ {rate} Hz ch={ch}",
                                file=sys.stderr,
                            )
                            while not self._stop.is_set():
                                data = rec.record(numframes=CHUNK_FRAMES)
                                arr = np.asarray(data, dtype=np.float32)
                                if arr.ndim == 2:
                                    mono = arr.mean(axis=1)
                                else:
                                    mono = arr.reshape(-1)
                                self._push_samples(mono)
                                self._analyze()
                            return
                    except Exception as exc:
                        last_err = exc
                        continue
            except Exception as exc:
                last_err = exc
                continue
        raise RuntimeError(str(last_err) if last_err else "recorder open failed")

    def _run(self) -> None:
        try:
            import soundcard as sc  # noqa: F401
        except Exception as exc:
            with self._lock:
                self._analysis.error = (
                    f"soundcard import failed: {exc}. "
                    "Install: pip install soundcard"
                )
            return

        while not self._stop.is_set():
            try:
                cands = list_soundcard_loopbacks()
            except Exception as exc:
                with self._lock:
                    self._analysis.error = f"device enum failed: {exc}"
                time.sleep(1.0)
                continue

            if not cands:
                with self._lock:
                    self._analysis.error = (
                        "No playback loopback found (mic ignored). "
                        "Check Speakers/Headphones in Windows sound settings."
                    )
                time.sleep(1.5)
                continue

            _log_loopbacks(cands)
            errors: list[str] = []
            opened = False
            for cand in cands:
                if self._stop.is_set():
                    return
                try:
                    self._record_loop(cand.mic, cand.name, cand.kind)
                    opened = True
                    break  # stopped cleanly
                except Exception as exc:
                    errors.append(f"{cand.name}: {exc}")
                    print(f"  loopback fail [{cand.kind}] {cand.name}: {exc}", file=sys.stderr)
                    continue

            if self._stop.is_set():
                return

            if not opened:
                with self._lock:
                    self._analysis.error = (
                        "WASAPI loopback failed on all playback devices "
                        "(microphone is NOT used).\n" + "\n".join(errors[:8])
                    )
                    self._analysis.ready = False
                time.sleep(2.0)
                # retry enum (device may appear later)
                continue

            # If _record_loop returned without stop, default device may have changed — re-enum
            time.sleep(0.3)
