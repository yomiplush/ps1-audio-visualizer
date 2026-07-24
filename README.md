# SoundOrbit

Fullscreen **3D system-audio visualizer** with a PlayStation 1–style look (fixed low internal resolution, nearest-neighbor upscale).

It captures the default PipeWire (PulseAudio-compatible) output monitor and reacts to whatever is playing on the system—browser, music player, games, and so on.

Designed for **GNOME** (Wayland or X11). Python app—no native compile step; install system packages, then run or install for the current user.

## Requirements

| Component | Notes |
|-----------|--------|
| Python | 3.11+ |
| Desktop | GNOME recommended (GTK4 / libadwaita) |
| Audio | PipeWire + PulseAudio compatibility (`parec`, `pactl`) |
| Graphics | OpenGL 3.3+ (via PyOpenGL + GTK `GLArea`) |

### Runtime libraries

- GTK 4 + libadwaita
- PyGObject (`python-gobject` / `python3-gi`)
- NumPy
- PyOpenGL
- `parec` / `pactl` (from PipeWire Pulse or PulseAudio utils)

---

## Dependencies by distribution

### Arch Linux / CachyOS

```bash
sudo pacman -S --needed \
  gtk4 libadwaita \
  python python-gobject python-numpy python-opengl \
  pipewire pipewire-pulse
```

`parec` and `pactl` come with `pipewire-pulse`.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y \
  python3 python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-1 libadwaita-1-0 \
  python3-numpy python3-opengl \
  pipewire pipewire-pulse pipewire-audio-client-libraries \
  pulseaudio-utils
```

Notes:

- `python3-gi` + `gir1.2-*` provide the GTK4 / Adwaita bindings.
- `pulseaudio-utils` provides `parec` and `pactl` (works with PipeWire’s PulseAudio layer).
- On older Debian releases, package names for libadwaita / GIR may differ slightly; install whatever provides `Adw-1` and `Gtk-4.0` introspection.

### Fedora

```bash
sudo dnf install -y \
  python3 python3-gobject \
  gtk4 libadwaita \
  python3-numpy python3-pyopengl \
  pipewire pipewire-pulseaudio \
  pulseaudio-utils
```

Notes:

- On Fedora, PyOpenGL is typically `python3-pyopengl`.
- `pipewire-pulseaudio` + `pulseaudio-utils` give you the Pulse-compatible tools (`parec`, `pactl`).

### Verify dependencies

```bash
python3 - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: F401
import numpy  # noqa: F401
from OpenGL import GL  # noqa: F401
print("deps ok")
PY
command -v parec && command -v pactl
```

---

## Get the source

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
```

(Or use your existing checkout, e.g. `~/Projects/sound-orbit`.)

---

## Install (user-local, app menu)

No root required for the app itself—copies into `~/.local`:

```bash
chmod +x install.sh sound-orbit
./install.sh
```

Then:

- Run: `sound-orbit`
- Or open **Sound Orbit** / **サウンドオービット** from the GNOME app menu

Ensure `~/.local/bin` is on your `PATH`:

```bash
# bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

# fish
fish_add_path ~/.local/bin
```

### Run without installing

```bash
python3 ./sound-orbit
```

---

## Controls

| Key | Action |
|-----|--------|
| `Esc` / `Ctrl+Q` | Quit |
| `F11` / `F` | Toggle fullscreen (starts fullscreen) |
| `Space` | Toggle auto camera orbit |
| `H` / click | Show help |

---

## Quality & ECO

On startup, SoundOrbit probes CPU / memory / GPU (integrated, VRAM, etc.) and picks **low** / **medium** / **high** / **ultra**.

**ECO is on by default** (one step down: lower FPS / FBO / particles to cut heat). Integrated GPUs are biased more conservatively.

Override with environment variables:

```bash
SOUNDORBIT_QUALITY=low sound-orbit       # low | medium | high | ultra
SOUNDORBIT_ECO=0 sound-orbit             # disable ECO bias
SOUNDORBIT_INTERNAL=320x240 sound-orbit  # fixed internal res (default PS1-style)
SOUNDORBIT_INTERNAL=off sound-orbit      # window-proportional FBO
```

Internally the scene is drawn at a **PS1-class fixed resolution** and stretched with **nearest-neighbor** (chunky pixels). No FSR-style clean upscaling.

### Memory watchdog

While running, RSS growth is monitored. If it climbs too much:

1. Clear particles and trail buffers (purge)
2. Run Python GC
3. Throttle FPS / particle spawn / trails

Status line shows `rss=…MB`, `thr`, `purge×N` when relevant.

---

## How it works

1. Capture the default sink’s `.monitor` via `parec` (`pactl get-default-sink`)
2. Hann-windowed FFT → 96 logarithmic bands
3. GTK4 `Gtk.GLArea` + OpenGL 3.3: circular spectrum, center orb, rings, particles
4. Offscreen trails + RGB-split post (simplified at lower quality)

---

## License

MIT — see [LICENSE](LICENSE).
