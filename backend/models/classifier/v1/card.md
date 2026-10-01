# Category classifier v1

**What it does:** predicts a spending category from a merchant key, channel hints,
payment mode, direction and an amount bucket. It never sees SMS text.

**Model:** TF-IDF (word 1-2 grams over all features, character 3-5 grams over the merchant
key) into a class-balanced multinomial logistic regression, C = 2.0, with temperature
scaling (T = 0.6804). Exported as JSON; the server runs it with numpy, and a
parity test checks it against scikit-learn.

**Classes:** entertainment, food, groceries, health, other, shopping, subscriptions, transport, utilities. Below a confidence of 0.3 for a named
merchant (0.75 for an anonymous UPI handle; above 1 means never
answer) the service returns `unknown` and the app asks the user, then remembers the answer
for that merchant or handle.

**Training data:** 21590 synthetic transactions (synth-2026.09).
Known merchants are resolved on the phone before the model is asked, so the model's real
job is unfamiliar local shops and anonymous UPI handles.

**Validation (synthetic, merchant-grouped, only rows the model would see):**
macro-F1 0.6731 overall; local shops
0.9348, anonymous UPI handles
0.1833 (the model cannot know who an
anonymous QR code belongs to, so it should mostly abstain there);
calibration error 0.1066 before and 0.0459 after temperature scaling,
76% of rows answered at 98% accuracy.

**Limits:** these numbers come from synthetic data written by the same team that wrote the
generator, so they are optimistic. Report results on the real, masked test set
(`python -m finsight_ml.evaluate`) instead. Shops with generic names ("Sri Balaji
Enterprises") are ambiguous by design and should be abstained on.
