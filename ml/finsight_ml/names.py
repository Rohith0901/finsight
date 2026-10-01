"""Merchant-name normalisation: the Python twin of app/lib/ingestion/normalizer.dart.

Both implementations read the rules from shared/merchants.json and are tested
against the same cases in shared/fixtures/merchant_name_cases.json, so the keys
the classifier is trained on match the keys the phone sends.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from .paths import SHARED

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"[0-9]+")


def normalize(text: str) -> str:
    return _NON_ALNUM.sub(" ", (text or "").lower()).strip()


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads((SHARED / "merchants.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _aliases() -> list[tuple[str, tuple[str, ...], int, dict]]:
    out = []
    for m in rules()["merchants"]:
        for alias in m["aliases"]:
            n = normalize(alias)
            out.append((n.replace(" ", ""), tuple(n.split()), len(n.replace(" ", "")), m))
    return out


def _has_token_run(tokens: list[str], run: tuple[str, ...]) -> bool:
    k = len(run)
    return any(tuple(tokens[i : i + k]) == run for i in range(len(tokens) - k + 1))


def match_known(text: str) -> dict | None:
    """Longest alias match; aliases shorter than the substring minimum match whole tokens."""
    n = normalize(text)
    if not n:
        return None
    tokens = n.split()
    compact = n.replace(" ", "")
    min_len = rules()["matching"]["substring_min_length"]
    best: tuple[int, dict] | None = None
    for alias_compact, alias_tokens, length, merchant in _aliases():
        hit = (alias_compact in compact) if length >= min_len else _has_token_run(tokens, alias_tokens)
        if hit and (best is None or length > best[0]):
            best = (length, merchant)
    return best[1] if best else None


def is_card_bill_name(text: str) -> bool:
    n = normalize(text)
    tokens = n.split()
    compact = n.replace(" ", "")
    min_len = rules()["matching"]["substring_min_length"]
    for alias in rules()["card_bill_aliases"]:
        a = normalize(alias)
        ac = a.replace(" ", "")
        if (ac in compact) if len(ac) >= min_len else _has_token_run(tokens, tuple(a.split())):
            return True
    return False


def strip_legal_suffixes(n: str) -> str:
    suffixes = sorted(rules()["names"]["legal_suffixes"], key=len, reverse=True)
    changed = True
    while changed:
        changed = False
        for suf in suffixes:
            if n.endswith(" " + suf):
                n = n[: -len(suf) - 1].strip()
                changed = True
                break
    return n


def _looks_like_person(tokens: list[str]) -> bool:
    cfg = rules()["names"]
    business = set(cfg["business_words"])
    return (
        cfg["person_min_tokens"] <= len(tokens) <= cfg["person_max_tokens"]
        and all(t.isalpha() for t in tokens)
        and any(len(t) >= 3 for t in tokens)
        and not any(t in business for t in tokens)
    )


def person_key(name: str, salt: str) -> str:
    """Stable pseudonym: the same payee always maps to the same key on one phone."""
    digest = hmac.new(salt.encode(), normalize(name).encode(), hashlib.sha256).hexdigest()
    return "person:" + digest[:10]


@dataclass(frozen=True)
class Name:
    kind: str  # "known" | "merchant" | "person" | "qr" | "unknown"
    key: str  # merchant_norm sent to the backend ("" when unknown); persons get a pseudonym
    display: str
    category: str | None = None


def _single_word_person(tokens: list[str]) -> bool:
    """One alphabetic word ("aishwaryakhan") with no 4+ letter business word inside."""
    vpa = rules()["vpa"]
    business = [w for w in rules()["names"]["business_words"] if len(w) >= 4]
    return (
        len(tokens) == 1
        and tokens[0].isalpha()
        and len(tokens[0]) >= vpa["single_token_person_min_length"]
        and not any(w in tokens[0] for w in business)
    )


def _title(tokens: list[str]) -> str:
    """Upper-cases the first character of each token, like the Dart twin
    (str.title() would also capitalise after digits: "7Eleven")."""
    return " ".join(t[:1].upper() + t[1:] for t in tokens if t)


def resolve(raw: str | None, salt: str, p2a: bool = False, p2m: bool = False) -> Name:
    raw = (raw or "").strip()
    if not raw:
        return Name("unknown", "", "Unknown")
    vpa = rules()["vpa"]
    if "@" in raw:
        handle, _, psp = raw.lower().partition("@")
        if handle.isdigit() and len(handle) >= 10:
            return Name("person", person_key(handle, salt), "UPI user")
        if any(handle.startswith(p) for p in vpa["qr_handle_prefixes"]) or re.match(
            vpa["qr_handle_pattern"], handle, re.A
        ):
            return Name("qr", "", "UPI merchant")
        known = match_known(handle)
        if known:
            return Name("known", known["id"], known["name"], known["category"])
        # Digits come off before the person check, so "rahul.sharma99@okhdfcbank"
        # is recognised as a person (and pseudonymised) rather than sent as a name.
        tokens = normalize(_DIGITS.sub(" ", handle)).split()
        business_psp = any(marker in psp for marker in vpa["business_psp_markers"])
        if not business_psp and not p2m and (
            p2a
            or (psp in vpa["personal_psps"]
                and (_looks_like_person(tokens) or _single_word_person(tokens)))
        ):
            return Name("person", person_key(" ".join(tokens), salt), _title(tokens))
        key = normalize(_DIGITS.sub(" ", handle))
        return Name("merchant", key, _title(key.split())) if key else Name("qr", "", "UPI merchant")

    known = match_known(raw)
    if known:
        return Name("known", known["id"], known["name"], known["category"])
    n = strip_legal_suffixes(normalize(raw))
    tokens = n.split()
    if not p2m and (p2a or _looks_like_person(tokens)):
        return Name("person", person_key(n, salt), _title(tokens))
    return Name("merchant", n, _title(tokens)) if n else Name("unknown", "", "Unknown")
