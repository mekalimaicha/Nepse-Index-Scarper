"""Scrape https://nepalstock.com/holiday-listing for every year (Year in AD) and archive it."""
from __future__ import annotations

import csv
import logging
import re
from datetime import date, datetime
from pathlib import Path

from . import config
from .browser import SET_VALUE_JS, open_browser, save_debug

log = logging.getLogger(__name__)

ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _first_date(cells: list[str]) -> date | None:
    for c in cells:
        m = ISO.search(c)
        if m:
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                pass
        m = SLASH.search(c)
        if m:
            try:
                return date(int(m[3]), int(m[1]), int(m[2]))
            except ValueError:
                pass
    return None


def _table_rows(page) -> list[list[str]]:
    return page.eval_on_selector_all(
        "table tbody tr",
        "trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))")


def _parse(rows: list[list[str]]) -> list[tuple[date, str]]:
    out = []
    for cells in rows:
        d = _first_date(cells)
        if d is None:
            continue
        desc = max((c for c in cells if not (ISO.search(c) or SLASH.search(c))), key=len, default="")
        out.append((d, desc.strip()))
    return out


def _select_ad(page) -> None:
    """Choose 'Year in AD' whether it's a radio, a tab/label, or an <option>."""
    for sel in ("label:has-text('Year in AD')", "text=Year in AD", "button:has-text('AD')"):
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.click(timeout=3000)
                return
            except Exception:
                continue
    for s in page.eval_on_selector_all(
            "select", "els => els.map((el,i)=>({i, opts:Array.from(el.options).map(o=>({v:o.value,t:o.text.trim()}))}))"):
        for o in s["opts"]:
            if re.search(r"year in ad", o["t"], re.I):
                page.locator("select").nth(s["i"]).evaluate(SET_VALUE_JS, o["v"])
                return
    log.info("No explicit 'Year in AD' control found - assuming the year list is already AD.")


def _year_select(page):
    """The <select> whose options look like years (AD)."""
    for s in page.eval_on_selector_all(
            "select", "els => els.map((el,i)=>({i, opts:Array.from(el.options).map(o=>({v:o.value,t:o.text.trim()}))}))"):
        years = [(o["v"], int(o["t"])) for o in s["opts"] if re.fullmatch(r"(19|20)\d{2}", o["t"])]
        if len(years) >= 2:
            return page.locator("select").nth(s["i"]), years
    return None, []


def fetch_all_years(headed: bool = False, min_year: int | None = None) -> dict[date, str]:
    """Scrape holiday years >= min_year (default: current year). Older years come from the seeded archive."""
    min_year = min_year or config.now_npt().year
    found: dict[date, str] = {}
    with open_browser(headed) as ctx:
        page = ctx.new_page()
        page.goto(config.HOLIDAY_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        _select_ad(page)
        page.wait_for_timeout(1500)
        select, years = _year_select(page)
        if select is None:
            log.warning("Year dropdown not found - parsing whatever table is shown.")
            for d, desc in _parse(_table_rows(page)):
                if d.year >= min_year:
                    found[d] = desc
        else:
            for value, year in sorted(years, key=lambda t: t[1]):
                if year < min_year:
                    continue
                select.evaluate(SET_VALUE_JS, value)
                page.wait_for_timeout(1200)
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                got = _parse(_table_rows(page))
                log.info("Holidays %s: %d rows", year, len(got))
                for d, desc in got:
                    found[d] = desc
        if not found:
            save_debug(page, "holiday_page_empty")
    return found


def archive(found: dict[date, str]) -> Path:
    """Merge into data/holidays/holidays.csv (never drops old dates) + monthly snapshot."""
    hol_dir = config.HOLIDAY_DIR
    (hol_dir / "archive").mkdir(parents=True, exist_ok=True)
    master = hol_dir / "holidays.csv"

    merged: dict[date, str] = {}
    if master.exists():
        with master.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    merged[date.fromisoformat(row["date"])] = row.get("description", "")
                except (KeyError, ValueError):
                    continue
    merged.update(found)

    with master.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["date", "weekday", "year", "description"])
        for d in sorted(merged):
            w.writerow([d.isoformat(), d.strftime("%A"), d.year, merged[d]])

    stamp = datetime.now(config.NPT).strftime("%Y-%m")
    snap = hol_dir / "archive" / f"holidays_snapshot_{stamp}.csv"
    with snap.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["date", "weekday", "year", "description"])
        for d in sorted(found):
            w.writerow([d.isoformat(), d.strftime("%A"), d.year, found[d]])
    return master


def run(headed: bool = False) -> int:
    found = fetch_all_years(headed)
    if not found:
        log.error("No holidays scraped; existing archive left untouched.")
        return 1
    path = archive(found)
    log.info("Holiday archive updated: %s (%d dates scraped this run)", path, len(found))
    return 0
