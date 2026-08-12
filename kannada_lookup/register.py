"""HTML word register: every lookup ever made, as a self-contained page.

Regenerated on demand from the SQLite store (tray menu → "Open word
register") — no server, no staleness, opens in the default browser. Meant
for revisiting and learning words: word + part of speech, English meaning,
English example, synonyms, translation, native example.
"""

import html
import time
from pathlib import Path

from .store import DB_PATH, LookupStore

OUT_DIR = DB_PATH.parent
_STEM = "register"

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<!-- Regenerated on every open, so a cached copy is always the stale one.
     Belt-and-braces with the cache-busting query main.py appends: this
     covers a manual reload or a bookmark, which carry no query. -->
<meta http-equiv="cache-control" content="no-store">
<title>Word Register</title>
<style>
  :root {{ color-scheme: light; }}
  body {{
    margin: 0; padding: 32px 24px; background: #f6f8fc;
    font-family: "Segoe UI", system-ui, sans-serif; color: #1a1a1a;
  }}
  .head {{
    max-width: 1100px; margin: 0 auto 20px auto; padding: 20px 24px;
    background: linear-gradient(#fdfdfe, #edf2fb);
    border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.08);
  }}
  h1 {{ margin: 0 0 4px 0; font-size: 20pt; }}
  .sub {{ color: #6a6a6a; font-size: 10.5pt; }}
  #search {{
    margin-top: 12px; width: 100%; max-width: 420px; padding: 8px 12px;
    font-size: 11pt; border: 1px solid #d5dcea; border-radius: 8px;
  }}
  table {{
    max-width: 1100px; margin: 0 auto; width: 100%;
    border-collapse: collapse; background: #ffffff;
    border-radius: 12px; overflow: hidden;
    box-shadow: 0 4px 24px rgba(0,0,0,.06);
  }}
  th, td {{
    text-align: left; vertical-align: top; padding: 10px 14px;
    border-bottom: 1px solid #eef1f7; font-size: 10.5pt;
  }}
  th {{ background: #f0f3fa; font-size: 9.5pt; text-transform: uppercase;
       letter-spacing: .05em; color: #55607a; }}
  .word {{ font-weight: bold; font-size: 12pt; }}
  .pos {{ color: #8a8f9c; font-style: italic; font-size: 9.5pt; }}
  .syn, .exen {{ color: #555; font-style: italic; }}
  .native {{
    font-family: "Noto Sans Kannada", "Nirmala UI", "Segoe UI", sans-serif;
  }}
  .translation {{ font-size: 12.5pt; }}
  .exnative {{ color: #555; font-style: italic; font-size: 10.5pt; }}
  .lang, .date {{ color: #8a8f9c; font-size: 9pt; white-space: nowrap; }}
</style>
</head>
<body>
<div class="head">
  <h1>Word Register</h1>
  <div class="sub">{count} lookups &middot; generated {generated}</div>
  <input id="search" type="search" placeholder="Search word, meaning, synonym&hellip;"
         oninput="filter(this.value)">
</div>
<table>
  <thead><tr>
    <th>Word</th><th>Meaning</th><th>English example</th><th>Synonyms</th>
    <th>Translation</th><th>Language</th><th>Added</th>
  </tr></thead>
  <tbody id="rows">
{rows}
  </tbody>
</table>
<script>
function filter(q) {{
  q = q.toLowerCase();
  for (const tr of document.querySelectorAll("#rows tr"))
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
}}
</script>
</body>
</html>
"""

_ROW = """    <tr>
      <td><span class="word">{word}</span>{pos}</td>
      <td>{meaning}</td>
      <td class="exen">{example_en}</td>
      <td class="syn">{synonyms}</td>
      <td class="native"><div class="translation">{translation}</div>
          <div class="exnative">{example_native}</div></td>
      <td class="lang">{language}</td>
      <td class="date">{date}</td>
    </tr>"""


def generate(store: LookupStore | None = None, out_path: Path | None = None) -> Path:
    """Write the register and return its path.

    Filename carries a timestamp (register-<epoch>.html) instead of the
    fixed `register.html` this used to be. Windows resolves a file:// URL
    for an .html path through the file-type association handler, which
    invokes the browser as `browser.exe --single-argument <path>` — the
    URL wrapper (and any ?query cache-buster on it) never reaches the
    browser at all, only the bare path. With a constant filename every
    open was therefore byte-identical from the browser's point of view,
    so it kept reusing its cached render no matter how fresh the file on
    disk actually was. A path that changes on every generate() is the
    only part of this Windows won't silently discard.

    Stale copies are deleted after the new one is written (not before —
    deleting first would leave a moment with no valid file to open).
    """
    store = store or LookupStore()
    if out_path is None:
        # Milliseconds, not whole seconds: two generate() calls inside the
        # same wall-clock second (a script, or a very fast double-click)
        # would otherwise collide on the same filename and silently
        # reintroduce the exact bug this scheme exists to fix.
        out_path = OUT_DIR / f"{_STEM}-{int(time.time() * 1000)}.html"
    rows = []
    entries = store.all_entries()
    for entry in entries:
        r = entry["result"]
        e = html.escape
        pos = (
            f' <span class="pos">&middot; {e(r.part_of_speech)}</span>'
            if r.part_of_speech
            else ""
        )
        rows.append(
            _ROW.format(
                word=e(r.original),
                pos=pos,
                meaning=e(r.meaning),
                example_en=e(r.example_en),
                synonyms=e(r.synonyms),
                translation=e(r.translation),
                example_native=e(r.example_native),
                language=e(entry["language"]),
                date=time.strftime("%d %b %Y", time.localtime(entry["created_at"])),
            )
        )
    page = _PAGE.format(
        count=len(entries),
        generated=time.strftime("%d %b %Y %H:%M"),
        rows="\n".join(rows) if rows else
        '    <tr><td colspan="7">No lookups yet — select a word and press '
        "the Forward button.</td></tr>",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    _clean_stale(out_path)
    return out_path


def _clean_stale(current: Path) -> None:
    """Remove earlier register-*.html files, keeping only the one just
    written. Best-effort: a locked file (still open in a browser tab from
    a previous click) is left for next time rather than raising — a
    leftover file is harmless, an unhandled exception here would take
    down the whole "open register" action over cache hygiene."""
    for old in current.parent.glob(f"{_STEM}-*.html"):
        if old != current:
            try:
                old.unlink()
            except OSError:
                pass
