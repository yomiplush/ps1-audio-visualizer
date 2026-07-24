# SoundOrbit

Fullscreen **3D system-audio visualizer** — PS1-style chunky pixels, CRT look, 256-color post, system audio via PipeWire.

**No compile.** One AppImage → auto GPU setup → app menu → run.

---

## Install (AppImage)

### 1. Download

**[Latest Release](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest)**  
→ `SoundOrbit-<version>-x86_64.AppImage`

### 2. Run once

```bash
chmod +x SoundOrbit-*-x86_64.AppImage
./SoundOrbit-*-x86_64.AppImage
```

### What happens automatically

| Step | Behavior |
|------|----------|
| **GPU detect** | AMD / NVIDIA / Intel (UHD·Iris·Arc) / hybrid |
| **Packages** | Installs GTK4 + **vendor-specific GL stack** via pacman/apt/dnf (polkit password once) |
| **venv** | `~/.local/share/sound-orbit/venv` — isolates numpy/PyOpenGL (`PYTHONNOUSERSITE=1`) |
| **GL autofix** | Probes context; tries default → `GDK_BACKEND=x11` → software GL |
| **App menu** | Adds **サウンドオービット** + `~/.local/bin/sound-orbit` |

NVIDIA + Wayland prefers X11 backend automatically. Kernel `nvidia` module is **not** installed (must already match your system); `nvidia-utils` / `egl-wayland` are.

### Skip automation (optional)

```bash
SOUNDORBIT_SKIP_PKGS=1 ./SoundOrbit-*.AppImage   # no pacman/apt
SOUNDORBIT_NO_MENU=1 ./SoundOrbit-*.AppImage      # no desktop entry
SOUNDORBIT_FORCE_SETUP=1 ./SoundOrbit-*.AppImage  # re-run full setup
SOUNDORBIT_GL=x11|wayland|software ./SoundOrbit-*.AppImage
```

---

## Controls

| Key | Action |
|-----|--------|
| `Esc` / `Ctrl+Q` | Quit |
| `F11` / `F` | Fullscreen |
| `Space` | Camera orbit |
| `H` / click | Help show/hide |

---

## Environment (look / quality)

```bash
SOUNDORBIT_QUALITY=low|medium|high|ultra
SOUNDORBIT_ECO=0
SOUNDORBIT_INTERNAL=240x180
SOUNDORBIT_CRT=0
SOUNDORBIT_TRAIL=0
```

---

## Developers

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage
```

---

## License

MIT — see [LICENSE](LICENSE).
