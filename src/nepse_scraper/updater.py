"""Incremental update / backfill / local sync / status orchestration."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from pathlib import Path

from . import config
from .browser import open_browser, save_debug
from .calendar import load_holidays, trading_days_between
from .config import IndexSpec
from .sharesansar import IndexHistoryPage, ScrapeError
from .storage import last_date, merge, read_csv, write_csv

log = logging.getLogger(__name__)

OVERLAP_DAYS = 7   # re-read the last week so late corrections on the site are picked up
RETRIES = 3


def _csv_path(out_dir: Path, spec: IndexSpec) -> Path:
    return out_dir / f"{spec.file_stem}.csv"


def plan(out_dir: Path, specs: list[IndexSpec], force: bool, backfill: bool,
         today: date | None = None) -> dict[IndexSpec, date | None]:
    """Decide, per index, the start date to scrape (None = nothing to do).

    Holidays / weekends are skipped here: if no expected trading day lies after the
    last stored date, the site is not contacted at all.
    """
    holidays = load_holidays()
    cutoff = today or config.latest_expected_session()
    todo: dict[IndexSpec, date | None] = {}
    for spec in specs:
        last = last_date(_csv_path(out_dir, spec))
        if backfill or last is None:
            todo[spec] = config.HISTORY_START
            continue
        pending = trading_days_between(last + timedelta(days=1), cutoff, holidays)
        if pending or force:
            todo[spec] = last - timedelta(days=OVERLAP_DAYS - 1)
            if pending:
                log.info("%s: last=%s, expecting %d new trading day(s): %s",
                         spec.file_stem, last, len(pending), ", ".join(d.isoformat() for d in pending[:5]))
        else:
            log.info("%s: up to date (last=%s) - no trading day pending, skipping.", spec.file_stem, last)
            todo[spec] = None
    return todo


def run_update(out_dir: Path, specs: list[IndexSpec], force: bool = False,
               backfill: bool = False, headed: bool = False) -> int:
    todo = {s: d for s, d in plan(out_dir, specs, force, backfill).items() if d is not None}
    if not todo:
        log.info("Nothing to scrape today (holiday, weekend, or already up to date).")
        return 0

    end = config.now_npt().date()
    failures: list[str] = []
    with open_browser(headed) as ctx:
        page = IndexHistoryPage(ctx)
        page.open()
        for spec, start in todo.items():
            for attempt in range(1, RETRIES + 1):
                try:
                    rows = page.fetch(spec, start, end)
                    if not rows:
                        raise ScrapeError("site returned 0 rows")
                    path = _csv_path(out_dir, spec)
                    merged, added, updated = merge(read_csv(path), rows)
                    write_csv(path, merged)
                    log.info("%-27s +%d new, %d revised, %d total rows (latest %s)",
                             spec.file_stem, added, updated, len(merged), max(merged))
                    break
                except Exception as exc:
                    log.warning("%s attempt %d/%d failed: %s", spec.file_stem, attempt, RETRIES, exc)
                    if attempt == RETRIES:
                        save_debug(page.page, f"fail_{spec.file_stem}")
                        failures.append(spec.file_stem)
                    else:
                        time.sleep(5 * attempt)
                        try:
                            page.open()
                        except Exception as exc2:
                            log.warning("reload failed: %s", exc2)
        page.close()

    if failures:
        log.error("FAILED indices: %s", ", ".join(failures))
        return 1
    return 0


def run_sync(src: Path, dst: Path, specs: list[IndexSpec]) -> int:
    """Merge the repo's data into the local clone folder (never deletes local rows)."""
    dst.mkdir(parents=True, exist_ok=True)
    code = 0
    for spec in specs:
        s, d = _csv_path(src, spec), _csv_path(dst, spec)
        if not s.exists():
            log.warning("%s: no source file %s", spec.file_stem, s)
            code = 1
            continue
        src_rows = read_csv(s)
        merged, added, updated = merge(read_csv(d), list(src_rows.values()))
        if added or updated or not d.exists():
            write_csv(d, merged)
        log.info("%-27s synced: +%d new, %d revised -> %s", spec.file_stem, added, updated, d)
    return code | sync_snapshots(src, dst)


def sync_snapshots(src: Path, dst: Path) -> int:
    """Snapshot files (Promoter Lock In, Merger and Acquisition) are full copies: replace when different."""
    for name in config.SNAPSHOT_FILES:
        s, d = src / name, dst / name
        if not s.exists():
            log.info("%s: not in repo yet - skipped.", name)
            continue
        if d.exists() and d.read_bytes() == s.read_bytes():
            log.info("%-27s already up to date", name)
            continue
        dst.mkdir(parents=True, exist_ok=True)
        tmp = d.with_suffix(".csv.tmp")
        tmp.write_bytes(s.read_bytes())
        tmp.replace(d)
        log.info("%-27s copied -> %s", name, d)
    return 0


sync_lockin = sync_snapshots   # backwards-compatible name


def run_status(out_dir: Path, specs: list[IndexSpec]) -> int:
    holidays = load_holidays()
    cutoff = config.latest_expected_session()
    print(f"Data folder : {out_dir}")
    print(f"Holidays    : {len(holidays)} dates in archive")
    print(f"Expected through {cutoff} (NPT)\n")
    print(f"{'Index':<28}{'Rows':>7}  {'Latest':<12}Pending trading days")
    for spec in specs:
        rows = read_csv(_csv_path(out_dir, spec))
        if not rows:
            print(f"{spec.file_stem:<28}{0:>7}  {'-':<12}(file missing - run backfill)")
            continue
        latest = max(rows)
        pending = trading_days_between(latest + timedelta(days=1), cutoff, holidays)
        print(f"{spec.file_stem:<28}{len(rows):>7}  {latest.isoformat():<12}"
              f"{', '.join(d.isoformat() for d in pending) or 'none'}")
    return 0
