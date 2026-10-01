from __future__ import annotations

from datetime import date, datetime, time, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient

from finsight_api.config import Settings
from finsight_api.engine.calendar import IST
from finsight_api.main import create_app
from finsight_api.schemas import Txn

TOKEN = "test-token-0123456789"
_ids = count(1)


def txn(day: date, rupees: float, merchant: str = "", category: str | None = "food",
        direction: str = "debit", hour: int = 12, **kw) -> Txn:
    return Txn(
        id=str(next(_ids)),
        ts=datetime.combine(day, time(hour), IST),
        amount_paise=int(round(rupees * 100)),
        direction=direction,
        merchant_norm=merchant,
        category=category,
        **kw,
    )


def daily(start: date, end: date, rupees: float, merchant: str = "swiggy",
          category: str = "food") -> list[Txn]:
    out, d = [], start
    while d <= end:
        out.append(txn(d, rupees, merchant, category))
        d += timedelta(days=1)
    return out


def monthly(first: date, months: int, rupees: float, merchant: str,
            category: str = "subscriptions") -> list[Txn]:
    from finsight_api.engine.calendar import add_months

    return [txn(add_months(first, k), rupees, merchant, category, hour=6) for k in range(months)]


class FakeProvider:
    """Scripted model: returns queued replies and records what it was sent."""

    def __init__(self, replies, name="ollama", is_cloud=False):
        self.replies = list(replies)
        self.name = name
        self.is_cloud = is_cloud
        self.calls = []

    def generate(self, messages, tools):
        self.calls.append((messages, tools))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def settings():
    return Settings(api_token=TOKEN)


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings, providers={}))


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def as_json(txns: list[Txn]) -> list[dict]:
    return [t.model_dump(mode="json") for t in txns]
