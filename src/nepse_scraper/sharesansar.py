"""Drive https://www.sharesansar.com/index-history-data like a user would.

Page layout (per the project brief): heading "Index History Data"; below it
"Select Indices:" dropdown, "From Date :" and "To Date :" inputs, a Search
button and a results table (S.N., Open, High, Low, Close, Change,
Per Change (%), Turnover, Date).

The scraper selects the index, enters the dates, presses Search, sets the table
page-length to its maximum and walks every result page. Working through the
real page (instead of guessing a private AJAX URL) keeps it valid if the site
changes its backend, and it handles the CSRF token / session automatically.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date

from . import config
from .browser import SET_VALUE_JS, save_debug
from .config import IndexSpec, norm_label
from .formatting import parse_date
from .storage import Record, record_from_cells

log = logging.getLogger(__name__)

EXPECTED_HEADERS = ["s.n.", "open", "high", "low", "close", "change", "per change", "turnover", "date"]


class ScrapeError(RuntimeError):
    pass


class IndexHistoryPage:
    def __init__(self, context):
        self.page = context.new_page()
        self._option_cache: dict[str, str] | None = None

    # ------------------------------------------------------------------ #
    def open(self) -> None:
        p = self.page
        p.goto(config.INDEX_HISTORY_URL, wait_until="domcontentloaded")
        try:
            p.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        if "index history data" not in p.content().lower():
            save_debug(p, "index_page_unexpected")
            raise ScrapeError("Page does not contain the 'Index History Data' heading "
                              "(blocked, or the site layout changed).")
        self._option_cache = None

    # ------------------------------------------------------------------ #
    def _index_options(self) -> dict[str, str]:
        """Return {normalised label: option value} of the 'Select Indices' dropdown."""
        if self._option_cache is not None:
            return self._option_cache
        selects = self.page.eval_on_selector_all(
            "select",
            "els => els.map((el, i) => ({i, id: el.id, name: el.name, "
            "options: Array.from(el.options).map(o => ({value: o.value, text: o.text.trim()}))}))")
        for s in selects:
            labels = {norm_label(o["text"]) for o in s["options"]}
            if "nepseindex" in labels:
                self._select_pos = s["i"]
                self._option_cache = {norm_label(o["text"]): o["value"] for o in s["options"] if o["value"] != ""}
                return self._option_cache
        raise ScrapeError("Could not find the 'Select Indices' dropdown (no <select> contains 'NEPSE Index').")

    def _index_select(self):
        self._index_options()
        return self.page.locator("select").nth(self._select_pos)

    def _date_inputs(self):
        """(from_input, to_input). Prefer id/name hints, fall back to the first two text inputs."""
        p = self.page
        sel = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=search])"
        inputs = p.eval_on_selector_all(
            sel, "els => els.map((el, i) => ({i, id: el.id, name: el.name, ph: el.placeholder || ''}))")
        frm = to = None
        for inp in inputs:
            hint = f"{inp['id']} {inp['name']} {inp['ph']}".lower()
            if frm is None and "from" in hint:
                frm = inp["i"]
            elif to is None and re.search(r"\bto\b|to[_-]?date|todate|_to|-to", hint):
                to = inp["i"]
        if frm is None or to is None:
            # DataTables adds its own search box; keep only inputs that look like dates.
            dateish = [i for i in inputs if "search" not in f"{i['id']} {i['name']}".lower()]
            if len(dateish) < 2:
                raise ScrapeError("Could not locate the 'From Date' / 'To Date' inputs.")
            frm, to = dateish[0]["i"], dateish[1]["i"]
        loc = p.locator(sel)
        return loc.nth(frm), loc.nth(to)

    def _search_button(self):
        p = self.page
        btn = p.get_by_role("button", name=re.compile(r"^\s*search\s*$", re.I))
        if btn.count():
            return btn.first
        alt = p.locator("input[type=submit], input[type=button][value*=earch], button:has-text('Search'), #btn_search")
        if alt.count():
            return alt.first
        raise ScrapeError("Could not locate the Search button.")

    # ------------------------------------------------------------------ #
    def _table(self):
        t = self.page.locator("table:has(th:has-text('Turnover'))")
        if not t.count():
            raise ScrapeError("Results table (with a 'Turnover' column) not found.")
        return t.first

    def _read_rows(self) -> list[list[str]]:
        rows = self._table().locator("tbody tr").evaluate_all(
            "trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))")
        return [r for r in rows if len(r) >= 9]

    def _headers(self) -> list[str]:
        return [h.lower() for h in self._table().locator("thead th").evaluate_all(
            "ths => ths.map(th => th.innerText.trim())")]

    def _info_total(self) -> int | None:
        txt = self.page.locator("[id$=_info]").first.inner_text() if self.page.locator("[id$=_info]").count() else ""
        m = re.search(r"of\s+([\d,]+)\s+entries", txt)
        return int(m.group(1).replace(",", "")) if m else None

    def _wait_results(self) -> None:
        p = self.page
        try:
            p.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        deadline = time.time() + 40
        while time.time() < deadline:
            busy = p.locator("[id$=_processing]:visible")
            if not busy.count():
                if self._read_rows() or "no data available" in p.content().lower() or "no matching" in p.content().lower():
                    return
            time.sleep(0.4)
        raise ScrapeError("Timed out waiting for the results table.")

    def _maximise_page_length(self) -> None:
        sel = self.page.locator("select[name$=_length]")
        if not sel.count():
            return
        values = sel.first.evaluate("el => Array.from(el.options).map(o => o.value)")
        nums = [int(v) for v in values if re.fullmatch(r"\d+", v)]
        best = "-1" if "-1" in values else (str(max(nums)) if nums else None)
        if best:
            sel.first.evaluate(SET_VALUE_JS, best)
            self._wait_results()

    def _go_next(self, first_before: list[str]) -> bool:
        nxt = self.page.locator("a.paginate_button.next, li.paginate_button.next a, .paginate_button.next")
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
            rows = self._read_rows()
            if rows and rows[0] != first_before:
                return True
            time.sleep(0.3)
        return False

    # ------------------------------------------------------------------ #
    def fetch(self, spec: IndexSpec, start: date, end: date) -> list[Record]:
        """Scrape every row for `spec` between start and end (inclusive)."""
        options = self._index_options()
        value = next((options[norm_label(l)] for l in spec.site_labels if norm_label(l) in options), None)
        if value is None:
            raise ScrapeError(f"Index '{spec.file_stem}' not in dropdown. Tried {spec.site_labels}; "
                              f"available: {sorted(options)}")
        self._index_select().evaluate(SET_VALUE_JS, value)
        frm, to = self._date_inputs()
        frm.evaluate(SET_VALUE_JS, start.isoformat())
        to.evaluate(SET_VALUE_JS, end.isoformat())
        self._search_button().click()
        self._wait_results()

        headers = self._headers()
        if headers and not (len(headers) >= 9 and headers[1].startswith("open") and headers[-1].startswith("date")):
            log.warning("Unexpected table headers %s - assuming standard column order", headers)

        self._maximise_page_length()
        total = self._info_total()
        seen: dict[date, Record] = {}
        page_no = 0
        while True:
            rows = self._read_rows()
            page_no += 1
            for cells in rows:
                try:
                    rec = record_from_cells(cells[:9])
                except ValueError:
                    continue  # "No data available" or malformed row
                seen[rec.day] = rec
            if not rows or not self._go_next(rows[0]):
                break
            if page_no > 2000:
                raise ScrapeError("Pagination runaway guard tripped.")
        if total is not None and total != len(seen):
            log.warning("%s: table says %s entries, parsed %s unique dates", spec.file_stem, total, len(seen))
        return sorted(seen.values(), key=lambda r: r.day, reverse=True)

    def close(self) -> None:
        self.page.close()
