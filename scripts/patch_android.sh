#!/usr/bin/env bash
# Applies FinSight's two Android build settings to the Gradle file that
# `flutter create` generates, so a fresh checkout builds the same way everywhere:
#   - minSdk at least 24 (flutter_secure_storage 11 needs it)
#   - the ProGuard rules in app/android/app/proguard-rules.pro for release builds
# Safe to run any number of times. Usage: scripts/patch_android.sh [app/android]
set -euo pipefail
ANDROID_DIR="${1:-$(dirname "$0")/../app/android}"

if [ -f "$ANDROID_DIR/app/build.gradle.kts" ]; then
  f="$ANDROID_DIR/app/build.gradle.kts"
  perl -pi -e 's/minSdk = flutter\.minSdkVersion/minSdk = maxOf(24, flutter.minSdkVersion)/' "$f"
  if ! grep -q 'proguard-rules.pro' "$f"; then
    perl -pi -e 's/^(\s*)(signingConfig = signingConfigs\.getByName\("debug"\))/$1$2\n$1proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")/' "$f"
  fi
elif [ -f "$ANDROID_DIR/app/build.gradle" ]; then
  f="$ANDROID_DIR/app/build.gradle"
  perl -pi -e 's/minSdk(Version)? = flutter\.minSdkVersion/minSdk$1 = Math.max(24, flutter.minSdkVersion)/; s/minSdkVersion flutter\.minSdkVersion/minSdkVersion Math.max(24, flutter.minSdkVersion)/' "$f"
  if ! grep -q 'proguard-rules.pro' "$f"; then
    perl -pi -e "s/^(\\s*)(signingConfig = signingConfigs\\.debug|signingConfig signingConfigs\\.debug)\$/\$1\$2\\n\$1proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'/" "$f"
  fi
else
  echo "No app/build.gradle(.kts) under $ANDROID_DIR. Run 'flutter create' in app/ first." >&2
  exit 1
fi

grep -Eq 'maxOf\(24|Math\.max\(24' "$f" || echo "warning: minSdk line not found in $f; set minSdk to 24 or higher by hand" >&2
grep -q 'proguard-rules.pro' "$f" || echo "warning: release block not found in $f; add the ProGuard file by hand" >&2
echo "patched $f"
