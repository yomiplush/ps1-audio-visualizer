#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export JAVA_HOME="${JAVA_HOME:-$HOME/tools/jdk-17}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$PATH"
cd "$ROOT"
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew :app:assembleDebug --no-daemon
OUT="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
if [[ -f "$OUT" ]]; then
  DEST="$ROOT/../../dist/SoundOrbit-Mobile-debug.apk"
  mkdir -p "$(dirname "$DEST")"
  cp -f "$OUT" "$DEST"
  # stable name in app outputs
  cp -f "$OUT" "$ROOT/app/build/outputs/apk/debug/SoundOrbit-Mobile-debug.apk"
  ls -lh "$OUT" "$DEST"
  echo "APK: $DEST"
else
  echo "Build failed — APK not found" >&2
  exit 1
fi
