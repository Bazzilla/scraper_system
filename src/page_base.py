"""Shared page building blocks — CSS, HTML wrapper, JS helpers.

All page generators import from here instead of duplicating boilerplate.
"""

from __future__ import annotations

from typing import Any

from report_helpers import FAVICON_LINK, render_nav

# ── Base CSS (shared by all pages) ──────────────────────────────────────────

_BASE_CSS = """\
:root { --bg: #0f1419; --card: #1a212b; --border: #2c3542; --text: #e6edf3;
        --muted: #8b949e; --green: #2ea043; --yellow: #d29922; --red: #f85149;
        --neutral: #58a6ff; }
[data-theme="light"] { --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
        --text: #1f2328; --muted: #57606a; --green: #1a7f37; --yellow: #9a6700;
        --red: #cf222e; --neutral: #0969da; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        sans-serif; background: var(--bg); color: var(--text); line-height: 1.5;
        padding: 24px; }
.container { max-width: 1100px; margin: 0 auto; }
header { display: flex; flex-direction: column; align-items: flex-start;
        gap: 8px; margin-bottom: 24px; }
h1 { font-size: 1.5rem; }
h2 { margin: 28px 0 12px; font-size: 1.15rem; }
.sub { color: var(--muted); font-size: 0.9rem; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: 0.8rem;
        font-weight: 600; }
.badge.fresh { background: var(--green); color: #fff; }
.badge.stale { background: var(--red); color: #fff; }
button#theme-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
.page-nav { display: inline-flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.page-nav a { padding: 4px 12px; border-radius: 999px; font-size: 0.85rem;
        font-weight: 600; text-decoration: none; background: var(--card);
        color: var(--text); border: 1px solid var(--border); }
.page-nav a.active { background: var(--green); color: #fff;
        border-color: var(--green); }
.page-nav a:hover { opacity: 0.85; }
button#sections-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
.sections-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
/* Shared card */
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
/* Shared table */
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
th, td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border);
        font-size: 0.9rem; }
th { background: var(--card); color: var(--muted); font-weight: 600;
        text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.04em;
        text-align: center; }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(88, 166, 255, 0.06); }
/* Shared message feedback */
.msg { padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; }
.msg.ok { background: var(--green); color: #fff; }
.msg.err { background: var(--red); color: #fff; }
/* Shared buttons */
button { cursor: pointer; border: none; border-radius: 8px; padding: 6px 12px;
        font-size: 0.85rem; font-weight: 600; }
button.primary { background: var(--green); color: #fff; }
button.danger { background: var(--red); color: #fff; }
button.subtle { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); }
/* Shared collapsible details */
details.section { margin: 28px 0 12px; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; }
details.section > summary { cursor: pointer; list-style: none; padding: 12px 16px;
        display: flex; align-items: center; justify-content: space-between; }
details.section > summary::-webkit-details-marker { display: none; }
details.section > summary h2 { margin: 0; font-size: 1.15rem; }
details.section > summary::after { content: "▾"; font-size: 1rem; color: var(--muted);
        transition: transform 0.15s ease; }
details.section[open] > summary::after { transform: rotate(180deg); }
details.section > .section-body { padding: 0 16px 16px; }
/* Shared footer */
footer { margin-top: 32px; color: var(--muted); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 16px; }
/* Shared sell signal badges */
.sell-signal { display: inline-block; padding: 2px 8px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; }
.sell-NESSUNA { background: var(--card); color: var(--muted); }
.sell-MANTIENI { background: #1a3a1a; color: #4ade80; }
.sell-PRENDI { background: #3a2a0a; color: #fbbf24; }
.sell-RIDUCI { background: #3a1a1a; color: #f87171; }
.sell-ATTENZIONE { background: #2a1a3a; color: #c084fc; }
/* Shared P/L classes */
.pnl-pos { color: var(--green); font-weight: 600; }
.pnl-neg { color: var(--red); font-weight: 600; }
"""

# ── Shared JS (theme toggle + helpers) ──────────────────────────────────────

_SHARED_SCRIPT = """\
<script>
(function () {
  /* Theme toggle */
  var saved = localStorage.getItem("report-theme");
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  var btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.textContent = theme === "dark" ? "\\u2600\\ufe0f Light" : "\\ud83c\\udf19 Dark";
    btn.addEventListener("click", function () {
      var next = theme === "dark" ? "light" : "dark";
      theme = next;
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("report-theme", next);
      btn.textContent = next === "dark" ? "\\u2600\\ufe0f Light" : "\\ud83c\\udf19 Dark";
    });
  }

  /* Collapsible sections toggle */
  var sections = document.querySelectorAll("details.section");
  var sectionsBtn = document.getElementById("sections-toggle");
  function allOpen() {
    for (var i = 0; i < sections.length; i++) {
      if (!sections[i].open) return false;
    }
    return true;
  }
  function updateSectionsLabel() {
    if (sectionsBtn) {
      sectionsBtn.textContent = allOpen() ? "\\ud83d\\uddc2\\ufe0f Chiudi tutte" : "\\ud83d\\uddc2\\ufe0f Apri tutte";
    }
  }
  if (sectionsBtn) {
    sectionsBtn.addEventListener("click", function () {
      var open = !allOpen();
      for (var i = 0; i < sections.length; i++) {
        sections[i].open = open;
      }
      updateSectionsLabel();
    });
    for (var i = 0; i < sections.length; i++) {
      sections[i].addEventListener("toggle", updateSectionsLabel);
    }
    updateSectionsLabel();
  }

  /* Shared helpers — available to page scripts */
  window.__helpers = {
    $: function (id) { return document.getElementById(id); },
    fmt: function (v) {
      if (v == null) return "\\u2014";
      return v.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    },
    fmtDate: function (iso) {
      if (!iso) return "\\u2014";
      var p = iso.split("-");
      return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
    },
    pnlClass: function (v) {
      if (v == null) return "neutral";
      return v >= 0 ? "pnl-pos" : "pnl-neg";
    },
    valClass: function (v) {
      if (v == null) return "neutral";
      return v >= 0 ? "positive" : "negative";
    },
    postJSON: function (url, payload, attempt) {
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (resp) {
        if (resp.status === 401 && (attempt || 0) < 2) {
          return window.__helpers.postJSON(url, payload, (attempt || 0) + 1);
        }
        return resp.json();
      });
    },
    api: function (method, path, body) {
      var opts = {method: method, headers: {"Content-Type": "application/json"}};
      if (body) opts.body = JSON.stringify(body);
      return fetch(path, opts).then(function (r) {
        return r.json().then(function (d) { return {status: r.status, data: d}; });
      });
    }
  };
})();
</script>"""


# ── HTML wrapper ────────────────────────────────────────────────────────────

def wrap_page(
    title: str,
    nav_active: str,
    css: str,
    header_html: str,
    content_html: str,
    scripts: str = "",
    *,
    extra_head: str = "",
) -> str:
    """Build a complete HTML page following the standard pattern:
    nav → title → content → footer (optional).

    Args:
        title: Page title (also used in <title>).
        nav_active: Active nav item key (e.g. "report", "portfolio").
        css: Page-specific CSS (appended to _BASE_CSS).
        header_html: Inner HTML of <header> (nav + title already wrapped).
        content_html: Inner HTML of <main> or direct content after header.
        scripts: Page-specific <script> tags (appended after _SHARED_SCRIPT).
        extra_head: Extra content inside <head> (e.g. JSON data script).
    """
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"{FAVICON_LINK}"
        f"<title>{title}</title>"
        f"{extra_head}"
        f"<style>{_BASE_CSS}{css}</style>"
        "</head>\n<body><div class=\"container\">"
        f"{header_html}"
        f"{content_html}"
        "</div>"
        f"{_SHARED_SCRIPT}"
        f"{scripts}"
        "</body>\n</html>"
    )


def render_header(
    nav_active: str,
    title: str,
    subtitle: str = "",
    *,
    extra_badge: str = "",
) -> str:
    """Render the standard page header: nav bar first, then title.

    Args:
        nav_active: Active nav item key.
        title: Page title (h1).
        subtitle: Optional subtitle text.
        extra_badge: Optional HTML to insert before nav (e.g. fresh/stale badge).
    """
    badge_html = f'{extra_badge} ' if extra_badge else ""
    sub_html = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return (
        "<header>"
        f"<div>{badge_html}{render_nav(nav_active)} "
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        f"<div><h1>{title}</h1>"
        f"{sub_html}</div>"
        "</header>"
    )
