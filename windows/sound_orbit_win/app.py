"""GLFW window + main loop for SoundOrbit Windows."""

from __future__ import annotations

import sys
import time

import glfw
from OpenGL.GL import glGetString, GL_VERSION, GL_RENDERER

from sound_orbit_win import __app_name__, __version__
from sound_orbit_win.audio import SystemAudioCapture
from sound_orbit_win.renderer import VisualizerRenderer


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


def run() -> int:
    if not glfw.init():
        print("Failed to init GLFW", file=sys.stderr)
        return 1

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
    glfw.window_hint(glfw.DOUBLEBUFFER, True)
    glfw.window_hint(glfw.SAMPLES, 0)

    # Start windowed; user can F11 fullscreen (more reliable on Win11)
    window = glfw.create_window(1280, 720, f"{__app_name__} {__version__}", None, None)
    if not window:
        print("Failed to create window (OpenGL 3.3 required)", file=sys.stderr)
        glfw.terminate()
        return 1

    glfw.make_context_current(window)
    glfw.swap_interval(1)

    print("OpenGL:", glGetString(GL_VERSION))
    print("Renderer:", glGetString(GL_RENDERER))

    audio = SystemAudioCapture()
    renderer = VisualizerRenderer()
    try:
        renderer.init_gl()
    except Exception as exc:
        print(f"GL init failed: {exc}", file=sys.stderr)
        glfw.terminate()
        return 1

    state = {"renderer": renderer, "audio": audio}
    glfw.set_window_user_pointer(window, state)
    glfw.set_key_callback(window, _key_callback)

    audio.start()
    last_title = 0.0

    # Enter fullscreen after short delay (optional)
    # glfw.set_window_monitor...

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
                title = f"{__app_name__} — {snap.error}"
            elif snap.ready:
                title = (
                    f"{__app_name__} — {snap.source_name}  "
                    f"B{snap.bass:.2f} M{snap.mid:.2f} T{snap.treble:.2f}  "
                    f"[Esc quit | Space orbit | F11 fullscreen]"
                )
            else:
                title = f"{__app_name__} — connecting audio…"
            glfw.set_window_title(window, title)

    audio.stop()
    glfw.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
