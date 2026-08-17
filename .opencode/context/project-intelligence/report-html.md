<!-- Context: project-intelligence/report-html | Priority: high | Version: 1.2 | Updated: 2026-08-17 -->

# Report HTML (Market Dashboard)

**Purpose**: Pattern del generatore di pagina HTML statica di scraper-system — come il segnale di trading viene sintetizzato dagli indicatori e dal clima di mercato. Deep dive del technical-domain.md.
**Last Updated**: 2026-08-12

## Quick Reference
**Update Triggers**: Nuovi moduli scraper (aggiornare render) | Modifiche alla strategia di trading | Nuovi indicatori nel segnale
**Audience**: Sviluppatori, agenti AI

## Concept
`src/report_html.py` (orchestratore) legge `output/output.json` e genera `output/report.html` (pagina self-contained, dark+light toggle, semafori, tabelle per categoria, legenda interattiva, guida operativa). Funzioni pure per ogni sezione, distribuite in `report_helpers.py`/`report_cards.py`/`report_tables.py`/`report_legend.py` e ri-esportate da `report_html.py`. CLI: `render(config_path)`.

**Card FGI**: può includere una mini-griglia dei 7 sub-indicatori da `fgi.fgi_components` (score + rating per componente, badge via `_fgi_rating_badge`). `fgi_components` è DISPLAY-ONLY: non entra mai nello score di segnale.

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
- **Mai sell dai dati tecnici**: vendere richiede trigger di uscita (take-profit +15/20%, deterioramento fondamentale, time-stop 18 mesi) non calcolabili dal dashboard — vedi Regola 4 in `docs/strategy/strategia_trading.md`.
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
**Report HTML**: `src/report_html.py` (orchestratore, ri-esporta) — `render(config_path)`, `build_page`; moduli: `report_helpers.py` (`compute_signal`, `market_regime`, `semaphore_class`, `format_iso_dt`, badge), `report_cards.py` (`render_market_cards`), `report_tables.py` (`render_ticker_table`, `render_indicator_matrix`, `render_stale_summary`), `report_legend.py` (`render_legend`)
**Test**: `src/tests/test_report_html.py` — test (semafori, format, segnale, gate, legenda, render)
**Output**: `output/report.html` (pagina generata), `output/output.json` (fonte)
**Spec**: `docs/superpowers/specs/2026-08-12-report-html-design.md`
**Strategia**: `docs/strategy/strategia_trading.md` + `specifiche_strategia.md`

## Related Files
- technical-domain.md (spina dorsale: stack, standard, security)
- scraping-patterns.md (pattern dei moduli scraper)
