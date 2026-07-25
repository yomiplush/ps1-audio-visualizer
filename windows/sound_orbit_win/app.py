"""GLFW window + main loop for SoundOrbit Windows.

Includes ResourceGuardian (RAM/CPU throttle, leak brake, FPS pacing)
and defensive try/except around the render path so driver glitches
cannot freeze the process in a hard loop.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
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
from sound_orbit_win.resources import (  # noqa: E402
    FramePacer,
    ResourceGuardian,
    eco_bias_enabled,
    set_process_priority_below_normal,
)

_GPU_PROFILE = build_profile()
apply_windows_gpu_env(_GPU_PROFILE)
print(describe_profile(_GPU_PROFILE), file=sys.stderr)

# Eco by default: slightly lower scheduling priority from the start
if eco_bias_enabled():
    if set_process_priority_below_normal():
        print("Process priority: BELOW_NORMAL (SOUNDORBIT_ECO=1)", file=sys.stderr)

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
    glfw.window_hint(glfw.SAMPLES, 0)  # MSAA off — less GPU + VRAM

    title0 = f"{__app_name__} {__version__} [{profile.primary}]"
    window = glfw.create_window(1280, 720, title0, None, None)
    if not window:
        print("Failed to create window (OpenGL 3.3 required)", file=sys.stderr)
        print("Update GPU drivers (Intel/AMD/NVIDIA) and retry.", file=sys.stderr)
        glfw.terminate()
        return 1

    glfw.make_context_current(window)
    # VSync on by default — caps FPS and reduces heat (BSOD-adjacent driver load)
    vsync = 1 if getattr(profile, "vsync", True) else 0
    if eco_bias_enabled():
        vsync = 1
    glfw.swap_interval(vsync)

    gl_ver = _decode_gl_str(glGetString(GL_VERSION))
    gl_renderer = _decode_gl_str(glGetString(GL_RENDERER))
    gl_vendor = _decode_gl_str(glGetString(GL_VENDOR))
    print("OpenGL:", gl_ver, file=sys.stderr)
    print("Vendor:", gl_vendor, file=sys.stderr)
    print("Renderer:", gl_renderer, file=sys.stderr)

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
            "  - SOUNDORBIT_GPU=INTEL|AMD|NVIDIA\n"
            "  - SOUNDORBIT_QUALITY=low\n"
            "  - SOUNDORBIT_ECO=1  (default) for lower load",
            file=sys.stderr,
        )
        glfw.terminate()
        return 1

    # Resource guardian: RAM ceiling, leak growth, FPS throttle
    base_fps = 28.0 if eco_bias_enabled() else 36.0
    # iGPU starts more conservative
    if getattr(profile, "is_integrated", False) or "intel" in gl_renderer.lower():
        base_fps = min(base_fps, 24.0)
    guardian = ResourceGuardian(base_fps=base_fps)
    guardian.arm()
    pacer = FramePacer(target_fps=base_fps)

    print(
        f"SoundOrbit {__version__} — visuals + ResourceGuardian "
        f"(ECO={int(eco_bias_enabled())} base_fps={base_fps:.0f})",
        file=sys.stderr,
        flush=True,
    )
    st0 = guardian.state()
    print(
        f"[guardian] {st0.note} soft≤{st0.soft_limit_mb:.0f}MB hard≤{st0.hard_limit_mb:.0f}MB",
        file=sys.stderr,
        flush=True,
    )

    state = {
        "renderer": renderer,
        "audio": audio,
        "profile": profile,
        "guardian": guardian,
    }
    glfw.set_window_user_pointer(window, state)
    glfw.set_key_callback(window, _key_callback)

    audio.start()
    last_title = 0.0
    gl_errors = 0
    max_gl_errors = 12  # stop spamming; still try to recover
    rstate = guardian.state()

    gpu_tag = profile.primary
    if "intel" in gl_renderer.lower():
        gpu_tag = "INTEL*"
    elif "nvidia" in gl_renderer.lower() or "geforce" in gl_renderer.lower():
        gpu_tag = "NVIDIA*"
    elif "amd" in gl_renderer.lower() or "radeon" in gl_renderer.lower():
        gpu_tag = "AMD*"

    while not glfw.window_should_close(window):
        # --- resource tick (may request purge) ---
        try:
            need_purge, rstate = guardian.tick()
            renderer.apply_resource_state(
                throttle=rstate.throttle,
                trails_allowed=rstate.trails_allowed,
                labels_allowed=rstate.labels_allowed,
                param_update_scale=rstate.param_update_scale,
            )
            pacer.set_fps(rstate.target_fps)
            if need_purge:
                try:
                    renderer.purge_runtime()
                except Exception:
                    pass
                guardian.run_python_purge(trim=True)
                print(
                    f"[guardian] purge×{rstate.purge_count} {rstate.level} {rstate.note}",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception as exc:
            print(f"[guardian] tick error (ignored): {exc}", file=sys.stderr)

        # Minimized / unfocused: barely spin (huge CPU/GPU save)
        try:
            iconified = bool(glfw.get_window_attrib(window, glfw.ICONIFIED))
        except Exception:
            iconified = False
        if iconified:
            time.sleep(0.25)
            glfw.poll_events()
            continue

        # Frame work
        try:
            w, h = glfw.get_framebuffer_size(window)
            # Clamp absurd sizes (display-cable glitches) to protect VRAM
            w = max(1, min(int(w), 3840))
            h = max(1, min(int(h), 2160))
            renderer.resize(w, h)
            snap = audio.snapshot()
            renderer.set_analysis(snap)
            renderer.render()
            glfw.swap_buffers(window)
            gl_errors = 0  # success resets counter
        except Exception as exc:
            gl_errors += 1
            if gl_errors <= max_gl_errors:
                print(f"[render] error ({gl_errors}/{max_gl_errors}): {exc}", file=sys.stderr)
                if gl_errors == 1:
                    traceback.print_exc(file=sys.stderr)
            # Back off instead of hot-looping (driver stress → freezes)
            time.sleep(min(0.5, 0.05 * gl_errors))
            if gl_errors >= max_gl_errors:
                print(
                    "[render] too many GL errors — lowering load (trails off, FPS 12)",
                    file=sys.stderr,
                )
                try:
                    renderer.apply_resource_state(
                        throttle=0.3,
                        trails_allowed=False,
                        labels_allowed=False,
                        param_update_scale=0.2,
                    )
                    renderer.purge_runtime()
                    pacer.set_fps(12.0)
                    gl_errors = max_gl_errors // 2  # allow retries at low rate
                except Exception:
                    pass
            snap = getattr(audio, "snapshot", lambda: None)()
            if snap is None:
                class _E:
                    error = str(exc)
                    ready = False
                    source_name = ""
                    bass = mid = treble = 0.0

                snap = _E()

        try:
            glfw.poll_events()
        except Exception:
            pass

        # Sleep remainder of frame budget (no busy-wait)
        pacer.end_frame()

        now = time.perf_counter()
        if now - last_title > 0.6:
            last_title = now
            try:
                if getattr(snap, "error", None):
                    title = f"{__app_name__} [{gpu_tag}] — {snap.error}"
                elif getattr(snap, "ready", False):
                    title = (
                        f"{__app_name__} {__version__} [{gpu_tag}] "
                        f"{rstate.level} {rstate.rss_mb:.0f}MB "
                        f"{rstate.target_fps:.0f}fps thr{rstate.throttle:.2f} "
                        f"— {snap.source_name}  "
                        f"B{snap.bass:.2f} M{snap.mid:.2f} T{snap.treble:.2f}"
                    )
                else:
                    title = f"{__app_name__} [{gpu_tag}] — connecting audio…"
                if rstate.leak_suspect:
                    title += " [MEM↑]"
                glfw.set_window_title(window, title)
            except Exception:
                pass

    try:
        audio.stop()
    except Exception:
        pass
    try:
        renderer.purge_runtime()
    except Exception:
        pass
    try:
        guardian.run_python_purge(trim=True)
    except Exception:
        pass
    glfw.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
