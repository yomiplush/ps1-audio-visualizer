# SoundOrbit

Fullscreen **3D system-audio visualizer** — PS1-style chunky pixels, CRT post, 256-color look.

Reacts to **whatever is playing on the PC**.

| Platform | Download |
|----------|----------|
| **Linux (any)** | [AppImage](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest) → `SoundOrbit-Linux-x86_64.AppImage` |
| **Arch / CachyOS** | `./install-pacman.sh` → package **`soundorbit`** (Octopi で削除可) |
| **Windows 11** | [same Release](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest) → `SoundOrbit-Windows-x64.exe` |

**[Latest Release (Linux + Windows)](https://github.com/yomiplush/ps1-audio-visualizer/releases/latest)**

---

## Linux — Arch / CachyOS (Octopi)

**Octopi で検出・削除するには** ユーザーローカル (`~/.local`) ではなく **pacman パッケージ**として入れてください。

```bash
git clone https://github.com/yomiplush/ps1-audio-visualizer.git
cd ps1-audio-visualizer
./install-pacman.sh
# または:
#   ./packaging/arch/build.sh
#   sudo pacman -U dist/soundorbit-*.pkg.tar.zst
```

| 操作 | 方法 |
|------|------|
| **起動** | `sound-orbit` またはアプリメニュー「サウンドオービット」 |
| **Octopi 削除** | 検索 `soundorbit` → 削除 |
| **CLI 削除** | `sudo pacman -R soundorbit` |
| **確認** | `pacman -Q soundorbit` |

パッケージ名: **`soundorbit`**（システム全体 `/usr` にインストール）。

> AppImage や `./install.sh` のユーザーインストールは Octopi に出ません。
> pacman 版に切り替えると `install-pacman.sh` が `~/.local` の起動スクリプトを掃除します。

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

# AppImage (any distro)
./packaging/appimage/build.sh
# → dist/SoundOrbit-<version>-x86_64.AppImage

# Arch/CachyOS pacman package (Octopi)
./packaging/arch/build.sh
# → dist/soundorbit-<version>-1-any.pkg.tar.zst
```

---

## Windows 11 (.exe)

**Separate codebase** under [`windows/`](windows/) (GLFW + WASAPI — not GTK).  
Visual look matches Linux: **CRT / PS1 pixels / trails / green neon frame / orbiting labels**.

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
| `SoundOrbit-Linux-x86_64.AppImage` | Linux (any) |
| `soundorbit-*-any.pkg.tar.zst` | Arch / CachyOS (Octopi / `pacman -U`) |
| `SoundOrbit-Windows-x64.exe` | Windows |

CI / maintainer builds:

- Linux AppImage: `packaging/appimage/build.sh`
- Arch package: `packaging/arch/build.sh` → install with `pacman -U` / Octopi
- Windows exe: GitHub Actions `Windows Build` on `windows-latest`

---

## License

MIT — see [LICENSE](LICENSE).
