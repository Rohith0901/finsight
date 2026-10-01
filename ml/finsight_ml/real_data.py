"""The team's own labelled messages (ml/data/real/, gitignored).

Each line of test.jsonl or train.jsonl is one parsed, masked transaction:

    {"merchant_norm": "sri balaji sweets", "descriptor": "", "mode": "upi",
     "direction": "debit", "amount_paise": 12000, "category": "food"}

Make it with the app's debug export and `python -m finsight_ml.labelling`.
test.jsonl is only ever used for final evaluation, never for training or tuning.
"""

from __future__ import annotations

import json

from .paths import REAL

FIELDS = ("merchant_norm", "descriptor", "mode", "direction", "amount_paise", "category")


def load_real(name: str = "test.jsonl") -> list[dict]:
    path = REAL / name
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [f for f in FIELDS if f not in row]
        if missing:
            raise ValueError(f"{path}:{n} is missing {missing}")
        row.setdefault("group", row["merchant_norm"] or f"row{n}")
        row.setdefault("known", False)
        rows.append(row)
    return rows
