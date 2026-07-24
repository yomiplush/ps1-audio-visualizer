# SoundOrbit

Fullscreen **3D system-audio visualizer** — PS1-style chunky pixels, CRT post, 256-color look.

Reacts to **whatever is playing on the PC**.

| Platform | Download |
|----------|----------|
| **Linux** | [AppImage](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest) → `SoundOrbit-Linux-x86_64.AppImage` |
| **Windows 11** | [same Release](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest) → `SoundOrbit-Windows-x64.exe` |

**[Latest Release (Linux + Windows)](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest)**

---

## Linux (AppImage)

```bash
# Download SoundOrbit-Linux-x86_64.AppImage from Releases, then:
chmod +x SoundOrbit-Linux-x86_64.AppImage
./SoundOrbit-Linux-x86_64.AppImage
```

### What happens automatically

| Step | Behavior |
|------|----------|
| **GPU detect** | AMD / NVIDIA / Intel / hybrid |
| **Packages** | Installs only *missing* deps (CachyOS-safe; no pipewire downgrade) |
| **venv** | `~/.local/share/sound-orbit/venv` |
| **GL autofix** | Multi-mode probe + re-launch (esp. NVIDIA Wayland) |
| **App menu** | **サウンドオービット** + `~/.local/bin/sound-orbit` |

Optional:

```bash
SOUNDORBIT_SKIP_PKGS=1 ./SoundOrbit-Linux-x86_64.AppImage
SOUNDORBIT_GL_MODE=nvidia-wayland ./SoundOrbit-Linux-x86_64.AppImage
SOUNDORBIT_GL_MODE=software ./SoundOrbit-Linux-x86_64.AppImage
```

### Controls (Linux)

| Key | Action |
|-----|--------|
| `Esc` / `Ctrl+Q` | Quit |
| `F11` / `F` | Fullscreen |
| `Space` | Camera orbit |
| `H` / click | Help show/hide |

### Linux build from source

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage
```

---

## Windows 11 (.exe)

**Separate codebase** under [`windows/`](windows/) (GLFW + WASAPI — not GTK).

```text
Download SoundOrbit-Windows-x64.exe from Releases → double-click
```

| Key | Action |
|-----|--------|
| Esc / Q | Quit |
| Space | Camera orbit |
| F11 / F | Fullscreen |

- Audio: **WASAPI loopback** (system playback)
- Needs GPU drivers with **OpenGL 3.3**

### Windows rebuild

```powershell
cd windows
powershell -ExecutionPolicy Bypass -File .\build.ps1
# → dist\SoundOrbit.exe
```

**Smart App Control:** unsigned GitHub builds are often blocked. That is normal.  
User can allow once via Windows UI / Unblock; for public distribution, **code-sign** the exe (see [`windows/README.md`](windows/README.md)). There is no app-side “bypass.”

Details: [`windows/README.md`](windows/README.md)

---

## Release layout

Each unified release (from **v1.6.0**) attaches:

| Asset | Platform |
|-------|----------|
| `SoundOrbit-Linux-x86_64.AppImage` | Linux |
| `SoundOrbit-Windows-x64.exe` | Windows |

CI:

- Linux AppImage: built with `packaging/appimage/build.sh` (maintainer / Linux host)
- Windows exe: GitHub Actions `Windows Build` on `windows-latest`

---

## License

MIT — see [LICENSE](LICENSE).
