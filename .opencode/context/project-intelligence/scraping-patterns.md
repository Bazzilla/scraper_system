<!-- Context: project-intelligence/scraping-patterns | Priority: high | Version: 1.6 | Updated: 2026-08-17 -->

# Scraping Patterns

**Purpose**: Pattern concreti dei moduli scraper di scraper-system — come fetchare e parsare ogni fonte finanziaria. Deep dive del technical-domain.md.
**Last Updated**: 2026-08-14

## Quick Reference
**Update Triggers**: Nuovi moduli scraper | Cambio selettori/API fonte | Scope cambiato
**Audience**: Sviluppatori, agenti AI

## Scraper Module (run() -> dict)
Ogni modulo in `src/scrapers/` espone `run(config) -> dict`. Funzioni pure per il parse, DI per la rete.
```python
def run(config: dict) -> dict:
    data = fetch(config["url"], config.get("timeout", 15))
    parsed = parse(data)          # funzione pura
    return build_result(parsed, now_iso())  # formato file.json
```

## FGI: catena fallback a 3 sorgenti (API JSON CNN primaria)
La pagina CNN è una SPA JS — il valore NON è nell'HTML. Usare l'API JSON interna con header browser (User-Agent generico → HTTP 418). Il modulo prova 3 sorgenti in ordine (CNN → feargreedmeter → feargreedindex) con `fetch_first_success`; la sorgente vincente è registrata nel campo `source` dell'output. Ogni sorgente ha il suo parser (scelto da `try_parsers` in base al nome della sorgente vincente).
```python
sources = config.get("sources") or DEFAULT_SOURCES   # [{"name","url"}, ...]
body, source = fetch_first_success(session, [(s["name"], s["url"]) for s in sources],
                                   timeout, retries, backoff)
data, _ = try_parsers(body, [(source, parsers[source])])
result["source"] = source   # "cnn" | "feargreedmeter" | "feargreedindex"
```
Parser per sorgente:
- **cnn**: JSON `{"fear_and_greed": {"score": 0-100, "rating": "greed"}}`
- **feargreedmeter**: regex sul `<title>` → `Fear and Greed Index: N (Label)`
- **feargreedindex**: JSON API `{"value": 0-100, "label": "..."}`

## Fallback fonti generico (fetch_utils.py)
Helper condivisi in `src/fetch_utils.py` per i moduli la cui fonte primaria è instabile. Due funzioni composte tra loro:
- **`fetch_first_success(session, sources, timeout, retries, backoff)`** → prova la lista `[(name, url), ...]` in ordine, ritorna `(body, name)` della prima che risponde (con retry+backoff esponenziale per fonte). Se tutte falliscono → `RuntimeError` con l'elenco dei fallimenti loggato.
- **`try_parsers(body, parsers)`** → prova la lista `[(name, func), ...]` sullo stesso body, ritorna `(result, name)` della prima che parsa. Se tutte falliscono → `ValueError`. Cattura solo errori di parse prevedibili (`ValueError`, `KeyError`, `TypeError`).

Pattern d'uso — due varianti (NON combinarle in un unico modulo):
```python
# FGI: fallback multi-sorgente → la sorgente vinta è il "source"
body, source = fetch_first_success(session, source_list, timeout, retries, backoff)
data, _ = try_parsers(body, [(source, parsers[source])])   # parser unico per fonte
result["source"] = source

# AAII: più parser sulla stessa pagina → il parser vinto è il "source"
data, parser = try_parsers(html, [("data_chart", parse_data_chart),
                                  ("html_bars", parse_html_bars)])
result["source"] = parser
```
Regola: il `name` del vincitore (sorgente o parser) va SEMPRE registrato nel campo `source` dell'output — è ciò che il report HTML mostra nella card.

## VIX spot: CSV ufficiale CBOE (non vixcentral.com!)
VIX Central non è scrapabile (gate di sessione Flask → risponde "hello"). Usare il CSV ufficiale CBOE: ultima riga = ultimo close.
```python
url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
csv_text = requests.get(url, headers=headers, timeout=20).text
rows = list(csv.DictReader(io.StringIO(csv_text)))
latest = rows[-1]                       # DATE,OPEN,HIGH,LOW,CLOSE
vix_close = float(latest["CLOSE"])
```

## AAII: HTML statico con fallback (dataChart5 → HTML bars)
La pagina AAII è server-rendered. Dati in 3 punti ridondanti. Primario: regex `var dataChart5`; fallback: `div.weekending div.datebars` (primo blocco = settimana corrente). I due parser vengono provati con `try_parsers` e il vincitore è registrato nel campo `source` dell'output (`data_chart` | `html_bars`).
```python
m = re.search(r"var dataChart5\s*=\s*(\[.*?\]);", html, re.S)
if m:
    rows = json.loads(m.group(1)); current = rows[0]
else:  # fallback HTML bars
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one("div.weekending div.datebars")
    bullish  = float(block.select_one("div.bar.bullish").text.strip("%"))
    bearish  = float(block.select_one("div.bar.bearish").text.strip("%"))
    neutral  = float(block.select_one("div.bar.neutral").text.strip("%"))
```
Dettaglio completo: `aaii-scraping-guide.md`.

## OHLCV fetcher: yfinance con multi_level_index=False + request_delay
yfinance 1.5.2 restituisce colonne MultiIndex `(Price, Ticker)` anche per un singolo ticker → `multi_level_index=False` per colonne flat. Rate limiting con `request_delay` (secondi) tra i ticker (Yahoo → HTTP 429).
```python
df = yf.download(symbol, period=period, interval=interval, progress=False,
                 auto_adjust=True, multi_level_index=False, timeout=timeout)
# _fetch_all: time.sleep(request_delay) dopo ogni ticker
```

## Indicators: cache OHLCV → libreria ta
Legge `output/ohlcv_cache.json`, normalizza colonne a TitleCase, calcola con `ta`.
```python
frame = records_to_frame(records)  # rename open→Open, close→Close, ...
rsi  = RSIIndicator(close=frame["Close"], window=14).rsi()
mfi  = money_flow_index(frame["High"], frame["Low"], frame["Close"], frame["Volume"], window=14)
sma  = SMAIndicator(close=frame["Close"], window=200).sma_indicator()
```

## PCT SMA: breadth settoriale da OHLCV locale (non IndexIndicators!)
IndexIndicators espone solo PNG del grafico (non parsabile). Calcolare la
percentuale di ticker sopra SMA50/SMA200 dai dati OHLCV della cache locale.
Riusare `records_to_frame` da indicators.py + `ta.trend.SMAIndicator`.

## PCR: JSON escapato CBOE (non Barchart!)
Per il Put/Call Ratio usare CBOE daily market statistics: il dato è in un JSON
escapato dentro `__next_f.push`. Estrarre `EQUITY PUT/CALL RATIO`. (Barchart
risponde 200 solo con header browser; per l'NH-NL vedi sezione dedicata — per
il PCR resta fonte CBOE, ufficiale.)
```python
# NB: l'array "ratios" termina prima di "SUM OF ALL PRODUCTS" — NON usare `]\}`
# come ancora finale (cattura dati extra e rompe il JSON parse).
m = re.search(r'\\"ratios\\":\[(.*?)\],\\"SUM OF ALL PRODUCTS', html, re.S)
clean = m.group(1).replace('\\"', '"').replace('\\\\', '')
rows = json.loads(f'[{clean}]')
pcr = next((r["value"] for r in rows if r["name"] == "EQUITY PUT/CALL RATIO"), None)
```
**Fallback**: se il blocco `ratios` non matcha (o il JSON non parsa), usare la
regex diretta sull'entry escapata `\\"EQUITY PUT/CALL RATIO\\",\\"value\\":\\"([\d.]+)\\"`;
se nemmeno quella matcha → `ValueError` (pagina senza dati). Loggare sempre il
fallback per rendere visibile la drift della pagina.

## NH-NL: NYSE New Highs/New Lows da Barchart (browser headers!)
Barchart è scrapabile (verificato 2026-08-19) SOLO con header browser
(User-Agent Chrome + Referer `https://www.barchart.com/`), altrimenti WAF 404.
URL: `https://www.barchart.com/stocks/highs-lows/summary` — i dati sono
nell'**HTML statico**, tabella summary (Period, OVERALL, NYSE, NASDAQ, NYSE
Arca, ETFs, OTC-US).
```python
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
for row in rows:
    if "timeFrame" not in row:      # skippa duplicato MOBILE (senza anchor)
        continue
    tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
    period = re.sub(r'<[^>]+>', '', tds[0]).strip()          # es. "52-Week Highs"
    m = re.search(r'<a[^>]*>\s*(\d+)\s*</a>', tds[2])        # NYSE = 2ª colonna dati
```
Timestamp: `Last Updated: MM/DD/YYYY HH:MM ET` → `trade_date` ISO. **Caveat**:
la pagina contiene una **seconda copia mobile** della tabella senza anchor
`timeFrame` — il parser DEVE filtrarla (righe senza `timeFrame`).

## Insider: OpenInsider via HTTP (non HTTPS!)
OpenInsider risponde SOLO su HTTP (HTTPS: connessione rifiutata dal server).
La pagina `/latest-officer-purchases-25k` include anche CEO/CFO (colonna Title).
Filtrare `P - Purchase`, ultimi 30 giorni, bonus H5: +0.5 (≥2 acquisti, valore
>$100K), +1.0 (CEO/CFO), max +1.5.
Il parsing usa **BeautifulSoup**: le righe reali contengono `>` dentro l'attributo
`onmouseover` (ToolTip) e rompono qualsiasi regex basata su `>`/`<`.

## Config YAML (chi/quando/dove + output configurabile)
```yaml
output:
  json_path: output/output.json      # configurabile
  db_path: output/scraper_audit.db   # configurabile
scrapers:
  fgi:
    module: scrapers.fgi_scraper     # dove sta lo script
    output_key: fgi                  # chiave nel JSON
    schedule: daily                  # daily | weekly
    config:
      sources:                       # catena fallback (primo che risponde vince)
        - {name: cnn, url: "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"}
        - {name: feargreedmeter, url: "https://feargreedmeter.com/"}
        - {name: feargreedindex, url: "https://feargreedindex.net/api/fear-greed"}
      timeout: 15
      retries: 3
      backoff: 2.0
      headers: {User-Agent: "Mozilla/5.0 ..."}
  ohlcv:
    module: scrapers.ohlcv_fetcher
    output_key: ohlcv
    schedule: daily
    config: {cache_path: "output/ohlcv_cache.json", request_delay: 1.0, ...}
  indicators:
    module: scrapers.indicators
    output_key: indicators
    schedule: daily
    config: {cache_path: "output/ohlcv_cache.json", rsi_window: 14, ...}
```

## Config YAML: sezione `tickers` (opzionale, validata)
Sezione top-level che elenca i titoli per i moduli OHLCV/indicators, raggruppati per categoria. Validata da `_validate_tickers` in `config_loader.py` (opzionale, categorie non vuote, `symbol`+`name` stringhe, `symbol` univoco globale).
```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
  defense:
    - symbol: RTX
      name: RTX
```
> **⚠️ Manutenibilità**: i simboli YAML ambigui (`ON`, `YES`, `NO`, `TRUE`, `FALSE`) vanno **QUOTATI** nel config.yaml (`symbol: "ON"`), altrimenti YAML li interpreta come boolean. `ON` (ON Semiconductor) è già quotato in `config.yaml`.

L'orchestratore **inietta** `tickers` nel config passato a ogni scraper (retrocompatibile — i moduli che non li usano li ignorano).

## 📂 Codebase References
**Fetch Utils**: `src/fetch_utils.py` — fallback generico (`fetch_first_success` + `try_parsers`), usato da FGI e AAII; il vincitore è registrato in `source`
**Scraper FGI**: `src/scrapers/fgi_scraper.py` — catena 3 sorgenti (CNN → feargreedmeter → feargreedindex), header browser, retry
**Scraper AAII**: `src/scrapers/aaii_scraper.py` — `try_parsers` (dataChart5 → HTML bars), `source` = `data_chart` | `html_bars`
**Scraper VIX**: `src/scrapers/vix_scraper.py` — VIX spot da CSV CBOE (scope cambiato da term structure)
**Scraper OHLCV**: `src/scrapers/ohlcv_fetcher.py` — yfinance → cache su disco, multi_level_index=False, request_delay
**Scraper Indicators**: `src/scrapers/indicators.py` — legge cache, normalizza TitleCase, calcola con `ta`
**Scraper PCT SMA**: *(rimosso 2026-08-17)* — il proxy breadth settoriale su 29 ticker non esiste più; `% sopra SMA50/200` del mercato USA (F3/#13-14) si alimenta manualmente via `manual_overrides.yaml` (pct_sma50/pct_sma200, `manual_supported`)
**Scraper Insider**: `src/scrapers/insider_scraper.py` — bonus H5 da OpenInsider (HTTP, solo acquisti, BeautifulSoup)
**Moduli**: `src/config_loader.py` (validazione incl. `_validate_tickers`), `src/registry.py`
**Config**: `config.yaml` — chi/quando/dove + path output configurabili + sezione `tickers` + request_delay

## Related Files
- technical-domain.md (spina dorsale: stack, standard, security)
- aaii-scraping-guide.md (guida dettagliata pattern AAII)
- report-html.md (pattern report HTML + segnale)
