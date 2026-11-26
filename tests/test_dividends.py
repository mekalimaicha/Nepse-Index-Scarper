import shutil
from pathlib import Path

import pytest

from nepse_scraper import config, dividends as dv, updater

SEED = config.REPO_FUNDAMENTAL_DIR / config.DIVIDEND_FILE
MOCK = Path(__file__).with_name("mock_dividend.html")


def test_site_value_parsing():
    assert dv.parse_pct("1,540.00%") == 1540.0
    assert dv.parse_pct("—") is None and dv.parse_pct("") is None
    assert str(dv.parse_site_date("2 Nov 2026")) == "2026-11-02"
    assert dv.parse_site_date("—") is None
    assert dv.normalize_fy("FY 2082/83") == "2082/2083" and dv.normalize_fy("2077/2078") == "2077/2078"
    assert dv.clean_book_close("2026-08-16\n[Closed]") == "2026-08-16 [Closed]" and dv.clean_book_close("—") == ""
    r = dv.make_incoming("UNL", "Unilever", "1,540.00%", "—", "1,540.00%", "2 Nov 2026", "—", "FY 2082/83")
    assert r["Cash (%)"] == "1,540.00" and r["Bonus (%)"] == "" and r["Announcement Date"] == "11/2/2026"


def _row(sym, fy, bonus="", cash="", total="", ann="", book="", dist="", listing=""):
    return {"SYMBOL": sym, "Company": sym + " Ltd", "Bonus (%)": bonus, "Cash (%)": cash, "Total (%)": total,
            "Announcement Date": ann, "Book Closure Date": book, "Distribution Date": dist,
            "Bonus Listing Date": listing, "Fiscal Year": fy}


def test_merge_rules():
    existing = [_row("AAA", "2081/2082", "5", "0.2632", "5.2632", "9/1/2025", dist="10/1/2025", listing="11/1/2025"),
                _row("OLD", "2080/2081", cash="3", total="3", ann="1/1/2025")]
    incoming = [
        _row("AAA", "2081/2082", "5", "0.26", "5.26", "9/1/2025", "2025-10-01 [Closed]"),   # same at 2dp -> keep precision
        _row("BBB", "2081/2082", cash="7", total="7", ann="9/2/2025"),                     # new
        _row("AAA", "2081/2082", "0", "9", "9", "12/1/2025"),                              # re-announcement -> new row
    ]
    rows, added, updated = dv.merge(existing, incoming)
    assert (added, updated) == (2, 1)
    aaa = [r for r in rows if r["SYMBOL"] == "AAA"]
    first = next(r for r in aaa if r["Announcement Date"] == "9/1/2025")
    assert first["Cash (%)"] == "0.2632" and first["Total (%)"] == "5.2632"      # precision kept
    assert first["Book Closure Date"] == "2025-10-01 [Closed]"                    # updated from site
    assert first["Distribution Date"] == "10/1/2025" and first["Bonus Listing Date"] == "11/1/2025"  # manual kept
    assert any(r["SYMBOL"] == "OLD" for r in rows)                                # never deleted
    assert len(aaa) == 2
    fys = [r["Fiscal Year"] for r in rows]
    assert fys == sorted(fys, reverse=True)
    # merging the same data again changes nothing
    again, a2, u2 = dv.merge(rows, incoming)
    assert (a2, u2) == (0, 0) and again == rows


@pytest.mark.skipif(not SEED.exists(), reason="seed missing")
def test_seed_roundtrip_is_byte_identical():
    rows = dv.read_rows(SEED)
    assert len(rows) == 951
    assert dv.render(dv.sort_rows(rows)) == SEED.read_bytes()


def test_local_sync_keeps_manual_data_and_makes_backup(tmp_path):
    repo, local = tmp_path / "repo", tmp_path / "local"
    repo.mkdir(), local.mkdir()
    dv.write_if_changed(repo / config.DIVIDEND_FILE, [
        _row("AAA", "2081/2082", "5", "0.26", "5.26", "9/1/2025", "2025-10-01 [Closed]"),
        _row("NEW", "2082/2083", cash="4", total="4", ann="1/1/2026")])
    dv.write_if_changed(local / config.DIVIDEND_FILE, [
        _row("AAA", "2081/2082", "5", "0.2632", "5.2632", "9/1/2025", dist="10/1/2025", listing="11/1/2025"),
        _row("LOCALONLY", "2077/2078", cash="1", total="1")])
    before = (local / config.DIVIDEND_FILE).read_bytes()
    assert updater.sync_dividend(repo, local) == 0
    rows = dv.read_rows(local / config.DIVIDEND_FILE)
    syms = {r["SYMBOL"]: r for r in rows}
    assert set(syms) == {"AAA", "NEW", "LOCALONLY"}
    assert syms["AAA"]["Distribution Date"] == "10/1/2025" and syms["AAA"]["Cash (%)"] == "0.2632"
    assert (local / "Dividend History.original.bak").read_bytes() == before
    assert updater.sync_dividend(repo, local) == 0            # second run: nothing to do
    assert (local / "Dividend History.original.bak").read_bytes() == before


def test_local_sync_refuses_foreign_file(tmp_path):
    repo, local = tmp_path / "repo", tmp_path / "local"
    repo.mkdir(), local.mkdir()
    dv.write_if_changed(repo / config.DIVIDEND_FILE, [_row("AAA", "2081/2082", cash="1", total="1")])
    (local / config.DIVIDEND_FILE).write_text("Some,Other,Header\r\n1,2,3\r\n", encoding="utf-8")
    assert updater.sync_dividend(repo, local) == 1
    assert (local / config.DIVIDEND_FILE).read_text(encoding="utf-8").startswith("Some,Other")


@pytest.mark.skipif(not SEED.exists() or not MOCK.exists(), reason="fixtures missing")
def test_scrape_mock_page_end_to_end(tmp_path):
    pytest.importorskip("playwright")
    from nepse_scraper import hamroshare
    out = tmp_path / "out"
    out.mkdir()
    shutil.copy(SEED, out / config.DIVIDEND_FILE)
    try:
        code = hamroshare.run(out, url=MOCK.resolve().as_uri())
    except Exception as exc:                                   # browser not installed in this environment
        pytest.skip(f"browser unavailable: {exc}")
    assert code == 0
    all_rows = dv.read_rows(out / config.DIVIDEND_FILE)
    assert len(all_rows) == 954                                           # 951 + 3 new, nothing lost
    rows = {(r["SYMBOL"], r["Fiscal Year"]): r for r in all_rows}
    assert rows[("NORVIC", "2082/2083")]["Cash (%)"] == "22.105"          # precision preserved
    assert rows[("BHDC", "2082/2083")]["Cash (%)"] == "0.3"               # revised by site
    assert rows[("UNL", "2082/2083")]["Cash (%)"] == "1,540.00"           # new row
    assert hamroshare.run(out, url=MOCK.resolve().as_uri()) == 0          # idempotent
