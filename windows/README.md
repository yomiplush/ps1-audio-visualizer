# SoundOrbit for Windows 11

**Separate from the Linux AppImage.**  
GLFW + OpenGL 3.3 + **WASAPI loopback** (system audio = what you hear).

## Quick start (on Windows)

```powershell
# 1) Install Python 3.11+ from python.org (Add to PATH)
# 2) Build
cd windows
powershell -ExecutionPolicy Bypass -File .\build.ps1

# 3) Run
.\dist\SoundOrbit.exe
```

Or without packaging:

```powershell
cd windows
py -3 -m venv .venv-win
.\.venv-win\Scripts\pip install -r requirements.txt
.\.venv-win\Scripts\python run_soundorbit.py
```

## Controls

| Key | Action |
|-----|--------|
| Esc / Q | Quit |
| Space | Toggle camera orbit |
| F11 / F | Fullscreen |

## Audio notes

- Uses **WASAPI loopback** on the default playback device (Windows 10/11).
- Play music/browser audio; the visualizer reacts automatically.
- If loopback fails, falls back to default **microphone** input (not ideal).

## Requirements (runtime)

- Windows 10/11 x64
- GPU with **OpenGL 3.3** (NVIDIA / AMD / Intel drivers)
- No Python install needed for the `.exe` (bundled by PyInstaller)

## GitHub Actions

Pushing changes under `windows/**` can build the `.exe` on `windows-latest`  
(see `.github/workflows/windows-build.yml`).

## Layout

```
windows/
  run_soundorbit.py      # entry
  requirements.txt
  build.ps1              # local Windows build
  SoundOrbitWin.spec     # PyInstaller
  sound_orbit_win/
    app.py               # GLFW loop
    audio.py             # WASAPI + FFT
    renderer.py          # OpenGL visualizer
    math3d.py
```
