from datetime import date

from conftest import FakeProvider, daily, monthly, txn

from finsight_api.llm.assistant import Assistant
from finsight_api.llm.base import ProviderError, Reply, ToolCall
from finsight_api.llm.intents import match, parse_amount_rupees
from finsight_api.llm.verifier import collect, verify
from finsight_api.schemas import ChatRequest

AS_OF = date(2026, 9, 20)


def history():
    t = daily(date(2026, 7, 1), date(2026, 9, 19), 300, "swiggy", "food")
    t += daily(date(2026, 7, 1), date(2026, 9, 19), 100, "uber", "transport")
    t += monthly(date(2026, 6, 25), 3, 649, "netflix")
    t.append(txn(date(2026, 9, 15), 9000, "croma", "shopping"))
    return t


def ask(q, provider=None, balance=2_000_000, which="auto"):
    providers = {provider.name: provider} if provider else {}
    a = Assistant(providers, provider.name if provider else "none")
    return a.answer(ChatRequest(question=q, transactions=history(), as_of=AS_OF,
                                balance_paise=balance, provider=which))


def test_verifier():
    allowed = collect({"total_rupees": 12345, "share_percent": 39.6, "date": "2026-09-12"})
    assert verify("You spent ₹12,345 (40%) by 12 Sep", allowed).ok
    assert verify("About ₹12,000 so far", allowed).ok
    assert not verify("You spent ₹15,000", allowed).ok
    assert verify("Top 3 categories", allowed).ok  # tiny counts are free


def test_intent_matching_and_amounts():
    assert match("Why did I overspend?")[0] == "overspend"
    assert match("Where did I spend most?")[0] == "top_spend"
    assert match("Can I afford a ₹2,000 jacket?")[0] == "can_afford"
    assert parse_amount_rupees("can i afford 2.5k shoes") == 2500
    assert parse_amount_rupees("₹1,20,000 laptop") == 120000


def test_category_questions():
    assert match("How much did I spend on food this month?")[0] == "category_spend"
    assert match("how much on groceries last month")[0] == "category_spend"
    assert match("What's my transport spending?")[0] == "category_spend"
    assert match("What subscriptions do I have?")[0] == "recurring"
    r = ask("How much did I spend on food this month?")
    assert r.intent == "category_spend" and r.verified
    assert "Food" in r.answer and "this month" in r.answer
    # 19 days of ₹300 a day.
    assert "₹5,700" in r.answer
    r = ask("How much did I spend on health?")
    assert r.answer.startswith("You haven't spent anything on Health")


def test_templates_without_a_model():
    r = ask("Where did I spend most?")
    assert r.intent == "top_spend" and r.provider_used == "none" and "Food" in r.answer
    r = ask("Can I afford a ₹500 dinner?")
    assert r.answer.startswith("Yes")
    r = ask("How much can I spend today?", balance=None)
    assert "balance" in r.answer


def test_rephrase_kept_only_if_numbers_survive():
    good = FakeProvider([Reply("Most of your money this month went on Food.", [])])
    r = ask("Where did I spend most?", good)
    assert r.provider_used == "ollama" and not r.fallback_used
    bad = FakeProvider([Reply("You spent ₹99,999 on Food.", [])])
    r = ask("Where did I spend most?", bad)
    assert r.fallback_used and "99,999" not in r.answer


def test_tool_loop_and_verification():
    p = FakeProvider([
        Reply("", [ToolCall("merchant_spend", {"merchant": "swiggy", "period": "this_month"})]),
        Reply("You spent ₹5,700 at Swiggy this month.", []),
    ])
    r = ask("How much at Swiggy?", p)
    assert r.verified and not r.fallback_used and "5,700" in r.answer
    invented = FakeProvider([Reply("You spent ₹1,234 at Swiggy.", [])])
    r = ask("How much at Swiggy?", invented)
    assert r.fallback_used


def test_cloud_provider_gets_only_aggregate_tools_and_no_details():
    cloud = FakeProvider([Reply("Fine.", [])], name="gemini", is_cloud=True)
    ask("How much at Swiggy?", cloud)
    offered = {t.name for t in cloud.calls[0][1]}
    assert "merchant_spend" not in offered and "list_recurring" not in offered
    cloud2 = FakeProvider([Reply("x", [])], name="gemini", is_cloud=True)
    r = ask("What subscriptions do I have?", cloud2)
    assert cloud2.calls == [] and r.provider_used == "none"  # merchant names never sent


def test_model_down_falls_back():
    r = ask("How much at Swiggy?", FakeProvider([ProviderError("down")]))
    assert r.fallback_used and "so far this month" in r.answer
