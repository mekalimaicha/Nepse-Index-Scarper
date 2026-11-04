# NEPSE Index Scraper

Scrapes the NEPSE index and all sub-indices from
<https://www.sharesansar.com/index-history-data> into CSV files, and keeps a
clone of them in `F:\MEGA\NEPSE Analysis\NEPSE Index Data`.

* **14 CSV files** with the same names and column layout you supplied
  (`NEPSE.csv`, `Banking.csv`, `Dev Bank.csv`, `Hotel and Tourism.csv`, ...).
* **History from 1997-07-20**, then one new row per trading day.
* **Holidays skipped.** Holiday dates come from <https://nepalstock.com/holiday-listing>
  (all years, *Year in AD*), are refreshed automatically once a month and archived in `data/holidays/`.
  If the only days since the last stored row are weekends/holidays, the site is not contacted at all.

## How the pieces fit

```
GitHub Actions (Mon-Fri 16:15 NPT)         GitHub Actions (1st of month)
   python -m nepse_scraper update             python -m nepse_scraper holidays
        -> commits data/indices/*.csv              -> commits data/holidays/*
                         \                        /
                          GitHub repo (source of truth)
                                    |
              git pull + python -m nepse_scraper sync   (Windows Task Scheduler, Mon-Fri 17:00)
                                    |
                F:\MEGA\NEPSE Analysis\NEPSE Index Data\*.csv   (merged, never loses local rows)
```

You can also skip GitHub and scrape straight into the F: folder (see "Run locally").

## Trading calendar

| Period | Trading days |
|---|---|
| to 2026-04-05 | Sunday-Thursday (inferred from the data; a handful of early Fridays exist) |
| from 2026-04-06 | Monday-Friday |
| always | Saturday never trades; dates in the holiday archive are skipped |

Change the switch date in `src/nepse_scraper/config.py` (`MON_FRI_FROM`) if the exchange changes its week again.
Add one-off closures by hand in `config/holidays_manual.csv` (`date,description`, ISO dates).

## Setup

### 1. Publish to GitHub
```bash
cd nepse-index-scraper
git init -b main
git add .
git commit -m "Initial NEPSE index scraper"
git remote add origin https://github.com/<you>/nepse-index-scraper.git
git push -u origin main
```
In the repo: **Settings -> Actions -> General -> Workflow permissions -> Read and write**.
Then **Actions -> Monthly holiday archive -> Run workflow** once (builds the holiday list), and
**Actions -> Daily index update -> Run workflow** to test.

### 2. Local clone on Windows
```powershell
git clone https://github.com/<you>/nepse-index-scraper.git
cd nepse-index-scraper
py -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m playwright install chromium   # only needed to scrape locally

.\scripts\windows\sync_local.ps1                      # first sync (merges into F:\MEGA\...)
.\scripts\windows\install_scheduled_task.ps1          # optional: Mon-Fri 17:00 auto-sync
```

### Run locally (no GitHub)
```powershell
setx NEPSE_OUT_DIR "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
python -m nepse_scraper holidays            # build the holiday archive
python -m nepse_scraper update              # append new trading days
python -m nepse_scraper update --force      # scrape even if nothing is due
python -m nepse_scraper update --indices NEPSE Banking
python -m nepse_scraper backfill            # re-download everything from 1997-07-20 and merge
python -m nepse_scraper status              # last date + pending trading days per file
```

## Behaviour details

* **Merge, never overwrite**: new rows are added by date; the last 7 days are re-read so corrections on the site
  are picked up. Untouched rows are written back byte-for-byte.
* **File format** matches your files: newest first, CRLF, `M/D/YYYY` dates, `1,234.50` number style.
  `S.N.` is renumbered 1..N on every write (your originals restart at 1 on page boundaries and have a few blanks).
* **Sub-indices not in your 14 files** (Float, Sensitive, Sensitive Float, Insurance) exist in the site dropdown;
  set `enabled=True` in `config.py` to clone them too.
* **Scraping method**: a headless Chromium (Playwright) drives the real page - selects the index, sets
  From/To dates, presses Search, sets the table to its largest page size and walks every page.
* **Failures**: each index retries 3 times; a failure in one index doesn't stop the others. The run exits non-zero
  and screenshots/HTML are written to `logs/debug/` (uploaded as a workflow artifact) to diagnose layout changes.

## Tests
```bash
pip install -e .[dev]
pytest
```
Tests cover number/date formatting (every original row is re-formatted and compared), the trading calendar,
holiday skipping, merge/write and the local sync.

## Layout
```
src/nepse_scraper/   config, formatting, storage, calendar, sharesansar (page driver), holidays, updater, cli
data/indices/        the 14 CSVs (seeded from your files, up to 2026-11-03)
data/holidays/       holidays.csv + archive/ monthly snapshots
.github/workflows/   daily-update.yml, monthly-holidays.yml
scripts/windows/     sync_local.ps1, install_scheduled_task.ps1
```

Data is scraped from third-party sites; check their terms of use and keep the schedule modest.
