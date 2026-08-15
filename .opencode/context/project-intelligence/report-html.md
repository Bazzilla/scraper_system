<!-- Context: project-intelligence/report-html | Priority: high | Version: 1.0 | Updated: 2026-08-12 -->

# Report HTML (Market Dashboard)

**Purpose**: Pattern del generatore di pagina HTML statica di scraper-system — come il segnale di trading viene sintetizzato dagli indicatori e dal clima di mercato. Deep dive del technical-domain.md.
**Last Updated**: 2026-08-12

## Quick Reference
**Update Triggers**: Nuovi moduli scraper (aggiornare render) | Modifiche alla strategia di trading | Nuovi indicatori nel segnale
**Audience**: Sviluppatori, agenti AI

## Concept
`src/report_html.py` legge `output/output.json` e genera `output/report.html` (pagina self-contained, dark+light toggle, semafori, tabelle per categoria, legenda interattiva, guida operativa). Funzioni pure per ogni sezione. CLI: `render(config_path)`.

## Segnale COMPRA / WATCHLIST / ATTENDI (compute_signal)
`compute_signal(entry, regime)` fa scoring ±1 per indicatore. Classe: `score>=2` → buy, `score<=-2` → watchlist (mai sell da tecnici), altrimenti hold. Gate: in greed (FGI≥55) nessun buy.
```python
def compute_signal(entry, regime="neutral"):
    # +1/-1: RSI<30/>70, MFI<20/>80, prezzo vs SMA50/200, drawdown>=−5/<-15
    if score >= 2: signal = "buy"
    elif score <= -2: signal = "watchlist"   # debolezza = profilo buy-the-dip, MAI sell
    else: signal = "hold"
    if regime == "greed" and signal == "buy":
        return "hold"                        # non inseguire mercato caldo
    return signal
```
Badge: 🟢 COMPRA / 🟠 WATCHLIST / ⚪ ATTENDI.

## Regole chiave del segnale (allineate alla strategia buy-the-dip)
- **Mai sell dai dati tecnici**: vendere richiede trigger di uscita (take-profit +15/20%, deterioramento fondamentale, time-stop 18 mesi) non calcolabili dal dashboard — vedi Regola 4 in `strategia_trading.md`.
- **Debolezza tecnica = WATCHLIST**: prezzo sotto SMA50/200 + drawdown profondo è il profilo buy-the-dip (calo ≥10%), NON un segnale di vendita — vedi Regola 2.
- **Gate FGI**: in greed (FGI ≥ 55) nessun COMPRA (Regola 0: "i cali potrebbero essere trappole"); il clima deve puntare nella stessa direzione del titolo.

## Semafori per metrica
| Metrica | Soglie | Classe |
|---------|--------|--------|
| RSI | >70 / <30 | overbought / oversold |
| MFI | >80 / <20 | overbought / oversold |
| Drawdown | >=-5 / -5..-15 / <-15 | ok / warning / critical |
| Stale | fresh / stale | verde / rosso |

Ogni cella mostra **sempre il valore numerico** + badge colorato. Valori None → "—". Date italiane (hardcoded, indipendenti dal locale).

## Legenda e guida
- **Legenda indicatori**: card espandibili (`<details>/<summary>` nativo, toggle per-riga) con spiegazione in italiano di ogni indicatore (mercato: FGI/VIX/AAII; azionari: RSI/MFI/OBV/SMA/drawdown/Segnale; semafori).
- **Guida operativa**: quando comprare (convergenza ipervenduto+inversione+clima fear), quando vendere se in profitto (ipercomprato/indebolimento+clima greed), cautela su segnali misti. Disclaimer.

## 📂 Codebase References
**Report HTML**: `src/report_html.py` — `render(config_path)`, `build_page`, `compute_signal(entry, regime)`, `market_regime(fgi_score)`, `render_legend`, `render_market_cards`, `render_ticker_table`, `semaphore_class`, `format_iso_dt`
**Test**: `src/tests/test_report_html.py` — 35 test (semafori, format, segnale, gate, legenda, render)
**Output**: `output/report.html` (pagina generata), `output/output.json` (fonte)
**Spec**: `docs/superpowers/specs/2026-08-12-report-html-design.md`
**Strategia**: `../Temp/strategia_trading/strategia_trading.md` + `specifiche_strategia.md`

## Related Files
- technical-domain.md (spina dorsale: stack, standard, security)
- scraping-patterns.md (pattern dei moduli scraper)
