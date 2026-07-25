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

## GPU auto-detect (NVIDIA / AMD / Intel)

On startup the app queries `Win32_VideoController` and picks a quality profile:

| Detected | Behavior |
|----------|----------|
| **NVIDIA** (GeForce/RTX/…) | Higher internal res, more particles, driver cache hints |
| **AMD** dGPU | Similar high profile |
| **AMD** iGPU / APU | ECO: fewer particles, lighter trails |
| **Intel** HD/UHD/Iris | ECO (tuned for HD 620-class) |
| **Intel Arc** | Mid-high profile |
| **Hybrid** (e.g. Intel+NVIDIA) | Prefers dGPU for *profile*; if Windows still gives iGPU GL, ECO is applied + console tip |

Override:

```powershell
# Force quality profile primary (does not always force the GL adapter)
$env:SOUNDORBIT_GPU = "NVIDIA"   # or AMD / INTEL
$env:SOUNDORBIT_QUALITY = "low"  # low | high | ultra
.\SoundOrbit-Windows-x64.exe
```

Hybrid laptops: if the title bar shows `INTEL*` while you wanted NVIDIA, use  
**Settings → System → Display → Graphics → SoundOrbit → High performance (NVIDIA)**.

## Visual look (Linux parity) — requires **1.4.0-win+**

Windows uses the same PS1 / CRT stack as Linux:

- Low internal resolution + nearest upscale (chunky pixels)
- Phosphor trails, RGB chromatic aberration
- CRT barrel, hard scanlines, vignette, 256-color quantize
- **Thick energy ribbons** (not 1px lines — Intel/NVIDIA Core GL safe)
- **Green neon frame ribbons** + tick quads
- Orbiting labels + BASS/MID/TREBLE/RMS/PEAK/BEAT panels

**Verify you have the right build:** window title shows `1.4.0-win` and `CRT`.  
Console must print: `[SoundOrbit-Win] visual stack READY CRT+trails+ribbons+frames+labels`.

If you only see bars/orb with smooth edges and no scanlines, you are running an **old Release** — rebuild or download a newer artifact:

```powershell
cd windows
powershell -ExecutionPolicy Bypass -File .\build.ps1
.\dist\SoundOrbit.exe
```

Quality auto-scales from GPU. Override: `$env:SOUNDORBIT_QUALITY="ultra"`.

## Controls

| Key | Action |
|-----|--------|
| Esc / Q | Quit |
| Space | Toggle camera orbit |
| F11 / F | Fullscreen |

## Audio notes

- **WASAPI loopback only** — captures *what you hear* (system playback).
- Enumerates **all output devices**: Realtek, Intel HD Audio, Bluetooth, HDMI,
  USB headsets, NVIDIA/AMD audio, etc. Prefers the Windows **default playback** device.
- Switches automatically if you change default output (e.g. plug in Bluetooth).
- **Never uses the microphone** (input-only devices are ignored).
- Console lists candidates and which loopback was opened.

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
