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

### Visual parity (Linux ↔ Windows)

Linux **1.5.1+** matches the Windows look reverse-ported from the Win CRT stack:

- Thick **energy ribbons** + **green neon frame** (not 1px lines)
- Strong CRT scanlines / trails / 256-color
- Premultiplied transparent orbiting labels
- PS1 frame lock (~15–20 fps)

### PS1 frame lock (~15–20 fps)

Motion is intentionally **stepped** (PlayStation 1 style), not smooth 60fps:

| Env | Effect |
|-----|--------|
| *(default)* | ~15–20 fps hard lock + fixed simulation step |
| `SOUNDORBIT_FPS=15` | Force 15 fps |
| `SOUNDORBIT_FPS=24` | Max “smooth” still PS1-ish |
| `SOUNDORBIT_PS1_FPS=0` | Disable PS1 bias (still quality-capped) |

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

Every GitHub Release attaches **both** binaries (required):

| Asset | Platform |
|-------|----------|
| `SoundOrbit-Linux-x86_64.AppImage` | Linux (any) |
| `SoundOrbit-Windows-x64.exe` | Windows |

CI workflow: [`.github/workflows/release-assets.yml`](.github/workflows/release-assets.yml)  
Builds Linux + Windows in parallel and **fails if either asset is missing**.

```bash
# Maintainer: clean tree, then tag — CI uploads both assets
./scripts/release.sh v1.7.0
# or
git tag v1.7.0 && git push origin v1.7.0
```

Optional Arch package (local / Octopi):

```bash
./packaging/arch/build.sh
# → dist/soundorbit-*-any.pkg.tar.zst
```

---


---

## Mobile (Android sideload)

Mic-driven PS1 CRT port (not system audio). See [`mobile/README.md`](mobile/README.md).

```bash
./mobile/android/build-apk.sh
# → dist/SoundOrbit-Mobile-debug.apk
adb install -r dist/SoundOrbit-Mobile-debug.apk
```

iOS IPA / Metal+MoltenVK: Phase 2 (`mobile/ios/`).


---

## WebGL Demo (Cloudflare Pages)

Static WebGL2 mic demo — no build step. See [`web/README.md`](web/README.md).

```bash
cd web && python3 -m http.server 8080
```

Cloudflare Pages: **output directory = `web`**, empty build command.

## License

MIT — see [LICENSE](LICENSE).
