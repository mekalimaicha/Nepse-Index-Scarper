"""Trading-day logic and the holiday archive."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from . import config


def is_trading_weekday(d: date) -> bool:
    wd = d.weekday()  # Mon=0 ... Sun=6
    if wd == 5:       # Saturday: never a trading day
        return False
    if d >= config.MON_FRI_FROM:
        return wd <= 4                   # Monday-Friday
    return wd in (6, 0, 1, 2, 3)         # Sunday-Thursday (historical week)


def is_trading_day(d: date, holidays: set[date]) -> bool:
    return is_trading_weekday(d) and d not in holidays


def trading_days_between(start: date, end: date, holidays: set[date]) -> list[date]:
    """All expected trading days in [start, end]."""
    out, d = [], start
    while d <= end:
        if is_trading_day(d, holidays):
            out.append(d)
        d += timedelta(days=1)
    return out


def _read_dates(path: Path) -> set[date]:
    out: set[date] = set()
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                out.add(date.fromisoformat(row["date"].strip()))
            except (KeyError, ValueError, AttributeError):
                continue
    return out


def load_holidays() -> set[date]:
    """Scraped archive + optional hand-maintained overrides (config/holidays_manual.csv)."""
    return _read_dates(config.HOLIDAY_DIR / "holidays.csv") | _read_dates(config.MANUAL_HOLIDAYS)
