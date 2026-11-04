"""Parse and format values exactly as they appear in the existing CSV files.

Observed conventions (see tests/test_formatting.py, which checks every row of
the original files):
  * values >= 1,000 -> thousands separators, always 2 decimals  ("2,691.10")
  * values  < 1,000 -> plain, trailing zeros trimmed            ("94.8", "100")
  * Turnover        -> thousands separators, 2 decimals, or "0"
  * Date            -> M/D/YYYY with no zero padding            ("11/3/2026")
"""
from __future__ import annotations

from datetime import date, datetime

HEADER = ["S.N.", "Open", "High", "Low", "Close", "Change", "Per Change (%)", "Turnover", "Date"]


def to_float(text: str | float | int | None) -> float:
    if text is None:
        raise ValueError("empty value")
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(",", "").replace("−", "-")
    if s in {"", "-", "--", "N/A", "n/a"}:
        raise ValueError(f"not a number: {text!r}")
    return float(s)


def to_float_or_zero(text) -> float:
    try:
        return to_float(text)
    except ValueError:
        return 0.0


def fmt_value(v: float) -> str:
    """Open/High/Low/Close/Change."""
    v = round(v, 2)
    if v == 0:
        return "0"
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fmt_pct(v: float) -> str:
    v = round(v, 2)
    if v == 0:
        return "0"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fmt_turnover(v: float) -> str:
    return "0" if v == 0 else f"{v:,.2f}"


def fmt_date(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y", "%d %b %Y")


def parse_date(text: str) -> date:
    s = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")
