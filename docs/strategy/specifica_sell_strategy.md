# Specifica Strategia SELL — Portfolio Management

**Data creazione**: 27 Agosto 2026
**Scopo**: Definire la logica SELL per gestire posizioni aperte dopo un ingresso Buy-the-Dip. Questa strategia è **separata e indipendente** dalla strategia BUY.

**Config file**: `config/sell_rules.yaml` — tutti i valori soglia vivono lì, non nel codice.

---

## A) FILOSOFIA

| # | Specifica |
|---|---|
| S-A1 | La strategia SELL risponde a: "come gestire posizioni già aperte?" |
| S-A2 | La strategia BUY risponde a: "devo valutare un nuovo ingresso?" |
| S-A3 | Le due logiche **non si modificano** a vicenda |
| S-A4 | Il sistema **non emette ordini operativi vincolanti** — solo indicazioni informative |
| S-A5 | Obiettivo: prendere profitto gradualmente quando il rimbalzo matura, senza vendere tutto a una soglia fissa |

---

## B) STATI SELL

Lo stato SELL è un'etichetta informativa assegnata a ogni posizione aperta.

| Stato | Significato |
|-------|-------------|
| `MANTIENI` | La posizione è sana, il trend è favorevole, non serve agire |
| `PRENDI PROFITTO PARZIALE` | Il gain ha raggiunto una soglia significativa, valutare realizzo parziale |
| `RIDUCI ESPOSIZIONE` | Gain elevato + surriscaldamento multiplo, riduzione più aggressiva |
| `ATTENZIONE` | Posizione in perdita o gain ridotto con indicatori in deterioramento |
| `NESSUNA POSIZIONE` | Il ticker non ha posizioni aperte (gestito dalla BUY strategy) |

---

## C) REGOLE SELL

### C1 — Nessuna posizione

```text
Se quantity_current <= 0:
    stato = NESSUNA POSIZIONE
    (questo ticker è gestito dalla BUY strategy)
```

### C2 — Mantieni (HOLD)

```text
Se unrealized_gain_pct < 15%
E nessun deterioramento tecnico forte:
    stato = MANTIENI
```

Condizioni favorevoli (tutte o quasi presenti):

- prezzo sopra SMA50
- prezzo sopra SMA200
- RSI non estremo (30-65)
- MFI non estremo (20-75)
- OBV stabile o crescente
- FGI non in Extreme Greed (>= 75)

### C3 — Take Profit parziale base (TP1)

```text
Se unrealized_gain_pct >= +15%:
    stato = PRENDI PROFITTO PARZIALE
    confidence = base
```

Interpretazione:

- valutare realizzo di circa 25-33% della posizione
- mettere in sicurezza parte del guadagno
- non vendere necessariamente tutto

### C4 — Take Profit parziale rafforzato (TP2)

```text
Se unrealized_gain_pct >= +25%:
    stato = PRENDI PROFITTO PARZIALE
    confidence = rafforzato
```

Interpretazione:

- il rimbalzo Buy-the-Dip ha prodotto un recupero significativo
- valutare ulteriore realizzo di circa 25-33%
- il gain è maturo per una presa di profitto

### C5 — Riduci esposizione (TP3)

```text
Se unrealized_gain_pct >= +30%
E almeno 2 delle seguenti condizioni sono vere:
    FGI >= 60
    RSI >= 70
    MFI >= 80
    prezzo > SMA50 * 1.10 (sopra SMA50 del 10%+)
    OBV in deterioramento (non conferma il rialzo)
    upside_pct residuo <= 5% (se disponibile)
    stato = RIDUCI ESPOSIZIONE
    confidence = alta
```

Interpretazione:

- il titolo è surriscaldato su più fronti
- valutare riduzione dell'40-50% della posizione
- il rischio di ritracciamento è elevato

### C6 — Attenzione

```text
Se unrealized_gain_pct <= 0
E almeno 2 delle seguenti condizioni tecniche sono negative:
    prezzo sotto SMA50
    prezzo sotto SMA200
    RSI < 45
    MFI < 40
    OBV in deterioramento
    stato = ATTENZIONE
    confidence = media
```

Interpretazione:

- la posizione è in perdita o in gain trascurabile
- gli indicatori tecnici stanno peggiorando
- **non generare automaticamente un'uscita**
- solo: monitorare attentamente, valutare se il deterioramento è temporaneo o strutturale

---

## D) SEGNALI DI SURRISCALDAMENTO

I segnali di surriscaldamento sono usati dalla regola C5 (RIDUCI ESPOSIZIONE).

| # | Segnale | Soglia | Fonte dati |
|---|---------|--------|------------|
| H1 | FGI in Greed/Extreme Greed | >= 60 | output.json → fgi |
| H2 | RSI ipercomprato | >= 70 | output.json → indicators |
| H3 | MFI ipercomprato | >= 80 | output.json → indicators |
| H4 | Prezzo distaccato da SMA50 | > SMA50 * 1.10 | output.json → indicators |
| H5 | OBV non conferma il rialzo | OBV in calo mentre prezzo sale | output.json → indicators |
| H6 | Upside residuo basso | <= 5% | output.json → valuation (opzionale) |

Con:

- **3+ segnali attivi** → surriscaldamento alto
- **2 segnali attivi** → surriscaldamento medio (soglia minima per RIDUCI ESPOSIZIONE)
- **0-1 segnali attivi** → nessun surriscaldamento

---

## E) FAIR VALUE NELLA STRATEGIA SELL

Il fair value (valuation) ha un ruolo **secondario e puramente informativo**.

| Regola | Comportamento |
|--------|---------------|
| Fair value mancante/stale | Nessun impatto, nessun blocco |
| Fair value da solo | **Mai** genera un segnale SELL autonomamente |
| Fair value + gain elevato + overheat | Rafforza il segnale esistente (es. PRENDI PROFITTO PARZIALE → rafforzato) |

Esempio di contributo:

```text
unrealized_gain_pct >= 25%
upside_pct <= 5%
RSI >= 70
→ rafforza PRENDI PROFITTO PARZIALE
```

---

## F) INTERAZIONE CON LA STRATEGIA BUY

| Regola | Comportamento |
|--------|---------------|
| Ticker senza posizione aperta | Usare logica BUY (VALUTA INGRESSO / OSSERVA / ATTENDI) |
| Ticker con posizione aperta | Usare logica SELL (MANTIENI / PRENDI PROFITTO / ...) |
| La SELL non modifica | Gli stati BUY (VALUTA INGRESSO / OSSERVA / ATTENDI) restano invariati |
| Report principale | Può mostrare nota "ticker in portafoglio" ma non è obbligatorio |
| Pagina portfolio | Mostra SELL signal solo per ticker detenuti |

---

## G) FAIL-SAFE

| Scenario | Comportamento |
|----------|---------------|
| Prezzo corrente mancante | Posizione calcolata ma P/L corrente non calcolabile. Mostrare warning |
| Indicatori tecnici mancanti | SELL evaluation prudente, confidence = low. Non generare suggerimenti aggressivi |
| FGI mancante | Non impedire calcolo P/L, ma ridurre confidence del suggerimento SELL |
| Fair value mancante/stale | Nessun impatto operativo, mostrare solo "non disponibile" |

---

## H) OUTPUT SELL EVALUATION

Per ogni posizione aperta, l'output SELL ha questa struttura:

```json
{
  "ticker": "NVDA",
  "sell_signal": "PRENDI PROFITTO PARZIALE",
  "confidence": "medium",
  "reasons": [
    "Gain non realizzato superiore al 15%",
    "RSI vicino a zona surriscaldata",
    "FGI non più in fear"
  ],
  "suggested_action_note": "Valutare realizzo parziale, non uscita totale automatica."
}
```

Campi:

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ticker` | string | Simbolo del titolo |
| `sell_signal` | enum | Uno dei 5 stati definiti in B |
| `confidence` | enum | `low` / `medium` / `high` |
| `reasons` | list | Lista di motivazioni leggibili |
| `suggested_action_note` | string |Nota sintetica con il suggerimento operativo |

---

## I) RELAZIONE CON INDICATOR_REGISTRY

La funzionalità SELL **non entra** automaticamente nel `indicator_registry.yaml` esistente.

Se in futuro si vuole formalizzare la SELL strategy nel registry:

- creare un `sell_indicator_registry.yaml` separato
- oppure aggiungere una sezione dedicata nel registry esistente

Per ora: **evitare di modificare** `indicator_registry.yaml` se pensato per la strategia BUY.

---

## J) SCOPO DEL SISTEMA

| Pipeline attuale | Nuova funzionalità portfolio |
|------------------|------------------------------|
| "Quali ticker sono interessanti per valutare ingressi Buy-the-Dip?" | "Date le posizioni che possiedo, come dovrei monitorarle e quando valutare prese di profitto?" |
| Genera report con segnali BUY | Genera pagina portfolio con posizioni + SELL evaluation |
| Output: output.json + report.html | Output: portfolio.db + portfolio.html |

Le due logiche restano separate ma condividono gli stessi dati scrapati.

---

*File creato il 27 Agosto 2026. Totale: 10 sezioni (A-J). Ogni modifica alla strategia SELL va validata contro questa lista.*
