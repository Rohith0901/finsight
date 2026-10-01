# ADR-002: Flutter UI with an Android-native SMS path

Status: Accepted (revised 2026-10-01)
Date: 2026-09-30 · Deciders: the team

## Context

Only Android lets apps read the SMS inbox, so Flutter's iOS reach is unused.
Flutter was still chosen for UI speed. The plan was to try the
`another_telephony` plugin first and fall back to a Kotlin receiver.

## Decision (as built)

No SMS plugin. `MainActivity.kt` exposes two platform channels:

- `finsight/sms` (method channel): `hasPermission`, `requestPermission`,
  `readInbox(since, limit)` returning `{address, body, date}` for messages newer
  than `since`, oldest first, paged without splitting a millisecond.
- `finsight/sms_events` (event channel): fires when the inbox changes while the
  app is open (a `ContentObserver`).

Messages from phone numbers are dropped in Kotlin, so their text never reaches
Dart. There is no background `BroadcastReceiver`: the app reads everything
since its checkpoint on launch and on resume, and dedupe makes re-reads safe.

## Why the revision

- The plugin route added a third-party dependency with full SMS access for
  about 100 lines of Kotlin we can read and test ourselves.
- Reading the inbox on resume gives the same data as a background receiver for
  this app, without a receiver that runs when the user isn't looking.
- Fewer permissions: `READ_SMS` only, no `RECEIVE_SMS`.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| `another_telephony` | Ready-made, background receipt | Community fork, broad access, another thing to audit |
| `telephony` | Popular | Discontinued since 2022 |
| **Own Kotlin channel (chosen)** | Small, auditable, filters personal SMS natively | We maintain it |
| Native Kotlin app | Best SMS access | Rebuild the whole UI |

## Consequences

- New transactions appear when the app opens or while it is open, not as
  notifications in the background. Acceptable for the capstone; a background
  receiver can be added later behind the same channel.
- Sideloaded installs on Android 13+ may need "Allow restricted settings"
  (Android 15 lists SMS among restricted permissions). Test on the demo phone.
