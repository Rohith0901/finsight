import logging
from datetime import date

from conftest import as_json, daily, monthly

BODY_SECRET = "SECRET-MERCHANT-XYZ"


def window():
    t = daily(date(2026, 7, 1), date(2026, 9, 19), 300, "swiggy", "food")
    t += monthly(date(2026, 6, 25), 3, 649, "netflix")
    return as_json(t)


def test_health_is_open(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_token_required(client):
    r = client.post("/v1/recurring", json={"transactions": []})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "unauthorized", "message": "Missing or wrong API token."}}
    r = client.post("/v1/recurring", json={"transactions": []},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_unknown_fields_rejected_without_echo(client, auth):
    t = window()[:1]
    t[0]["body"] = BODY_SECRET
    r = client.post("/v1/forecast", json={"transactions": t, "as_of": "2026-09-20"}, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "transactions.0.body" in r.json()["error"]["message"]
    assert BODY_SECRET not in r.text


def test_bad_category_rejected(client, auth):
    t = window()[:1]
    t[0]["category"] = "crypto"
    assert client.post("/v1/recurring", json={"transactions": t}, headers=auth).status_code == 422


def test_body_limit(client, auth):
    r = client.post("/v1/recurring", content=b"x" * (6 * 1024 * 1024), headers={
        **auth, "content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_insights_bundle(client, auth):
    r = client.post("/v1/insights", json={"transactions": window(), "as_of": "2026-09-20",
                                          "balance_paise": 2_000_000}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert [i["merchant_norm"] for i in body["recurring"]["items"]] == ["netflix"]
    assert body["forecast"]["chosen_model"] == "ewma"
    assert body["safe_to_spend"]["days_left"] == 11


def test_whatif_and_safe_to_spend(client, auth):
    r = client.post("/v1/whatif", json={
        "transactions": window(), "as_of": "2026-09-20", "balance_paise": 1_000_000,
        "changes": [{"category": "food", "percent_change": -20},
                    {"kind": "cancel_recurring", "merchant_norm": "netflix"}]}, headers=auth)
    assert r.status_code == 200 and r.json()["saving_per_month_paise"] > 0
    r = client.post("/v1/safe-to-spend", json={"as_of": "2026-09-20", "balance_paise": 500_000},
                    headers=auth)
    assert r.json()["safe_daily_paise"] == 500_000 // 11


def test_classify_with_trained_model(client, auth):
    r = client.post("/v1/classify", json={"items": [
        {"id": "1", "merchant_norm": "sharma medical stores", "mode": "upi", "amount_paise": 25000},
        {"id": "2", "merchant_norm": "annapurna tiffin centre", "mode": "upi",
         "amount_paise": 6000},
    ]}, headers=auth)
    assert r.status_code == 200
    got = {i["id"]: i["category"] for i in r.json()["items"]}
    assert got == {"1": "health", "2": "food"}
    assert r.json()["model_version"] == "v1"


def test_chat(client, auth):
    r = client.post("/v1/chat", json={"question": "Where did I spend most?",
                                      "transactions": window(), "as_of": "2026-09-20"},
                    headers=auth)
    assert r.status_code == 200 and r.json()["intent"] == "top_spend"


def test_access_log_has_no_bodies(client, auth, caplog):
    caplog.set_level(logging.INFO)
    t = window()
    t[0]["merchant_norm"] = BODY_SECRET.lower()
    client.post("/v1/recurring", json={"transactions": t}, headers=auth)
    text = caplog.text
    assert "POST /v1/recurring 200" in text
    assert BODY_SECRET.lower() not in text and "Bearer" not in text


def test_model_info(client, auth):
    info = client.get("/v1/model-info", headers=auth).json()
    assert info["classifier"]["loaded"] and info["llm"]["enabled_providers"][0] == "none"
