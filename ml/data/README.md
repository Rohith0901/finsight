# Real data (the only results to present)

Synthetic data trains the model and catches regressions, but the generator and
the parser were written by the same people, so synthetic scores are optimistic.
The real test set is what the review should see.

1. On each team member's phone, with their consent, use **Settings > Developer >
   Export masked messages** (debug builds only). Account numbers, references,
   phone numbers and payee names are masked; amounts and structure are kept.
2. Copy the file to `ml/data/exports/` (gitignored) and **read every row** before
   sharing it inside the team.
3. `python -m finsight_ml.labelling to-csv ml/data/exports/<file>.jsonl labels.csv`
   and fill in the `category` column.
4. `python -m finsight_ml.labelling from-csv labels.csv ml/data/real/test.jsonl`
5. `make eval`: the report gains a "Real, masked test set" section.

Keep `test.jsonl` for final evaluation only. If you label more, put the extra rows
in `train.jsonl` and retrain with `python -m finsight_ml.train --with-real-train`.

The parser has its own real check: add masked messages with their expected
fields to `shared/fixtures/sms_real.jsonl` (same format as `sms_synthetic.jsonl`)
and `flutter test` runs them too.
