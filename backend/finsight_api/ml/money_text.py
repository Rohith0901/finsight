"""Rupee formatting with Indian digit grouping (1,23,456)."""

from __future__ import annotations


def group_indian(n: int) -> str:
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def rupees(paise: int, decimals: bool = False) -> str:
    """₹ string for an amount in paise. Whole rupees unless decimals is True."""
    if decimals:
        sign = "-" if paise < 0 else ""
        whole, frac = divmod(abs(paise), 100)
        return f"{sign}₹{group_indian(whole)}.{frac:02d}"
    whole = (abs(paise) + 50) // 100  # round half up, not to even
    return ("-₹" if paise < 0 and whole else "₹") + group_indian(whole)
