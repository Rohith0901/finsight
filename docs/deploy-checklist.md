# Demo release checklist

The "deployment" is a release APK on the demo phone and the backend on the
demo laptop. Run this the day before the review, then the short version in
`docs/demo-runbook.md` on the day. Tick each box; if one fails, it's a no-go
until fixed or a fallback is agreed.

## 1. Code is ready

- [ ] `main` is green in CI (backend and app workflows).
- [ ] `make test` passes on the laptop (ruff, backend tests, ML tests).
- [ ] `cd app && flutter analyze && flutter test` passes.
- [ ] `make eval` has been run on the commit being demoed;
      `ml/reports/latest.md` is committed and the slide numbers match it.
- [ ] `/v1/model-info` reports the classifier version in the report.
- [ ] Tag the commit: `git tag demo-YYYY-MM-DD && git push --tags`.

## 2. Privacy checks (do not skip)

- [ ] `grep -rn "body" app/lib/data` finds nothing (no SMS text in the schema
      or models), and in `app/lib/api` only the HTTP request and response body.
- [ ] `test/api_client_test.dart` passes (it pins the exact fields sent).
- [ ] Run the backend, use the app for five minutes, then read the server log:
      only method, path, status and duration.
- [ ] `.env`, `certs/` and `ml/data/exports/` are not in git
      (`git status --ignored`).
- [ ] Gemini is off (`FINSIGHT_GEMINI_API_KEY` unset) unless the team agreed to
      enable it with a paid key.
- [ ] If real messages appear in the demo, their owner has seen the screens
      and agreed.

## 3. Laptop

- [ ] Docker Desktop running; `docker compose build` succeeds offline after one
      online build (venue internet may be unreliable).
- [ ] `.env` filled in: token (32+ characters), provider `ollama`.
- [ ] `make cert` run once; fingerprint saved somewhere the team can reach.
      Don't regenerate it on the day.
- [ ] `ollama pull qwen2.5:3b` done; the three headline questions answered on
      this laptop in under 10 seconds each after warm-up.
- [ ] macOS firewall allows incoming connections to Docker (or Python).
- [ ] Power adapter packed; sleep disabled during the demo
      (`caffeinate -dims` in a terminal).

## 4. Phone

- [ ] The phone runs Android 7.0 or newer (minSdk 24); rehearse on the exact
      phone used on the day.
- [ ] Release build: `flutter build apk --release`; install with
      `adb install -r build/app/outputs/flutter-apk/app-release.apk`.
      Keep a copy of this exact APK as `finsight-demo.apk`.
- [ ] Fresh install shows the consent screen; SMS permission can be granted
      (or "Allow restricted settings" steps are known).
- [ ] Settings > Server filled in; **Test connection** says Connected on the
      demo network (phone hotspot).
- [ ] Demo data loads; Overview shows safe-to-spend and forecast; Spending,
      Recurring and Ask all work.
- [ ] A correction sticks after closing and reopening the app.
- [ ] Settings > Delete all my data returns to the consent screen.
- [ ] Do Not Disturb on, notifications from chat apps silenced.

## 5. Fallbacks ready

- [ ] Screen recording of the full demo flow on the laptop and a second device.
- [ ] Templates-only chat tested (Settings > Assistant > No model).
- [ ] App works with the laptop off (demo data, rule categories).
- [ ] Printed or offline copy of the slides and `ml/reports/latest.md`.

## Go / no-go

| Check | Owner | Result |
| --- | --- | --- |
| CI green, tag pushed | Backend and delivery | |
| Privacy checks | Android app | |
| Laptop ready | Backend and delivery | |
| Phone ready | Android app | |
| Report and slides match | ML and engine | |

**Rollback:** reinstall the previous `finsight-demo.apk` and check out the
previous `demo-*` tag on the laptop (`git checkout demo-<date> && docker
compose up --build -d`). The phone's data survives an APK reinstall with
`-r`; the backend has no data to roll back.
