#!/usr/bin/env bash
# Builds the FinSight Android app from a fresh checkout, end to end:
#   1. generates the Android project files the repo doesn't keep (first run only)
#   2. applies FinSight's Gradle settings (minSdk 24, ProGuard rules)
#   3. fetches packages, runs the analyzer and every test
#   4. builds a release APK, and installs it if you pass --install
#
# Usage, from the finsight folder:
#   scripts/build_app.sh             # build only
#   scripts/build_app.sh --install   # build, then install on the phone plugged in by USB
#
# Needs Flutter 3.35+ and the Android SDK (Android Studio installs it).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/app"

step() { printf '\n==> %s\n' "$1"; }

if ! command -v flutter >/dev/null 2>&1; then
  cat >&2 <<'MSG'
Flutter isn't installed, or isn't on your PATH.
  macOS with Homebrew:  brew install --cask flutter
  or follow:            https://docs.flutter.dev/get-started/install/macos/mobile-android
Then run `flutter doctor` and accept the Android licenses (`flutter doctor --android-licenses`).
MSG
  exit 1
fi
flutter --version | head -1

if [ ! -f android/settings.gradle.kts ] && [ ! -f android/settings.gradle ]; then
  step "Generating Android project files (kept files are not touched)"
  flutter create --platforms=android --org com.finsight --project-name finsight .
fi

step "Applying FinSight's Android settings"
"$ROOT/scripts/patch_android.sh" android

step "Fetching packages"
flutter pub get

step "Analyzer"
flutter analyze --no-fatal-infos   # lint hints are reported but do not stop the build

step "Tests"
flutter test

step "Release APK"
flutter build apk --release
APK="$ROOT/app/build/app/outputs/flutter-apk/app-release.apk"
cp "$APK" "$ROOT/finsight-demo.apk"
echo "APK: $ROOT/finsight-demo.apk"

if [ "${1:-}" = "--install" ]; then
  step "Installing on the connected phone"
  flutter install --release
fi

cat <<'MSG'

Done. Next:
  - Backend on this laptop:  make serve   (or: docker compose up -d)
  - On the phone: open FinSight > Settings > Server, enter https://<this laptop's IP>:8443,
    the API token from .env and the certificate fingerprint from `make cert`.
  - No backend yet? "Try with demo data instead" works on its own.
MSG
