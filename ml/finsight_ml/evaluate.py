"""One command for every number in the report: python -m finsight_ml.evaluate

Writes ml/reports/latest.md and ml/reports/latest.json. Every module is compared
with a simple baseline. Synthetic results are labelled as such; results on the
team's real, masked test set (ml/data/real/test.jsonl) are reported separately
and are the only ones to present as findings.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold

from finsight_api.engine.calendar import month_end
from finsight_api.engine.forecast import MODELS, compute_forecast
from finsight_api.engine.spend import total_spend
from finsight_api.ml.anomaly import SKIP_CATEGORIES, detect_anomalies
from finsight_api.ml.classifier import JsonClassifier
from finsight_api.ml.recurring import detect_recurring
from finsight_api.schemas import ClassifyItem

from . import synth
from .baseline import predict as baseline_predict
from .datasets import api_window, classifier_rows
from .model import ece_from_confidence, fit
from .paths import MODELS as MODEL_DIR
from .paths import REPORTS
from .real_data import load_real

NONE = "(abstain)"


def _load_model_json(version: str) -> dict:
    return json.loads((MODEL_DIR / version / "model.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- classifier


def _classifier_scores(y, pred, base, conf, named, thr_named, thr_anon) -> dict:
    y, pred, base = np.array(y), np.array(pred), np.array(base)
    named = np.array(named)
    answered = np.where(named, conf >= thr_named, conf >= thr_anon)
    correct = pred == y
    labels = sorted(set(y))
    out = {
        "rows": len(y),
        "model_macro_f1": round(float(f1_score(y, pred, average="macro", labels=labels)), 4),
        "model_accuracy": round(float(correct.mean()), 4),
        "baseline_macro_f1": round(float(f1_score(y, base, average="macro", labels=labels)), 4),
        "baseline_accuracy": round(float((base == y).mean()), 4),
        "baseline_coverage": round(float((base != NONE).mean()), 4),
        "coverage_at_threshold": round(float(answered.mean()), 4),
        "answered_accuracy": round(float(correct[answered].mean()), 4) if answered.any() else None,
        "per_class_f1": {
            c: round(float(f), 4)
            for c, f in zip(labels, f1_score(y, pred, average=None, labels=labels))
        },
        "confusion": {"labels": labels,
                      "matrix": confusion_matrix(y, pred, labels=labels).tolist()},
    }
    # Fair head-to-head: model accuracy on its most confident rows, at the baseline's coverage.
    k = int(round((base != NONE).mean() * len(y)))
    if k:
        top = np.argsort(-conf)[:k]
        out["model_accuracy_at_baseline_coverage"] = round(float(correct[top].mean()), 4)
        out["baseline_answered_accuracy"] = round(float((base == y)[base != NONE].mean()), 4)
    for seg_name, mask in (("local_shops", named), ("anonymous_handles", ~named)):
        if mask.any():
            out[seg_name] = {
                "rows": int(mask.sum()),
                "model_accuracy": round(float(correct[mask].mean()), 4),
                "baseline_accuracy": round(float((base[mask] == y[mask]).mean()), 4),
                "coverage_at_threshold": round(float(answered[mask].mean()), 4),
                "answered_accuracy": round(float(correct[mask & answered].mean()), 4)
                if (mask & answered).any() else None,
            }
    return out


def eval_classifier_synthetic(rows: list[dict], model_json: dict, folds: int = 5) -> dict:
    C = model_json["metrics"].get("C", 1.0)
    temperature = model_json["temperature"]
    y, pred, base, conf, named, correct_all = [], [], [], [], [], []
    groups = [r["group"] for r in rows]
    for train_idx, test_idx in GroupKFold(n_splits=folds).split(rows, groups=groups):
        train = [rows[i] for i in train_idx]
        test = [rows[i] for i in test_idx if not rows[i]["known"]]
        m = fit(train, C=C)
        m.temperature = temperature
        p = m.proba(test)
        guesses = [m.classes[i] for i in p.argmax(axis=1)]
        for r, g, pr in zip(test, guesses, p):
            y.append(r["category"])
            pred.append(g)
            b = baseline_predict(r["merchant_norm"], r["descriptor"], r["direction"])
            base.append(b or NONE)
            conf.append(float(pr.max()))
            named.append(bool(r["merchant_norm"]))
            correct_all.append(g == r["category"])
    out = _classifier_scores(y, pred, base, np.array(conf), named, model_json["threshold"],
                             model_json.get("threshold_anonymous", model_json["threshold"]))
    out["ece"] = round(ece_from_confidence(np.array(conf), np.array(correct_all)), 4)
    out["folds"] = folds
    return out


def eval_classifier_real(model_json: dict) -> dict | None:
    rows = load_real("test.jsonl")
    if not rows:
        return None
    clf = JsonClassifier(model_json)
    items = [ClassifyItem(id=str(i), merchant_norm=r["merchant_norm"], descriptor=r["descriptor"],
                          mode=r["mode"], direction=r["direction"], amount_paise=r["amount_paise"])
             for i, r in enumerate(rows)]
    y, pred, base, conf, named = [], [], [], [], []
    for r, item in zip(rows, items):
        p = clf.probabilities(*_docs(item))
        y.append(r["category"])
        pred.append(clf.classes[int(np.argmax(p))])
        base.append(baseline_predict(r["merchant_norm"], r["descriptor"], r["direction"]) or NONE)
        conf.append(float(p.max()))
        named.append(bool(r["merchant_norm"]))
    return _classifier_scores(y, pred, base, np.array(conf), named, clf.threshold,
                              clf.threshold_anonymous)


def _docs(item: ClassifyItem) -> tuple[str, str]:
    from finsight_api.ml.text import char_text, word_text

    return (word_text(item.merchant_norm, item.descriptor, item.mode, item.direction,
                      item.amount_paise), char_text(item.merchant_norm))


# ---------------------------------------------------------------- recurring


def _match(predicted: list[set[str]], truth: list[set[str]]) -> tuple[int, int]:
    """Greedy one-to-one matching on Jaccard >= 0.5 over transaction ids."""
    used: set[int] = set()
    hits = 0
    for p in predicted:
        best, best_j = None, 0.5
        for k, t in enumerate(truth):
            if k in used:
                continue
            j = len(p & t) / len(p | t)
            if j >= best_j:
                best, best_j = k, j
        if best is not None:
            used.add(best)
            hits += 1
    return hits, len(used)


def _exact_monthly(txns) -> list[set[str]]:
    groups = defaultdict(list)
    for t in txns:
        if t.direction == "debit" and not t.is_self_transfer and t.merchant_norm:
            groups[(t.merchant_norm, t.amount_paise)].append(t)
    out = []
    for series in groups.values():
        series.sort(key=lambda t: t.ts)
        gaps = [(b.ts.date() - a.ts.date()).days for a, b in zip(series, series[1:])]
        if len(series) >= 3 and all(28 <= g <= 31 for g in gaps):
            out.append({t.id for t in series})
    return out


def eval_recurring(users) -> dict:
    tp_m = n_pred_m = tp_b = n_pred_b = n_truth = 0
    for u in users:
        window = api_window(u)
        truth_groups = defaultdict(set)
        for t in u.txns:
            if t.recurring_group and t.direction == "debit" and not t.is_self_transfer:
                truth_groups[t.recurring_group].add(t.txn_id)
        truth = [g for g in truth_groups.values() if len(g) >= 3]
        n_truth += len(truth)
        pred = [set(i.txn_ids) for i in detect_recurring(window, synth.END)]
        hits, _ = _match(pred, truth)
        tp_m += hits
        n_pred_m += len(pred)
        base = _exact_monthly(window)
        hits_b, _ = _match(base, truth)
        tp_b += hits_b
        n_pred_b += len(base)

    def pr(tp, n_pred):
        precision = tp / n_pred if n_pred else 0.0
        recall = tp / n_truth if n_truth else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
                "predicted": n_pred}

    return {"truth_series": n_truth, "interval_amount": pr(tp_m, n_pred_m),
            "exact_monthly_baseline": pr(tp_b, n_pred_b)}


# ---------------------------------------------------------------- anomalies


EVAL_MONTH_ENDS = [date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 31)]


def _candidates(window, as_of, exclude, lookback=120):
    start = as_of - timedelta(days=lookback - 1)
    return [t for t in window if start <= t.ts.date() <= as_of and t.direction == "debit"
            and not t.is_self_transfer and t.category and t.category not in SKIP_CATEGORIES
            and t.merchant_norm not in exclude]


def eval_anomalies(users, seed: int = 0) -> dict:
    counts = {m: Counter() for m in ("log_mad_tail", "fixed_3x_mean", "isolation_forest")}
    cat_codes = {c: i for i, c in enumerate(sorted({t.category for u in users for t in u.txns}))}
    for u in users:
        window = api_window(u)
        truth_ids = {t.txn_id for t in u.txns if t.is_anomaly}
        for as_of in EVAL_MONTH_ENDS:
            recent_start = as_of - timedelta(days=29)
            exclude = frozenset(r.merchant_norm for r in detect_recurring(window, as_of))
            in_window = {t.id for t in window
                         if recent_start <= t.ts.date() <= as_of} & truth_ids
            flagged = {
                "log_mad_tail": {a.id for a in detect_anomalies(window, as_of,
                                                              exclude_merchants=exclude)},
            }
            cands = _candidates(window, as_of, exclude)
            by_cat = defaultdict(list)
            for t in cands:
                by_cat[t.category].append(t.amount_paise)
            flagged["fixed_3x_mean"] = {
                t.id for t in cands
                if t.ts.date() >= recent_start and t.amount_paise >= 30_000
                and t.amount_paise > 3 * statistics.fmean(by_cat[t.category])
            }
            if len(cands) >= 30:
                X = np.array([[math.log1p(t.amount_paise / 100), cat_codes.get(t.category, 0),
                               t.ts.hour / 24, t.ts.weekday() / 7] for t in cands])
                forest = IsolationForest(contamination=0.02, random_state=seed).fit(X)
                labels = forest.predict(X)
                flagged["isolation_forest"] = {
                    t.id for t, lab in zip(cands, labels)
                    if lab == -1 and t.ts.date() >= recent_start and t.amount_paise >= 30_000
                }
            else:
                flagged["isolation_forest"] = set()
            for method, ids in flagged.items():
                counts[method]["tp"] += len(ids & in_window)
                counts[method]["fp"] += len(ids - in_window)
                counts[method]["fn"] += len(in_window - ids)

    def score(c):
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4),
                "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0, **dict(c)}

    return {m: score(c) for m, c in counts.items()}


# ---------------------------------------------------------------- forecast


def eval_forecast(users) -> dict:
    errors = {m: [] for m in (*MODELS, "auto")}
    pct = {m: [] for m in (*MODELS, "auto")}
    chosen = Counter()
    by_cutoff = {d: {m: [] for m in (*MODELS, "auto")} for d in (8, 15, 22)}
    for u in users:
        full = api_window(u)
        for m_end in EVAL_MONTH_ENDS:
            m_start = m_end.replace(day=1)
            actual = total_spend(full, m_start, month_end(m_start))
            for day in (8, 15, 22):
                cutoff = m_start.replace(day=day)
                before = [t for t in full if t.ts.date() < cutoff]
                rec = detect_recurring(before, cutoff)
                for model in (*MODELS, "auto"):
                    f = compute_forecast(before, cutoff, rec, model=model)
                    if model == "auto":
                        chosen[f.chosen_model] += 1
                    err = abs(f.projected_month_end_paise - actual)
                    errors[model].append(err)
                    by_cutoff[day][model].append(err)
                    denom = (abs(f.projected_month_end_paise) + abs(actual)) / 2
                    pct[model].append(err / denom if denom else 0.0)
    return {
        "points": len(errors["auto"]),
        "mae_rupees": {m: round(statistics.fmean(v) / 100) for m, v in errors.items()},
        "smape_percent": {m: round(100 * statistics.fmean(v), 1) for m, v in pct.items()},
        "mae_rupees_by_cutoff_day": {d: {m: round(statistics.fmean(v) / 100)
                                         for m, v in row.items()} for d, row in by_cutoff.items()},
        "auto_chose": dict(chosen),
    }


# ---------------------------------------------------------------- report


def _table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render(results: dict) -> str:
    c = results["classifier_synthetic"]
    lines = [
        "# FinSight evaluation report",
        "",
        f"Dataset {results['dataset_version']}, {results['users']} synthetic users, model "
        f"{results['model_version']}. Generated by `python -m finsight_ml.evaluate`.",
        "",
        "> **Synthetic data.** The generator and the parser were written by the same team, so "
        "these numbers are optimistic. They show the pipeline works and catch regressions. "
        "Present only the real-data section as findings.",
        "",
        "## Category classifier (rows the model actually sees)",
        "",
        f"{c['folds']}-fold merchant-grouped cross-validation. Known brands are resolved on "
        "the phone and are excluded from these rows.",
        "",
        _table(["", "Model", "Baseline (lookup + keywords)"], [
            ["Macro-F1", c["model_macro_f1"], c["baseline_macro_f1"]],
            ["Accuracy", _pct(c["model_accuracy"]), _pct(c["baseline_accuracy"])],
            ["Local shops accuracy", _pct(c["local_shops"]["model_accuracy"]),
             _pct(c["local_shops"]["baseline_accuracy"])],
            ["Anonymous handles accuracy", _pct(c["anonymous_handles"]["model_accuracy"]),
             _pct(c["anonymous_handles"]["baseline_accuracy"])],
            ["Coverage", _pct(c["coverage_at_threshold"]) + " answered at threshold",
             _pct(c["baseline_coverage"]) + " matched a rule"],
            ["Accuracy when answering", _pct(c["answered_accuracy"]),
             _pct(c.get("baseline_answered_accuracy"))],
            ["Accuracy at the baseline's coverage",
             _pct(c.get("model_accuracy_at_baseline_coverage")),
             _pct(c.get("baseline_answered_accuracy"))],
        ]),
        "",
        "Macro-F1 counts every abstention as wrong, so it favours whichever answers more "
        "carefully; compare the coverage rows. Calibration error (ECE) " + str(c["ece"]) + ".",
        "",
        _table(["Class", "F1"], [[k, v] for k, v in c["per_class_f1"].items()]),
        "",
    ]
    real = results.get("classifier_real")
    lines += ["## Real, masked test set", ""]
    if real is None:
        lines += ["Not run yet: put the labelled test set at `ml/data/real/test.jsonl` "
                  "(see ml/data/README.md). **This is the section examiners should see.**", ""]
    else:
        lines += [
            _table(["", "Model", "Baseline"], [
                ["Rows", real["rows"], real["rows"]],
                ["Macro-F1", real["model_macro_f1"], real["baseline_macro_f1"]],
                ["Accuracy", _pct(real["model_accuracy"]), _pct(real["baseline_accuracy"])],
                ["Coverage", _pct(real["coverage_at_threshold"]), _pct(real["baseline_coverage"])],
                ["Accuracy when answering", _pct(real["answered_accuracy"]), "n/a"],
            ]), "",
        ]
    r = results["recurring"]
    lines += [
        "## Recurring payments",
        "",
        f"{r['truth_series']} true recurring series (3 or more payments).",
        "",
        _table(["Method", "Precision", "Recall", "F1"], [
            ["Interval and amount (served)", _pct(r["interval_amount"]["precision"]),
             _pct(r["interval_amount"]["recall"]), r["interval_amount"]["f1"]],
            ["Exact monthly match (baseline)", _pct(r["exact_monthly_baseline"]["precision"]),
             _pct(r["exact_monthly_baseline"]["recall"]), r["exact_monthly_baseline"]["f1"]],
        ]),
        "",
    ]
    a = results["anomalies"]
    lines += [
        "## Unusual spending (injected anomalies, 6-15x typical)",
        "",
        "Injected anomalies are easy to spot, so recall here is an upper bound. The served "
        "thresholds were tuned on this data; re-tune them on real histories.",
        "",
        _table(["Method", "Precision", "Recall", "F1"], [
            [name, _pct(v["precision"]), _pct(v["recall"]), v["f1"]]
            for name, v in (("Log-MAD + tail check (served)", a["log_mad_tail"]),
                            ("3x category mean (baseline)", a["fixed_3x_mean"]),
                            ("Isolation Forest (comparison)", a["isolation_forest"]))
        ]),
        "",
    ]
    f = results["forecast"]
    lines += [
        "## Month-end forecast",
        "",
        f"Rolling origin: cut-offs on days 8, 15 and 22 of May-August, {f['points']} "
        "forecasts per model. Error is on the projected month-end total.",
        "",
        _table(["Model", "MAE", "sMAPE"], [
            [m, f"₹{f['mae_rupees'][m]:,}", f"{f['smape_percent'][m]}%"]
            for m in f["mae_rupees"]
        ]),
        "",
        _table(["Cut-off day", *f["mae_rupees"].keys()], [
            [d, *(f"₹{v:,}" for v in row.values())]
            for d, row in f["mae_rupees_by_cutoff_day"].items()
        ]),
        "",
        f"Per-user automatic selection (\"auto\") picked: {f['auto_chose']}. The service "
        "uses EWMA by default because it had the lowest error here.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--users", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    model_json = _load_model_json(args.version)
    users = synth.generate(args.users, args.seed)
    rows = classifier_rows(users)
    print("classifier (synthetic, grouped CV)...")
    results = {
        "dataset_version": synth.DATASET_VERSION,
        "model_version": model_json["version"],
        "users": args.users,
        "classifier_synthetic": eval_classifier_synthetic(rows, model_json),
    }
    print("classifier (real test set)...")
    results["classifier_real"] = eval_classifier_real(model_json)
    print("recurring...")
    results["recurring"] = eval_recurring(users)
    print("anomalies...")
    results["anomalies"] = eval_anomalies(users)
    print("forecast...")
    results["forecast"] = eval_forecast(users)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "latest.json").write_text(json.dumps(results, indent=2, default=str),
                                         encoding="utf-8")
    report = render(results)
    (REPORTS / "latest.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
