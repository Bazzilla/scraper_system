# Page Pattern — Ordine degli elementi HTML

Ogni pagina del progetto deve seguire questo ordine fisso:

```
1. NAV BAR       ← sempre in alto per prima
2. TITOLO        ← h1 + sottotitolo
3. CONTENUTO     ← main / sezioni
4. FOOTER        ← opzionale
```

## Struttura HTML standard

```html
<!DOCTYPE html>
<html lang="it" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pagina — scraper-system</title>
  {FAVICON_LINK}
  <style>{_PAGE_CSS}</style>
</head>
<body>
  <div class="container">
  <header>
    <!-- 1. NAV BAR — sempre prima -->
    <div>{render_nav("active-page")}
      <button id="theme-toggle" type="button">☀️ Light</button></div>
    <!-- 2. TITOLO -->
    <div><h1>Titolo della pagina</h1>
      <div class="sub">Sottotitolo descrittivo</div></div>
  </header>

  <!-- 3. CONTENUTO -->
  <main>
    ...
  </main>
  </div>

  {_SCRIPT}
  <script>{_PAGE_SCRIPT}</script>
</body>
</html>
```

## Regole

- **Nav bar sempre in alto per prima** dentro `<header>` — non dopo il titolo.
- **`<div class="container">`** avvolge tutto il body (max-width: 1100px, centrato).
- **`data-theme="dark"`** sul tag `<html>` per il dark mode di default.
- **`{_SCRIPT}`** (da report_html) va prima di `_PAGE_SCRIPT` — include il theme toggle JS.
- **Tema toggle** `#theme-toggle` sempre presente nel nav.
- **Prime colonne** delle tabelle: `text-align: left`; altre colonne: `text-align: center`.
- **Date**: formato DD/MM/YYYY (italiano/europeo).

## Pagine che seguono il pattern

| Pagina | File | Stato |
|--------|------|-------|
| Report | `src/report_html.py` | ✅ |
| Immissione manuale | `src/overrides_page.py` | ✅ |
| Ticker | `src/tickers_page.py` | ✅ |
| Portfolio | `src/portfolio_page.py` | ✅ |
| Scraping | `src/scraper_run_page.py` | ✅ |
