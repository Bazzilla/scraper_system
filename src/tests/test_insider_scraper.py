"""Unit tests for the insider scraper (pure functions, no network)."""

from __future__ import annotations

import unittest

from scrapers.insider_scraper import (
    build_result,
    compute_bonuses,
    filter_recent,
    parse_rows,
)

# HTML mock con la struttura REALE della tabella OpenInsider (tinytable, 17 celle/riga).
# Ordine colonne reale: X, Filing Date, Trade Date, Ticker, Company Name,
# Insider Name, Title, Trade Type, Price, Qty, Owned, DeltaOwn, Value, 1d, 1w, 1m, 6m.
# Il parsing usa: tds[2]=trade_date, tds[3]=ticker, tds[5]=insider,
# tds[6]=role, tds[7]=trade_type, tds[8]=price, tds[9]=qty, tds[12]=value.
# NOTA: l'attributo onmouseover contiene ">" (come nella pagina reale) —
# questo blocca la regressione verso un parsing regex che si romperebbe su
# quel carattere dentro l'attributo (motivo del rewrite a BeautifulSoup).
_HTML_SAMPLE = """
<table class="tinytable"><thead><tr>
<th><h3>X</h3></th><th><h3>Filing Date</h3></th><th><h3>Trade Date</h3></th>
<th><h3>Ticker</h3></th><th><h3>Company Name</h3></th><th><h3>Insider Name</h3></th>
<th><h3>Title</h3></th><th><h3>Trade Type</h3></th>
<th><h3>Price</h3></th><th><h3>Qty</h3></th><th><h3>Owned</h3></th><th><h3>DeltaOwn</h3></th>
<th><h3>Value</h3></th><th><h3>1d</h3></th><th><h3>1w</h3></th><th><h3>1m</h3></th><th><h3>6m</h3></th>
</tr></thead><tbody>
<tr><td>M</td><td><a href="http://sec.gov/form4.xml">2026-08-12 18:00:06</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/ACDC" onmouseover="Tip('<b>x</b>')">ACDC</a></b></td>
<td>ACDC Company</td>
<td><a href="/insider/Wilks-Matthew/1">Wilks Matthew</a></td>
<td>CEO</td><td>P - Purchase</td>
<td>$5.02</td><td>+80,000</td><td>2,290,224</td><td>+4%</td>
<td>+$401,851</td><td></td><td></td><td></td><td></td></tr>
<tr><td>M</td><td><a href="http://sec.gov/form4.xml">2026-08-12 17:08:22</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/MTDR" onmouseover="Tip('<b>x</b>')">MTDR</a></b></td>
<td>MTDR Company</td>
<td><a href="/insider/Elsener-William/2">Elsener William Thomas</a></td>
<td>EVP, Reservoir Engineering</td><td>P - Purchase</td>
<td>$50.94</td><td>+850</td><td>114,879</td><td>+1%</td>
<td>+$43,299</td><td></td><td></td><td></td><td></td></tr>
<tr><td>M</td><td><a href="http://sec.gov/form4.xml">2026-08-12 16:00:00</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/ACDC" onmouseover="Tip('<b>x</b>')">ACDC</a></b></td>
<td>ACDC Company</td>
<td><a href="/insider/Other/3">Other Person</a></td>
<td>Director</td><td>S - Sale</td>
<td>$6.00</td><td>+100</td><td>1,000</td><td>+1%</td>
<td>+$600</td><td></td><td></td><td></td><td></td></tr>
</tbody></table>
"""


class TestParseRows(unittest.TestCase):
    def test_parses_rows(self):
        rows = parse_rows(_HTML_SAMPLE)
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["ticker"], "ACDC")
        self.assertEqual(first["role"], "CEO")
        self.assertEqual(first["trade_type"], "P - Purchase")
        self.assertEqual(first["price"], 5.02)
        self.assertEqual(first["qty"], 80000)
        self.assertEqual(first["value"], 401851)
        self.assertEqual(first["trade_date"], "2026-08-10")

    def test_empty_html_returns_empty(self):
        self.assertEqual(parse_rows("<html></html>"), [])


class TestFilterRecent(unittest.TestCase):
    def test_keeps_only_purchases(self):
        rows = parse_rows(_HTML_SAMPLE)
        filtered = filter_recent(rows, days_back=30)
        # solo P - Purchase (2 righe), la S - Sale esclusa
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["trade_type"] == "P - Purchase" for r in filtered))


class TestComputeBonuses(unittest.TestCase):
    def test_officer_and_ceo_bonus(self):
        rows = parse_rows(_HTML_SAMPLE)
        tickers = {
            "semiconductors": [{"symbol": "ACDC", "name": "A"}],
            "defense": [{"symbol": "MTDR", "name": "M"}],
        }
        result = compute_bonuses(rows, tickers)
        # ACDC: 1 purchase (CEO) → ceo_cfo_bonus 1.0
        acdc = result["semiconductors"]["ACDC"]
        self.assertEqual(acdc["purchases_30d"], 1)
        self.assertTrue(acdc["ceo_cfo"])
        self.assertEqual(acdc["ceo_cfo_bonus"], 1.0)
        # MTDR: 1 purchase EVP < 2 → nessun officer bonus
        mtdr = result["defense"]["MTDR"]
        self.assertEqual(mtdr["purchases_30d"], 1)
        self.assertEqual(mtdr["officer_bonus"], 0.0)

    def test_officer_bonus_requires_two_purchases_and_value(self):
        rows = [
            {"ticker": "NVDA", "role": "VP", "trade_type": "P - Purchase",
             "value": 60000, "price": 100.0, "qty": 600, "trade_date": "2026-08-10"},
            {"ticker": "NVDA", "role": "VP", "trade_type": "P - Purchase",
             "value": 60000, "price": 100.0, "qty": 600, "trade_date": "2026-08-11"},
        ]
        tickers = {"semiconductors": [{"symbol": "NVDA", "name": "N"}]}
        result = compute_bonuses(rows, tickers)
        nvda = result["semiconductors"]["NVDA"]
        self.assertEqual(nvda["purchases_30d"], 2)
        self.assertEqual(nvda["total_value_30d"], 120000)
        # 2 acquisti + valore > 100K → officer bonus 0.5
        self.assertEqual(nvda["officer_bonus"], 0.5)


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        per_ticker = {
            "semiconductors": {"NVDA": {"purchases_30d": 2, "total_value_30d": 120000,
                                         "ceo_cfo": False, "officer_bonus": 0.5,
                                         "ceo_cfo_bonus": 0.0, "total_bonus": 0.5,
                                         "last_trade_date": "2026-08-11"}},
            "total": {"tickers_with_bonus": 1, "max_bonus": 0.5, "max_ticker": "NVDA"},
        }
        result = build_result(per_ticker, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["total"]["max_bonus"], 0.5)
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
