#!/usr/bin/env bash
# Create a GitHub Release tag and let CI attach BOTH assets:
#   SoundOrbit-Linux-x86_64.AppImage
#   SoundOrbit-Windows-x64.exe
#
# Usage:
#   ./scripts/release.sh v1.7.0
#   ./scripts/release.sh v1.7.0 --notes "bugfixes"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "Usage: $0 vX.Y.Z [--notes \"text\"]" >&2
  exit 1
fi
shift || true

NOTES=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --notes)
      NOTES="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI required" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree not clean — commit first" >&2
  git status -sb
  exit 1
fi

# Ensure we're on main / pushed
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Branch: $BRANCH"
echo "==> Tag:    $TAG"

git fetch origin --tags 2>/dev/null || true
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "error: tag $TAG already exists" >&2
  exit 1
fi

git push origin "$BRANCH"
git tag -a "$TAG" -m "SoundOrbit $TAG"
git push origin "$TAG"

echo "==> Tag pushed. Waiting for dual-asset workflow…"
echo "    (Linux AppImage + Windows .exe will upload to the Release)"

# softprops creates the release when the workflow runs; also create a draft shell
# so the release page exists immediately (workflow will attach files).
if [[ -n "$NOTES" ]]; then
  gh release create "$TAG" --title "SoundOrbit $TAG" --notes "$NOTES" || true
else
  gh release create "$TAG" --title "SoundOrbit $TAG" --generate-notes || true
fi

# Trigger dual asset workflow explicitly (covers race where tag push was missed)
gh workflow run "Release dual assets" -f "tag=$TAG" || true

echo ""
echo "Watch:"
echo "  gh run list --workflow=release-assets.yml --limit 3"
echo "  gh release view $TAG"
echo ""
echo "Expected assets:"
echo "  SoundOrbit-Linux-x86_64.AppImage"
echo "  SoundOrbit-Windows-x64.exe"
