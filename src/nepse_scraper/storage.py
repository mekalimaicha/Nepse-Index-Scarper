"""Read / merge / write the per-index CSV files (newest row first)."""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .formatting import (HEADER, fmt_date, fmt_pct, fmt_turnover, fmt_value,
                         parse_date, to_float, to_float_or_zero)


@dataclass
class Record:
    day: date
    open: float
    high: float
    low: float
    close: float
    change: float
    pct_change: float
    turnover: float
    raw: list[str] | None = None   # original CSV cells, kept so untouched rows stay byte-identical

    def values(self) -> tuple:
        return (self.open, self.high, self.low, self.close, self.change, self.pct_change, self.turnover)

    def cells(self) -> list[str]:
        """Formatted cells, S.N. left blank (assigned on write)."""
        if self.raw is not None:
            return list(self.raw)
        return ["", fmt_value(self.open), fmt_value(self.high), fmt_value(self.low),
                fmt_value(self.close), fmt_value(self.change), fmt_pct(self.pct_change),
                fmt_turnover(self.turnover), fmt_date(self.day)]


def record_from_cells(cells: list[str], keep_raw: bool = False) -> Record:
    """cells = [S.N., Open, High, Low, Close, Change, Per Change, Turnover, Date]"""
    if len(cells) < 9:
        raise ValueError(f"expected 9 cells, got {len(cells)}: {cells}")
    return Record(
        day=parse_date(cells[8]),
        open=to_float(cells[1]), high=to_float(cells[2]), low=to_float(cells[3]), close=to_float(cells[4]),
        change=to_float_or_zero(cells[5]), pct_change=to_float_or_zero(cells[6]),
        turnover=to_float_or_zero(cells[7]),
        raw=list(cells) if keep_raw else None,
    )


def read_csv(path: Path) -> dict[date, Record]:
    out: dict[date, Record] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for cells in reader:
            if not cells or not any(c.strip() for c in cells):
                continue
            rec = record_from_cells(cells, keep_raw=True)
            out[rec.day] = rec
    return out


def last_date(path: Path) -> date | None:
    data = read_csv(path)
    return max(data) if data else None


def merge(existing: dict[date, Record], new: list[Record]) -> tuple[dict[date, Record], int, int]:
    """Merge scraped rows into existing ones. Returns (merged, added, updated)."""
    merged = dict(existing)
    added = updated = 0
    for rec in new:
        old = merged.get(rec.day)
        if old is None:
            added += 1
            merged[rec.day] = rec
        elif old.values() != rec.values():
            updated += 1
            merged[rec.day] = rec
    return merged, added, updated


def write_csv(path: Path, records: dict[date, Record]) -> None:
    """Atomic write, newest first, S.N. renumbered 1..N, CRLF like the originals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\r\n")
            writer.writerow(HEADER)
            for n, day in enumerate(sorted(records, reverse=True), start=1):
                cells = records[day].cells()
                cells[0] = str(n)
                writer.writerow(cells)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
