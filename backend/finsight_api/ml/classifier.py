"""Category classifier inference from a portable JSON export.

The model is TF-IDF (word 1-2 grams + character 3-5 grams of the merchant)
feeding a multinomial logistic regression, with temperature scaling for
calibrated confidence. Inference re-implements scikit-learn's transform step by
step; ml/tests/test_export_parity.py checks the probabilities match.
"""

from __future__ import annotations

import base64
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..categories import UNKNOWN
from ..schemas import Candidate, ClassifyItem, ClassifyResult
from .text import char_text, word_text

FORMAT = "finsight-linear-v1"
_TOKEN = re.compile(r"(?u)\b\w\w+\b")  # scikit-learn's default token_pattern
_WHITE_SPACES = re.compile(r"\s\s+")


def _decode(blob: str, dtype: str, shape: tuple[int, ...] | None = None) -> np.ndarray:
    arr = np.frombuffer(base64.b64decode(blob), dtype=np.dtype(dtype).newbyteorder("<"))
    return arr.reshape(shape) if shape else arr


def word_terms(doc: str, ngram_range: tuple[int, int]) -> Counter:
    tokens = _TOKEN.findall(doc.lower())
    lo, hi = ngram_range
    terms: list[str] = []
    for n in range(lo, hi + 1):
        for i in range(len(tokens) - n + 1):
            terms.append(" ".join(tokens[i : i + n]))
    return Counter(terms)


def char_wb_terms(doc: str, ngram_range: tuple[int, int]) -> Counter:
    doc = _WHITE_SPACES.sub(" ", doc.lower())
    lo, hi = ngram_range
    terms: list[str] = []
    for w in doc.split():
        w = f" {w} "
        length = len(w)
        for n in range(lo, hi + 1):
            offset = 0
            terms.append(w[offset : offset + n])
            while offset + n < length:
                offset += 1
                terms.append(w[offset : offset + n])
            if offset == 0:  # a word shorter than n is counted once
                break
    return Counter(terms)


@dataclass
class _Vectorizer:
    vocabulary: dict[str, int]
    idf: np.ndarray
    ngram_range: tuple[int, int]
    analyzer: str
    sublinear_tf: bool
    offset: int

    def transform(self, doc: str) -> tuple[list[int], list[float]]:
        counts = (
            char_wb_terms(doc, self.ngram_range)
            if self.analyzer == "char_wb"
            else word_terms(doc, self.ngram_range)
        )
        idx: list[int] = []
        val: list[float] = []
        for term, count in counts.items():
            j = self.vocabulary.get(term)
            if j is None:
                continue
            tf = 1.0 + math.log(count) if self.sublinear_tf else float(count)
            idx.append(j)
            val.append(tf * float(self.idf[j]))
        norm = math.sqrt(sum(v * v for v in val))
        if norm > 0:
            val = [v / norm for v in val]
        return [self.offset + j for j in idx], val


class JsonClassifier:
    def __init__(self, model: dict):
        if model.get("format") != FORMAT:
            raise ValueError(f"unsupported model format {model.get('format')!r}")
        self.version: str = model["version"]
        self.dataset_version: str = model.get("dataset_version", "")
        self.trained_at: str = model.get("trained_at", "")
        self.classes: list[str] = list(model["classes"])
        self.temperature: float = float(model["temperature"])
        self.threshold: float = float(model["threshold"])
        # Anonymous handles (no merchant name) carry little signal and get their own bar.
        self.threshold_anonymous: float = float(model.get("threshold_anonymous", self.threshold))
        self.metrics: dict = model.get("metrics", {})
        w, c = model["word"], model["char"]
        n_word = len(w["vocabulary"])
        self.word = _Vectorizer(
            vocabulary=w["vocabulary"],
            idf=_decode(w["idf"], "float64"),
            ngram_range=tuple(w["ngram_range"]),
            analyzer="word",
            sublinear_tf=bool(w["sublinear_tf"]),
            offset=0,
        )
        self.char = _Vectorizer(
            vocabulary=c["vocabulary"],
            idf=_decode(c["idf"], "float64"),
            ngram_range=tuple(c["ngram_range"]),
            analyzer="char_wb",
            sublinear_tf=bool(c["sublinear_tf"]),
            offset=n_word,
        )
        shape = tuple(model["coef"]["shape"])
        self.coef = _decode(model["coef"]["data"], model["coef"]["dtype"], shape).astype(np.float64)
        self.intercept = np.asarray(model["intercept"], dtype=np.float64)
        if self.coef.shape != (len(self.classes), n_word + len(c["vocabulary"])):
            raise ValueError("coefficient shape does not match the vocabularies")

    @classmethod
    def load(cls, path: Path) -> JsonClassifier:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def decision(self, word_doc: str, char_doc: str) -> np.ndarray:
        wi, wv = self.word.transform(word_doc)
        ci, cv = self.char.transform(char_doc)
        idx = wi + ci
        if not idx:
            return self.intercept.copy()
        return self.coef[:, idx] @ np.asarray(wv + cv) + self.intercept

    def probabilities(self, word_doc: str, char_doc: str) -> np.ndarray:
        z = self.decision(word_doc, char_doc) / self.temperature
        z = z - z.max()
        e = np.exp(z)
        return e / e.sum()

    def predict(self, items: list[ClassifyItem]) -> list[ClassifyResult]:
        results = []
        for item in items:
            p = self.probabilities(
                word_text(
                    item.merchant_norm, item.descriptor, item.mode, item.direction,
                    item.amount_paise,
                ),
                char_text(item.merchant_norm),
            )
            order = np.argsort(-p)
            best = int(order[0])
            confidence = float(p[best])
            bar = self.threshold if item.merchant_norm.strip() else self.threshold_anonymous
            abstained = confidence < bar
            results.append(
                ClassifyResult(
                    id=item.id,
                    category=UNKNOWN if abstained else self.classes[best],
                    confidence=round(confidence, 4),
                    abstained=abstained,
                    candidates=[
                        Candidate(category=self.classes[int(k)], probability=round(float(p[k]), 4))
                        for k in order[:3]
                    ],
                )
            )
        return results
