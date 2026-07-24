#!/usr/bin/env bash
# Install SoundOrbit for the current user (GNOME app menu).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
INSTALL_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/sound-orbit"

echo "==> Installing SoundOrbit（サウンドオービット）"
echo "    source: $ROOT"

# Runtime checks
if ! command -v python3 >/dev/null; then
  echo "error: python3 が必要です" >&2
  exit 1
fi
if ! command -v parec >/dev/null; then
  echo "warning: parec が見つかりません。pipewire-pulse を入れてください:"
  echo "  sudo pacman -S pipewire-pulse"
fi
python3 - <<'PY' || { echo "error: python 依存を確認してください (gtk4, libadwaita, numpy, PyOpenGL)"; exit 1; }
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: F401
import numpy  # noqa: F401
from OpenGL import GL  # noqa: F401
print("deps ok")
PY

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
sed -i "s|^Exec=.*|Exec=$BIN_DIR/sound-orbit|" \
  "$APP_DIR/io.github.yomiplush.SoundOrbit.desktop"

cp "$ROOT/data/icons/io.github.yomiplush.SoundOrbit.svg" \
   "$ICON_DIR/io.github.yomiplush.SoundOrbit.svg"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
fi

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "注意: $BIN_DIR が PATH にありません。"
  echo "  fish:  fish_add_path $BIN_DIR"
  echo "  bash:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
fi

echo ""
echo "インストール完了。"
echo "  起動: sound-orbit"
echo "  または GNOME アプリメニューから「サウンドオービット」"
echo ""
echo "操作:"
echo "  Esc / Ctrl+Q … 終了"
echo "  F11 / F ……… 全画面切替"
echo "  Space ……… カメラ回転 ON/OFF"
echo "  H ………… ヘルプ再表示"
echo ""
echo "システムで再生中の音（ブラウザ・音楽プレイヤー等）に反応します。"
