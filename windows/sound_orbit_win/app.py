"""GLFW window + main loop for SoundOrbit Windows."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Help PyInstaller onefile find glfw3.dll before importing glfw
def _bootstrap_native_libs() -> None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass)
        candidates.append(root)
        candidates.extend(root.rglob("glfw3.dll"))
    try:
        import importlib.util

        spec = importlib.util.find_spec("glfw")
        if spec and spec.origin:
            candidates.append(Path(spec.origin).parent)
    except Exception:
        pass
    for c in candidates:
        d = c if c.is_dir() else c.parent
        if not d.is_dir():
            continue
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(d))
            except OSError:
                pass
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


_bootstrap_native_libs()

# GPU profile BEFORE creating the GL context (driver env hints)
from sound_orbit_win.gpu import (  # noqa: E402
    apply_windows_gpu_env,
    build_profile,
    describe_profile,
    profile_from_gl_renderer,
)

_GPU_PROFILE = build_profile()
apply_windows_gpu_env(_GPU_PROFILE)
print(describe_profile(_GPU_PROFILE), file=sys.stderr)

try:
    import glfw
except ImportError as exc:
    print(
        "Failed to import glfw / load glfw3.dll.\n"
        "This build may be missing the native GLFW library.\n"
        f"Detail: {exc}\n"
        "Reinstall from the latest GitHub Release or run: pip install glfw",
        file=sys.stderr,
    )
    raise

from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString

from sound_orbit_win import __app_name__, __version__
from sound_orbit_win.audio import SystemAudioCapture
from sound_orbit_win.renderer import VisualizerRenderer


def _decode_gl_str(v) -> str:
    if v is None:
        return "?"
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


def _key_callback(window, key, scancode, action, mods) -> None:  # noqa: ANN001
    app = glfw.get_window_user_pointer(window)
    if app is None or action not in (glfw.PRESS, glfw.REPEAT):
        return
    if key in (glfw.KEY_ESCAPE, glfw.KEY_Q):
        glfw.set_window_should_close(window, True)
    elif key == glfw.KEY_SPACE:
        app["renderer"].toggle_rotation()
    elif key == glfw.KEY_F11 or key == glfw.KEY_F:
        mon = glfw.get_window_monitor(window)
        if mon:
            glfw.set_window_monitor(window, None, 100, 100, 1280, 720, 0)
        else:
            m = glfw.get_primary_monitor()
            mode = glfw.get_video_mode(m)
            glfw.set_window_monitor(window, m, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)


def _match_vendor(renderer: str, vendor_gl: str, expected: str) -> bool:
    blob = (renderer + " " + vendor_gl).lower()
    if expected == "NVIDIA":
        return "nvidia" in blob or "geforce" in blob
    if expected == "AMD":
        return "amd" in blob or "radeon" in blob or "ati " in blob
    if expected == "INTEL":
        return "intel" in blob
    return True


def run() -> int:
    profile = _GPU_PROFILE

    if not glfw.init():
        print("Failed to init GLFW", file=sys.stderr)
        return 1

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
    glfw.window_hint(glfw.DOUBLEBUFFER, True)
    glfw.window_hint(glfw.SAMPLES, 0)
    # Prefer dedicated GPU when driver exposes it (best-effort)
    if hasattr(glfw, "OPENGL_PROFILE"):
        pass
    # GLFW 3.4+ : GLFW_COCOA / WIN32 — not always available in python binding

    title0 = f"{__app_name__} {__version__} [{profile.primary}]"
    window = glfw.create_window(1280, 720, title0, None, None)
    if not window:
        print("Failed to create window (OpenGL 3.3 required)", file=sys.stderr)
        print("Update GPU drivers (Intel/AMD/NVIDIA) and retry.", file=sys.stderr)
        glfw.terminate()
        return 1

    glfw.make_context_current(window)
    glfw.swap_interval(1 if profile.vsync else 0)

    gl_ver = _decode_gl_str(glGetString(GL_VERSION))
    gl_renderer = _decode_gl_str(glGetString(GL_RENDERER))
    gl_vendor = _decode_gl_str(glGetString(GL_VENDOR))
    print("OpenGL:", gl_ver, file=sys.stderr)
    print("Vendor:", gl_vendor, file=sys.stderr)
    print("Renderer:", gl_renderer, file=sys.stderr)

    # If WMI failed (UNKNOWN), recover profile from the live GL device
    if profile.primary == "UNKNOWN" or not profile.adapters or profile.detail == "unknown":
        profile = profile_from_gl_renderer(gl_renderer, gl_vendor)
        print("→ GPU profile recovered from OpenGL:", describe_profile(profile), file=sys.stderr)

    if not _match_vendor(gl_renderer, gl_vendor, profile.primary):
        print(
            f"warning: WMI primary GPU is {profile.primary}, but active GL device is:\n"
            f"  {gl_renderer}\n"
            "  Hybrid laptop? Windows may be using the iGPU.\n"
            "  Settings → System → Display → Graphics → SoundOrbit → High performance",
            file=sys.stderr,
        )
        # If we wanted NVIDIA/AMD but got Intel, lighten load to match actual device
        if "intel" in gl_renderer.lower() and profile.primary in ("NVIDIA", "AMD"):
            print("→ applying Intel ECO quality for actual GL device", file=sys.stderr)
            profile = profile_from_gl_renderer(gl_renderer, gl_vendor)

    audio = SystemAudioCapture()
    renderer = VisualizerRenderer(profile=profile)
    try:
        renderer.init_gl()
    except Exception as exc:
        print(f"GL init failed: {exc}", file=sys.stderr)
        print(
            "Tips:\n"
            "  - Update GPU drivers\n"
            "  - SOUNDORBIT_GPU=INTEL|AMD|NVIDIA  (force WMI primary for quality profile)\n"
            "  - SOUNDORBIT_QUALITY=low",
            file=sys.stderr,
        )
        glfw.terminate()
        return 1

    state = {"renderer": renderer, "audio": audio, "profile": profile}
    glfw.set_window_user_pointer(window, state)
    glfw.set_key_callback(window, _key_callback)

    audio.start()
    last_title = 0.0
    gpu_tag = profile.primary
    if "intel" in gl_renderer.lower():
        gpu_tag = "INTEL*"
    elif "nvidia" in gl_renderer.lower() or "geforce" in gl_renderer.lower():
        gpu_tag = "NVIDIA*"
    elif "amd" in gl_renderer.lower() or "radeon" in gl_renderer.lower():
        gpu_tag = "AMD*"

    while not glfw.window_should_close(window):
        w, h = glfw.get_framebuffer_size(window)
        renderer.resize(w, h)
        snap = audio.snapshot()
        renderer.set_analysis(snap)
        renderer.render()
        glfw.swap_buffers(window)
        glfw.poll_events()

        now = time.perf_counter()
        if now - last_title > 0.5:
            last_title = now
            if snap.error:
                title = f"{__app_name__} [{gpu_tag}] — {snap.error}"
            elif snap.ready:
                title = (
                    f"{__app_name__} [{gpu_tag}] — {snap.source_name}  "
                    f"B{snap.bass:.2f} M{snap.mid:.2f} T{snap.treble:.2f}  "
                    f"{profile.internal_w}x{profile.internal_h}  "
                    f"[Esc quit | Space orbit | F11 fullscreen]"
                )
            else:
                title = f"{__app_name__} [{gpu_tag}] — connecting audio…"
            glfw.set_window_title(window, title)

    audio.stop()
    glfw.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
