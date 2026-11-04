import csv
from datetime import date
from pathlib import Path

import pytest

from nepse_scraper import calendar, config, updater
from nepse_scraper.formatting import (fmt_date, fmt_pct, fmt_turnover, fmt_value, parse_date, to_float)
from nepse_scraper.storage import Record, merge, read_csv, record_from_cells, write_csv

DATA = config.DEFAULT_REPO_DATA


# ---------------------------------------------------------------- formatting
def test_value_formats():
    assert fmt_value(2691.1) == "2,691.10"
    assert fmt_value(94.8) == "94.8"
    assert fmt_value(100.0) == "100"
    assert fmt_value(0) == "0"
    assert fmt_value(-165.29) == "-165.29"
    assert fmt_pct(-0.2) == "-0.2"
    assert fmt_turnover(126421771.9) == "126,421,771.90"
    assert fmt_turnover(0) == "0"
    assert fmt_date(date(2026, 11, 3)) == "11/3/2026"
    assert parse_date("2026-11-03") == parse_date("11/3/2026") == date(2026, 11, 3)
    assert to_float("1,234.50") == 1234.5


@pytest.mark.skipif(not DATA.exists(), reason="seed data missing")
def test_formatting_reproduces_every_original_row():
    """Re-formatting parsed values must give back the original cells (S.N. excluded)."""
    total = mismatches = 0
    for path in sorted(DATA.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            r = csv.reader(fh)
            next(r)
            for cells in r:
                if len(cells) < 9:
                    continue
                total += 1
                formatted = record_from_cells(cells).cells()
                if formatted[1:] != cells[1:9]:
                    mismatches += 1
    assert total > 30000
    assert mismatches / total < 0.001, f"{mismatches}/{total} rows would be reformatted differently"


# ---------------------------------------------------------------- calendar
def test_trading_week():
    assert not calendar.is_trading_weekday(date(2026, 11, 7))    # Saturday
    assert calendar.is_trading_weekday(date(2026, 11, 6))        # Friday (Mon-Fri era)
    assert not calendar.is_trading_weekday(date(2026, 11, 8))    # Sunday (Mon-Fri era)
    assert calendar.is_trading_weekday(date(2026, 4, 5))         # last Sunday session
    assert not calendar.is_trading_weekday(date(2026, 4, 3))     # Friday of the old week
    assert calendar.is_trading_weekday(date(2026, 4, 10))        # first Friday session


def test_holidays_are_skipped():
    hol = {date(2026, 11, 5)}
    days = calendar.trading_days_between(date(2026, 11, 4), date(2026, 11, 9), hol)
    assert days == [date(2026, 11, 4), date(2026, 11, 6), date(2026, 11, 9)]


# ---------------------------------------------------------------- storage
def _rec(d, close, raw=None):
    return Record(d, close, close, close, close, 0.0, 0.0, 0.0, raw)


def test_merge_and_write_roundtrip(tmp_path):
    p = tmp_path / "X.csv"
    a = {date(2026, 11, 2): _rec(date(2026, 11, 2), 100.0)}
    merged, added, updated = merge(a, [_rec(date(2026, 11, 3), 101.5), _rec(date(2026, 11, 2), 100.0)])
    assert (added, updated) == (1, 0)
    merged, added, updated = merge(merged, [_rec(date(2026, 11, 3), 102.0)])
    assert (added, updated) == (0, 1)
    write_csv(p, merged)
    lines = p.read_bytes().decode().split("\r\n")
    assert lines[0] == "S.N.,Open,High,Low,Close,Change,Per Change (%),Turnover,Date"
    assert lines[1].startswith("1,102,102,102,102,0,0,0,11/3/2026")
    assert lines[2].endswith("11/2/2026")
    assert sorted(read_csv(p)) == [date(2026, 11, 2), date(2026, 11, 3)]


def test_plan_skips_when_only_holiday_pending(tmp_path, monkeypatch):
    spec = config.INDICES[0]
    write_csv(tmp_path / f"{spec.file_stem}.csv", {date(2026, 11, 3): _rec(date(2026, 11, 3), 1.0)})
    monkeypatch.setattr(updater, "load_holidays", lambda: {date(2026, 11, 4)})
    plan = updater.plan(tmp_path, [spec], force=False, backfill=False, today=date(2026, 11, 4))
    assert plan[spec] is None                       # Nov 4 is a holiday -> no scrape
    monkeypatch.setattr(updater, "load_holidays", lambda: set())
    plan = updater.plan(tmp_path, [spec], force=False, backfill=False, today=date(2026, 11, 4))
    assert plan[spec] == date(2026, 10, 28)         # last stored - 6 days overlap


def test_sync_merges_without_losing_local_rows(tmp_path):
    spec = config.INDICES[0]
    src, dst = tmp_path / "src", tmp_path / "dst"
    write_csv(src / "NEPSE.csv", {date(2026, 11, 3): _rec(date(2026, 11, 3), 5.0)})
    write_csv(dst / "NEPSE.csv", {date(2026, 11, 2): _rec(date(2026, 11, 2), 4.0)})
    updater.run_sync(src, dst, [spec])
    assert set(read_csv(dst / "NEPSE.csv")) == {date(2026, 11, 2), date(2026, 11, 3)}
