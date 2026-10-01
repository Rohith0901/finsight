# FinSight app (Flutter, Android)

The phone side of FinSight: reads bank SMS with consent, parses them on the
phone, keeps only the parsed fields in an encrypted SQLite database, and shows
insights computed by the backend.

> **Status.** This code was written without a Flutter toolchain (it was syntax
> checked and its logic was cross-checked against the Python reference, but it
> has never been compiled). Expect a few small fixes the first time you run
> `flutter analyze`. CI (`.github/workflows/app.yml`) runs the same commands.

## Build it: one command

You need Flutter 3.35 or newer (`flutter --version`) and Android Studio with an
Android SDK. From the `finsight` folder:

```bash
scripts/build_app.sh --install    # or `make app-install`; drop --install to only build
```

It generates the Android project files on the first run, applies FinSight's
Gradle settings, runs the analyzer and every test, builds a release APK
(copied to `finsight/finsight-demo.apk`) and installs it on the phone
connected by USB.

**No Flutter on your machine?** Push the repo to GitHub. The `app` workflow
(`.github/workflows/app.yml`) does the same steps on GitHub's servers and
attaches the APK to the run: Actions > app > the latest run > Artifacts >
`finsight-apk`. Unzip it and install the APK on the phone.

## What the script does, step by step

If you'd rather run the steps yourself, from this folder:

```bash
# 1. Generate the Android build files that aren't in the repo (Gradle, the
#    wrapper, launcher icons, styles). Existing files are kept, including
#    AndroidManifest.xml, MainActivity.kt and test/widget_test.dart.
flutter create --platforms=android --org com.finsight --project-name finsight .

# 2. Fetch packages and check everything.
flutter pub get
flutter analyze --no-fatal-infos
flutter test        # needs the sqlite3 library: preinstalled on macOS;
                    # on Linux, `sudo apt install libsqlite3-dev`
```

Then set two Gradle options (`../scripts/patch_android.sh` does this for you)
in `android/app/build.gradle.kts`, the file `flutter create` just made:

```kotlin
android {
    defaultConfig {
        minSdk = maxOf(24, flutter.minSdkVersion)   // flutter_secure_storage 11 needs 24
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")   // already there
            // SQLCipher's native classes must survive shrinking.
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}
```

Commit the generated `android/` files so everyone builds the same thing.

If `flutter create` reports that it overwrote `AndroidManifest.xml` or
`MainActivity.kt` (it shouldn't), restore them with `git checkout -- android/app/src/main`.

## Run

```bash
flutter run                     # on a connected phone (USB debugging on)
flutter build apk --release     # app/build/app/outputs/flutter-apk/app-release.apk
```

On first launch the consent screen explains what is read. "Try with demo data
instead" loads three months of a synthetic user's messages, so the app works
without SMS permission and without a backend (categories from rules only).

To connect the backend, open **Settings > Server** and enter:

| Field | Value |
| --- | --- |
| Server address | `https://<laptop IP>:8443` (same Wi-Fi or phone hotspot) |
| API token | `FINSIGHT_API_TOKEN` from the laptop's `.env` |
| Certificate fingerprint | printed by `make cert` (`scripts/gen_cert.sh`) |

**Test connection** should say "Connected". The app trusts only a certificate
with that exact fingerprint, so the laptop's IP can change without a new cert.

### Sideloaded installs on Android 13+

Android 15 treats SMS as a restricted permission for sideloaded apps, and
Android 13 and 14 do the same for some settings. Installing with `flutter run` or
`adb install` usually avoids it; an APK opened from a browser download, a chat
app or a file manager triggers it. If the permission dialog never appears or SMS
stays "not allowed": open **App info > FinSight > ⋮ > Allow restricted
settings**, then tap **Allow** in FinSight's Settings again. Test this on the
demo phone early.

## Layout

| Path | What |
| --- | --- |
| `lib/ingestion/` | `sender_filter` (bank vs personal), `sms_parser` (port of `ml/finsight_ml/parser_ref.py`), `normalizer` (port of `names.py`), `pipeline` (dedupe, rules, insert), `sms_source` (inbox and demo) |
| `lib/data/` | encrypted database and schema, `Txn` model, repository |
| `lib/api/` | HTTPS client with certificate pinning |
| `lib/state/app_state.dart` | everything the screens call |
| `lib/ui/` | consent, overview, spending, recurring, ask, settings |
| `android/.../MainActivity.kt` | SMS permission, inbox reads and change events (platform channels `finsight/sms`, `finsight/sms_events`) |
| `assets/shared/` | copies of `../shared/*.json` (`make fixtures` refreshes them; a test fails if they drift) |
| `assets/demo/demo_sms.jsonl` | demo messages |

## Rules that keep the privacy promise

- The SMS body is parsed in memory and never stored, logged or sent. Messages
  from phone numbers are dropped in Kotlin before Dart sees them.
- `Txn.toApi()` is the only thing sent to the server, and it holds no names,
  references or account numbers. People appear as `person:<hash>` with a
  per-install salt. A test pins the exact field list.
- The database key and the salt live in the Android Keystore
  (`flutter_secure_storage`). Settings > Delete all my data wipes every table.

## Changing the parser

The Dart parser and `ml/finsight_ml/parser_ref.py` must stay regex-for-regex
identical. Change both, run `make fixtures` and the Python tests
(`ml/tests/test_parser_fixtures.py`), then `flutter test`
(`test/parser_test.dart` runs the same 1,083 fixtures). See
`docs/onboarding.md` for adding a bank template.
