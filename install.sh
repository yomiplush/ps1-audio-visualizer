#!/usr/bin/env bash
# Install SoundOrbit for the current user (GNOME app menu).
# This is a pure Python app — no compile / make / cmake step.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
INSTALL_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/sound-orbit"

echo "==> Installing SoundOrbit（サウンドオービット）"
echo "    source: $ROOT"
echo "    (Python app — no native compile required)"
echo ""

# ---------------------------------------------------------------------------
# Runtime checks with clear per-dependency errors
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null; then
  echo "error: python3 が見つかりません。" >&2
  echo "  Arch/CachyOS: sudo pacman -S python" >&2
  exit 1
fi

echo "Python: $(python3 --version 2>&1)"

if ! command -v parec >/dev/null; then
  echo "warning: parec が見つかりません（音声キャプチャに必要）。"
  echo "  Arch/CachyOS: sudo pacman -S pipewire-pulse"
fi
if ! command -v pactl >/dev/null; then
  echo "warning: pactl が見つかりません。"
  echo "  Arch/CachyOS: sudo pacman -S pipewire-pulse"
fi

echo "==> Checking Python modules…"
if ! python3 - <<'PY'
import sys

def need(label, fn):
    try:
        fn()
        print(f"  ok  {label}")
        return True
    except Exception as exc:
        print(f"  FAIL {label}: {exc}", file=sys.stderr)
        return False

ok = True
ok &= need("PyGObject (gi)", lambda: __import__("gi"))
if ok:
    def _gtk():
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # noqa: F401
    def _adw():
        import gi
        gi.require_version("Adw", "1")
        from gi.repository import Adw  # noqa: F401
    ok &= need("GTK 4 (gi.repository.Gtk)", _gtk)
    ok &= need("libadwaita (gi.repository.Adw)", _adw)

ok &= need("numpy", lambda: __import__("numpy"))
ok &= need("PyOpenGL (OpenGL.GL)", lambda: __import__("OpenGL.GL", fromlist=["GL"]))

# optional but recommended for green labels
try:
    import cairo  # noqa: F401
    print("  ok  python-cairo (optional labels)")
except Exception as exc:
    print(f"  warn python-cairo missing ({exc}) — labels fall back to simple blocks")

if not ok:
    sys.exit(1)
print("deps ok")
PY
then
  echo ""
  echo "error: 依存パッケージが不足しています。venv は使わず、システムパッケージを入れてください。" >&2
  echo "" >&2
  echo "  Arch / CachyOS:" >&2
  echo "    sudo pacman -S --needed \\" >&2
  echo "      gtk4 libadwaita \\" >&2
  echo "      python python-gobject python-cairo python-numpy python-opengl \\" >&2
  echo "      pipewire pipewire-pulse mesa" >&2
  echo "" >&2
  echo "  確認:" >&2
  echo "    python3 -c 'import gi; gi.require_version(\"Gtk\",\"4.0\"); from gi.repository import Gtk; import numpy; from OpenGL import GL; print(\"ok\")'" >&2
  exit 1
fi

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR" "$INSTALL_ROOT"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "$ROOT/" "$INSTALL_ROOT/"
else
  rm -rf "$INSTALL_ROOT"
  mkdir -p "$INSTALL_ROOT"
  cp -a "$ROOT/." "$INSTALL_ROOT/"
  find "$INSTALL_ROOT" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
fi

cat > "$BIN_DIR/sound-orbit" <<EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_ROOT/sound-orbit" "\$@"
EOF
chmod +x "$BIN_DIR/sound-orbit"
chmod +x "$INSTALL_ROOT/sound-orbit"

cp "$ROOT/share/applications/io.github.yomiplush.SoundOrbit.desktop" \
   "$APP_DIR/io.github.yomiplush.SoundOrbit.desktop"
# Portable in-place edit (GNU sed / busybox)
if sed --version >/dev/null 2>&1; then
  sed -i "s|^Exec=.*|Exec=$BIN_DIR/sound-orbit|" \
    "$APP_DIR/io.github.yomiplush.SoundOrbit.desktop"
else
  tmp="$(mktemp)"
  sed "s|^Exec=.*|Exec=$BIN_DIR/sound-orbit|" \
    "$APP_DIR/io.github.yomiplush.SoundOrbit.desktop" >"$tmp"
  mv "$tmp" "$APP_DIR/io.github.yomiplush.SoundOrbit.desktop"
fi

cp "$ROOT/data/icons/io.github.yomiplush.SoundOrbit.svg" \
   "$ICON_DIR/io.github.yomiplush.SoundOrbit.svg"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
fi

echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "注意: $BIN_DIR が PATH にありません。今のシェルでは次のように起動できます:"
  echo "  $BIN_DIR/sound-orbit"
  echo ""
  echo "常に使うなら:"
  echo "  fish:  fish_add_path $BIN_DIR"
  echo "  bash:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
  echo ""
fi

echo "インストール完了。"
echo "  起動: sound-orbit"
echo "  または: $BIN_DIR/sound-orbit"
echo "  または GNOME アプリメニューから「サウンドオービット」"
echo ""
echo "インストールなしで試す場合（リポジトリ直下）:"
echo "  python3 ./sound-orbit"
echo ""
echo "操作: Esc 終了 · F11 全画面 · Space 回転 · H ヘルプ"
echo "システムで再生中の音（ブラウザ・音楽プレイヤー等）に反応します。"
