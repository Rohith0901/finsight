"""Classifier training, temperature calibration and export to the portable JSON format."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from finsight_api.ml.classifier import FORMAT
from finsight_api.ml.text import char_text, word_text

WORD = {"analyzer": "word", "ngram_range": (1, 2), "min_df": 2, "sublinear_tf": True,
        "max_features": 20_000}
CHAR = {"analyzer": "char_wb", "ngram_range": (3, 5), "min_df": 2, "sublinear_tf": True,
        "max_features": 30_000}


def docs(rows: list[dict]) -> tuple[list[str], list[str]]:
    words = [word_text(r["merchant_norm"], r["descriptor"], r["mode"], r["direction"],
                       r["amount_paise"]) for r in rows]
    chars = [char_text(r["merchant_norm"]) for r in rows]
    return words, chars


@dataclass
class Fitted:
    word: TfidfVectorizer
    char: TfidfVectorizer
    lr: LogisticRegression
    temperature: float = 1.0

    @property
    def classes(self) -> list[str]:
        return [str(c) for c in self.lr.classes_]

    def matrix(self, rows: list[dict]):
        w, c = docs(rows)
        return hstack([self.word.transform(w), self.char.transform(c)]).tocsr()

    def decision(self, rows: list[dict]) -> np.ndarray:
        return self.lr.decision_function(self.matrix(rows))

    def proba(self, rows: list[dict], temperature: float | None = None) -> np.ndarray:
        z = self.decision(rows) / (self.temperature if temperature is None else temperature)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def fit(rows: list[dict], C: float = 4.0, seed: int = 0) -> Fitted:
    w, c = docs(rows)
    word = TfidfVectorizer(**WORD)
    char = TfidfVectorizer(**CHAR)
    X = hstack([word.fit_transform(w), char.fit_transform(c)]).tocsr()
    y = [r["category"] for r in rows]
    lr = LogisticRegression(C=C, max_iter=5000, class_weight="balanced", random_state=seed)
    lr.fit(X, y)
    return Fitted(word, char, lr)


def fit_temperature(model: Fitted, rows: list[dict]) -> float:
    """Temperature that minimises negative log-likelihood on held-out rows."""
    z = model.decision(rows)
    index = {c: i for i, c in enumerate(model.classes)}
    y = np.array([index.get(r["category"], -1) for r in rows])
    keep = y >= 0
    z, y = z[keep], y[keep]

    def nll(t: float) -> float:
        s = z / t
        s = s - s.max(axis=1, keepdims=True)
        log_p = s - np.log(np.exp(s).sum(axis=1, keepdims=True))
        return float(-log_p[np.arange(len(y)), y].mean())

    return float(minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded").x)


def expected_calibration_error(probs: np.ndarray, correct: np.ndarray, bins: int = 15) -> float:
    return ece_from_confidence(probs.max(axis=1), correct, bins)


def ece_from_confidence(conf: np.ndarray, correct: np.ndarray, bins: int = 15) -> float:
    conf = np.asarray(conf, dtype=float)
    correct = np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


NEVER = 1.01  # a threshold no probability reaches: always abstain


def choose_threshold(probs: np.ndarray, correct: np.ndarray, target: float = 0.9) -> float:
    """Lowest confidence cut-off whose answered predictions are at least `target` correct.

    If no cut-off gets there, the model should not answer for these rows at all.
    """
    conf = probs.max(axis=1)
    for t in np.round(np.arange(0.30, 0.96, 0.05), 2):
        answered = conf >= t
        if answered.sum() >= 20 and correct[answered].mean() >= target:
            return float(t)
    return NEVER


def _b64(arr: np.ndarray, dtype: str) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype=np.dtype(dtype).newbyteorder("<"))
                            .tobytes()).decode("ascii")


def export(model: Fitted, threshold: float, threshold_anonymous: float, version: str,
           dataset_version: str, metrics: dict) -> dict:
    wv = {t: int(i) for t, i in model.word.vocabulary_.items()}
    cv = {t: int(i) for t, i in model.char.vocabulary_.items()}
    return {
        "format": FORMAT,
        "version": version,
        "dataset_version": dataset_version,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "classes": model.classes,
        "temperature": model.temperature,
        "threshold": threshold,
        "threshold_anonymous": threshold_anonymous,
        "word": {"analyzer": "word", "ngram_range": list(WORD["ngram_range"]),
                 "sublinear_tf": True, "vocabulary": wv, "idf": _b64(model.word.idf_, "float64")},
        "char": {"analyzer": "char_wb", "ngram_range": list(CHAR["ngram_range"]),
                 "sublinear_tf": True, "vocabulary": cv, "idf": _b64(model.char.idf_, "float64")},
        "coef": {"shape": list(model.lr.coef_.shape), "dtype": "float32",
                 "data": _b64(model.lr.coef_, "float32")},
        "intercept": [float(b) for b in model.lr.intercept_],
        "metrics": metrics,
    }
