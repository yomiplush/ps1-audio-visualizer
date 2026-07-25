# SoundOrbit Mobile / VR

Mic-driven **PS1 CRT** visualizer ports (not desktop system-audio loopback).

| Platform | Status | Output |
|----------|--------|--------|
| **Android phone** | Phase 1 | `dist/SoundOrbit-Mobile-debug.apk` |
| **Meta Quest 2 / 3 / 3S** | Phase 1 | `dist/SoundOrbit-Quest-debug.apk` |
| **iOS IPA** | Phase 2 planned | — |

## Limits

- **Not system audio** (Spotify internal). Uses **mic** ambient sound.
- Desktop GTK/GLFW code is separate.

---

## Android phone (GLES)

```bash
export JAVA_HOME=$HOME/tools/jdk-17
export ANDROID_HOME=$HOME/Android/Sdk
./mobile/android/build-apk.sh
# → dist/SoundOrbit-Mobile-debug.apk
adb install -r dist/SoundOrbit-Mobile-debug.apk
```

## Meta Quest VR (OpenXR + GLES3)

Full native app under [`quest/`](quest/) with **automatic quality** for Quest 2 / 3 / 3S:

```bash
./mobile/quest/build-apk.sh
# → dist/SoundOrbit-Quest-debug.apk
adb install -r dist/SoundOrbit-Quest-debug.apk
```

See [`quest/README.md`](quest/README.md) for profiles, architecture, and sideload notes.

| Device | Auto profile |
|--------|----------------|
| Quest 2 | ECO (32 bands, scale 0.72) |
| Quest 3S | HIGH (48 bands, scale 0.88) |
| Quest 3 | ULTRA (64 bands, scale 1.0) |

## Graphics plan

- Phone: **OpenGL ES 3.0**
- Quest: **OpenXR + OpenGL ES 3** (stereo, LOCAL space ring)
- Later: Vulkan path; **Metal** / **MoltenVK** on iOS

## Permissions

- `RECORD_AUDIO`
