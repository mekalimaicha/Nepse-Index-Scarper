"""Merge logic for 'Dividend History.csv' (hand-collected data + automatic updates).

The CSV is a hybrid: some columns follow the website, some are maintained by hand.
Merging therefore never replaces the file - it updates it:

  * Rows are never deleted (e.g. FY 2080/2081 is not on the site and stays untouched).
  * Bonus / Cash / Total: the site value wins, EXCEPT when the stored value is the same
    number at the site's 2-decimal precision (so 0.2632 is not downgraded to 0.26).
  * Announcement Date / Book Closure Date: a non-empty site value wins.
  * Distribution Date / Bonus Listing Date (not on the site): never overwritten, only filled if blank.
  * New (symbol, fiscal year) records are appended; S.N. is renumbered; order is
    fiscal year newest first, then announcement date newest first (blank dates last).
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from .formatting import fmt_date, fmt_value, parse_date, to_float

COLUMNS = ["S.N.", "SYMBOL", "Company", "Bonus (%)", "Cash (%)", "Total (%)", "Announcement Date",
           "Book Closure Date", "Distribution Date", "Bonus Listing Date", "Fiscal Year"]
PCT_COLS = ("Bonus (%)", "Cash (%)", "Total (%)")
TOL = 0.0051   # two values equal at 2-decimal precision


class DividendFileError(RuntimeError):
    pass


# ------------------------------------------------------------------ parsing (site -> CSV style)
_DASHES = {"", "-", "--", "—", "–", "n/a", "na", "null"}


def blank(text: str | None) -> bool:
    return (text or "").strip().lower() in _DASHES


def parse_pct(text: str | None) -> float | None:
    """'1,540.00%' -> 1540.0 ; '—' -> None"""
    if blank(text):
        return None
    try:
        return to_float(str(text).replace("%", "").strip())
    except ValueError:
        return None


def fmt_pct_cell(value: float | None) -> str:
    return "" if value is None else fmt_value(value)


_SITE_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y")


def parse_site_date(text: str | None) -> date | None:
    if blank(text):
        return None
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = re.sub(r"\[.*?\]", "", s).strip()
    for fmt in _SITE_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def clean_book_close(text: str | None) -> str:
    """Stored exactly as the site shows it (e.g. '2026-08-16 [Closed]'), blank for dashes."""
    if blank(text):
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def normalize_fy(text: str) -> str:
    """'FY 2082/83' -> '2082/2083'"""
    m = re.search(r"(\d{4})\s*/\s*(\d{2,4})", text or "")
    if not m:
        raise ValueError(f"not a fiscal year label: {text!r}")
    a, b = m.group(1), m.group(2)
    if len(b) == 2:
        b = a[:2] + b
    return f"{a}/{b}"


def make_incoming(symbol: str, company: str, cash: str, bonus: str, total: str,
                  announced: str, book_close: str, fy_label: str) -> dict[str, str]:
    d = parse_site_date(announced)
    return {
        "SYMBOL": symbol.strip(), "Company": re.sub(r"\s+", " ", company or "").strip(),
        "Bonus (%)": fmt_pct_cell(parse_pct(bonus)), "Cash (%)": fmt_pct_cell(parse_pct(cash)),
        "Total (%)": fmt_pct_cell(parse_pct(total)),
        "Announcement Date": fmt_date(d) if d else "",
        "Book Closure Date": clean_book_close(book_close),
        "Distribution Date": "", "Bonus Listing Date": "",
        "Fiscal Year": normalize_fy(fy_label),
    }


# ------------------------------------------------------------------ file I/O
def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise DividendFileError(f"{path.name}: unexpected header {reader.fieldnames}; expected {COLUMNS}")
        return [{c: (r.get(c) or "") for c in COLUMNS} for r in reader if any((v or "").strip() for v in r.values())]


def render(rows: list[dict[str, str]]) -> bytes:
    import io
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for n, r in enumerate(rows, start=1):
        w.writerow([str(n)] + [r.get(c, "") for c in COLUMNS[1:]])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def write_if_changed(path: Path, rows: list[dict[str, str]]) -> bool:
    data = render(rows)
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


# ------------------------------------------------------------------ merge
def _d(row: dict[str, str]) -> date | None:
    try:
        return parse_date(row.get("Announcement Date", "")) if row.get("Announcement Date", "").strip() else None
    except ValueError:
        return None


def _n(text: str | None) -> float | None:
    return parse_pct(text)


def _close(a: float | None, b: float | None) -> bool:
    return abs((a or 0.0) - (b or 0.0)) <= TOL


def _pick(cands: list[dict], used: set[int], inc: dict[str, str]) -> dict | None:
    free = [c for c in cands if id(c) not in used]
    if not free:
        return None
    idate = _d(inc)
    if idate is None:
        return free[0]
    for c in free:                       # 1) same announcement date
        if _d(c) == idate:
            return c
    for c in free:                       # 2) stored row has no date yet
        if _d(c) is None:
            return c
    for c in free:                       # 3) same payout, date differs -> same record
        if _close(_n(c["Cash (%)"]), _n(inc.get("Cash (%)"))) and _close(_n(c["Bonus (%)"]), _n(inc.get("Bonus (%)"))):
            return c
    return None                          # re-announcement with different payout -> new row


def _update(target: dict[str, str], inc: dict[str, str]) -> bool:
    changed = False

    def setv(col: str, val: str) -> None:
        nonlocal changed
        if target.get(col, "") != val:
            target[col] = val
            changed = True

    if not target["Company"].strip() and inc.get("Company", "").strip():
        setv("Company", inc["Company"])
    for col in PCT_COLS:
        iv = (inc.get(col) or "").strip()
        if not iv:
            continue
        inum, enum = _n(iv), _n(target[col]) if target[col].strip() else None
        if inum is None:
            continue
        if enum is None:
            if inum != 0:
                setv(col, iv)
        elif abs(enum - inum) > TOL:
            setv(col, iv)
    for col in ("Announcement Date", "Book Closure Date"):
        iv = (inc.get(col) or "").strip()
        if iv:
            setv(col, iv)
    for col in ("Distribution Date", "Bonus Listing Date"):
        if not target[col].strip() and (inc.get(col) or "").strip():
            setv(col, inc[col].strip())
    return changed


def sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def key(r):
        d = _d(r)
        return (r["Fiscal Year"], d.toordinal() if d else -1)
    return sorted(rows, key=key, reverse=True)   # stable: ties keep their existing order


def merge(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    """Returns (rows, added, updated). `existing` is not modified."""
    rows = [dict(r) for r in existing]
    index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        index[(r["SYMBOL"].strip().upper(), r["Fiscal Year"].strip())].append(r)
    used: set[int] = set()
    added = updated = 0
    for inc in incoming:
        key = (inc["SYMBOL"].strip().upper(), inc["Fiscal Year"].strip())
        target = _pick(index.get(key, []), used, inc)
        if target is None:
            new = {c: (inc.get(c) or "") for c in COLUMNS if c != "S.N."}
            rows.append(new)
            index[key].append(new)
            used.add(id(new))
            added += 1
        else:
            used.add(id(target))
            if _update(target, inc):
                updated += 1
    return sort_rows(rows), added, updated
