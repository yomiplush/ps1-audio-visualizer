# SoundOrbit

Fullscreen **3D system-audio visualizer** — PS1-style chunky pixels, CRT scanlines / barrel warp / afterimage. Reacts to **system audio** (browser, music, games) via PipeWire.

**No compile.** Download the AppImage → run.

---

## Install (AppImage)

### 1. Download

**[Latest Release](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest)**  
→ `SoundOrbit-<version>-x86_64.AppImage`

### 2. Run

```bash
chmod +x SoundOrbit-*-x86_64.AppImage
./SoundOrbit-*-x86_64.AppImage
```

### What the smart AppImage does

| Step | Behavior |
|------|----------|
| **GPU detect** | AMD / NVIDIA / Intel (UHD, Iris, Arc) / hybrid |
| **Host packages** | Asks once to install GTK4 + **vendor-specific GL stack** |
| **Isolated venv** | `~/.local/share/sound-orbit/venv` with `PYTHONNOUSERSITE=1` (avoids `~/.local` pip fights). Uses system GTK/gi via `--system-site-packages` |
| **GL env** | Soft defaults per GPU (e.g. NVIDIA GLVND). Wayland+NVIDIA can retry `GDK_BACKEND=x11` |

> **Note:** A Python venv cannot ship GPU *drivers*. OpenGL still needs host Mesa / NVIDIA. Isolation fixes **Python package conflicts**; GPU packages fix **“Unable to create a GL Context”**.

### Optional menu entry

```bash
SOUNDORBIT_INSTALL=1 ./SoundOrbit-*-x86_64.AppImage
```

---

## GPU packages (auto or manual)

### Arch / CachyOS

**Always (base):**

```bash
sudo pacman -S --needed \
  gtk4 libadwaita \
  python python-gobject python-cairo python-numpy python-opengl python-pip \
  pipewire pipewire-pulse mesa libepoxy libglvnd
```

| GPU | Extra packages |
|-----|----------------|
| **AMD** | `mesa-utils vulkan-radeon libva-mesa-driver mesa-vdpau` |
| **NVIDIA** | `nvidia-utils egl-wayland libvdpau` (+ matching **kernel** `nvidia` module you already use) |
| **Intel** (UHD / Iris / Arc) | `mesa-utils vulkan-intel intel-media-driver` |

Force package prompt again:

```bash
rm -f ~/.local/share/sound-orbit/pkgs.stamp
SOUNDORBIT_INSTALL_PKGS=1 ./SoundOrbit-*.AppImage
```

---

## If you see “Unable to create a GL Context”

Try in order:

```bash
# 1) X11 backend (helps many Wayland + NVIDIA setups)
GDK_BACKEND=x11 ./SoundOrbit-*.AppImage

# 2) Force software GL (slow, but proves the app works)
LIBGL_ALWAYS_SOFTWARE=1 ./SoundOrbit-*.AppImage

# 3) Or set permanently for this launcher
SOUNDORBIT_GL=x11 ./SoundOrbit-*.AppImage        # x11 | wayland | software | auto
```

Also install the **GPU row** in the package table above, then:

```bash
rm -rf ~/.local/share/sound-orbit/venv ~/.local/share/sound-orbit/env.stamp
./SoundOrbit-*.AppImage
```

---

## Controls

| Key | Action |
|-----|--------|
| `Esc` / `Ctrl+Q` | Quit |
| `F11` / `F` | Fullscreen |
| `Space` | Camera orbit on/off |
| `H` / click | Help |

---

## Environment variables

```bash
# Quality / look
SOUNDORBIT_QUALITY=low|medium|high|ultra
SOUNDORBIT_ECO=0
SOUNDORBIT_INTERNAL=240x180   # or 160x120 / off
SOUNDORBIT_CRT=0
SOUNDORBIT_TRAIL=0

# AppImage smart launcher
SOUNDORBIT_GL=auto|x11|wayland|software
SOUNDORBIT_VENV=$HOME/.local/share/sound-orbit/venv
SOUNDORBIT_SKIP_PKGS=1        # never prompt for packages
SOUNDORBIT_INSTALL_PKGS=1     # force package install prompt
SOUNDORBIT_INSTALL=1          # also install desktop entry
```

---

## Developers

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage

# From source (host packages required):
PYTHONNOUSERSITE=1 python3 ./sound-orbit
```

---

## License

MIT — see [LICENSE](LICENSE).
