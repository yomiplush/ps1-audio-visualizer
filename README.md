# SoundOrbit

Fullscreen **3D system-audio visualizer** with a PlayStation 1–style look (chunky low internal resolution, nearest-neighbor upscale, CRT scanlines / barrel warp / afterimage).

Reacts to **whatever your PC is playing** (browser, music app, games, …) via PipeWire’s default output monitor.

**No compile. No package build. Download the AppImage and run it.**

---

## Install (AppImage)

### 1. Download

Get the latest **`SoundOrbit-*-x86_64.AppImage`** from:

**[Releases](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest)**

| File | What it is |
|------|------------|
| `SoundOrbit-<version>-x86_64.AppImage` | The app (recommended) |

### 2. Make it executable

```bash
chmod +x SoundOrbit-*-x86_64.AppImage
```

Some browsers / file managers clear the executable bit after download—this step is required.

### 3. Run

```bash
./SoundOrbit-*-x86_64.AppImage
```

Or from a file manager: double-click (if your desktop allows executing AppImages).

That’s it.

---

## First run (dependencies)

The AppImage is **thin** (~1 MB): it ships SoundOrbit and a launcher.  
**GTK 4, OpenGL, NumPy, and PipeWire tools stay on the host** (same idea as most Linux graphics apps—drivers and audio must match your system).

If anything required is missing, the launcher **asks once** and installs packages with your package manager (polkit password):

| Distro | Packages (installed automatically if you accept) |
|--------|---------------------------------------------------|
| **Arch / CachyOS** | `gtk4` `libadwaita` `python` `python-gobject` `python-cairo` `python-numpy` `python-opengl` `pipewire` `pipewire-pulse` `mesa` |
| **Ubuntu / Debian** | `python3-gi` `gir1.2-gtk-4.0` `gir1.2-adw-1` `python3-numpy` `python3-opengl` `pipewire-pulse` `pulseaudio-utils` … |
| **Fedora** | `python3-gobject` `gtk4` `libadwaita` `python3-numpy` `python3-pyopengl` `pipewire-pulseaudio` … |

You can also install them yourself beforehand:

```bash
# Arch / CachyOS
sudo pacman -S --needed \
  gtk4 libadwaita \
  python python-gobject python-cairo python-numpy python-opengl \
  pipewire pipewire-pulse mesa
```

---

## Optional: app menu install

Run once with:

```bash
SOUNDORBIT_INSTALL=1 ./SoundOrbit-*-x86_64.AppImage
```

This copies a launcher into `~/.local` and adds **サウンドオービット / SoundOrbit** to the app menu (same as `./install.sh` from source).

Ensure `~/.local/bin` is on your `PATH` if you want the `sound-orbit` command:

```bash
# fish
fish_add_path ~/.local/bin

# bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

---

## If the AppImage won’t start

| Symptom | Fix |
|---------|-----|
| `Permission denied` | `chmod +x SoundOrbit-*.AppImage` |
| “Not marked as executable” in file manager | Properties → Allow executing, or use the terminal as above |
| FUSE / “Cannot mount AppImage” | `./SoundOrbit-*.AppImage --appimage-extract-and-run` |
| Missing GTK / numpy / OpenGL | Accept the install prompt, or install packages from the table above |
| Black window / GL error | Update GPU drivers / `mesa` (or NVIDIA proprietary stack) |
| No reaction to sound | Play audio on the **default** output; need `parec` (`pipewire-pulse`) |

```bash
# Audio sanity check
pactl get-default-sink
command -v parec
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

## Options (environment variables)

```bash
# Quality
SOUNDORBIT_QUALITY=low ./SoundOrbit-*.AppImage    # low | medium | high | ultra
SOUNDORBIT_ECO=0 ./SoundOrbit-*.AppImage          # disable ECO bias (default ECO on)

# Pixel look
SOUNDORBIT_INTERNAL=240x180 ./SoundOrbit-*.AppImage   # default chunky
SOUNDORBIT_INTERNAL=160x120 ./SoundOrbit-*.AppImage   # more jagged
SOUNDORBIT_INTERNAL=off ./SoundOrbit-*.AppImage       # window-proportional FBO

# CRT
SOUNDORBIT_CRT=0 ./SoundOrbit-*.AppImage
SOUNDORBIT_CRT_BARREL=0.16 ./SoundOrbit-*.AppImage
SOUNDORBIT_CRT_SCANLINE=0.92 ./SoundOrbit-*.AppImage
SOUNDORBIT_CRT_VIGNETTE=0.62 ./SoundOrbit-*.AppImage

# Afterimage
SOUNDORBIT_TRAIL=0 ./SoundOrbit-*.AppImage
SOUNDORBIT_TRAIL_MIX=0.78 ./SoundOrbit-*.AppImage
SOUNDORBIT_TRAIL_DECAY=0.93 ./SoundOrbit-*.AppImage
```

---

## How it works

1. Capture default sink `.monitor` with `parec`
2. Hann-windowed FFT → 96 log bands
3. GTK4 `GLArea` + OpenGL 3.3 scene (bars, orb, rings, particles)
4. Post: trails, scanlines, barrel distortion, vignette

---

## For developers

### Build the AppImage

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage
```

### Run from source (without AppImage)

```bash
# install host deps (see table above), then:
python3 ./sound-orbit
# or:
./install.sh && sound-orbit
```

> Do **not** use a Python venv—GTK / PyGObject must come from the system packages.

---

## Requirements (host)

| Component | Notes |
|-----------|--------|
| Linux x86_64 | AppImage target |
| Python 3.11+ | System package |
| GTK 4 + libadwaita | UI |
| NumPy + PyOpenGL | Analysis / GL |
| PipeWire + `parec` | System audio capture |
| OpenGL 3.3+ | Via Mesa or vendor drivers |
| Desktop | GNOME recommended (Wayland/X11) |

---

## License

MIT — see [LICENSE](LICENSE).
