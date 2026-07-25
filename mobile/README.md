# SoundOrbit Mobile

Mobile-tuned **PS1 CRT visualizer** driven by the **device microphone**.

| Platform | Status |
|----------|--------|
| **Android APK** | Phase 1 — build & sideload |
| **iOS IPA** | Phase 2 — Metal / MoltenVK (planned) |

## Limits

- **Not system audio** (Spotify-in-the-phone). Uses **mic** ambient sound.
- Desktop GTK/GLFW code is not packaged; this is a native **OpenGL ES 3** port of the look.

## Build APK

```bash
export JAVA_HOME=$HOME/tools/jdk-17
export ANDROID_HOME=$HOME/Android/Sdk
./mobile/android/build-apk.sh
# → dist/SoundOrbit-Mobile-debug.apk
```

## Sideload

```bash
adb install -r dist/SoundOrbit-Mobile-debug.apk
```

Or copy the APK to the phone and open it (allow unknown sources).  
Grant **Microphone** when asked.

## Graphics plan

- Phase 1: **OpenGL ES 3.0** (ships now)
- Later: **Vulkan** on Android; **Metal** / **MoltenVK** on iOS for a shared core

## Permissions

- `RECORD_AUDIO` only
