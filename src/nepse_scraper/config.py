"""Central configuration: indices, URLs, paths and trading-week rules."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
INDEX_HISTORY_URL = "https://www.sharesansar.com/index-history-data"
HOLIDAY_URL = "https://nepalstock.com/holiday-listing"

# First date available on the site ("From Date" default).
HISTORY_START = date(1997, 7, 20)

# --------------------------------------------------------------------------- #
# Time zone (Nepal has no DST, so a fixed offset is exact)
# --------------------------------------------------------------------------- #
NPT = timezone(timedelta(hours=5, minutes=45), name="NPT")
# Market closes 15:00 NPT; allow time for the site to publish end-of-day data.
PUBLISH_AFTER = time(15, 30)


def now_npt() -> datetime:
    return datetime.now(NPT)


def latest_expected_session(now: datetime | None = None) -> date:
    """Latest calendar date for which end-of-day data should already be online."""
    now = now or now_npt()
    return now.date() if now.timetz().replace(tzinfo=None) >= PUBLISH_AFTER else now.date() - timedelta(days=1)


# --------------------------------------------------------------------------- #
# Trading week
# --------------------------------------------------------------------------- #
# Saturday has never been a trading day. Historically NEPSE traded Sun-Thu
# (a few early-year Fridays exist in the data). The last Sunday session in the
# data is 2026-04-05; from 2026-04-06 the exchange trades Monday-Friday.
MON_FRI_FROM = date(2026, 4, 6)


# --------------------------------------------------------------------------- #
# Indices
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IndexSpec:
    file_stem: str                 # local CSV name (without .csv) - matches the files you attached
    site_labels: tuple[str, ...]   # label(s) in the site's "Select Indices" dropdown
    enabled: bool = True


INDICES: tuple[IndexSpec, ...] = (
    IndexSpec("NEPSE", ("NEPSE Index",)),
    IndexSpec("Banking", ("Banking SubIndex", "Banking Index")),
    IndexSpec("Dev Bank", ("Development Bank Index",)),
    IndexSpec("Finance", ("Finance Index",)),
    IndexSpec("Hotel and Tourism", ("Hotels And Tourism", "Hotel And Tourism")),
    IndexSpec("Hydropower", ("HydroPower Index", "Hydropower Index")),
    IndexSpec("Investment", ("Investment", "Investment Index")),
    IndexSpec("Life Insurance", ("Life Insurance",)),
    IndexSpec("Manufacture and Processing", ("Manufacturing And Processing", "Manufacture And Processing")),
    IndexSpec("MicroFinance", ("Microfinance Index", "Micro Finance Index")),
    IndexSpec("Mutual Fund", ("Mutual Fund",)),
    IndexSpec("Non Life Insurance", ("Non Life Insurance",)),
    IndexSpec("Others", ("Others Index",)),
    IndexSpec("Trading", ("Trading Index",)),
    # Present in the site dropdown but not among your 14 files - off by default.
    # Set enabled=True to also clone them.
    IndexSpec("Float", ("Float Index",), enabled=False),
    IndexSpec("Sensitive", ("Sensitive Index",), enabled=False),
    IndexSpec("Sensitive Float", ("Sensitive Float Index",), enabled=False),
    IndexSpec("Insurance", ("Insurance",), enabled=False),
)


def norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def enabled_indices(names: list[str] | None = None) -> list[IndexSpec]:
    if not names:
        return [i for i in INDICES if i.enabled]
    wanted = {norm_label(n) for n in names}
    picked = [i for i in INDICES if norm_label(i.file_stem) in wanted]
    missing = wanted - {norm_label(i.file_stem) for i in picked}
    if missing:
        raise SystemExit(f"Unknown index name(s): {sorted(missing)}. "
                         f"Valid: {[i.file_stem for i in INDICES]}")
    return picked


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_DATA = REPO_ROOT / "data" / "indices"
HOLIDAY_DIR = REPO_ROOT / "data" / "holidays"
MANUAL_HOLIDAYS = REPO_ROOT / "config" / "holidays_manual.csv"
LOG_DIR = REPO_ROOT / "logs"

# Your local clone folder (Windows). Used by `sync` and as a documented default.
LOCAL_CLONE_DIR = r"F:\MEGA\NEPSE Analysis\NEPSE Index Data"


def resolve_out_dir(cli_value: str | None) -> Path:
    """--out beats $NEPSE_OUT_DIR beats the repo's data/indices folder."""
    value = cli_value or os.environ.get("NEPSE_OUT_DIR")
    return Path(value) if value else DEFAULT_REPO_DATA
