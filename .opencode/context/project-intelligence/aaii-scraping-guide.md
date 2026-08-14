<!-- Context: project-intelligence/aaii-scraping-guide | Priority: high | Version: 1.0 | Updated: 2026-08-07 -->

# Scraping the AAII Investor Sentiment Survey

## 1. Static vs JS-rendered

**The page is server-rendered (static HTML).** All sentiment data is embedded directly in the
raw HTML returned by `GET https://www.aaii.com/sentimentsurvey`. No headless browser / JS
execution is required. `requests` + `BeautifulSoup` (or even regex) is sufficient.

The data appears in THREE redundant places in the HTML, which is great for robustness:

1. An embedded JS array `var dataChart5 = [...]` (full ~52-week history, JSON objects).
2. Inline `<div class="bar ...">` elements (current week + last 3 weeks + historical averages).
3. JS vars `bullTotalCnt`, `neutralTotalCnt`, `bearTotalCnt` (current week live vote %).

## 2. Exact selectors / JSON keys

### A) Embedded JSON array `dataChart5` (BEST source — full history)
A `<script>` block contains:
```js
var dataChart5 =
[
  {"date_": "2026-08-05", "bullAvg":"37", "bearAvg":"37", "bullish": "37", "bearish": "37", "neutral": "25", spread:"0"},
  {"date_": "2026-07-29", "bullAvg":"31", "bearAvg":"42", "bullish": "31", "bearish": "42", "neutral": "26", spread:"-11"},
  ...
]
```
Keys per object:
- `date_`  -> ISO date string of the week ending (e.g. "2026-08-05")
- `bullish` -> bullish % (string)
- `bearish` -> bearish % (string)
- `neutral` -> neutral % (string)
- `bullAvg` -> running bullish average
- `bearAvg` -> running bearish average
- `spread`  -> bull-bear spread (bullish - bearish)

**Extraction:** regex `var dataChart5\s*=\s*(\[.*?\]);` then `json.loads()` the captured group.
The LAST element is the current week.

### B) Inline HTML bars (current week + recent weeks)
```html
<div class="weekending">
  <div class="datebars">
    <div class="date">8/5/2026</div>
    <div class="bars">
      <div class="bar bullish" style="width:37.0%">37.0%</div>
      <div class="bar neutral" style="width:25.0%">25.0%</div>
      <div class="bar bearish" style="width:38.0%">38.0%</div>
    </div>
  </div>
</div>
```
Selectors (BeautifulSoup):
- `soup.select('div.weekending div.datebars')` -> each week block
- Within a block: `div.date` (the date), `div.bar.bullish`, `div.bar.neutral`, `div.bar.bearish`
- The percentage is in the element's text (e.g. "37.0%") AND in `style="width:37.0%"`.
- The FIRST `div.weekending` block is the current week.

### C) Current-week live vote percentages (JS vars)
```js
var bullTotalCnt = 35.59;
var neutralTotalCnt = 25.11;
var bearTotalCnt = 39.30;
```
These are the LIVE in-progress vote percentages (updated in real time as members vote),
which differ from the published weekly result. Regex: `var (bull|neutral|bear)TotalCnt\s*=\s*([\d.]+);`

### D) Special question (weekly poll) — embedded JSON
```js
var specialQuestionCfData = [{"QUESTION":"...","QUESTIONDATE":"July, 30 2026 00:00:00","SENTIMENTANS":"It was the right move","TOTALVOTES":196,"TOTALVOTESPERQUESTION":108,"QUESTIONPERCENTAGE":55.1}, ...]
```
Regex: `var specialQuestionCfData\s*=\s*(\[.*?\]);` then `json.loads()`.

## 3. JSON API endpoint / embedded JSON

- **No public JSON API** is exposed by AAII for this data. The data is embedded in the HTML
  as the JS variables above (effectively embedded JSON).
- Third-party wrappers exist (e.g. parse.bot "AAII Sentiment API") but are NOT official and
  require their own auth/keys.
- **Official bulk download:** `https://www.aaii.com/files/surveys/sentiment.xls` — an Excel
  file with the COMPLETE history back to 1987 (includes S&P 500 weekly close). This is the
  recommended way to get full history; scrape the HTML only for the latest week.
- Historical table page: `https://www.aaii.com/sentimentsurvey/sent_results` renders ~22
  recent weeks in an HTML `<table>`.

## 4. Known Python scraping examples

A public GitHub notebook (`justmobiledev/python-algorithmic-trading`, `trends/aaii_survey_results_1.ipynb`)
scrapes the historical table using `requests` + `BeautifulSoup`:
```python
soup = BeautifulSoup(html_text, "html.parser")
results = soup.find_all('tr', {'align': 'center'})
for i in range(1, len(results) - 1):
    elements = results[i].find_all('td')
    reported_date = elements[0].getText().strip().replace(':', '')
    bullish  = elements[1].getText().strip().replace('%', '')
    neutral  = elements[2].getText().strip().replace('%', '')
    bearish  = elements[3].getText().strip().replace('%', '')
```
This targets the `sent_results` table where each row is `<tr align="center">` with 4 `<td class="tableTxt">`
cells: [Reported Date, Bullish, Neutral, Bearish]. NOTE: this table structure is on the
`sent_results` page; the main `/sentimentsurvey` page uses the div-bar layout above.

## 4. Authentication / bot protection

- **Viewing results requires NO authentication.** The page is public. Only *voting* in the
  survey requires a member login (`/o/login_aaii?dest=/sentimentsurvey`).
- **Bot protection:** The page loads an Imperva/Incapsula resource script
  (`/_Incapsula_Resource?...`) and a Cloudflare-style challenge script
  (`/I-Mornices-To-can-And-blowt-Thund-dish-your-heri`). This means:
  - A plain `requests.get()` with default headers MAY be challenged/blocked.
  - **Always send a realistic `User-Agent`** (e.g. a current Chrome/Firefox UA) and standard
    browser headers (`Accept`, `Accept-Language`, `Accept-Encoding`).
  - Use a `requests.Session()` to persist cookies across requests (the GitHub example builds
    a cookie from the session and re-sends it).
  - If you get a challenge page (HTML containing "Incapsula" or a JS challenge), retry with
    full browser headers, or fall back to the `.xls` download, or use a headless browser.

## Frequency / schedule

- Survey runs **Thursday 12:01 a.m. to Wednesday 11:59 p.m.** each week.
- Results are **published early Thursday morning** (some sources say ~10:30 ET).
- So scrape on **Thursdays** for the freshest reading. The "week ending" date on the page is
  the Thursday publication date.

## Recommended robust strategy

1. `GET https://www.aaii.com/sentimentsurvey` with a browser User-Agent + Session.
2. Primary: regex `var dataChart5\s*=\s*(\[.*?\]);` -> `json.loads` -> take row[0] for current week.
3. Fallback A: parse `div.weekending div.datebars` blocks; first block = current week.
4. Fallback B: parse `var bullTotalCnt/neutralTotalCnt/bearTotalCnt` for live percentages.
5. For full history: download `https://www.aaii.com/files/surveys/sentiment.xls` and parse with `pandas.read_excel`.
6. If blocked by Incapsula challenge, add full browser headers / session cookies, or use a headless browser.

## Sample minimal scraper (current week)
```python
import re, json, requests

url = "https://www.aaii.com/sentimentsurvey"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
s = requests.Session()
s.headers.update(headers)
html = s.get(url, timeout=20).text

m = re.search(r"var dataChart5\s*=\s*(\[.*?\]);", html, re.S)
rows = json.loads(m.group(1))
current = rows[0]  # most recent week
print(current["date_"], current["bullish"], current["neutral"], current["bearish"])
```