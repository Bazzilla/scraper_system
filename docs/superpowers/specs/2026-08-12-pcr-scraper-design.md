# Design: Modulo PCR scraper (Equity Put/Call Ratio)

**Data**: 2026-08-12
**Stato**: Approvato
**Scope**: Nuovo modulo scraper per il Put/Call Ratio, indicatore macro della strategia buy-the-dip

## Obiettivo

Creare `src/scrapers/pcr_scraper.py` che estrae l'**Equity Put/Call Ratio** dalla pagina
daily market statistics della CBOE e lo produce nel formato `file.json`. Il PCR è
l'indicatore supplementare #11 della strategia (`specifiche_strategia.md` F3): soglia
**PCR > 0.80 = segnale fear** (fonte originale Barchart, sostituita da CBOE ufficiale
perché Barchart non è scrapabile — 404 WAF).

## Fonte

- **URL**: `https://www.cboe.com/us/options/market_statistics/daily/`
- **Metodo**: GET con header browser (User-Agent, come fgi/vix)
- **Dato**: `EQUITY PUT/CALL RATIO` dal JSON embeddata (`optionsData.ratios[]`)
- **Lag**: 1 giorno di trading (la pagina espone `selectedDate` = giorno precedente)

## Parsing

La pagina contiene il JSON **escapato** in una stringa JS (`self.__next_f.push`).
Approccio robusto con due regex:

```python
# 1. Estrai il blocco ratios escapato
m = re.search(r'\\"optionsData\\":\{.*?\\"ratios\\":\[(.*?)\]\}', html, re.S)
# 2. De-escapare e parsare
clean = m.group(1).replace('\\"', '"').replace('\\\\', '')
rows = json.loads(f'[{clean}]')
pcr = next(r["value"] for r in rows if r["name"] == "EQUITY PUT/CALL RATIO")
```

- Regex principale: blocca `\\"optionsData\\":{...\\"ratios\\":[ ... ]}`
- De-escaping: `\\\"` → `"`, `\\` → `` (JSON embeddata in Next.js)
- Fallback: regex diretta su `EQUITY PUT/CALL RATIO` se il blocco non matcha

## Output (formato file.json)

```json
"pcr": {
  "equity_pcr": 0.63,
  "total_pcr": 0.81,
  "index_pcr": 0.90,
  "trade_date": "2026-08-11",
  "fetched_at": "...",
  "frequency": "daily",
  "stale_after_hours": 24,
  "status": "fresh"
}
```

- `equity_pcr`: il dato principale per la strategia
- `total_pcr` / `index_pcr`: valori aggiuntivi per contesto
- `trade_date`: `selectedDate` estratto dalla pagina (giorno dei dati)
- `fetched_at`/`frequency`/`stale_after_hours`/`status`: formato file.json

## Pattern del modulo

Segue il contratto `run(config) -> dict` di fgi/vix:
- `fetch_page(session, url, timeout) -> str` — DI per la rete
- `parse_ratios(html: str) -> dict` — **funzione pura** (testabile senza rete)
- `build_result(data, fetched_at) -> dict` — funzione pura
- `_fetch_with_retry(...)` — retry con backoff (pattern esistente)
- `run(config) -> dict` — entry point

## Config.yaml

```yaml
pcr:
  module: scrapers.pcr_scraper
  output_key: pcr
  schedule: daily
  config:
    url: "https://www.cboe.com/us/options/market_statistics/daily/"
    timeout: 20
    retries: 3
    backoff: 2.0
    headers:
      User-Agent: "Mozilla/5.0 ... Chrome/126.0"
      Accept: "text/html,application/xhtml+xml"
    stale_after_hours: 24
```

## Report HTML

- **Card macro**: nuova card "Put/Call Ratio" nel gruppo indicatori di mercato
  (valore equity_pcr + semaforo + trade_date)
- **Semaforo**: `equity_pcr >= 0.80` → classe `fear` (rosso/verde secondo convenzione
  strategia), `<= 0.70` → `greed`/ok, intermedio → neutral
- **Legenda**: voce "Put/Call Ratio" con spiegazione (PCR alto = paura/put dominanti,
  >0.80 = segnale fear per la strategia)
- **compute_signal NON cambia**: il PCR è conferma macro indipendente (F3), non entra
  nello scoring per-ticker

## Test

- **`parse_ratios`**: HTML mock con JSON escapato → estrae equity/total/index + trade_date;
  HTML senza il blocco → ValueError pulito; fallback regex
- **`build_result`**: formato file.json corretto
- **Orchestratore**: config valida con il nuovo modulo

## File

```
src/scrapers/pcr_scraper.py
src/tests/test_pcr_scraper.py
config.yaml (aggiunta sezione pcr)
src/report_html.py (card + legenda PCR)
src/tests/test_report_html.py (test card/legenda PCR)
```

## Fuori scope

- Modifiche a compute_signal (il PCR non entra nello scoring ticker)
- Indicatori supplementari #12-14 (NH-NL, % sopra SMA — moduli separati)
- Scheduler
