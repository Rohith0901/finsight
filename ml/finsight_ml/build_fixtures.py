"""Write test fixtures and app assets: python -m finsight_ml.build_fixtures

- shared/fixtures/sms_synthetic.jsonl: stratified SMS sample for the Dart parser tests
- app/assets/demo/demo_sms.jsonl: one user's last 3 months for the app's demo mode
- app/assets/shared/*.json: copies of the shared contracts (a Dart test checks they match)
"""

from __future__ import annotations

import shutil

from . import synth
from .datasets import write_demo_sms, write_parser_fixtures
from .paths import APP_ASSETS, FIXTURES, SHARED

SHARED_FILES = ("categories.json", "merchants.json", "sms_hints.json")


def main() -> None:
    users = synth.generate(60, 7)
    noise = synth.noise_messages(users)
    n = write_parser_fixtures(users, noise, FIXTURES / "sms_synthetic.jsonl")
    print(f"wrote {n} parser fixtures")
    demo = next(u for u in users if u.persona == "professional" and u.card() is not None)
    m = write_demo_sms(demo, noise, APP_ASSETS / "demo" / "demo_sms.jsonl")
    print(f"wrote {m} demo messages for {demo.uid}")
    (APP_ASSETS / "shared").mkdir(parents=True, exist_ok=True)
    for name in SHARED_FILES:
        shutil.copyfile(SHARED / name, APP_ASSETS / "shared" / name)
    shutil.copyfile(FIXTURES / "merchant_name_cases.json",
                    APP_ASSETS / "shared" / "merchant_name_cases.json")
    print("copied shared contracts into app/assets/shared")


if __name__ == "__main__":
    main()
