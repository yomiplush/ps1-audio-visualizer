"""Adw 全画面ウィンドウ + Gtk.GLArea。"""

from __future__ import annotations

import os
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from soundorbit import __app_id__, __app_name__, __version__
from soundorbit.audio import SystemAudioCapture
from soundorbit.glsetup import (
    GpuInfo,
    clipboard_fix_commands,
    detect_gpu,
    detect_shell,
    gl_failure_hints,
    mark_gl_success,
    try_gl_autofix,
)
from soundorbit.quality import detect_quality
from soundorbit.renderer import VisualizerRenderer
from soundorbit.resources import ResourceGuardian


class SoundOrbitWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, gpu: Optional[GpuInfo] = None) -> None:
        super().__init__(application=app, title=__app_name__)
        self.set_default_size(1280, 720)
        self.set_icon_name(__app_id__)

        self._gpu = gpu or detect_gpu()
        self._quality = detect_quality()
        self._audio = SystemAudioCapture()
        self._renderer = VisualizerRenderer(quality=self._quality)
        self._guardian = ResourceGuardian()
        self._gl_ready = False
        self._tick_id = 0
        self._overlay_hide_id = 0
        self._paused = False
        self._base_fps = max(18, int(self._quality.target_fps))
        self._tick_interval_ms = max(12, int(round(1000.0 / self._base_fps)))
        self._res_status_counter = 0
        self._hint_visible = True  # H キーでトグル

        # ルート: オーバーレイ（GL + ヒント）
        self._overlay = Gtk.Overlay()
        self.set_content(self._overlay)

        self._gl = Gtk.GLArea()
        self._gl.set_hexpand(True)
        self._gl.set_vexpand(True)
        self._gl.set_required_version(3, 3)
        self._gl.set_has_depth_buffer(True)
        # CRT 外周ベゼルをデスクトップへ透過させる
        if hasattr(self._gl, "set_has_alpha"):
            try:
                self._gl.set_has_alpha(True)
            except Exception:
                pass
        self._gl.set_auto_render(False)
        self._gl.set_focusable(True)
        # Prefer desktop GL; allow GLES as fallback when API exists (GTK 4.12+)
        if hasattr(self._gl, "set_allowed_apis") and hasattr(Gdk, "GLAPI"):
            try:
                apis = Gdk.GLAPI.GL
                if hasattr(Gdk.GLAPI, "GLES"):
                    apis = apis | Gdk.GLAPI.GLES
                self._gl.set_allowed_apis(apis)
            except Exception:
                pass
        if hasattr(self._gl, "set_use_es"):
            try:
                # Prefer core GL 3.3; ES path is last resort via allowed_apis
                self._gl.set_use_es(False)
            except Exception:
                pass
        self._gl.connect("realize", self._on_gl_realize)
        self._gl.connect("unrealize", self._on_gl_unrealize)
        self._gl.connect("render", self._on_gl_render)
        self._gl.connect("resize", self._on_gl_resize)
        self._overlay.set_child(self._gl)

        # 上部ヒント（数秒でフェード）
        self._hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._hint.set_halign(Gtk.Align.CENTER)
        self._hint.set_valign(Gtk.Align.START)
        self._hint.set_margin_top(28)
        self._hint.add_css_class("osd")

        title = Gtk.Label(label=__app_name__)
        title.add_css_class("title-1")
        title.add_css_class("osd-title")
        subtitle = Gtk.Label(
            label="システム音声に反応する 3D ビジュアライザー"
        )
        subtitle.add_css_class("dim-label")
        keys = Gtk.Label(
            label="Esc 終了  ·  F11 全画面  ·  Space 回転ON/OFF  ·  H ヘルプ表示/非表示"
        )
        keys.add_css_class("osd-keys")

        q = self._quality
        self._quality_label = Gtk.Label(
            label=f"描画品質: {q.label}  ·  {q.target_fps}fps  ·  自動検出"
        )
        self._quality_label.add_css_class("dim-label")

        self._status = Gtk.Label(label="音声モニター接続中…")
        self._status.add_css_class("dim-label")

        self._hint.append(title)
        self._hint.append(subtitle)
        self._hint.append(keys)
        self._hint.append(self._quality_label)
        self._hint.append(self._status)
        self._overlay.add_overlay(self._hint)

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window, .background {
                background-color: transparent;
            }
            .osd-title { color: alpha(white, 0.92); text-shadow: 0 2px 12px alpha(black, 0.7); }
            .osd-keys { color: alpha(white, 0.75); margin-top: 8px; font-size: 0.95em; }
            .osd {
                padding: 12px 20px;
                background-color: transparent;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # キー入力
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # クリックでもヘルプ表示トグル
        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: self._toggle_hint())
        self._gl.add_controller(click)

        self.connect("close-request", self._on_close)
        self.connect("map", self._on_map)

    def _on_map(self, *_args) -> None:
        # 起動直後に全画面
        GLib.idle_add(self._enter_fullscreen)

    def _enter_fullscreen(self) -> bool:
        self.fullscreen()
        self._gl.grab_focus()
        self._show_hint(temporary=True)
        return GLib.SOURCE_REMOVE

    def _show_hint(self, temporary: bool = True) -> None:
        self._hint_visible = True
        self._hint.set_opacity(1.0)
        self._hint.set_visible(True)
        if self._overlay_hide_id:
            GLib.source_remove(self._overlay_hide_id)
            self._overlay_hide_id = 0
        if temporary:
            self._overlay_hide_id = GLib.timeout_add(4500, self._hide_hint)

    def _hide_hint(self) -> bool:
        self._hint_visible = False
        self._hint.set_opacity(0.0)
        self._hint.set_visible(False)
        self._overlay_hide_id = 0
        return GLib.SOURCE_REMOVE

    def _toggle_hint(self) -> None:
        """H キー / クリック: 表示⇔非表示。"""
        if self._overlay_hide_id:
            GLib.source_remove(self._overlay_hide_id)
            self._overlay_hide_id = 0
        if self._hint_visible and self._hint.get_opacity() > 0.05:
            self._hide_hint()
        else:
            # 手動表示は自動で消さない
            self._show_hint(temporary=False)

    def _copy_text_to_clipboard(self, text: str) -> bool:
        try:
            display = self.get_display() or Gdk.Display.get_default()
            if display is None:
                return False
            clipboard = display.get_clipboard()
            clipboard.set(text)
            return True
        except Exception:
            try:
                # Fallback older API
                clipboard = Gdk.Display.get_default().get_clipboard()  # type: ignore[union-attr]
                clipboard.set(text)
                return True
            except Exception:
                return False

    def _show_gl_failure(self, message: str) -> None:
        # 1) 自動で別 GL モードに切り替えて再起動（Fish/Bash 不要）
        self._status.set_text(f"OpenGL 初期化失敗… 自動修正中 ({message[:40]})")
        self._hint.set_opacity(1.0)
        self._hint.set_visible(True)
        print(f"GL failure: {message}", file=__import__("sys").stderr)
        print("==> trying automatic GL backend switch…", file=__import__("sys").stderr)

        def _autofix() -> bool:
            try:
                if try_gl_autofix(self._gpu):
                    return GLib.SOURCE_REMOVE  # re-execed
            except Exception as exc:  # noqa: BLE001
                print(f"autofix error: {exc}", file=__import__("sys").stderr)
            # 2) 全モード尽きた → コピー用コマンドを提示
            hints = gl_failure_hints(self._gpu)
            print(hints, file=__import__("sys").stderr)
            shell = detect_shell()
            cmd_primary = clipboard_fix_commands(self._gpu, soft=False)
            cmd_soft = clipboard_fix_commands(self._gpu, soft=True)
            # 既定で推奨コマンドをクリップボードへ（貼るだけに）
            copied = self._copy_text_to_clipboard(cmd_primary)
            self._status.set_text(
                "OpenGL 失敗 — コマンドをコピー済み。ターミナルに貼り付けて実行してください"
                if copied
                else f"OpenGL 初期化失敗: {message}"
            )
            try:
                paste_key = "Ctrl+Shift+V" if shell != "fish" else "Ctrl+Shift+V（または右クリック→貼り付け）"
                body = (
                    f"{message}\n\n"
                    f"{self._gpu.label}\n"
                    f"{self._gpu.detail[:140]}\n\n"
                    f"検出シェル: {shell}\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "ターミナルを開いて、コマンドを貼り付けて実行してください。\n"
                    f"（貼り付け: {paste_key}）\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    + (
                        "【すでにクリップボードにコピー済みです】\n"
                        "そのままターミナルで貼り付け → Enter\n\n"
                        if copied
                        else "下のボタンでコピーしてから貼り付けてください。\n\n"
                    )
                    + "■ コピーされる内容（推奨）:\n"
                    f"{cmd_primary}\n"
                    "■ それでもダメなとき（ソフトウェア描画）:\n"
                    f"{cmd_soft}"
                )
                dlg = Adw.AlertDialog(
                    heading="コマンドをターミナルに貼り付けてください",
                    body=body,
                )
                dlg.add_response("copy", "推奨コマンドをコピー")
                dlg.add_response("copy_soft", "ソフト描画コマンドをコピー")
                dlg.add_response("close", "閉じる")
                dlg.set_default_response("copy")
                dlg.set_close_response("close")

                def _on_response(_d, response: str) -> None:
                    if response == "copy":
                        ok = self._copy_text_to_clipboard(cmd_primary)
                        self._status.set_text(
                            "✓ 推奨コマンドをコピーしました — ターミナルに貼り付けて Enter"
                            if ok
                            else "コピーに失敗しました（ターミナルの表示を手動コピー）"
                        )
                    elif response == "copy_soft":
                        ok = self._copy_text_to_clipboard(cmd_soft)
                        self._status.set_text(
                            "✓ ソフト描画コマンドをコピーしました — ターミナルに貼り付けて Enter"
                            if ok
                            else "コピーに失敗しました"
                        )

                dlg.connect("response", _on_response)
                dlg.present(self)
            except Exception as exc:
                print(f"dialog error: {exc}", file=__import__("sys").stderr)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(200, _autofix)

    def _on_gl_realize(self, area: Gtk.GLArea) -> None:
        try:
            area.make_current()
        except Exception as exc:
            self._show_gl_failure(str(exc))
            return
        err = area.get_error()
        if err:
            self._show_gl_failure(err.message)
            return
        try:
            self._renderer.init_gl()
            self._gl_ready = True
            mark_gl_success()
        except Exception as exc:
            self._show_gl_failure(str(exc))
            return

        self._audio.start()
        self._guardian.arm()
        if self._tick_id:
            GLib.source_remove(self._tick_id)
        # 品質プロファイルの target_fps（ECO 寄り）に合わせる
        self._base_fps = max(18, int(self._renderer.target_fps))
        self._tick_interval_ms = max(12, int(round(1000.0 / self._base_fps)))
        self._tick_id = GLib.timeout_add(self._tick_interval_ms, self._on_tick)
        q = self._quality
        r = self._renderer
        if r.ps1_mode:
            res = f"{r.internal_w}×{r.internal_h} PS1"
        else:
            res = f"FBO {int(q.fbo_scale * 100)}%"
        self._quality_label.set_text(
            f"描画品質: {q.label}  ·  {self._base_fps}fps  ·  粒子{q.particle_count}  ·  "
            f"{res}  ·  ECO"
        )
        # 初回ヒントに検出理由を短く出す
        reason = (q.reason or "").replace("自動 score=", "score=")
        if len(reason) > 90:
            reason = reason[:87] + "…"
        if reason:
            self._status.set_text(reason)

    def _on_gl_unrealize(self, area: Gtk.GLArea) -> None:
        self._gl_ready = False
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        self._audio.stop()

    def _on_gl_resize(self, area: Gtk.GLArea, width: int, height: int) -> None:
        if not self._gl_ready:
            return
        area.make_current()
        self._renderer.resize(width, height)

    def _on_gl_render(self, area: Gtk.GLArea, _ctx) -> bool:
        if not self._gl_ready:
            return True
        area.make_current()
        try:
            self._renderer.render()
        except Exception as exc:
            self._status.set_text(f"描画エラー: {exc}")
            self._status.set_opacity(1.0)
            self._hint.set_opacity(1.0)
        # True = 自前で描いたので GTK のクリア不要
        return True

    def _desired_interval_ms(self, throttle: float) -> int:
        fps = max(12, int(self._base_fps * max(0.3, throttle)))
        return max(16, int(round(1000.0 / fps)))

    def _on_tick(self) -> bool:
        if not self._gl_ready:
            return GLib.SOURCE_CONTINUE

        # メモリ監視 → 必要ならパージ & GPU スロットル
        need_purge, rstate = self._guardian.tick()
        self._renderer.apply_resource_state(
            throttle=rstate.throttle,
            trails_allowed=rstate.trails_allowed,
            param_update_scale=rstate.param_update_scale,
        )
        if need_purge:
            try:
                self._gl.make_current()
                self._renderer.purge_runtime()
            except Exception:
                pass
            self._guardian.run_python_purge()

        snap = self._audio.snapshot()
        if snap.error:
            self._status.set_text(f"⚠ {snap.error}")
            self._hint.set_opacity(1.0)
        elif snap.ready:
            src = os.path.basename(snap.source_name) if snap.source_name else "monitor"
            self._res_status_counter = (self._res_status_counter + 1) % 45
            if self._res_status_counter == 0 and rstate.note:
                self._status.set_text(
                    f"モニター: {src}  ·  {rstate.note}  ·  "
                    f"thr {rstate.throttle:.2f}  purge×{rstate.purge_count}"
                )
            else:
                self._status.set_text(
                    f"モニター: {src}  ·  Bass {snap.bass:.2f}  Mid {snap.mid:.2f}  "
                    f"Treble {snap.treble:.2f}"
                )
        self._renderer.set_analysis(snap)
        self._gl.queue_render()

        # 間隔変更時はタイマーを張り直し（このコールバックは終了）
        new_iv = self._desired_interval_ms(rstate.throttle)
        if new_iv != self._tick_interval_ms:
            self._tick_interval_ms = new_iv
            self._tick_id = GLib.timeout_add(self._tick_interval_ms, self._on_tick)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_key(self, _ctrl, keyval: int, _keycode: int, _state) -> bool:
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
            return True
        if keyval == Gdk.KEY_F11:
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        if keyval in (Gdk.KEY_space,):
            self._renderer.toggle_rotation()
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H, Gdk.KEY_F1):
            self._toggle_hint()
            return True
        if keyval in (Gdk.KEY_f, Gdk.KEY_F):
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        return False

    def _on_close(self, *_args) -> bool:
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        if self._overlay_hide_id:
            GLib.source_remove(self._overlay_hide_id)
            self._overlay_hide_id = 0
        self._audio.stop()
        return False
