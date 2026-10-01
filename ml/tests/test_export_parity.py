"""The server's numpy inference must reproduce scikit-learn's probabilities."""

import numpy as np
import pytest

from finsight_api.ml.classifier import JsonClassifier
from finsight_api.schemas import ClassifyItem
from finsight_ml import synth
from finsight_ml.datasets import classifier_rows
from finsight_ml.model import export, fit


@pytest.fixture(scope="module")
def trained():
    rows = classifier_rows(synth.generate(n_users=8, seed=3))
    train, test = rows[: int(len(rows) * 0.8)], rows[int(len(rows) * 0.8):]
    model = fit(train, C=2.0)
    model.temperature = 0.8
    return model, test


def test_json_inference_matches_sklearn(trained):
    model, test = trained
    clf = JsonClassifier(export(model, 0.5, 0.8, "test", "test", {}))
    expected = model.proba(test)
    for row, want in zip(test[:1500], expected[:1500]):
        from finsight_api.ml.text import char_text, word_text

        got = clf.probabilities(
            word_text(row["merchant_norm"], row["descriptor"], row["mode"], row["direction"],
                      row["amount_paise"]),
            char_text(row["merchant_norm"]),
        )
        assert np.max(np.abs(got - want)) < 1e-5
        assert int(np.argmax(got)) == int(np.argmax(want))


def test_abstains_below_threshold(trained):
    model, _ = trained
    clf = JsonClassifier(export(model, 0.99, 1.01, "test", "test", {}))
    [named, anonymous] = clf.predict([
        ClassifyItem(id="a", merchant_norm="some unknown shop", amount_paise=10_000),
        ClassifyItem(id="b", merchant_norm="", descriptor="qr", mode="upi", amount_paise=5_000),
    ])
    assert anonymous.abstained and anonymous.category == "unknown"
    assert len(named.candidates) == 3
    assert named.candidates[0].probability >= named.candidates[1].probability


def test_rejects_unknown_format():
    with pytest.raises(ValueError):
        JsonClassifier({"format": "something-else"})
