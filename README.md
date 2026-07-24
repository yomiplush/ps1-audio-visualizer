# SoundOrbit

Fullscreen **3D system-audio visualizer** with a PlayStation 1–style look (fixed low internal resolution, nearest-neighbor upscale).

It captures the default PipeWire (PulseAudio-compatible) output monitor and reacts to whatever is playing on the system—browser, music player, games, and so on.

Designed for **GNOME** (Wayland or X11). Works on other desktops too if GTK4 / libadwaita are installed.

> **Important: there is nothing to compile.**  
> SoundOrbit is a pure **Python** app. No `make`, `cmake`, `gcc`, or build step.

---

## Easiest: AppImage (recommended)

One file. Download → mark executable → run.

```bash
# From GitHub Releases (example):
chmod +x SoundOrbit-*-x86_64.AppImage
./SoundOrbit-*-x86_64.AppImage
```

On first launch, if GTK / numpy / OpenGL packages are missing, the AppImage **offers to install them** via your package manager (pacman / apt / dnf; polkit password once).

Optional: also install a menu entry into `~/.local`:

```bash
SOUNDORBIT_INSTALL=1 ./SoundOrbit-*-x86_64.AppImage
```

### Build the AppImage yourself

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage
```

The AppImage is intentionally **thin** (~1 MB): it ships the app and a smart launcher; graphics/audio stacks stay on the host (correct for OpenGL + PipeWire).

---

## Requirements

| Component | Notes |
|-----------|--------|
| Python | 3.11+ (system package; **do not use a venv**) |
| Desktop | GNOME recommended (GTK4 / libadwaita) |
| Audio | PipeWire + PulseAudio compatibility (`parec`, `pactl`) |
| Graphics | OpenGL 3.3+ (Mesa + PyOpenGL + GTK `GLArea`) |

### Runtime libraries

- GTK 4 + libadwaita
- PyGObject (`python-gobject`)
- NumPy (`python-numpy`)
- PyOpenGL (`python-opengl`)
- Cairo bindings recommended (`python-cairo`) for text labels
- `parec` / `pactl` (from `pipewire-pulse`)

---

## From source (Arch Linux / CachyOS)

If you prefer git over AppImage, copy-paste in order:

```bash
# 1) Dependencies (system packages only — no pip / venv)
sudo pacman -S --needed \
  git \
  gtk4 libadwaita \
  python python-gobject python-cairo python-numpy python-opengl \
  pipewire pipewire-pulse mesa

# 2) Source
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer

# 3) Install for current user (~/.local) — not a compile step
chmod +x install.sh sound-orbit
./install.sh

# 4) Run
# If ~/.local/bin is on PATH:
sound-orbit
# Or always works:
~/.local/bin/sound-orbit
# Or without install, from the repo directory:
python3 ./sound-orbit
```

### PATH (if `sound-orbit` is “command not found”)

```bash
# fish
fish_add_path ~/.local/bin

# bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

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

If any import fails, reinstall the matching **pacman** package (not pip).

---

## Dependencies by distribution

### Arch Linux / CachyOS

```bash
sudo pacman -S --needed \
  gtk4 libadwaita \
  python python-gobject python-cairo python-numpy python-opengl \
  pipewire pipewire-pulse mesa
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

### Fedora

```bash
sudo dnf install -y \
  python3 python3-gobject \
  gtk4 libadwaita \
  python3-numpy python3-pyopengl python3-cairo \
  pipewire pipewire-pulseaudio \
  pulseaudio-utils mesa-libGL
```

---

## Get the source

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
```

(Or use an existing checkout, e.g. `~/Projects/sound-orbit`.)

---

## Install (user-local, app menu)

No root required for the app itself—copies into `~/.local`:

```bash
chmod +x install.sh sound-orbit
./install.sh
```

Then:

- Run: `sound-orbit` or `~/.local/bin/sound-orbit`
- Or open **Sound Orbit** / **サウンドオービット** from the app menu

### Run without installing

From the repository root:

```bash
python3 ./sound-orbit
```

---

## Troubleshooting (CachyOS / Arch)

### “コンパイルできない / make がない / cmake がない”

正常です。**ビルド不要**です。`./install.sh` はファイルを `~/.local` にコピーするだけです。

### `./install.sh` が `deps` / import で失敗する

`install.sh` は足りないモジュール名を表示します。venv や `pip install` は使わず:

```bash
sudo pacman -S --needed \
  python-gobject python-cairo python-numpy python-opengl \
  gtk4 libadwaita mesa
```

特に:

| エラーの例 | 入れるパッケージ |
|-----------|------------------|
| `No module named 'gi'` | `python-gobject` |
| `Adw` / `Gtk` namespace | `gtk4` `libadwaita` |
| `No module named 'numpy'` | `python-numpy` |
| `No module named 'OpenGL'` | `python-opengl` |
| `parec` not found | `pipewire-pulse` |

### `sound-orbit: command not found`

```bash
~/.local/bin/sound-orbit
# or
fish_add_path ~/.local/bin   # fish
```

### ウィンドウは出るが真っ黒 / OpenGL エラー

```bash
sudo pacman -S --needed mesa
# NVIDIA プロプライエタリドライバ利用時はドライバが最新か確認
```

### 音に反応しない

```bash
pactl get-default-sink
# 何か再生しながら:
parec --device="$(pactl get-default-sink).monitor" --raw | head -c 100 | wc -c
```

PipeWire が動いていること、デフォルト出力が正しいことを確認してください。

### venv を使ってしまった

システムに入っている GTK / GI と切り離されるため、**非推奨**です。venv を無効にして、上記の `pacman` パッケージだけで起動してください。

```bash
deactivate  # if inside a venv
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

On startup, SoundOrbit probes CPU / memory / GPU and picks **low** / **medium** / **high** / **ultra**.

**ECO is on by default** (one step down). Integrated GPUs are biased more conservatively.

```bash
SOUNDORBIT_QUALITY=low sound-orbit       # low | medium | high | ultra
SOUNDORBIT_ECO=0 sound-orbit             # disable ECO bias
SOUNDORBIT_INTERNAL=240x180 sound-orbit  # fixed internal res (chunky default)
SOUNDORBIT_INTERNAL=160x120 sound-orbit  # even more jagged
SOUNDORBIT_INTERNAL=off sound-orbit      # window-proportional FBO
SOUNDORBIT_CRT=0 sound-orbit             # disable CRT look
SOUNDORBIT_CRT_BARREL=0.16 sound-orbit
SOUNDORBIT_CRT_SCANLINE=0.92 sound-orbit
SOUNDORBIT_CRT_VIGNETTE=0.62 sound-orbit
SOUNDORBIT_TRAIL=0 sound-orbit           # disable afterimage
SOUNDORBIT_TRAIL_MIX=0.78 sound-orbit
SOUNDORBIT_TRAIL_DECAY=0.93 sound-orbit
```

Internally the scene is drawn at a **PS1-class fixed resolution** and stretched with **nearest-neighbor**.

### Memory watchdog

If RSS climbs too much: purge particles/trails, run GC, throttle FPS.

---

## How it works

1. Capture the default sink’s `.monitor` via `parec`
2. Hann-windowed FFT → 96 logarithmic bands
3. GTK4 `Gtk.GLArea` + OpenGL 3.3 visualizer
4. Offscreen trails + CRT post (scanlines, barrel, vignette)

---

## License

MIT — see [LICENSE](LICENSE).
