# Demo runbook

For the capstone review: one laptop running the backend, one Android phone
running a release APK, about 10 minutes of demo. Do the deploy checklist
(`docs/deploy-checklist.md`) the day before.

## 30 minutes before

1. **Network.** Use the phone's hotspot or a network you control; venue Wi-Fi
   often blocks device-to-device traffic. Connect the laptop to it and note its
   IP (`ipconfig getifaddr en0` on macOS).
2. **Backend.**
   ```bash
   cd finsight
   ollama serve &            # if the Ollama app isn't already running
   docker compose up -d      # or: make serve
   curl -k https://127.0.0.1:8443/healthz
   ```
3. **Warm the model** so the first answer isn't slow:
   `ollama run qwen2.5:3b "hello" > /dev/null`
4. **Phone.** Settings > Server: update the address to the new IP if it
   changed, then **Test connection**. Close other apps. Brightness up, Do Not
   Disturb on (bank OTPs and chats shouldn't pop up on screen).
5. **Data.** Decide: real messages (only if the presenter consents and has
   checked what will be on screen) or demo data. Default to demo data.
6. Open a terminal with `docker compose logs -f api` (or the `make serve`
   window) to show during the privacy part.

## The script

| Time | Show | Say |
| --- | --- | --- |
| 0:00 | Consent screen | "We read bank messages only. The text never leaves the phone; the server stores nothing." |
| 0:45 | Tap **Try with demo data instead** | "Three months of a synthetic student's bank SMS, about 250 messages. OTPs, offers and failed payments are ignored." |
| 1:30 | **Overview**: safe-to-spend today, month-end forecast | "Balance minus bills still due minus the savings target, divided by days left. The forecast says how sure it is." |
| 3:00 | **Spending**: open an Unknown or wrong row, pick a category | "Corrections apply at once to that merchant's past and future payments." |
| 4:00 | **Recurring** | "Found from payment intervals and amounts, not from merchant names." |
| 5:00 | **Ask**: "How much can I spend today?", "Why did I overspend?", "Can I afford a ₹2,000 jacket?" | "Every number comes from our engine. A verifier rejects answers with numbers it didn't compute." Tap the facts under an answer. |
| 7:00 | Laptop log window | "The server logged method, path, status, time. No amounts, no merchants, no messages." |
| 8:00 | `ml/reports/latest.md` (or the slide) | "Synthetic results first, clearly labelled; then our real masked test set." |
| 9:00 | Settings > **Delete all my data** | "One tap, everything gone." |

Keep a second phone or a screen recording of the full flow as a backup.

## If something goes wrong

| Symptom | Fix in the room |
| --- | --- |
| Test connection fails | Check the IP; check both devices are on the same network; `curl -k https://<IP>:8443/healthz` from the laptop; macOS firewall may be blocking Docker or Python (System Settings > Network > Firewall). |
| "Certificate did not match" | The cert was regenerated. Paste the new fingerprint from `make cert` output (or `openssl x509 -in certs/finsight.crt -noout -fingerprint -sha256`). |
| 401 unauthorized | Token in the app differs from `.env`. Re-paste it. |
| Chat is slow or says it used templates | Ollama is down or cold. Answers still work from templates; say so, it's a designed fallback. Or set Settings > Assistant > No model. |
| No backend at all | Demo data still loads; known merchants, people and salary are categorised on the phone. Show Spending and say the rest needs the laptop. Switch to the recording for the insights part. |
| SMS permission dialog doesn't appear | Use demo data. (Sideload restriction: App info > ⋮ > Allow restricted settings, after the demo.) |
| App crashes on launch | Reinstall the APK you tested yesterday: `adb install -r finsight-demo.apk`. |

## After the demo

`docker compose down`. If real messages were used, delete the data on the
phone (Settings > Delete all my data) unless the owner wants to keep it.
