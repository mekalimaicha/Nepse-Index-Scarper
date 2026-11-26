"""Scrape https://hamroshare.com.np/investment/proposed-dividend (one tab per fiscal year)
and merge the result into 'Dividend History.csv'.

Site columns: Symbol, Company, Cash %, Bonus %, Total %, Announced, Book Close, Status.
Tabs are discovered from the page (any "FY 2082/83"-style label), so a new fiscal year
appears automatically. Merge rules: see dividends.py - existing/manual data is never deleted.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from . import config, dividends as dv
from .browser import open_browser, save_debug

log = logging.getLogger(__name__)

FY_TEXT = re.compile(r"^(?:FY\s*)?(\d{4})\s*/\s*(\d{2,4})(?:\s*FY)?(?:\s*\(?\s*latest(?:\s*FY)?\s*\)?)?$", re.I)

# JS: find fiscal-year tab candidates and tag the best element per year with data-fy-tab.
FIND_TABS_JS = r"""
(pattern) => {
  const re = new RegExp(pattern, 'i');
  const pref = el => {
    const tag = el.tagName.toLowerCase(), role = el.getAttribute('role') || '';
    if (role === 'tab') return 0;
    if (tag === 'button') return 1;
    if (tag === 'a' || tag === 'li' || tag === 'label') return 2;
    return 3;
  };
  const best = {};
  for (const el of document.querySelectorAll('button,[role=tab],a,li,label,div,span')) {
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 40 || el.children.length > 3) continue;
    const m = t.match(re);
    if (!m) continue;
    let b = m[2]; if (b.length === 2) b = m[1].slice(0, 2) + b;
    const fy = m[1] + '/' + b;
    if (!(fy in best) || pref(el) < pref(best[fy])) best[fy] = el;
  }
  const out = [];
  for (const [fy, el] of Object.entries(best)) { el.setAttribute('data-fy-tab', fy); out.push([fy, el.innerText.replace(/\s+/g,' ').trim()]); }
  return out;
}
"""

READ_TABLE_JS = r"""
() => {
  for (const t of document.querySelectorAll('table')) {
    if (t.offsetParent === null) continue;
    const hs = [...t.querySelectorAll('thead th, thead td')].map(h => h.innerText.replace(/\s+/g, ' ').trim());
    const hl = hs.map(h => h.toLowerCase());
    if (!hl.some(h => h.includes('symbol')) || !hl.some(h => h.includes('cash'))) continue;
    const rows = [...t.querySelectorAll('tbody tr')].map(tr =>
      [...tr.children].map(td => (td.innerText || '').replace(/ /g, ' ').split('\n').map(x => x.trim()).filter(Boolean).join(' ')));
    return {headers: hs, rows: rows};
  }
  return null;
}
"""


class HamroShareError(RuntimeError):
    pass


def _col_map(headers: list[str]) -> dict[str, int]:
    want = {"symbol": "symbol", "company": ("company", "name"), "cash": "cash", "bonus": "bonus",
            "total": "total", "announced": "announc", "book": "book"}
    out: dict[str, int] = {}
    for key, needle in want.items():
        needles = (needle,) if isinstance(needle, str) else needle
        for i, h in enumerate(headers):
            if any(n in h.lower() for n in needles):
                out[key] = i
                break
    missing = [k for k in ("symbol", "cash", "bonus", "announced") if k not in out]
    if missing:
        raise HamroShareError(f"Table columns not recognised (missing {missing}); headers: {headers}")
    return out


def rows_to_records(table: dict, fy: str) -> list[dict[str, str]]:
    cm = _col_map(table["headers"])

    def cell(cells, key):
        i = cm.get(key)
        return cells[i] if i is not None and i < len(cells) else ""

    recs, seen = [], set()
    for cells in table["rows"]:
        sym_cell = cell(cells, "symbol").split()
        if not sym_cell or len(cells) < 4:
            continue
        rec = dv.make_incoming(sym_cell[0], cell(cells, "company"), cell(cells, "cash"), cell(cells, "bonus"),
                               cell(cells, "total"), cell(cells, "announced"), cell(cells, "book"), fy)
        sig = tuple(rec.values())
        if sig in seen:
            continue
        seen.add(sig)
        recs.append(rec)
    return recs


class DividendPage:
    def __init__(self, context, url: str):
        self.page = context.new_page()
        self.url = url

    def open(self) -> None:
        p = self.page
        p.goto(self.url, wait_until="domcontentloaded")
        try:
            p.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        if "dividend" not in p.content().lower():
            save_debug(p, "dividend_page_unexpected")
            raise HamroShareError("Dividend page not recognised (blocked, or layout changed).")

    def fy_tabs(self) -> list[str]:
        found = self.page.evaluate(FIND_TABS_JS, FY_TEXT.pattern)
        fys = sorted({fy for fy, _ in found}, reverse=True)
        if not fys:
            save_debug(self.page, "dividend_no_fy_tabs")
            raise HamroShareError("No fiscal-year tabs (e.g. 'FY 2082/83') found on the page.")
        return fys

    def _table(self) -> dict | None:
        return self.page.evaluate(READ_TABLE_JS)

    @staticmethod
    def _sig(table: dict | None) -> tuple:
        return tuple(tuple(r) for r in (table or {"rows": []})["rows"][:3])

    def _load_more(self) -> None:
        for _ in range(200):
            btn = self.page.get_by_role("button", name=re.compile(r"^\s*(show|load|view)\s+more", re.I))
            if not btn.count() or not btn.first.is_visible() or not btn.first.is_enabled():
                return
            before = len((self._table() or {"rows": []})["rows"])
            btn.first.click()
            self.page.wait_for_timeout(700)
            if len((self._table() or {"rows": []})["rows"]) <= before:
                return

    def scrape_fy(self, fy: str, previous_sig: tuple | None) -> tuple[list[dict[str, str]], tuple]:
        self.page.locator(f"[data-fy-tab='{fy}']").first.click()
        deadline = time.time() + 15
        table = None
        while time.time() < deadline:
            table = self._table()
            sig = self._sig(table)
            if table and table["rows"] and (previous_sig is None or sig != previous_sig):
                break
            time.sleep(0.4)
        else:
            save_debug(self.page, f"dividend_tab_{fy.replace('/', '-')}")
            raise HamroShareError(f"FY {fy}: table did not load or did not change after clicking the tab.")
        self._load_more()
        table = self._table() or table
        return rows_to_records(table, fy), self._sig(table)

    def close(self) -> None:
        self.page.close()


def scrape(url: str | None = None, headed: bool = False) -> list[dict[str, str]]:
    url = url or config.DIVIDEND_URL
    out: list[dict[str, str]] = []
    with open_browser(headed) as ctx:
        page = DividendPage(ctx, url)
        try:
            page.open()
            fys = page.fy_tabs()
            log.info("Fiscal-year tabs found: %s", ", ".join(fys))
            prev, sigs = None, {}
            for fy in fys:
                for attempt in (1, 2, 3):
                    try:
                        recs, sig = page.scrape_fy(fy, prev)
                        break
                    except Exception as exc:
                        log.warning("FY %s attempt %d/3 failed: %s", fy, attempt, exc)
                        if attempt == 3:
                            raise
                        time.sleep(4 * attempt)
                        page.open()
                        page.fy_tabs()
                if sig in sigs:
                    raise HamroShareError(f"FY {fy} shows the same rows as FY {sigs[sig]} (tab switch failed).")
                sigs[sig] = fy
                prev = sig
                log.info("FY %s: %d rows scraped", fy, len(recs))
                out.extend(recs)
        finally:
            page.close()
    return out


def run(out_dir: Path, headed: bool = False, url: str | None = None, force: bool = False) -> int:
    path = out_dir / config.DIVIDEND_FILE
    try:
        incoming = scrape(url, headed)
        if not incoming:
            raise HamroShareError("Scrape returned 0 rows; existing file kept.")
        existing = dv.read_rows(path)
        merged, added, updated = dv.merge(existing, incoming)
        if existing and added > max(40, int(len(existing) * 0.25)) and not force:
            raise HamroShareError(f"Would add {added} new rows to {len(existing)} existing - looks wrong; "
                                  f"nothing written. Re-run with --force if this is expected.")
        changed = dv.write_if_changed(path, merged)
        log.info("Dividend History: +%d new, %d updated, %d total rows (%s) -> %s",
                 added, updated, len(merged), "file written" if changed else "no change", path)
        return 0
    except Exception as exc:
        log.error("Dividend History FAILED: %s", exc)
        return 1
