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
- **glfw3.dll** is bundled inside the exe (PyInstaller). If you see  
  `Failed to load GLFW3 shared library`, download a newer Release build.

## Smart App Control / SmartScreen blocks the .exe?

**Expected** for an unsigned PyInstaller build from GitHub. Windows does not trust new publishers until the binary is **Authenticode-signed** (and often after some reputation builds up).

There is **no supported “bypass” inside the app** — that would be malware-like. Legitimate options:

### A) You (the PC owner) allow it once

1. Windows Security → **App & browser control** → **Smart App Control**  
   - If set to *Evaluation* / *On*, unsigned apps from the internet are often blocked.
2. Or right-click `SoundOrbit-Windows-x64.exe` → **Properties** → if present, check **Unblock** → OK.
3. When Windows shows a blue/yellow filter UI: **More info** → **Run anyway** (wording varies).
4. For your own machine only, you can set Smart App Control to **Off** (Settings). That is a *user* choice, not something the .exe should force.

### B) Distributor: code-sign the .exe (real fix for others)

Buy or use a **code signing certificate**, then sign after build:

```powershell
# Example with signtool (Windows SDK) + your cert
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f YourCert.pfx /p YOUR_PASSWORD .\dist\SoundOrbit.exe
```

Or **[Azure Trusted Signing](https://learn.microsoft.com/en-us/azure/trusted-signing/)** (Microsoft’s cloud signing; often cheaper than classic EV certs).

Optional env for `build.ps1` after you have a cert:

```powershell
$env:SOUNDOBIT_SIGN_PFX = "C:\path\to\cert.pfx"
$env:SOUNDOBIT_SIGN_PASSWORD = "..."
powershell -File .\build.ps1
```

Self-signed certificates **usually still fail** Smart App Control. Public trust needs a CA-issued code signing cert.

### C) Avoid the packaged .exe on a blocked PC

Run from source (no single-file exe reputation issues as often):

```powershell
cd windows
py -3 -m venv .venv-win
.\.venv-win\Scripts\pip install -r requirements.txt
.\.venv-win\Scripts\python run_soundorbit.py
```

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
