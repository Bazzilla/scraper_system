<!-- Context: project-intelligence/report-html | Priority: high | Version: 1.3 | Updated: 2026-08-19 -->

# Report HTML (Market Dashboard)

**Purpose**: Pattern del generatore di pagina HTML statica di scraper-system — come il segnale di trading viene sintetizzato dagli indicatori e dal clima di mercato. Deep dive del technical-domain.md.
**Last Updated**: 2026-08-12

## Quick Reference
**Update Triggers**: Nuovi moduli scraper (aggiornare render) | Modifiche alla strategia di trading | Nuovi indicatori nel segnale
**Audience**: Sviluppatori, agenti AI

## Concept
`src/report_html.py` (orchestratore) legge `output/output.json` e genera `output/report.html` (pagina self-contained, dark+light toggle, semafori, tabelle per categoria, legenda interattiva, guida operativa). Funzioni pure per ogni sezione, distribuite in `report_helpers.py`/`report_cards.py`/`report_tables.py`/`report_legend.py` e ri-esportate da `report_html.py`. CLI: `render(config_path)`.

**Card FGI**: può includere una mini-griglia dei 7 sub-indicatori da `fgi.fgi_components` (score + rating per componente, badge via `_fgi_rating_badge`). `fgi_components` è DISPLAY-ONLY: non entra mai nello score di segnale.

## Segnale VALUTA INGRESSO / OSSERVA / ATTENDI (pipeline)
Pipeline a 3 stadi: `technical_signal(entry)` (valutazione tecnica locale: score≥2 bullish, ≤-2 weak, altrimenti neutral) → `buy_the_dip_gate(fgi_score)` (gate operativo: FGI None/stale/>40 → closed; 25<FGI≤40 → watch_only; 20<FGI≤25 → open; ≤20 → strong_open) → `final_action(technical, gate)` (buy/watchlist/hold). `compute_signal(entry, regime, proxy_accepted, fgi_score)` è wrapper compatibile che delega alla pipeline.
```python
def compute_signal(entry, regime="neutral", proxy_accepted=None, fgi_score=None):
    technical = technical_signal(entry)      # +1/-1: RSI<30/>70, MFI<20/>80, prezzo vs SMA50/200, drawdown>=−5/<-15
    if regime == "greed" and technical == "bullish":
        return "hold"                        # non inseguire mercato caldo (legacy)
    gate = buy_the_dip_gate(fgi_score)       # closed / watch_only / open / strong_open
    return final_action(technical, gate)     # buy / watchlist / hold
```
Badge (non-operativi, segnali da VALUTARE): 🟢 VALUTA INGRESSO / 🟠 OSSERVA / ⚪ ATTENDI.

## Regole chiave del segnale (allineate alla strategia buy-the-dip)
- **Mai sell dai dati tecnici**: vendere richiede trigger di uscita (take-profit +15/20%, deterioramento fondamentale, time-stop 18 mesi) non calcolabili dal dashboard — vedi Regola 4 in `docs/strategy/strategia_trading.md`.
- **Debolezza tecnica = OSSERVA**: prezzo sotto SMA50/200 + drawdown profondo è il profilo buy-the-dip (calo ≥10%), NON un segnale di vendita né di ingresso automatico — vedi Regola 2.
- **Gate FGI Buy-the-Dip**: VALUTA INGRESSO solo con FGI ≤ 25; 25 < FGI ≤ 40 → OSSERVA; FGI > 40 o mancante/stale → ATTENDI (fail-closed, nessun ingresso).

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
