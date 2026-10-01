"""Train the category classifier and write backend/models/classifier/<version>/.

    python -m finsight_ml.train [--version v1] [--users 60] [--seed 7]

Steps: grouped train/validation split by merchant; choose C by validation
macro-F1; fit a temperature on validation; pick the abstain threshold that keeps
answered predictions at least 90% correct; refit on everything; export JSON and
a model card.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupShuffleSplit

from . import synth
from .datasets import classifier_rows
from .model import (
    choose_threshold,
    expected_calibration_error,
    export,
    fit,
    fit_temperature,
)
from .paths import MODELS
from .real_data import load_real

C_GRID = (0.5, 1.0, 2.0, 4.0, 8.0)


def split(rows: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    groups = [r["group"] for r in rows]
    tr, va = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
                  .split(rows, groups=groups))
    return [rows[i] for i in tr], [rows[i] for i in va]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--users", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--with-real-train", action="store_true",
                    help="also train on ml/data/real/train.jsonl if it exists")
    args = ap.parse_args()

    users = synth.generate(args.users, args.seed)
    rows = classifier_rows(users)
    if args.with_real_train:
        extra = load_real("train.jsonl")
        print(f"adding {len(extra)} real training rows")
        rows += extra
    train_rows, valid_all = split(rows, args.seed)
    # Known merchants are resolved on the phone and never reach the model, so tune and
    # report on the rows the model actually sees: unfamiliar shops and anonymous handles.
    valid_rows = [r for r in valid_all if not r["known"]]
    y_valid = [r["category"] for r in valid_rows]

    best = None
    for C in C_GRID:
        m = fit(train_rows, C=C, seed=args.seed)
        pred = [m.classes[i] for i in m.proba(valid_rows).argmax(axis=1)]
        score = f1_score(y_valid, pred, average="macro")
        print(f"C={C:<4} validation macro-F1 {score:.3f}")
        if best is None or score > best[0]:
            best = (score, C, m)
    score, C, m = best

    raw = m.proba(valid_rows, temperature=1.0)
    correct = np.array([m.classes[i] == y for i, y in zip(raw.argmax(axis=1), y_valid)])
    ece_before = expected_calibration_error(raw, correct)
    m.temperature = fit_temperature(m, valid_rows)
    cal = m.proba(valid_rows)
    ece_after = expected_calibration_error(cal, correct)
    named = np.array([bool(r["merchant_norm"]) for r in valid_rows])
    threshold = choose_threshold(cal[named], correct[named])
    threshold_anonymous = choose_threshold(cal[~named], correct[~named])
    answered = np.where(named, cal.max(axis=1) >= threshold,
                        cal.max(axis=1) >= threshold_anonymous)
    answered_accuracy = float(correct[answered].mean()) if answered.any() else 0.0
    print(f"chosen C={C}  temperature={m.temperature:.3f}  ECE {ece_before:.3f} -> "
          f"{ece_after:.3f}  thresholds: named={threshold} anonymous={threshold_anonymous}  "
          f"coverage={answered.mean():.1%}  answered accuracy={answered_accuracy:.1%}")

    segments = {}
    for name, keep in (("local_shops", lambda r: bool(r["merchant_norm"])),
                       ("anonymous_handles", lambda r: not r["merchant_norm"])):
        idx = [i for i, r in enumerate(valid_rows) if keep(r)]
        if idx:
            ys = [y_valid[i] for i in idx]
            ps = [m.classes[j] for j in cal[idx].argmax(axis=1)]
            ans = answered[idx]
            ok = correct[idx]
            segments[name] = {
                "rows": len(idx),
                "macro_f1": round(f1_score(ys, ps, average="macro"), 4),
                "accuracy": round(float(np.mean([a == b for a, b in zip(ys, ps)])), 4),
                "coverage_at_threshold": round(float(ans.mean()), 4),
                "answered_accuracy": round(float(ok[ans].mean()), 4) if ans.any() else None,
            }
            print(f"  {name:18} rows={len(idx):5} macro-F1={segments[name]['macro_f1']:.3f} "
                  f"accuracy={segments[name]['accuracy']:.3f} "
                  f"answered={segments[name]['coverage_at_threshold']:.0%}")

    metrics = {
        "data": "synthetic; merchant-grouped 80/20 split; validation excludes merchants the "
                "phone resolves itself",
        "validation_rows": len(valid_rows),
        "segments": segments,
        "validation_macro_f1": round(score, 4),
        "C": C,
        "temperature": round(m.temperature, 4),
        "ece_before": round(ece_before, 4),
        "ece_after": round(ece_after, 4),
        "threshold": threshold,
        "threshold_anonymous": threshold_anonymous,
        "coverage_at_threshold": round(float(answered.mean()), 4),
        "answered_accuracy": round(answered_accuracy, 4),
        "train_rows": len(rows),
    }

    final = fit(rows, C=C, seed=args.seed)
    final.temperature = m.temperature
    model = export(final, threshold, threshold_anonymous, args.version, synth.DATASET_VERSION,
                   metrics)
    out = MODELS / args.version
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "card.md").write_text(model_card(args.version, metrics, final.classes), encoding="utf-8")
    size = (out / "model.json").stat().st_size / 1e6
    print(f"wrote {out / 'model.json'} ({size:.1f} MB), metrics.json, card.md")


def model_card(version: str, m: dict, classes: list[str]) -> str:
    return f"""# Category classifier {version}

**What it does:** predicts a spending category from a merchant key, channel hints,
payment mode, direction and an amount bucket. It never sees SMS text.

**Model:** TF-IDF (word 1-2 grams over all features, character 3-5 grams over the merchant
key) into a class-balanced multinomial logistic regression, C = {m['C']}, with temperature
scaling (T = {m['temperature']}). Exported as JSON; the server runs it with numpy, and a
parity test checks it against scikit-learn.

**Classes:** {", ".join(classes)}. Below a confidence of {m['threshold']} for a named
merchant ({m['threshold_anonymous']} for an anonymous UPI handle; above 1 means never
answer) the service returns `unknown` and the app asks the user, then remembers the answer
for that merchant or handle.

**Training data:** {m['train_rows']} synthetic transactions ({synth.DATASET_VERSION}).
Known merchants are resolved on the phone before the model is asked, so the model's real
job is unfamiliar local shops and anonymous UPI handles.

**Validation (synthetic, merchant-grouped, only rows the model would see):**
macro-F1 {m['validation_macro_f1']} overall; local shops
{m['segments'].get('local_shops', {}).get('macro_f1')}, anonymous UPI handles
{m['segments'].get('anonymous_handles', {}).get('macro_f1')} (the model cannot know who an
anonymous QR code belongs to, so it should mostly abstain there);
calibration error {m['ece_before']} before and {m['ece_after']} after temperature scaling,
{m['coverage_at_threshold']:.0%} of rows answered at {m['answered_accuracy']:.0%} accuracy.

**Limits:** these numbers come from synthetic data written by the same team that wrote the
generator, so they are optimistic. Report results on the real, masked test set
(`python -m finsight_ml.evaluate`) instead. Shops with generic names ("Sri Balaji
Enterprises") are ambiguous by design and should be abstained on.
"""


if __name__ == "__main__":
    main()
