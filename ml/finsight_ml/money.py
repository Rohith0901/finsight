"""Amount formats that appear in bank SMS."""

from __future__ import annotations


def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def comma(paise: int) -> str:
    """1,23,456.78"""
    return f"{_indian(paise // 100)}.{paise % 100:02d}"


def plain2(paise: int) -> str:
    """123456.78"""
    return f"{paise // 100}.{paise % 100:02d}"


def plain1(paise: int) -> str:
    """SBI style: 485.0, 485.5, 485.55"""
    rupees, p = divmod(paise, 100)
    if p == 0:
        return f"{rupees}.0"
    if p % 10 == 0:
        return f"{rupees}.{p // 10}"
    return f"{rupees}.{p:02d}"


def plain_int(paise: int) -> str:
    """25000 when whole, else 25000.50"""
    rupees, p = divmod(paise, 100)
    return str(rupees) if p == 0 else f"{rupees}.{p:02d}"
