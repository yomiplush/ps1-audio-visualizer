#!/usr/bin/env python3
"""Entry point for SoundOrbit（サウンドオービット）."""

from __future__ import annotations

import os
import sys

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from soundorbit import __app_id__, __version__
from soundorbit.window import SoundOrbitWindow


class SoundOrbitApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._window: SoundOrbitWindow | None = None

    def do_activate(self) -> None:
        if not self._window:
            self._window = SoundOrbitWindow(self)
        self._window.present()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
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
        dlg = Adw.AboutDialog(
            application_name="サウンドオービット",
            application_icon=__app_id__,
            developer_name="yomiplush",
            version=__version__,
            comments="PC の再生音に反応する GNOME 向け 3D サウンドビジュアライザー",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/yomiplush",
        )
        if self._window:
            dlg.present(self._window)


def main(argv: list[str] | None = None) -> int:
    app = SoundOrbitApp()
    return app.run(argv or sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
