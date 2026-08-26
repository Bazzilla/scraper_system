"""Legend and operational guide for the HTML report generator."""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_helpers import _collapsible

_LEGEND_MARKET = [
    {
        "name": "Fear &amp; Greed (FGI)",
        "range": "0-100",
        "short": "Sentiment del mercato: meno di 25 = paura estrema, oltre 75 = avidità estrema.",
        "detail": (
            "Indice composito CNN che misura il sentiment prevalente degli investitori. "
            "Valori bassi (paura) spesso coincidono con fasi di debolezza o con punti di "
            "massima cautela; valori alti (avidità) indicano ottimismo spinto, che può "
            "precedere correzioni. Va letto come termometro dell'umore di mercato, non "
            "come segnale di compra/vendita diretto."
        ),
        "strategy": (
            'FGI basso (paura, ≤25) = contesto migliore per <strong>comprare</strong> (gate aperto). Tra 25 e 40 = solo <strong>osservare</strong>. Sopra 40 (avidità) = <strong>evitare acquisti</strong>; se hai posizioni in profitto è il momento tipico per valutarne la presa parziale.'
        ),
    },
    {
        "name": "VIX",
        "range": "indice",
        "short": "Volatilità implicita: oltre 30 tensione elevata, sotto 15 mercato calmo.",
        "detail": (
            "Detto anche 'indice della paura', stima la volatilità attesa del mercato "
            "azionario USA a 30 giorni. Un VIX alto segnala incertezza e possibili "
            "oscillazioni forti; un VIX basso indica condizioni tranquille. Non va usato "
            "da solo per decidere, ma come indicatore del clima di rischio complessivo. "
            "<strong>Nota (audit 2026-08-14)</strong>: la strategia F3/10 richiede la "
            "<em>VIX term structure</em> (backwardation M1&gt;M2 = panico a breve); questa "
            "card mostra il <em>VIX spot</em> (livello), che è un indicatore diverso. "
            "La term structure non è scrapabile da fonti gratuite (VIX Central/VolChart "
            "bloccato), ma può essere inserita manualmente (M1/M2) via "
            "<code>manual_overrides.yaml</code> — valori leggibili da "
            "https://vixcentral.com/. Il dato spot resta un proxy parziale."
        ),
        "strategy": (
            'VIX alto = mercato teso: può offrire buoni punti di ingresso ma anche rischio elevato — serve paura sana, non panico. VIX basso = calma: poco sconto sui prezzi. Da solo non dice compra/vendi: è il termometro del rischio.'
        ),
    },
    {
        "name": "AAII Sentiment",
        "range": "%",
        "short": "Percentuale di investitori retail bullish, neutral e bearish.",
        "detail": (
            "Sondaggio settimanale AAII sull'orientamento degli investitori privati. "
            "Un'estrema prevalenza di bullish può segnalare euforia (possibile eccesso), "
            "un'estrema prevalenza di bearish può segnalare pessimismo diffuso. Indicatore "
            "contrarian: spesso i massimi si formano con sentiment molto positivo e i "
            "minimi con sentiment molto negativo."
        ),
        "strategy": (
            "Molti bearish e pochi bullish = segnale storico di fondo di mercato → contesto favorevole all'<strong>acquisto</strong>. Il contrario (euforia) = cautela: buon momento per <strong>valutare profitti</strong>, non per entrare."
        ),
    },
    {
        "name": "Put/Call Ratio (PCR)",
        "range": "ratio",
        "short": "Put venduti vs call: oltre 0.80 = paura, sotto 0.70 = avidità.",
        "detail": (
            "Rapporto tra il volume di opzioni put e call (equity). Un PCR alto "
            "(> 0.80) indica che gli investitori comprano più protezione che "
            "speculazione — segnale di paura, storicamente favorevole per chi "
            "cerca sconti (buy-the-dip). Un PCR basso (< 0.70) indica ottimismo. "
            "Fonte: CBOE (lag 1 giorno di trading)."
        ),
        "strategy": (
            'PCR alto (&gt;0.80) = paura → contesto favorevole al <strong>buy-the-dip</strong>. PCR basso (&lt;0.70) = ottimismo → meglio non inseguire; chi ha posizioni può valutare presa di profitto.'
        ),
    },
    {
        "name": "NYSE New Highs/Lows (52w)",
        "range": "conteggio",
        "short": "Titoli NYSE a nuovi massimi vs nuovi minimi di 52 settimane.",
        "detail": (
            "Rapporto tra i titoli del NYSE che hanno toccato nuovi massimi e "
            "nuovi minimi a 52 settimane (F3/#12 della strategia). Quando i "
            "massimi superano ampiamente i minimi (ratio ≥ 2) il mercato è in "
            "fase di forza (greed); quando i minimi dominano (ratio ≤ 0.5) "
            "prevale la debolezza (fear). Un picco di nuovi minimi coincide "
            "spesso con fasi di panico — potenziale contesto buy-the-dip. "
            "Fonte: Barchart (dati end-of-day)."
        ),
        "strategy": (
            'Nuovi minimi ≫ nuovi massimi = mercato debole → possibili occasioni da <strong>comprare</strong> (con conferme). Massimi ≫ minimi = mercato forte e caro → <strong>non inseguire</strong>.'
        ),
    },
    {
        "name": "Breadth di mercato (% sopra SMA)",
        "range": "%",
        "short": "Quota di titoli del MERCATO USA sopra SMA50/SMA200 (inserita manualmente).",
        "detail": (
            "Percentuale di titoli USA con prezzo sopra la media mobile a 50 e 200 "
            "giorni (F3/#13-14 della strategia). Sotto il 20% su SMA50 il mercato è "
            "ipervenduto diffuso (potenziale opportunità); sotto il 30% su SMA200 il "
            "mercato è deteriorato. Sopra il 50%/60% la struttura è positiva. "
            "<strong>Nota (2026-08-17)</strong>: il proxy locale sui 29 ticker è stato "
            "rimosso; il valore si inserisce manualmente (fonte con breadth del mercato "
            "USA, es. IndexIndicators via browser, StockCharts, Finviz)."
        ),
        "strategy": (
            '% su SMA50 molto basso (&lt;20%) = ipervenduto diffuso → zona storicamente buona per <strong>comprare</strong>. Valori alti (&gt;50-60%) = struttura sana ma prezzi meno scontati → selezionare bene.'
        ),
    },
    {
        "name": "Insider (bonus opportunità)",
        "range": "punti",
        "short": "Acquisti insider dei dirigenti come bonus alla matrice Opportunità.",
        "detail": (
            "Bonus H5 della strategia: <strong>+0.5</strong> se almeno 2 acquisti "
            "insider (dirigenti) sul mercato aperto negli ultimi 30 giorni con valore "
            "complessivo oltre $100K; <strong>+1.0</strong> se CEO o CFO compra; "
            "cumulabile fino a <strong>max +1.5</strong>. Gli acquisti insider sono tra "
            "i segnali più forti perché chi conosce l'azienda mette soldi veri sul "
            "titolo. Fonte: OpenInsider (Form 4 SEC, lag 2 giorni)."
        ),
        "strategy": (
            'Acquisti dei dirigenti sul proprio titolo = voto di fiducia concreto → <strong>rafforza il caso acquisto</strong> su quel titolo (bonus alla matrice opportunità). Nessun acquisto insider = nessun bonus, né pro né contro.'
        ),
    },
]

_LEGEND_STOCK = [
    {
        "name": "RSI",
        "range": "0-100",
        "short": "Momentum: oltre 70 ipercomprato, sotto 30 ipervenduto.",
        "detail": (
            "Relative Strength Index: misura la forza del movimento dei prezzi. "
            "RSI oltre 70 indica un titolo potenzialmente ipercomprato (il prezzo è "
            "salito troppo in fretta, possibile correzione); sotto 30 ipervenduto "
            "(possibile rimbalzo). Se molti titoli di un settore hanno RSI alto, il "
            "settore nel suo insieme appare 'caldo'."
        ),
        "strategy": (
            'RSI &lt;30 = ipervenduto → <strong>candidato acquisto</strong> (con altre conferme). RSI &gt;70 = ipercomprato → se detenuto in profitto, momento tipico per <strong>presa di profitto</strong>; se non detenuto, evitare di inseguire.'
        ),
    },
    {
        "name": "MFI",
        "range": "0-100",
        "short": "Flusso monetario: oltre 80 ipercomprato, sotto 20 ipervenduto.",
        "detail": (
            "Money Flow Index: come l'RSI ma ponderato per il volume. Misura la "
            "pressione di acquisto/vendita. Valori estremi indicano eccessi che spesso "
            "precedono inversioni. Un MFI in salita con prezzi in salita conferma il "
            "trend; divergenze (prezzi che salgono, MFI che scende) segnalano debolezza."
        ),
        "strategy": (
            "Come RSI ma pesa i volumi: &lt;20 = ipervenduto (possibile <strong>acquisto</strong>), &gt;80 = ipercomprato (possibile <strong>presa di profitto</strong>). Conferma i segnali dell'RSI."
        ),
    },
    {
        "name": "OBV",
        "range": "cumulativo",
        "short": "Conferma del trend attraverso il volume.",
        "detail": (
            "On-Balance Volume: accumula il volume in base alla direzione del prezzo "
            "(giorni in rialzo sommano, giorni in ribasso sottraggono). Un OBV in "
            "tendenza con i prezzi conferma il movimento; un OBV che diverge dai prezzi "
            "può anticipare un'inversione. Utile come conferma, non come segnale isolato."
        ),
        "strategy": (
            'Conferma la direzione del prezzo: prezzo in calo ma OBV che tiene = venditori deboli → buon segno per <strong>comprare</strong>. Divergenze evidenti = <strong>attendere conferme</strong> prima di agire.'
        ),
    },
    {
        "name": "SMA50 / SMA200",
        "range": "prezzo",
        "short": "Media mobile: trend di medio (50) e lungo (200) termine.",
        "detail": (
            "Simple Moving Average: prezzo medio degli ultimi N giorni. Il prezzo sopra "
            "la SMA50 indica trend di medio termine positivo, sopra la SMA200 trend di "
            "lungo termine positivo. L'incrocio prezzo/SMA o SMA50/SMA200 è usato come "
            "segnale di cambio trend (golden cross / death cross)."
        ),
        "strategy": (
            'Prezzo sopra SMA50/SMA200 = tendenza positiva → si <strong>tiene</strong> la posizione. Prezzo sotto entrambe = debolezza → solo <strong>osservazione</strong> finché non rientra sopra le medie.'
        ),
    },
    {
        "name": "Drawdown",
        "range": "%",
        "short": "Distanza dal massimo delle 52 settimane: ok, attenzione, critico.",
        "detail": (
            "Indica di quanto il prezzo è sceso rispetto al massimo dell'ultimo anno. "
            "Un drawdown lieve (fino a -5%) è fisiologico; tra -5% e -15% la correzione "
            "è più marcata; oltre -15% la situazione è critica. Valuta la debolezza "
            "relativa del titolo rispetto al suo stesso recente massimo."
        ),
        "strategy": (
            "Calo ampio dal massimo (-15% o più) = possibile <strong>sconto</strong> "
            "per il buy-the-dip, ma verificane la causa. Drawdown contenuto = titolo "
            "in salute → nessuna azione urgente."
        ),
    },
    {
        "name": "Upside FV (fair value)",
        "range": "%",
        "short": "Distanza del prezzo dal target mediano degli analisti (informativo).",
        "detail": (
            "Stima di margine di sicurezza: quanto il prezzo attuale è sotto (+) o "
            "sopra (-) il fair value inteso come target mediano degli analisti, con "
            "multipli di supporto (P/E, P/B, EV/EBITDA, PEG) da Yahoo Finance. "
            "<strong>Artefatto informativo</strong>: non entra nel punteggio della "
            "strategia. I target sono stime — vanno letti come indicazione, non verità."
        ),
        "strategy": (
            "Drawdown ampio + upside alto (≥ +20%) = lo sconto è reale → "
            "<strong>rafforza il caso acquisto</strong>. Upside negativo (≤ -10%) = "
            "titolo caro nonostante il calo → <strong>osservare/evitare</strong>, "
            "possibile trappola da valore."
        ),
    },
    {
        "name": "Segnale",
        "range": "VALUTA INGRESSO / OSSERVA / ATTENDI",
        "short": "Sintesi degli indicatori del ticker + clima di mercato.",
        "detail": (
            "Punteggio che combina RSI, MFI, SMA50, SMA200 e drawdown (+1 bullish, "
            "-1 bearish per indicatore). Il report NON dà ordini operativi: i "
            "segnali indicano setup da <strong>valutare</strong>, non acquisti "
            "automatici.<br>"
            "<strong>VALUTA INGRESSO</strong> (punteggio ≥ +2): setup tecnico "
            "positivo (convergenza di ipervenduto e forza) E gate Buy-the-Dip "
            "aperto (FGI ≤ 25) — candidato da valutare per un ingresso, con le "
            "conferme della strategia.<br>"
            "<strong>OSSERVA</strong>: setup interessante o contesto in "
            "avvicinamento, ma ingresso non pienamente abilitato — debolezza "
            "profonda (punteggio ≤ -2, profilo buy-the-dip con calo ≥10%) oppure "
            "FGI tra 25 e 40: osserva, non entrare senza conferme (causa del "
            "calo, MFI, volume).<br>"
            "<strong>ATTENDI</strong> (tra -1 e +1): segnali misti o nessuna "
            "azione operativa.<br>"
            "<strong>Gate di mercato (FGI)</strong>: con la strategia buy-the-dip "
            "un ingresso è valutabile solo in paura sufficiente. FGI ≤ 25 → "
            "valutazione ingresso consentita; 25 &lt; FGI ≤ 40 → solo "
            "osservazione; FGI &gt; 40 → nessun ingresso Buy-the-Dip; FGI "
            "mancante/stale → fail-closed, nessun ingresso. <strong>Nessun VENDI "
            "viene emesso dai dati tecnici</strong>: vendere richiede un trigger "
            "di uscita esplicito (take-profit +15/20%, deterioramento "
            "fondamentale, time-stop 18 mesi) che il dashboard non può calcolare. "
            "Non è un consiglio finanziario."
        ),
    },
]

_LEGEND_SEMAPHORES = [
    {
        "name": "Semafori",
        "range": "",
        "short": "Colori che riassumono lo stato di ogni indicatore.",
        "detail": (
            "<span class='sema-dot ok'></span><strong>Verde (ok / oversold)</strong>: "
            "condizione favorevole o di ipervenduto (potenziale rimbalzo).<br>"
            "<span class='sema-dot warning'></span><strong>Giallo (warning)</strong>: "
            "zona di cautela, correzione marcata.<br>"
            "<span class='sema-dot critical'></span><strong>Rosso (critical / overbought)</strong>: "
            "condizione critica o di ipercomprato (possibile correzione).<br>"
            "<span class='sema-dot neutral'></span><strong>Blu (neutral)</strong>: "
            "valore in zona neutra, nessun segnale particolare.<br>"
            "<strong>Nelle card di mercato</strong> (FGI, Put/Call Ratio) il colore segue "
            "il <em>sentiment</em>: verde = greed/avidità (ottimismo), rosso = "
            "fear/paura (cautela). Non va confuso con ok/critical dei singoli ticker."
        ),
    },
]

_GUIDE = (
    "<div class='guide'>"
    "<h3>Guida operativa — quando comprare o vendere</h3>"
    "<p>La tabella non è un consiglio finanziario: è un riepilogo tecnico. I segnali "
    "vanno valutati insieme, non singolarmente. Ecco una lettura indicativa:</p>"
    "<ul>"
    "<li><strong>Possibile acquisto</strong> se più indicatori convergono su condizioni "
    "di debolezza con segnali di inversione: RSI/MFI ipervenduti (sotto 30/20), drawdown "
    "ampio ma in miglioramento, prezzo che torna sopra la SMA50, sentiment di mercato in "
    "zona paura (FGI basso). La convergenza di più segnali riduce il rischio di un falso "
    "minimo.</li>"
    "<li><strong>Possibile vendita (se detenuto in profitto)</strong> se il titolo mostra "
    "segnali di eccesso o indebolimento: RSI/MFI ipercomprati (sopra 70/80), drawdown in "
    "peggioramento, prezzo che perde la SMA50 o la SMA200, sentiment di mercato in zona "
    "avidità (FGI alto). L'idea è proteggere il guadagno quando la probabilità di "
    "correzione aumenta.</li>"
    "<li><strong>Cautela / nessuna azione</strong> se i segnali sono misti: alcuni "
    "indicatori positivi e altri negativi. In quel caso è meglio attendere conferme "
    "piuttosto che agire su un segnale singolo.</li>"
    "<li>Gli indicatori di mercato (FGI, VIX, AAII) descrivono il <em>clima generale</em>; "
    "gli indicatori del ticker (RSI, MFI, OBV, SMA, drawdown) descrivono il <em>titolo "
    "singolo</em>. I segnali più forti arrivano quando clima e titolo puntano nella stessa "
    "direzione.</li>"
    "</ul>"
    "<p><em>Disclaimer: strumento informativo a scopo didattico. Non costituisce "
    "consulenza finanziaria.</em></p>"
    "</div>"
)


def _legend_item(item: dict[str, str]) -> str:
    """Render one expandable legend item using native <details>/<summary>."""
    strategy_html = ""
    if item.get("strategy"):
        strategy_html = (
            "<p class='legend-strategy'>💡 <strong>In pratica "
            "(compra / osserva / vendi):</strong> "
            f"{item['strategy']}</p>"
        )
    return (
        "<details class='legend-card'>"
        f"<summary>{item['name']} <span class='legend-range'>({item['range']})</span></summary>"
        f"<div class='legend-detail'><p>{item['short']}</p>"
        f"<p>{item['detail']}</p>{strategy_html}</div>"
        "</details>"
    )


def render_legend() -> str:
    """Render the indicators legend with per-row toggles and the guide."""
    market = "".join(_legend_item(item) for item in _LEGEND_MARKET)
    stock = "".join(_legend_item(item) for item in _LEGEND_STOCK)
    sema = "".join(_legend_item(item) for item in _LEGEND_SEMAPHORES)
    return _collapsible(
        "Legenda indicatori",
        (
            "<div class='legend'>"
            "<div class='legend-grid'>"
            f"<div><h3>Indicatori di mercato</h3>{market}</div>"
            f"<div><h3>Indicatori azionari</h3>{stock}</div>"
            "</div>"
            f"<h3>Semafori</h3>{sema}"
            f"{_GUIDE}"
            "</div>"
        ),
    )
