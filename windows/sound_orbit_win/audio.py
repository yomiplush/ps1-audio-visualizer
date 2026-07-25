"""Windows WASAPI *loopback only* — system playback (what you hear), never microphone."""

from __future__ import annotations

import re
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

# Name hints for logging / prioritization (not exclusive filters)
_VENDOR_HINTS = (
    "realtek",
    "intel",
    "nvidia",
    "amd",
    "bluetooth",
    "hands-free",
    "headset",
    "airpods",
    "sony",
    "bose",
    "jabra",
    "logitech",
    "steelseries",
    "razer",
    "hyperx",
    "corsair",
    "usb",
    "hdmi",
    "displayport",
    "dp audio",
    "nvidia high definition",
    "amd high definition",
    "high definition audio",
    "speakers",
    "headphone",
    "earphone",
    "output",
    "digital audio",
    "spdif",
    "optical",
)


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


@dataclass(frozen=True)
class OutputCandidate:
    index: int
    name: str
    hostapi_name: str
    max_out: int
    default_samplerate: float
    is_default_out: bool
    score: int
    kind: str  # realtek|intel|bluetooth|hdmi|usb|other


def _classify_output_name(name: str) -> str:
    low = name.lower()
    if "bluetooth" in low or "hands-free ag audio" in low or "a2dp" in low:
        return "bluetooth"
    if "realtek" in low:
        return "realtek"
    if "intel" in low:
        return "intel"
    if "nvidia" in low:
        return "hdmi" if ("hdmi" in low or "display" in low) else "nvidia"
    if "amd" in low or "radeon" in low:
        return "hdmi" if ("hdmi" in low or "display" in low) else "amd"
    if "hdmi" in low or "displayport" in low or "dp audio" in low:
        return "hdmi"
    if "usb" in low:
        return "usb"
    return "other"


def _score_output(name: str, is_default: bool, kind: str) -> int:
    """Higher = try earlier for loopback."""
    s = 0
    low = name.lower()
    if is_default:
        s += 1000
    # Prefer real speaker/headphone endpoints over obscure virtual devices
    if any(k in low for k in ("speaker", "headphone", "headset", "earphone", "realtek")):
        s += 80
    if kind == "bluetooth":
        s += 40  # valid when user listens via BT
    if kind in ("hdmi", "nvidia", "amd"):
        s += 30
    if kind == "usb":
        s += 50
    if kind == "intel":
        s += 35
    # Deprioritize likely non-playback or capture-adjacent names
    if any(k in low for k in ("microphone", "mic ", "array", "webcam", "camera")):
        s -= 500  # should already be filtered as no outputs
    if any(k in low for k in ("mapper", "primary sound driver", "dummy", "null")):
        s -= 50
    if "stereo mix" in low or "what u hear" in low or "wave out mix" in low:
        s += 20  # rare legacy mix devices (still output-side)
    return s


def list_loopback_candidates(sd: Any) -> list[OutputCandidate]:
    """All *output* devices we can open with WASAPI loopback (never pure mics)."""
    hostapis = sd.query_hostapis()
    wasapi_indices = {
        i for i, h in enumerate(hostapis) if "wasapi" in str(h.get("name", "")).lower()
    }

    try:
        default_out = sd.default.device[1]
    except Exception:
        default_out = None

    devices = sd.query_devices()
    cands: list[OutputCandidate] = []
    for idx, dev in enumerate(devices):
        max_out = int(dev.get("max_output_channels") or 0)
        if max_out <= 0:
            continue  # microphone / input-only — skip entirely
        # Prefer WASAPI hostapi when present; still list others as last resort
        hostapi = int(dev.get("hostapi", -1))
        ha_name = ""
        try:
            ha_name = str(hostapis[hostapi].get("name", ""))
        except Exception:
            ha_name = str(hostapi)
        name = str(dev.get("name", f"device-{idx}"))
        kind = _classify_output_name(name)
        is_def = default_out is not None and idx == default_out
        score = _score_output(name, is_def, kind)
        if hostapi in wasapi_indices:
            score += 200  # WASAPI first
        elif "mme" in ha_name.lower():
            score -= 30
        elif "directsound" in ha_name.lower() or "dsound" in ha_name.lower():
            score -= 20
        cands.append(
            OutputCandidate(
                index=idx,
                name=name,
                hostapi_name=ha_name,
                max_out=max_out,
                default_samplerate=float(dev.get("default_samplerate") or SAMPLE_RATE),
                is_default_out=is_def,
                score=score,
                kind=kind,
            )
        )

    cands.sort(key=lambda c: (-c.score, c.index))
    return cands


def _log_candidates(cands: list[OutputCandidate]) -> None:
    print("==> Playback devices (loopback candidates, mic excluded):", file=sys.stderr)
    for c in cands[:24]:
        mark = "*" if c.is_default_out else " "
        print(
            f"  {mark} [{c.index}] {c.kind:10} score={c.score:4}  "
            f"{c.name}  ({c.hostapi_name}, out={c.max_out}ch)",
            file=sys.stderr,
        )
    if len(cands) > 24:
        print(f"  … +{len(cands) - 24} more", file=sys.stderr)


class SystemAudioCapture:
    """
    Capture *what you hear* via WASAPI loopback on output devices only.

    - Enumerates Realtek / Intel HD Audio / Bluetooth / HDMI / USB / etc.
    - Prefers Windows default playback device
    - Tries other outputs if default loopback fails
    - NEVER opens microphone / input-only devices
    - Re-binds if the default output changes (e.g. plug in BT headphones)
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
        self._device_index: Optional[int] = None
        self._device_name: str = ""

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
        self._close_stream()
        if self._thread is not None:
            self._thread.join(timeout=2.5)
            self._thread = None

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

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

    def _open_loopback(self, sd: Any, cand: OutputCandidate) -> Any:
        """Open WASAPI loopback InputStream on an *output* device. Raises on failure."""
        try:
            wasapi = sd.WasapiSettings(loopback=True)
        except Exception as exc:
            raise RuntimeError(f"WasapiSettings(loopback=True) unavailable: {exc}") from exc

        # Prefer device default rate when plausible, else 48k
        rates = []
        for r in (int(cand.default_samplerate), self.sample_rate, 48000, 44100):
            if r and r not in rates:
                rates.append(int(r))

        chans = min(CHANNELS, max(1, cand.max_out))
        last_err: Optional[Exception] = None
        for rate in rates:
            try:
                stream = sd.InputStream(
                    samplerate=rate,
                    channels=chans,
                    dtype="float32",
                    blocksize=CHUNK_FRAMES,
                    device=cand.index,
                    extra_settings=wasapi,
                    callback=self._callback,
                )
                self.sample_rate = rate
                # rebuild window/edges if rate changed
                self._band_edges = self._make_band_edges(self.bands, self.fft_size, rate)
                self._window = np.hanning(self.fft_size).astype(np.float32)
                return stream
            except Exception as exc:
                last_err = exc
                continue
        raise RuntimeError(str(last_err) if last_err else "loopback open failed")

    def _bind_best_loopback(self, sd: Any) -> tuple[Any, OutputCandidate]:
        cands = list_loopback_candidates(sd)
        if not cands:
            raise RuntimeError(
                "No playback (output) devices found for WASAPI loopback. "
                "Microphone-only devices are intentionally ignored."
            )
        _log_candidates(cands)
        errors: list[str] = []
        for cand in cands:
            try:
                stream = self._open_loopback(sd, cand)
                print(
                    f"==> Loopback OK: [{cand.index}] {cand.kind} — {cand.name} "
                    f"@ {self.sample_rate} Hz ({cand.hostapi_name})",
                    file=sys.stderr,
                )
                return stream, cand
            except Exception as exc:
                msg = f"[{cand.index}] {cand.name}: {exc}"
                errors.append(msg)
                print(f"  loopback fail {msg}", file=sys.stderr)
        raise RuntimeError(
            "Could not open WASAPI loopback on any playback device.\n" + "\n".join(errors[:12])
        )

    def _current_default_out_index(self, sd: Any) -> Optional[int]:
        try:
            d = sd.default.device
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                return int(d[1])
            return int(d) if d is not None else None
        except Exception:
            return None

    def _run(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            with self._lock:
                self._analysis.error = f"sounddevice import failed: {exc}"
            return

        try:
            stream, cand = self._bind_best_loopback(sd)
        except Exception as exc:
            with self._lock:
                self._analysis.error = (
                    f"Playback loopback failed (mic is NOT used): {exc}"
                )
                self._analysis.ready = False
            return

        self._stream = stream
        self._device_index = cand.index
        self._device_name = cand.name
        with self._lock:
            self._analysis.source_name = f"loopback:{cand.kind}:{cand.name}"
            self._analysis.error = None

        try:
            self._stream.start()
        except Exception as exc:
            with self._lock:
                self._analysis.error = f"stream.start failed: {exc}"
            self._close_stream()
            return

        # Watch for default-device changes (BT connect, HDMI plug, etc.)
        check_every = 2.0
        last_check = time.monotonic()
        while not self._stop.is_set():
            time.sleep(0.05)
            self._analyze()
            now = time.monotonic()
            if now - last_check < check_every:
                continue
            last_check = now
            try:
                new_default = self._current_default_out_index(sd)
                if (
                    new_default is not None
                    and self._device_index is not None
                    and new_default != self._device_index
                ):
                    # Default output switched — rebind to new device loopback
                    print(
                        f"==> Default output changed {self._device_index} → {new_default}, rebinding…",
                        file=sys.stderr,
                    )
                    self._close_stream()
                    stream, cand = self._bind_best_loopback(sd)
                    self._stream = stream
                    self._device_index = cand.index
                    self._device_name = cand.name
                    with self._lock:
                        self._analysis.source_name = f"loopback:{cand.kind}:{cand.name}"
                        self._analysis.error = None
                    self._stream.start()
            except Exception as exc:
                with self._lock:
                    self._analysis.error = f"rebind failed: {exc}"
                # keep trying analyze; next loop may recover
                try:
                    stream, cand = self._bind_best_loopback(sd)
                    self._stream = stream
                    self._device_index = cand.index
                    with self._lock:
                        self._analysis.source_name = f"loopback:{cand.kind}:{cand.name}"
                        self._analysis.error = None
                    self._stream.start()
                except Exception as exc2:
                    with self._lock:
                        self._analysis.error = f"No loopback device: {exc2}"

        self._close_stream()

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
