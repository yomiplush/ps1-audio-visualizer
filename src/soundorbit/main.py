#!/usr/bin/env python3
"""Entry point for SoundOrbit（サウンドオービット）."""

from __future__ import annotations

import os
import sys

# Avoid ~/.local pip packages shadowing system/venv stacks (common GL/import pain)
os.environ.setdefault("PYTHONNOUSERSITE", "1")

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# CRITICAL: apply GDK_BACKEND / GL vendor BEFORE importing Gdk
from soundorbit.glsetup import apply_runtime_gl_env, detect_gpu  # noqa: E402

_gpu_early = detect_gpu()
apply_runtime_gl_env(_gpu_early)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from soundorbit import __app_id__, __version__  # noqa: E402
from soundorbit.window import SoundOrbitWindow  # noqa: E402


class SoundOrbitApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: SoundOrbitWindow | None = None
        self._gpu = _gpu_early
        mode = os.environ.get("SOUNDORBIT_GL_MODE", "default")
        print(f"SoundOrbit GL mode: {mode} | {self._gpu.label}", file=sys.stderr)

    def do_activate(self) -> None:
        if not self._window:
            self._window = SoundOrbitWindow(self, gpu=self._gpu)
        self._window.present()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)

        # Warm up display GL early (better errors than a blank GLArea)
        display = Gdk.Display.get_default()
        if display is not None and hasattr(display, "prepare_gl"):
            try:
                display.prepare_gl()
            except GLib.Error as exc:
                print(f"warning: display.prepare_gl failed: {exc}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                print(f"warning: prepare_gl: {exc}", file=sys.stderr)

        # ダーク基調（ビジュアライザー向け）
        style = self.get_style_manager()
        style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def _on_about(self, *_args) -> None:
        gpu = self._gpu
        dlg = Adw.AboutDialog(
            application_name="サウンドオービット",
            application_icon=__app_id__,
            developer_name="yomiplush",
            version=__version__,
            comments=(
                "PC の再生音に反応する GNOME 向け 3D サウンドビジュアライザー\n"
                f"{gpu.label} — {gpu.detail[:120]}"
            ),
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/yomiplush/ps1-audio-visualizer",
        )
        if self._window:
            dlg.present(self._window)


def main(argv: list[str] | None = None) -> int:
    app = SoundOrbitApp()
    return app.run(argv or sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
