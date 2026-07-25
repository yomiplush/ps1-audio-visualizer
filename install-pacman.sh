#!/usr/bin/env bash
# Build + install SoundOrbit as a real pacman package (Octopi-visible).
# Uninstall later: sudo pacman -R soundorbit  (or Octopi → 削除)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="${DIST:-$ROOT/dist}"

echo "==> SoundOrbit pacman install (Arch / CachyOS / Octopi)"
echo ""

if ! command -v pacman >/dev/null 2>&1; then
  echo "error: pacman が見つかりません。このスクリプトは Arch / CachyOS 向けです。" >&2
  echo "  他の Linux では AppImage を使ってください。" >&2
  exit 1
fi

if ! command -v makepkg >/dev/null 2>&1; then
  echo "error: makepkg がありません。base-devel を入れてください:" >&2
  echo "  sudo pacman -S --needed base-devel" >&2
  exit 1
fi

# Remove conflicting user-local install leftovers that hide system package
USER_BIN="${XDG_BIN_HOME:-$HOME/.local/bin}/sound-orbit"
USER_DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.yomiplush.SoundOrbit.desktop"
if [[ -e "$USER_BIN" ]] || [[ -e "$USER_DESKTOP" ]]; then
  echo "==> ユーザーローカルインストールを検出 → 退避（システムパッケージ優先のため）"
  [[ -e "$USER_BIN" ]] && rm -f "$USER_BIN" && echo "    removed $USER_BIN"
  [[ -e "$USER_DESKTOP" ]] && rm -f "$USER_DESKTOP" && echo "    removed $USER_DESKTOP"
fi

echo "==> パッケージをビルド中…"
"$ROOT/packaging/arch/build.sh"

# Prefer stable symlink, then newest versioned package
if [[ -L "$DIST/soundorbit-latest.pkg.tar.zst" ]] || [[ -f "$DIST/soundorbit-latest.pkg.tar.zst" ]]; then
  PKG="$(readlink -f "$DIST/soundorbit-latest.pkg.tar.zst")"
else
  shopt -s nullglob
  PKGS=("$DIST"/soundorbit-*-any.pkg.tar.zst)
  if [[ ${#PKGS[@]} -eq 0 ]]; then
    echo "error: パッケージが見つかりません ($DIST)" >&2
    exit 1
  fi
  PKG="$(ls -1t "${PKGS[@]}" | head -1)"
  PKG="$(readlink -f "$PKG")"
fi
if [[ ! -f "$PKG" ]]; then
  echo "error: パッケージが見つかりません: $PKG" >&2
  exit 1
fi

echo ""
echo "==> インストール: $PKG"
if [[ "$(id -u)" -eq 0 ]]; then
  pacman -U --noconfirm "$PKG"
else
  if command -v sudo >/dev/null 2>&1; then
    sudo pacman -U --noconfirm "$PKG"
  elif command -v pkexec >/dev/null 2>&1; then
    pkexec pacman -U --noconfirm "$PKG"
  else
    echo "error: root 権限が必要です。次を実行してください:" >&2
    echo "  sudo pacman -U $PKG" >&2
    exit 1
  fi
fi

echo ""
echo "インストール完了 — Octopi で「soundorbit」と検索すると表示されます。"
echo "  起動:     sound-orbit"
echo "  削除 CLI: sudo pacman -R soundorbit"
echo "  削除 GUI: Octopi → 検索 soundorbit → 削除"
echo ""
pacman -Q soundorbit 2>/dev/null || true
