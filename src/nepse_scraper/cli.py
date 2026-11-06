"""Command line: python -m nepse_scraper <update|backfill|holidays|sync|status>"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import config, holidays, lockin, updater


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nepse_scraper", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, out=True):
        sp.add_argument("--indices", nargs="*", metavar="NAME",
                        help="Only these indices (file names without .csv, e.g. NEPSE Banking). Default: all enabled.")
        sp.add_argument("--headed", action="store_true", help="Show the browser window (debugging).")
        if out:
            sp.add_argument("--out", metavar="DIR",
                            help="Folder holding the CSV files. Default: $NEPSE_OUT_DIR, else <repo>/data/indices.")

    u = sub.add_parser("update", help="Append new trading days (skips weekends/holidays; no web call if nothing is due).")
    common(u)
    u.add_argument("--force", action="store_true", help="Scrape even if no trading day is pending.")

    b = sub.add_parser("backfill", help=f"Re-download full history from {config.HISTORY_START} and merge.")
    common(b)

    lk = sub.add_parser("lockin", help="Scrape sharesansar.com/promoter-lockin into 'Promoter Lock In.csv'.")
    lk.add_argument("--headed", action="store_true")
    lk.add_argument("--out", metavar="DIR", help="Folder for the CSV (default: $NEPSE_OUT_DIR, else <repo>/data/indices).")
    lk.add_argument("--url", help=argparse.SUPPRESS)

    h = sub.add_parser("holidays", help="Scrape nepalstock.com holiday list (all years, AD) into the archive.")
    h.add_argument("--headed", action="store_true")

    s = sub.add_parser("sync", help="Merge repo data into the local clone folder.")
    s.add_argument("--src", metavar="DIR", help="Source folder (default: <repo>/data/indices).")
    s.add_argument("--dst", metavar="DIR", default=None,
                   help=f"Destination (default: $NEPSE_OUT_DIR, else {config.LOCAL_CLONE_DIR}).")
    s.add_argument("--indices", nargs="*", metavar="NAME")

    st = sub.add_parser("status", help="Show last stored date and pending trading days per index.")
    st.add_argument("--out", metavar="DIR")
    st.add_argument("--indices", nargs="*", metavar="NAME")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(config.LOG_DIR / "scraper.log", encoding="utf-8")])

    if args.cmd == "holidays":
        return holidays.run(args.headed)
    if args.cmd == "lockin":
        return lockin.run(config.resolve_out_dir(args.out), args.headed, args.url)

    specs = config.enabled_indices(getattr(args, "indices", None))
    if args.cmd == "sync":
        src = Path(args.src) if args.src else config.DEFAULT_REPO_DATA
        dst = Path(args.dst or os.environ.get("NEPSE_OUT_DIR") or config.LOCAL_CLONE_DIR)
        return updater.run_sync(src, dst, specs)

    out = config.resolve_out_dir(args.out)
    if args.cmd == "status":
        return updater.run_status(out, specs)
    return updater.run_update(out, specs, force=getattr(args, "force", False),
                              backfill=args.cmd == "backfill", headed=args.headed)


if __name__ == "__main__":
    sys.exit(main())
