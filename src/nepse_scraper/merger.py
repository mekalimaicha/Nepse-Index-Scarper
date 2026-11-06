"""Scrape https://www.sharesansar.com/merger-acquisition (tabs: Completed, On Process).

Output: <out>/Merger and Acquisition.csv = "Status" (Completed / On Process) + the page's own columns.
Full snapshot, replaced on each run (same safety guards as the Promoter Lock In file).
The page has no sector filter or Search button, so none is used.
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .lockin import run_tabs

TABS = ("Completed", "On Process")
ANCHORS = {"Completed": "completed", "On Process": "onprocess"}


def run(out_dir: Path, headed: bool = False, url: str | None = None) -> int:
    return run_tabs(out_dir, config.MERGER_FILE, url or config.MERGER_URL, TABS, "Merger and Acquisition",
                    headed, expect="merger", anchors=ANCHORS, use_search=False)
