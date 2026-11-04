"""Playwright helpers shared by the index and holiday scrapers."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 nepse-index-scraper/1.0")


@contextmanager
def open_browser(headed: bool = False):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 1000})
        context.set_default_timeout(45_000)
        try:
            yield context
        finally:
            context.close()
            browser.close()


def save_debug(page, name: str) -> None:
    """Dump screenshot + HTML so a changed page layout can be diagnosed."""
    try:
        d = config.LOG_DIR / "debug"
        d.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        page.screenshot(path=str(d / f"{safe}.png"), full_page=True)
        (d / f"{safe}.html").write_text(page.content(), encoding="utf-8")
        log.warning("Debug files written to %s", Path(d) / safe)
    except Exception as exc:  # debugging must never mask the real error
        log.debug("could not save debug files: %s", exc)


# JS: set a form control's value and fire the events jQuery/select2/datepicker listen for.
SET_VALUE_JS = """
(el, value) => {
  el.value = value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  if (window.jQuery) { window.jQuery(el).trigger('change'); }
}
"""
