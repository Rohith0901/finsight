"""Turn the app's debug export into a spreadsheet to label, and back.

    python -m finsight_ml.labelling to-csv  ml/data/exports/export.jsonl  labels.csv
    (fill the "category" column in Excel or Google Sheets, then)
    python -m finsight_ml.labelling from-csv labels.csv ml/data/real/test.jsonl

Valid categories are listed in shared/categories.json. Review every row before
sharing the file inside the team; it stays out of git (ml/data/real is ignored).
"""

from __future__ import annotations

import csv
import json
import sys

from .paths import SHARED
from .real_data import FIELDS


def to_csv(src: str, dst: str) -> None:
    with open(src, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[*FIELDS, "masked_sms"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in (*FIELDS, "masked_sms")})
    print(f"{len(rows)} rows -> {dst}")


def from_csv(src: str, dst: str) -> None:
    valid = {c["id"] for c in json.loads((SHARED / "categories.json").read_text())["categories"]}
    out, bad = [], []
    with open(src, newline="", encoding="utf-8") as f:
        for n, r in enumerate(csv.DictReader(f), 2):
            if r["category"] not in valid:
                bad.append(f"line {n}: '{r['category']}'")
                continue
            out.append({"merchant_norm": r["merchant_norm"], "descriptor": r["descriptor"],
                        "mode": r["mode"] or "other", "direction": r["direction"],
                        "amount_paise": int(r["amount_paise"]), "category": r["category"]})
    if bad:
        sys.exit("unknown categories: " + "; ".join(bad[:10]))
    with open(dst, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(out)} labelled rows -> {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("to-csv", "from-csv"):
        sys.exit(__doc__)
    (to_csv if sys.argv[1] == "to-csv" else from_csv)(sys.argv[2], sys.argv[3])
