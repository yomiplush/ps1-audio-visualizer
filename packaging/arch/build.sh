#!/usr/bin/env bash
# Build Arch/CachyOS pacman package (.pkg.tar.zst) for Octopi / pacman -U.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST="${DIST:-$ROOT/dist}"
WORKDIR="${WORKDIR:-$DIST/arch-build}"

VERSION="$(python3 - <<PY
import pathlib, re
p = pathlib.Path("$ROOT/src/soundorbit/__init__.py").read_text()
m = re.search(r'__version__\s*=\s*["\']([^"\']+)', p)
print(m.group(1) if m else "0.0.0")
PY
)"
PKGREL="${PKGREL:-1}"
PKGNAME="soundorbit"
TARBALL="${PKGNAME}-${VERSION}.tar.gz"

echo "==> Building Arch package: ${PKGNAME}-${VERSION}-${PKGREL}"
echo "    source:  $ROOT"
echo "    workdir: $WORKDIR"
echo "    out:     $DIST/"

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR" "$DIST"

# Stage source tree (only runtime files for package())
STAGE="$WORKDIR/${PKGNAME}-${VERSION}"
mkdir -p "$STAGE/src/soundorbit" "$STAGE/data/icons" "$STAGE/share/applications"

cp -a "$ROOT/sound-orbit" "$STAGE/sound-orbit"
cp -a "$ROOT/src/soundorbit/"*.py "$STAGE/src/soundorbit/"
cp -a "$ROOT/data/icons/io.github.yomiplush.SoundOrbit.svg" "$STAGE/data/icons/"
cp -a "$ROOT/share/applications/io.github.yomiplush.SoundOrbit.desktop" \
  "$STAGE/share/applications/"
cp -a "$ROOT/LICENSE" "$STAGE/LICENSE"
cp -a "$ROOT/README.md" "$STAGE/README.md"

# System launcher installed to /usr/bin/sound-orbit
cat >"$STAGE/usr-bin-sound-orbit" <<'EOF'
#!/usr/bin/env bash
# SoundOrbit system launcher (pacman package)
export PYTHONNOUSERSITE=1
exec python3 /usr/share/sound-orbit/sound-orbit "$@"
EOF
chmod +x "$STAGE/usr-bin-sound-orbit"

# Tar for makepkg source=
(
  cd "$WORKDIR"
  tar -czf "$TARBALL" "${PKGNAME}-${VERSION}"
)

# PKGBUILD + install script (sync pkgver)
cp "$PKG_DIR/PKGBUILD" "$WORKDIR/PKGBUILD"
cp "$PKG_DIR/soundorbit.install" "$WORKDIR/soundorbit.install"
sed -i "s/^pkgver=.*/pkgver=${VERSION}/" "$WORKDIR/PKGBUILD"
sed -i "s/^pkgrel=.*/pkgrel=${PKGREL}/" "$WORKDIR/PKGBUILD"

# Build as non-root (makepkg refuses root)
if [[ "$(id -u)" -eq 0 ]]; then
  echo "error: run as normal user (makepkg cannot run as root)" >&2
  exit 1
fi

(
  cd "$WORKDIR"
  # Prefer --nodeps so build works without sudo; pacman -U still resolves depends.
  # Set MAKEPKG_SYNCDEPS=1 to let makepkg install missing deps (needs privilege).
  if [[ "${MAKEPKG_SYNCDEPS:-0}" == "1" ]]; then
    makepkg -f --syncdeps --noconfirm || makepkg -f --nodeps
  else
    makepkg -f --nodeps
  fi
)

# Collect package
shopt -s nullglob
PKGS=("$WORKDIR"/${PKGNAME}-*.pkg.tar.zst "$WORKDIR"/${PKGNAME}-*.pkg.tar.xz)
if [[ ${#PKGS[@]} -eq 0 ]]; then
  echo "error: makepkg produced no package in $WORKDIR" >&2
  ls -la "$WORKDIR" >&2 || true
  exit 1
fi

for p in "${PKGS[@]}"; do
  cp -f "$p" "$DIST/"
  echo "    → $DIST/$(basename "$p")"
done

# Stable symlink for scripts
LATEST="$(ls -1t "$DIST"/${PKGNAME}-*.pkg.tar.zst 2>/dev/null | head -1 || true)"
if [[ -n "$LATEST" ]]; then
  ln -sfn "$(basename "$LATEST")" "$DIST/${PKGNAME}-latest.pkg.tar.zst"
  echo "    → $DIST/${PKGNAME}-latest.pkg.tar.zst -> $(basename "$LATEST")"
fi

echo ""
echo "Build complete."
echo "  Install:   sudo pacman -U $DIST/${PKGNAME}-${VERSION}-${PKGREL}-any.pkg.tar.zst"
echo "  Or:        ./install-pacman.sh"
echo "  Uninstall: sudo pacman -R ${PKGNAME}"
echo "  Octopi:    search 「soundorbit」 → 削除"
