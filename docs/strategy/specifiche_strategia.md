# 📋 Specifiche Strategia Buy-the-Dip — Semiconduttori & Difesa

**Data cristallizzazione**: 5 Agosto 2026
**Scopo**: Questo file è il "contratto" di riferimento. Ogni modifica alla strategia o al prompt operativo deve rispettare queste specifiche. Se una specifica viene violata, deve essere una scelta intenzionale e dichiarata.

---

## A) FILOSOFIA E OBIETTIVO

| # | Specifica | Fonte |
|---|---|---|
| A1 | Capitale "funny money", sacrificabile (~3% del patrimonio totale) | Prompt iniziale + chat |
| A2 | Orizzonte medio-breve: da settimane a mesi, target gain +15/20% | Prompt iniziale + chat |
| A3 | Max 18 mesi di tenuta, poi chiusura forzata anche in perdita | Chat |
| A4 | Max 3 trade simultanei aperti | Chat |
| A5 | Max 3 ingressi per trade (1 acquisto + 2 medie) | Chat |
| A6 | L'utente segue i mercati, ha conoscenza di contesto — il prompt deve essere tecnico, non divulgativo | Prompt iniziale |
| A7 | Risposte oggettive, non accondiscendenti. Se la strategia ha un punto debole, va detto | Prompt iniziale |

---

## B) UNIVERSO INVESTIBILE

| # | Specifica | Fonte |
|---|---|---|
| B1 | Due settori: **Semiconduttori/Hardware Tech** e **Difesa/Aerospazio** | Chat |
| B2 | Semiconduttori: aziende della filiera chip (foundry, equipment, design, packaging, networking) — criterio oggettivo: GICS o appartenenza ETF SOXX/SMH | Chat |
| B3 | Difesa: ≥50% ricavi da contratti con governi USA/NATO/alleati — criterio oggettivo: appartenenza ETF ITA o PPA | Chat |
| B4 | **Esclusioni esplicite**: software puro, servizi IT, biotech, fintech, REITs, aziende in perdita, aziende senza fossato | Prompt iniziale + chat |
| B5 | **Boeing (BA) esclusa** per problemi strutturali (qualità, debito, scioperi) | Chat |
| B6 | Le liste di ticker negli esempi sono **punto di partenza, NON vincolo**. Se un titolo soddisfa i criteri oggettivi ma non è nella lista, va incluso | Chat |

---

## C) CRITERI DI SCREENING FONDAMENTALE (REGOLA 1)

| # | Specifica | Fonte |
|---|---|---|
| C1 | **Settore corretto**: vedi B1-B6 | Chat |
| C2 | **Fossato competitivo**: tecnologico (semiconduttori) o regolatorio+tecnologico (difesa: clearance, contratti pluriennali, know-how classificato) | Prompt iniziale + chat |
| C3 | **In utile**: EPS trailing positivo, preferibilmente in crescita YoY | Prompt iniziale |
| C4 | **FCF positivo o giustificato**: se negativo, deve essere per capex strategico, non inefficienza. Nella difesa è quasi sempre positivo | Chat |
| C5 | **Crescita ricavi YoY**: non in contrazione. Per la difesa, crescita piatta (+0/3%) accettabile se accompagnata da margini in espansione o backlog in crescita | Chat |
| C6 | **Debito gestibile**: Debt/EBITDA <3x. Per la difesa tollera fino a 3.5x se backlog >2 anni | Chat |
| C7 | **Domanda strutturale**: AI/cloud/data center/5G (semi) o spesa militare globale in crescita/riarmo NATO (difesa) | Prompt iniziale + chat |
| C8 | Aziende "solide" con fondamentali che crescono anche se il prezzo lateralizza | Prompt iniziale |
| C9 | Anche aziende più piccole ma profittevoli, con presenza di investitori istituzionali | Prompt iniziale |

---

## D) TRIGGER DI ENTRATA (REGOLA 2)

| # | Specifica | Fonte |
|---|---|---|
| D1 | **Calo ≥10%** dal massimo recente (4-8 settimane). Sweet spot: 15-20%. Per la difesa, anche 10-12% è significativo data la minore volatilità | Prompt iniziale + chat |
| D2 | **Causa identificata e NON strutturale**: sentiment, panico settoriale, profit-taking, contagio, dati macro. NON perdita clienti, crollo guidance >10%, disruption tecnologica, sanzioni permanenti | Chat |
| D3 | **Volume nella media o inferiore** (no distribuzione massiccia). Volume >2x media su calo = possibile distribuzione istituzionale → rischio più alto | Chat |
| D4 | **Target analyst rialzisti**: upside ≥15-20% (se disponibile) | Chat |
| D5 | **OBV Divergence**: se prezzo fa minimo più basso ma OBV fa minimo più alto → accumulazione nascosta. Fonte: TradingView o calcolo locale (gratuito) | Chat |
| D6 | **MFI(14)**: MFI < 20 = ipervenduto confermato da volume. MFI che incrocia sopra 20 = segnale inversione. Fonte: TradingView o calcolo locale (gratuito) | Chat |
| D7 | **Volume Profile HVN**: prezzo entro ±2% da High Volume Node storico (6-12 mesi) = maggior probabilità di rimbalzo. Prezzo in LVN = possibile ulteriore discesa. Fonte: TradingView (gratuito) | Chat |

---

## E) REGOLE DI USCITA (REGOLA 4)

| # | Specifica | Fonte |
|---|---|---|
| E1 | **Take-profit**: +15/20%, vendere senza rimpianti | Prompt iniziale + chat |
| E2 | **Stop-loss**: SOLO su deterioramento fondamentale, MAI su prezzo | Chat |
| E3 | **Time-stop**: 18 mesi senza recupero → chiudere | Chat |
| E4 | I recuperi nella difesa possono essere più lenti (3-6 mesi vs 2-8 settimane). La pazienza è parte del vantaggio in questo settore | Chat |

---

## F) CONTESTO MACRO (REGOLA 0)

| # | Specifica | Fonte |
|---|---|---|
| F1 | **Fear & Greed Index** come semaforo: Extreme Fear (0-24) = 🟢 ideale; Fear (25-44) = 🟢 buono; Neutral (45-55) = 🟡 setup perfetto; Greed (56-74) = 🟠 cautela; Extreme Greed (75-100) = 🔴 non entrare | Chat |
| F2 | I **7 indicatori CNN** vanno conosciuti: Market Momentum, Stock Price Strength, Stock Price Breadth, Put/Call Options, Market Volatility, Safe Haven Demand, Junk Bond Demand | Chat |
| F3 | **7 indicatori supplementari gratuiti**: AAII Sentiment, NAAIM Exposure, VIX Term Structure, Equity PCR, NYSE NH-NL, % Stocks above SMA 50, % Stocks above SMA 200 | Chat |

---

## G) DIFFERENZE TRA I DUE SETTORI (conoscenza di dominio per l'LLM)

| # | Specifica | Fonte |
|---|---|---|
| G1 | La difesa ha **ciclicità molto bassa** (spesa militare strutturale), i semiconduttori media-alta | Chat |
| G2 | Nella difesa, la **concentrazione clienti su governo USA/NATO è un punto di FORZA**, non di rischio. Penalizzare invece concentrazione su singolo programma o fornitore | Chat |
| G3 | Il **FCF nella difesa è molto stabile** (contratti pluriennali), nei semiconduttori è variabile (capex AI) | Chat |
| G4 | Le **cause di calo tipiche** sono diverse: paura capex/competizione cinese (semi) vs paura tagli budget/cambio amministrazione (difesa) | Chat |
| G5 | I **catalizzatori di recupero** sono diversi: earnings/product launch (semi) vs budget approval/contract win/escalation geopolitica (difesa) | Chat |
| G6 | **O/R più alti nella difesa sono normali** (rischio molto basso + opportunità moderata-alta) e non devono insospettire | Chat |
| G7 | **Bilanciamento settori**: max 2 trade su 3 nello stesso settore | Chat |

---

## H) MATRICE RISCHIO/OPPORTUNITÀ (scoring)

| # | Specifica | Fonte |
|---|---|---|
| H1 | **Rischio (0-10)** = somma di 5 fattori (0-2 punti ciascuno): Ciclicità, Geopolitica, Concentrazione clienti, Leva finanziaria, Rischio disruption | Chat |
| H2 | **Opportunità (0-10)** = somma di 5 fattori (0-2 punti ciascuno): Magnitudo calo, Qualità causa, Upside potenziale, Contesto FGI, Catalizzatore visibile | Chat |
| H3 | Ogni fattore ha una **griglia esplicita 0/1/2 punti** con condizioni chiare (vedi matrice nel prompt operativo) | Chat |
| H4 | **Rapporto O/R**: >2.0 = 🟢 ENTRA, 1.3-2.0 = 🟡 MONITORA, 1.0-1.3 = 🟠 WATCHLIST, <1.0 = 🔴 LASCIA | Chat |
| H5 | **Bonus Insider Transactions**: +0.5 se ≥2 acquisti insider in 4 settimane, +1.0 se CEO/CFO compra. Cumulabile max +1.5. Solo open market, non stock options. Fonte: OpenInsider (gratuito) | Chat |

---

## I) FORMATO OUTPUT (come deve rispondere l'LLM)

| # | Specifica | Fonte |
|---|---|---|
| I1 | Il prompt è **operativo e diretto a un LLM**, non un documento descrittivo. Tono: `TASK:`, `Esegui SUBITO`, `Non chiedermi conferme` | Chat |
| I2 | Deve produrre un report strutturato: Contesto Macro → Opportunità (schede) → Tabella Riepilogativa → Watchlist → Riepilogo Analisi | Chat |
| I3 | Ogni scheda opportunità ha **campi obbligatori**: prezzo, calo, market cap, fondamentali (EPS, FCF, revenue, debito), causa calo, volume, OBV, MFI, Volume Profile, target analyst, catalizzatore, R/O, O/R, analisi | Chat |
| I4 | **Tabella riepilogativa** con legenda colonne esplicita (EPS, FCF, Rev. YoY, Volume vs 30gg, R, O, O/R, Azione) | Chat |
| I5 | **Legenda Azione**: 🟢 ENTRA, 🟡 MONITORA, 🟠 WATCHLIST, 🔴 LASCIA | Chat |
| I6 | **Legenda Volume**: ✓ normale, ⚠️ >2x media, — non disponibile | Chat |
| I7 | **Casi storici di riferimento** per calibrare il giudizio (AVGO, TSMC, ASML, RTX, LMT, NOC, Boeing come caso negativo) | Chat |
| I8 | Sezione "Nessuna Opportunità?" se non si trova nulla — è una risposta valida | Chat |
| I9 | **Riepilogo Analisi**: sempre includere conteggio totale, in tabella, watchlist, scartate, divisi per settore | Chat |

---

## J) GESTIONE DATI

| # | Specifica | Fonte |
|---|---|---|
| J1 | Dati stimati ammessi e incoraggiati con tag `[stimato]`. "Meglio approssimato che rinunciare" | Chat |
| J2 | Fonti valide: Yahoo Finance, MarketBeat, Reuters, CNBC, Bloomberg (pubblico), MarketScreener, Google Finance, CNN, TradingView | Chat |
| J3 | Citare le fonti nel testo: `[Fonte: Yahoo Finance]` | Chat |
| J4 | **8 fonti scraping gratuite** documentate: CNN (FGI), AAII, NAAIM, VIX Central, Barchart, IndexIndicators, OpenInsider, Yahoo Finance (yfinance) | Chat |
| J5 | Suggerimento: script Python che produce un JSON strutturato da iniettare nel prompt prima di inviarlo all'LLM | Chat |

---

## K) REGOLE DI INTERAZIONE CON L'UTENTE

| # | Specifica | Fonte |
|---|---|---|
| K1 | Il prompt è monolitico: l'LLM deve eseguire senza chiedere conferme o chiarimenti | Chat |
| K2 | L'utente NON vuole risposte accondiscendenti | Prompt iniziale |
| K3 | Se una strategia o un titolo ha un problema, va detto esplicitamente | Prompt iniziale |

---

*File cristallizzato il 5 Agosto 2026. Totale: 51 specifiche. Ogni modifica alla strategia va validata contro questa lista.*
