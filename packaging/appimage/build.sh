#!/usr/bin/env bash
# Build SoundOrbit-x86_64.AppImage
#
# Thin AppImage: ships the app + smart launcher. Uses host Python/GTK
# (auto-installs system packages on first run if missing).
#
# Requires: appimagetool (downloaded automatically if missing)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$(cd "$(dirname "$0")" && pwd)"
DIST="${DIST:-$ROOT/dist}"
APPDIR="$DIST/SoundOrbit.AppDir"
ARCH="${ARCH:-$(uname -m)}"
VERSION="$(python3 - <<PY
import pathlib, re
p = pathlib.Path("$ROOT/src/soundorbit/__init__.py").read_text()
m = re.search(r'__version__\s*=\s*["\']([^"\']+)', p)
print(m.group(1) if m else "0.0.0")
PY
)"
OUT="$DIST/SoundOrbit-${VERSION}-${ARCH}.AppImage"
TOOLS="${TOOLS_DIR:-$DIST/tools}"

echo "==> Building SoundOrbit AppImage"
echo "    version: $VERSION"
echo "    arch:    $ARCH"
echo "    out:     $OUT"

mkdir -p "$DIST" "$TOOLS"

# Icon PNG (generated if tooling available)
ICON_PNG="$PKG/sound-orbit.png"
if [[ ! -f "$ICON_PNG" ]]; then
  SVG="$ROOT/data/icons/io.github.yomiplush.SoundOrbit.svg"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 256 -h 256 "$SVG" -o "$ICON_PNG"
  elif command -v convert >/dev/null 2>&1; then
    convert -background none -resize 256x256 "$SVG" "$ICON_PNG"
  else
    echo "error: need rsvg-convert or ImageMagick to create icon PNG" >&2
    exit 1
  fi
fi

# --- tools ---
need_tool() {
  local name="$1" url="$2" dest="$3"
  if [[ -x "$dest" ]]; then
    return 0
  fi
  echo "==> Downloading $name…"
  curl -fsSL -o "$dest" "$url"
  chmod +x "$dest"
}

APPIMAGETOOL="$TOOLS/appimagetool-${ARCH}.AppImage"
need_tool appimagetool \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage" \
  "$APPIMAGETOOL"

# --- AppDir ---
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/sound-orbit" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# App payload (source tree without .git / pyc)
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'dist' \
    --exclude 'packaging' \
    "$ROOT/" "$APPDIR/usr/share/sound-orbit/"
else
  cp -a "$ROOT/." "$APPDIR/usr/share/sound-orbit/"
  rm -rf "$APPDIR/usr/share/sound-orbit/.git" \
         "$APPDIR/usr/share/sound-orbit/dist" \
         "$APPDIR/usr/share/sound-orbit/packaging"
  find "$APPDIR/usr/share/sound-orbit" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
fi

chmod +x "$APPDIR/usr/share/sound-orbit/sound-orbit" \
         "$APPDIR/usr/share/sound-orbit/install.sh" || true

# Runtime helpers for AppRun (GPU detect) — packaging/ is excluded from payload
mkdir -p "$APPDIR/usr/share/sound-orbit-runtime"
install -m 644 "$PKG/gpu-detect.sh" "$APPDIR/usr/share/sound-orbit-runtime/gpu-detect.sh"
# Also keep a copy under app tree for source installs that vendor AppRun
mkdir -p "$APPDIR/usr/share/sound-orbit/packaging/appimage"
install -m 644 "$PKG/gpu-detect.sh" \
  "$APPDIR/usr/share/sound-orbit/packaging/appimage/gpu-detect.sh"

# Launcher name expected by desktop Exec=
install -m 755 "$PKG/AppRun" "$APPDIR/AppRun"
# Also provide usr/bin/sound-orbit for desktop integration inside image
cat > "$APPDIR/usr/bin/sound-orbit" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
# usr/bin -> AppDir root is ../..
exec "$HERE/../../AppRun" "$@"
EOF
chmod +x "$APPDIR/usr/bin/sound-orbit"

# Desktop + icons (top-level required by appimagetool)
install -m 644 "$PKG/sound-orbit.desktop" "$APPDIR/sound-orbit.desktop"
install -m 644 "$PKG/sound-orbit.desktop" "$APPDIR/usr/share/applications/sound-orbit.desktop"
# Patch version into desktop
sed -i "s/^X-AppImage-Version=.*/X-AppImage-Version=$VERSION/" \
  "$APPDIR/sound-orbit.desktop" \
  "$APPDIR/usr/share/applications/sound-orbit.desktop" 2>/dev/null || true

install -m 644 "$PKG/sound-orbit.png" "$APPDIR/sound-orbit.png"
install -m 644 "$PKG/sound-orbit.png" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps/sound-orbit.png"
install -m 644 "$ROOT/data/icons/io.github.yomiplush.SoundOrbit.svg" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps/sound-orbit.svg" 2>/dev/null || true

# Symlink icon name for appimagetool
ln -sf sound-orbit.png "$APPDIR/.DirIcon" 2>/dev/null || cp "$APPDIR/sound-orbit.png" "$APPDIR/.DirIcon"

echo "==> AppDir ready: $APPDIR"
du -sh "$APPDIR"

echo "==> Running appimagetool…"
export ARCH
# Extract-and-run if FUSE is unavailable
if ! "$APPIMAGETOOL" --appimage-help >/dev/null 2>&1; then
  export APPIMAGE_EXTRACT_AND_RUN=1
fi

# Prefer type-2 runtime; fail clearly if squashfs tools missing
if ! "$APPIMAGETOOL" "$APPDIR" "$OUT" 2>"$DIST/appimagetool.log"; then
  echo "appimagetool failed; log:" >&2
  cat "$DIST/appimagetool.log" >&2 || true
  # Retry with extract-and-run
  APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$OUT"
fi

chmod +x "$OUT"
ln -sfn "$(basename "$OUT")" "$DIST/SoundOrbit-x86_64.AppImage" 2>/dev/null \
  || ln -sfn "$(basename "$OUT")" "$DIST/SoundOrbit-${ARCH}.AppImage"

echo ""
echo "Built: $OUT"
echo "Size:  $(du -h "$OUT" | awk '{print $1}')"
echo ""
echo "Usage on any Linux (Arch/CachyOS/Ubuntu/Fedora):"
echo "  chmod +x $OUT"
echo "  $OUT"
echo ""
echo "First run may ask to install GTK / numpy / OpenGL system packages."
echo "Optional desktop install after run: SOUNDORBIT_INSTALL=1 $OUT"
