"""Scrape https://www.sharesansar.com/promoter-lockin (Locked + Unlocked tabs, all sectors).

The page has a "Select Sector" filter (default ALL), a Search button and two tabs,
"Locked" (#locked) and "Unlocked" (#unlocked), each holding a DataTables table.
Column headers are read from the page itself, so the CSV mirrors the site.

Output: <out>/Promoter Lock In.csv  = "Status" column (Locked/Unlocked) + the page's columns.
The file is a full snapshot that is replaced on every run (lock-in status is current state,
not a time series). An empty or badly shrunken result never overwrites the existing file.
"""
from __future__ import annotations

import csv
import logging
import os
import re
import tempfile
import time
from pathlib import Path

from . import config
from .browser import SET_VALUE_JS, open_browser, save_debug

log = logging.getLogger(__name__)

TABS = ("Locked", "Unlocked")
SHRINK_GUARD = 0.5   # refuse to replace the file if the new row count < 50% of the old one


class LockInError(RuntimeError):
    pass


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_serial(header: str) -> bool:
    return re.fullmatch(r"s\.?\s*(n|no)\.?", header.strip().lower()) is not None


class LockInPage:
    def __init__(self, context, url: str):
        self.page = context.new_page()
        self.url = url

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        p = self.page
        p.goto(self.url, wait_until="domcontentloaded")
        try:
            p.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        if "lock" not in p.content().lower():
            save_debug(p, "lockin_page_unexpected")
            raise LockInError("Promoter Lock In page not recognised (blocked, or layout changed).")

    def _pane(self, tab: str):
        loc = self.page.locator(f"#{tab.lower()}")
        return loc if loc.count() else self.page

    def _activate_tab(self, tab: str) -> None:
        link = self.page.locator(f"a[href='#{tab.lower()}']")
        if link.count():
            link.first.click()
        else:
            alt = self.page.get_by_text(re.compile(rf"^\s*{tab}\s*$", re.I))
            if alt.count():
                alt.first.click()
        self.page.wait_for_timeout(500)

    def _set_sector_all(self) -> None:
        for s in self.page.eval_on_selector_all(
                "select",
                "els => els.map((el,i)=>({i, opts:Array.from(el.options).map(o=>({v:o.value,t:o.text.trim()}))}))"):
            texts = {o["t"].lower() for o in s["opts"]}
            if "all" in texts and any("bank" in t or "hydro" in t for t in texts):
                val = next(o["v"] for o in s["opts"] if o["t"].lower() == "all")
                self.page.locator("select").nth(s["i"]).evaluate(SET_VALUE_JS, val)
                return

    def _click_search(self) -> None:
        p = self.page
        btn = p.get_by_role("button", name=re.compile(r"^\s*search\s*$", re.I))
        if btn.count():
            btn.first.click()
            return
        alt = p.locator("input[type=submit], button:has-text('Search'), #btn_search")
        if alt.count():
            alt.first.click()
            return
        log.info("No Search button found - using the table as loaded.")

    # ------------------------------------------------------------------ #
    def _table(self, pane):
        tables = pane.locator("table:has(thead th)")
        for i in range(tables.count()):
            t = tables.nth(i)
            if t.is_visible():
                return t
        raise LockInError("No visible data table found.")

    @staticmethod
    def _headers(table) -> list[str]:
        return [_clean(h) for h in table.locator("thead tr").last.locator("th").evaluate_all(
            "ths => ths.map(th => th.innerText)")]

    @staticmethod
    def _rows(table, width: int) -> list[list[str]]:
        raw = table.locator("tbody tr").evaluate_all(
            "trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText))")
        rows = []
        for cells in raw:
            cells = [_clean(c) for c in cells]
            if len(cells) == width and any(cells):
                rows.append(cells)
        return rows

    def _wait_rows(self, pane, width: int) -> None:
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                table = self._table(pane)
                if self._rows(table, width):
                    return
                if re.search(r"no (data|matching|record)", table.inner_text(), re.I):
                    return
            except LockInError:
                pass
            time.sleep(0.4)
        raise LockInError("Timed out waiting for table rows.")

    def _max_page_length(self, pane) -> None:
        sel = pane.locator("select[name$=_length]")
        if not sel.count():
            return
        values = sel.first.evaluate("el => Array.from(el.options).map(o => o.value)")
        nums = [int(v) for v in values if re.fullmatch(r"\d+", v)]
        best = "-1" if "-1" in values else (str(max(nums)) if nums else None)
        if best:
            sel.first.evaluate(SET_VALUE_JS, best)
            self.page.wait_for_timeout(800)

    def _next(self, pane, table, width: int, first_before: list[str]) -> bool:
        nxt = pane.locator(".paginate_button.next, a.paginate_button.next, li.next a")
        if not nxt.count():
            return False
        node = nxt.first
        cls = (node.get_attribute("class") or "") + " " + (
            node.evaluate("el => el.parentElement ? el.parentElement.className : ''") or "")
        if "disabled" in cls:
            return False
        node.click()
        deadline = time.time() + 30
        while time.time() < deadline:
            rows = self._rows(table, width)
            if rows and rows[0] != first_before:
                return True
            time.sleep(0.3)
        return False

    # ------------------------------------------------------------------ #
    def scrape_tab(self, tab: str) -> tuple[list[str], list[list[str]]]:
        self._activate_tab(tab)
        self._set_sector_all()
        self._click_search()
        pane = self._pane(tab)
        table = self._table(pane)
        headers = self._headers(table)
        if not headers:
            raise LockInError(f"{tab}: table has no headers.")
        width = len(headers)
        self._wait_rows(pane, width)
        self._max_page_length(pane)
        table = self._table(pane)

        out: list[list[str]] = []
        for page_no in range(1, 3001):
            rows = self._rows(table, width)
            out.extend(rows)
            if not rows or not self._next(pane, table, width, rows[0]):
                break
        keep = [i for i, h in enumerate(headers) if not _is_serial(h)]
        return ([headers[i] for i in keep], [[r[i] for i in keep] for r in out])

    def close(self) -> None:
        self.page.close()


# ---------------------------------------------------------------------- #
def combine(parts: dict[str, tuple[list[str], list[list[str]]]]) -> tuple[list[str], list[list[str]]]:
    """Merge Locked/Unlocked into one table: Status + union of columns (ordered by first appearance)."""
    cols: list[str] = []
    for _, (headers, _rows) in parts.items():
        for h in headers:
            if h not in cols:
                cols.append(h)
    rows: list[list[str]] = []
    for status, (headers, data) in parts.items():
        idx = {h: i for i, h in enumerate(headers)}
        for r in data:
            rows.append([status] + [r[idx[c]] if c in idx else "" for c in cols])
    return ["Status"] + cols, rows


def write_snapshot(path: Path, header: list[str], rows: list[list[str]]) -> str:
    """Atomic replace. Returns 'written', 'unchanged' or raises LockInError if the guard trips."""
    if not rows:
        raise LockInError("Scrape returned 0 rows; existing file kept.")
    old_rows = 0
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as fh:
            old_rows = max(sum(1 for _ in fh) - 1, 0)
        if old_rows and len(rows) < old_rows * SHRINK_GUARD:
            raise LockInError(f"Scrape returned {len(rows)} rows vs {old_rows} stored; existing file kept.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(header)
            w.writerows(rows)
        if path.exists() and path.read_bytes() == Path(tmp).read_bytes():
            os.unlink(tmp)
            return "unchanged"
        os.replace(tmp, path)
        return "written"
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def run(out_dir: Path, headed: bool = False, url: str | None = None) -> int:
    url = url or config.PROMOTER_LOCKIN_URL
    parts: dict[str, tuple[list[str], list[list[str]]]] = {}
    try:
        with open_browser(headed) as ctx:
            page = LockInPage(ctx, url)
            try:
                page.open()
                for tab in TABS:
                    for attempt in (1, 2, 3):
                        try:
                            parts[tab] = page.scrape_tab(tab)
                            log.info("Promoter Lock In - %s: %d rows, columns %s",
                                     tab, len(parts[tab][1]), parts[tab][0])
                            break
                        except Exception as exc:
                            log.warning("%s attempt %d/3 failed: %s", tab, attempt, exc)
                            if attempt == 3:
                                save_debug(page.page, f"lockin_fail_{tab}")
                                raise
                            time.sleep(4 * attempt)
                            page.open()
            finally:
                page.close()
        header, rows = combine(parts)
        path = out_dir / config.LOCKIN_FILE
        result = write_snapshot(path, header, rows)
        log.info("Promoter Lock In: %s (%d rows) -> %s", result, len(rows), path)
        return 0
    except Exception as exc:
        log.error("Promoter Lock In FAILED: %s", exc)
        return 1
