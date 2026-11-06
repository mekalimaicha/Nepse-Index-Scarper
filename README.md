# NEPSE Index Scraper

Scrapes the NEPSE index and all sub-indices from
<https://www.sharesansar.com/index-history-data> into CSV files, and keeps a
clone of them in `F:\MEGA\NEPSE Analysis\NEPSE Index Data`.

* **14 CSV files** with the same names and column layout you supplied
  (`NEPSE.csv`, `Banking.csv`, `Dev Bank.csv`, `Hotel and Tourism.csv`, ...).
* **History from 1997-07-20**, then one new row per trading day.
* **Holidays skipped.** Holiday history 2007-2027 is seeded from `Holidays List 2007-2027.csv` into `data/holidays/holidays.csv`.
  From **1 January 2027** an automatic check of <https://nepalstock.com/holiday-listing> (*Year in AD*, current year onward) runs on the 1st of every month and is merged into the archive.
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

## Promoter Lock In
`python -m nepse_scraper lockin` scrapes <https://www.sharesansar.com/promoter-lockin> (sector ALL, both the
**Locked** and **Unlocked** tabs, every page) into **`Promoter Lock In.csv`**, stored next to the index CSVs
and copied to `F:\MEGA\NEPSE Analysis\NEPSE Index Data` by the same local sync.
Columns = `Status` (Locked/Unlocked) + the columns shown on the website. The file is a full snapshot replaced on
each run; an empty result, or one with under half the stored rows, never overwrites it. It runs after the index update in the
daily GitHub job (a lock-in failure does not stop the index update, and vice versa).

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

### 2. Automatic pull to your laptop (F: drive)
Everything lives on F: - nothing is kept in `C:\Users\...`:

| What | Where |
|---|---|
| CSV data (same file names) | `F:\MEGA\NEPSE Analysis\NEPSE Index Data` |
| Code + git clone + logs | `F:\MEGA\NEPSE Analysis\NEPSE Index Scraper` |

```powershell
cd "F:\MEGA\NEPSE Analysis\NEPSE Index Scraper\scripts\windows"
powershell -ExecutionPolicy Bypass -File .\setup_local.ps1 -RepoUrl https://github.com/<user>/<repo>.git
```
Runs at every Windows login, Mon-Fri 17:00, **and a silent check every 5 minutes** (so data from a manual workflow run reaches F: within about 5 minutes; the check is a cheap `git fetch` and only syncs when GitHub has something new; the laptop must be on): `git pull`, then new rows are merged into your CSVs by date
(local rows are never deleted). Check: `Get-Content "F:\MEGA\NEPSE Analysis\NEPSE Index Scraper\logs\local_sync.log" -Tail 20`.
Tip: exclude the `NEPSE Index Scraper` folder from MEGA sync (it contains `.venv` and `.git`).

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
