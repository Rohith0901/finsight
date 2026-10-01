#!/bin/bash
# Double-click in Finder. Installs FinSight on the Android phone plugged in by
# USB, then lets Claude test it: while this window is open, Claude can tap,
# swipe, type, take screenshots and read FinSight's logs on the phone, one
# action at a time. Every action is printed below. Close the window to stop.
#
# Claude writes requests to phone-bridge/request.txt in this folder; this
# script answers in phone-bridge/response.txt and phone-bridge/screen.png.
# Only the actions listed in run_action are accepted.

cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
BRIDGE="$ROOT/phone-bridge"
PKG="com.finsight.finsight"
REPO_ACTIONS="https://github.com/Rohith0901/finsight/actions/workflows/app.yml"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
pause_exit() { echo; read -r -p "Press Enter to close this window." _; exit "${1:-1}"; }

# ---------------------------------------------------------------- adb
ADB=""
for c in "$ANDROID_HOME/platform-tools/adb" "$HOME/Library/Android/sdk/platform-tools/adb" \
         "$(command -v adb 2>/dev/null)" /opt/homebrew/bin/adb /usr/local/bin/adb; do
  if [ -n "$c" ] && [ -x "$c" ]; then ADB="$c"; break; fi
done
if [ -z "$ADB" ]; then
  say "adb (Android's USB tool) isn't installed."
  if command -v brew >/dev/null 2>&1; then
    read -r -p "Install it now with Homebrew? [y/N] " ans
    if [ "$ans" = y ] || [ "$ans" = Y ]; then
      brew install --cask android-platform-tools && ADB="$(command -v adb)"
    fi
  fi
  if [ -z "$ADB" ]; then
    echo "Install it from Android Studio: Settings > Languages & Frameworks > Android SDK >"
    echo "SDK Tools > tick 'Android SDK Platform-Tools' > Apply. Then double-click this again."
    pause_exit 1
  fi
fi
echo "Using $ADB"

# ---------------------------------------------------------------- APK
find_apk() {
  for f in "$ROOT/finsight-demo.apk" "$HOME/Downloads/finsight-apk/app-release.apk" \
           "$HOME/Downloads/app-release.apk"; do
    if [ -f "$f" ]; then echo "$f"; return; fi
  done
  z="$(ls -t "$HOME"/Downloads/finsight-apk*.zip 2>/dev/null | head -1)"
  if [ -n "$z" ]; then
    rm -rf /tmp/finsight-apk && mkdir -p /tmp/finsight-apk && unzip -o -q "$z" -d /tmp/finsight-apk \
      && [ -f /tmp/finsight-apk/app-release.apk ] && echo /tmp/finsight-apk/app-release.apk
  fi
}
APK="$(find_apk)"
if [ -z "$APK" ]; then
  say "Download the app from GitHub"
  echo "Your browser is opening the build page. Click the latest green run,"
  echo "then 'finsight-apk' under Artifacts. This window continues by itself."
  open "$REPO_ACTIONS"
  for _ in $(seq 1 300); do APK="$(find_apk)"; [ -n "$APK" ] && break; sleep 2; done
  [ -z "$APK" ] && { echo "No download found in Downloads."; pause_exit 1; }
fi
echo "APK: $APK"

# ---------------------------------------------------------------- phone
say "Connect the phone"
"$ADB" start-server >/dev/null 2>&1
while true; do
  n="$("$ADB" devices | awk 'NR>1 && $2=="device"' | wc -l | tr -d ' ')"
  [ "$n" = 1 ] && break
  if [ "$n" -gt 1 ]; then echo "More than one phone is connected. Unplug the others."; fi
  if "$ADB" devices | grep -q unauthorized; then
    echo "On the phone, tap 'Allow' on the USB debugging prompt (tick 'Always allow')."
  else
    echo "Waiting for the phone: plug it in, turn on Developer options > USB debugging."
  fi
  sleep 3
done
echo "Phone: $("$ADB" shell getprop ro.product.model | tr -d '\r') (Android $("$ADB" shell getprop ro.build.version.release | tr -d '\r'))"

install_app() {
  echo "Installing... if the phone asks (Play Protect), tap 'Install anyway'."
  "$ADB" install -r "$APK"
}
launch_app() { "$ADB" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; }

say "Installing FinSight"
install_app || { echo "Install failed (see the line above)."; pause_exit 1; }
launch_app
echo "FinSight is open on the phone."

# ---------------------------------------------------------------- helper
mkdir -p "$BRIDGE"
: > "$BRIDGE/request.txt"
echo "ready $(date +%s)" > "$BRIDGE/response.txt"
say "Claude can now test FinSight on your phone. Close this window to stop."
echo "Tip: turn on Do Not Disturb so notifications don't show up in screenshots."
echo "If macOS asks whether Terminal may access a folder, click OK."

screenshot() {
  "$ADB" exec-out screencap -p > "$BRIDGE/screen-full.png" 2>/dev/null || return 1
  # Smaller copy for Claude; keeps tap coordinates in the phone's pixels (scale noted).
  sips -Z 1280 "$BRIDGE/screen-full.png" --out "$BRIDGE/screen.png" >/dev/null 2>&1 \
    || cp "$BRIDGE/screen-full.png" "$BRIDGE/screen.png"
  size="$("$ADB" shell wm size | tail -1 | awk '{print $NF}' | tr -d '\r')"
  echo "screen $size"
}

run_action() { # one line: <id> <action> [args]
  set -f; set -- $1; set +f   # split into words without expanding * or ?
  id="$1"; action="$2"; shift 2
  case "$action" in
    screenshot) screenshot ;;
    tap)        [[ "$1$2" =~ ^[0-9]+$ ]] && "$ADB" shell input tap "$1" "$2" && sleep 1 && screenshot ;;
    swipe)      [[ "$1$2$3$4${5:-300}" =~ ^[0-9]+$ ]] && "$ADB" shell input swipe "$1" "$2" "$3" "$4" "${5:-300}" && sleep 1 && screenshot ;;
    text)       t="$*"; [[ "$t" =~ ^[A-Za-z0-9\ @._:/,-]*$ ]] || { echo "refused: text has characters outside the allowed set"; return; }
                "$ADB" shell input text "$(printf '%s' "$t" | sed 's/ /%s/g')" && sleep 1 && screenshot ;;
    key)        case "$1" in back) k=4;; home) k=3;; enter) k=66;; recents) k=187;; *) echo "refused: unknown key"; return;; esac
                "$ADB" shell input keyevent "$k" && sleep 1 && screenshot ;;
    wait)       [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -le 30 ] && sleep "$1" && screenshot ;;
    launch)     launch_app && sleep 2 && screenshot ;;
    stop)       "$ADB" shell am force-stop "$PKG" && echo "stopped" ;;
    reset)      "$ADB" shell pm clear "$PKG" && echo "FinSight's data on the phone was cleared" ;;
    install)    install_app && launch_app && sleep 2 && screenshot ;;
    logs)       pid="$("$ADB" shell pidof "$PKG" | tr -d '\r')"
                { echo "--- crash buffer"; "$ADB" logcat -d -b crash -t 200
                  echo "--- FinSight (pid ${pid:-not running})"
                  [ -n "$pid" ] && "$ADB" logcat -d --pid="$pid" -t 400; } > "$BRIDGE/logs.txt" 2>&1
                echo "logs written ($(wc -l < "$BRIDGE/logs.txt" | tr -d ' ') lines)" ;;
    info)       echo "model $("$ADB" shell getprop ro.product.model | tr -d '\r')"
                echo "android $("$ADB" shell getprop ro.build.version.release | tr -d '\r')"
                "$ADB" shell dumpsys package "$PKG" | grep -E "versionName|READ_SMS" | head -5 ;;
    *)          echo "refused: unknown action '$action'" ;;
  esac
}

last=""
while true; do
  if ! "$ADB" get-state >/dev/null 2>&1; then echo "Phone disconnected; waiting..."; sleep 3; continue; fi
  line="$(head -1 "$BRIDGE/request.txt" 2>/dev/null)"
  id="${line%% *}"
  if [ -n "$line" ] && [ "$id" != "$last" ]; then
    last="$id"
    echo "$(date +%H:%M:%S)  Claude: ${line#* }"
    out="$(run_action "$line" 2>&1)"
    printf 'done %s\n%s\n' "$id" "$out" > "$BRIDGE/response.txt"
  fi
  sleep 1
done
