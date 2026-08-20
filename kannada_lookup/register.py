"""HTML word register: every lookup ever made, as a self-contained page.

Regenerated on demand from the SQLite store (tray menu → "Open word
register") - no server, no staleness, opens in the default browser. Meant
for revisiting and learning words: word + part of speech, English meaning,
English example, synonyms, translation, native example.
"""

import html
import itertools
import time
from pathlib import Path

from .store import DB_PATH, LookupStore

OUT_DIR = DB_PATH.parent
_STEM = "register"
_counter = itertools.count()

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
  /* Tokens from DESIGN.md. Every text/background pair here was checked
     against WCAG AA in both themes; none is below 4.5:1. */
  :root {{
    color-scheme: light dark;
    --primary:#14171C; --secondary:#5B6472; --tertiary:#7150F0;
    --neutral:#F6F8FC; --surface:#FFFFFF; --outline:#E3E8F0;
    --tertiary-subtle:#F1EDFF;
    --header-surface:#EEF2F9; --header-on-surface:#4A5261;
    --shadow:0 4px 24px rgba(0,0,0,.06);
    /* Light mode needs no border: the drop shadow defines the table's
       edge. Page-vs-surface is only 1.06:1 on its own, so SOMETHING has
       to draw that boundary — see the dark override below. */
    --table-border:transparent;
    --latin:"Inter","Segoe UI",system-ui,sans-serif;
    --native:"Noto Sans Kannada","Nirmala UI","Segoe UI",sans-serif;
    /* Fills the window instead of sitting in a fixed column that looks
       stranded on a large monitor. Capped because past roughly this the
       eye loses the row it was on. */
    --page-max:1680px;
  }}
  /* Follows the OS rather than offering a toggle — the page is opened,
     read and closed, so a per-visit control would be noise. The accent
     LIGHTENS here: the light-mode violet is unreadable on dark. */
  @media (prefers-color-scheme: dark) {{
    :root {{
      --primary:#E7E9EE; --secondary:#A2AAB8; --tertiary:#B7A4FF;
      --neutral:#111318; --surface:#1A1D23; --outline:#2C313A;
      --tertiary-subtle:#23212E;
      --header-surface:#20242B; --header-on-surface:#A2AAB8;
      /* A drop shadow does nothing on a dark ground, so it is dropped —
         but that left NOTHING marking where the table ends: surface vs
         page measures 1.10:1 and header vs surface 1.08:1, both
         imperceptible. The result read as a header that did not line up
         with the table and dates floating outside it. An explicit border
         (1.29:1 against the surface) draws the edge instead, which is
         how dark UIs generally replace elevation. */
      --shadow:none;
      --table-border:#2C313A;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 24px 64px; background: var(--neutral);
    font-family: var(--latin); color: var(--primary);
  }}
  .head {{ width: min(100%, var(--page-max)); margin: 0 auto 20px auto; }}
  h1 {{ margin: 0 0 4px 0; font-size: 28px; font-weight: 600;
       letter-spacing: -.02em; line-height: 1.2; }}
  .sub {{ color: var(--secondary); font-size: 13.5px; }}
  #search {{
    margin-top: 16px; width: 100%; max-width: 420px; height: 40px;
    padding: 0 12px; font: inherit; font-size: 15px;
    color: var(--primary); background: var(--surface);
    border: 1px solid var(--outline); border-radius: 8px; outline: none;
  }}
  #search:focus {{
    border-color: var(--tertiary); box-shadow: 0 0 0 2px var(--tertiary-subtle);
  }}
  /* NO overflow:hidden — it silently disables position:sticky on the
     header. Rounded corners come from the corner cells instead. */
  table {{
    width: min(100%, var(--page-max)); margin: 0 auto;
    border-collapse: separate; border-spacing: 0;
    background: var(--surface); border-radius: 12px;
    box-shadow: var(--shadow); table-layout: fixed;
    border: 1px solid var(--table-border);
  }}
  th, td {{ overflow-wrap: anywhere; text-align: left; vertical-align: top; }}
  th {{
    position: sticky; top: 0; z-index: 5;
    background: var(--header-surface); color: var(--header-on-surface);
    font-size: 11px; font-weight: 600; letter-spacing: .07em;
    text-transform: uppercase; padding: 8px 16px; min-height: 36px;
    border-bottom: 1px solid var(--outline);
  }}
  th:first-child {{ border-top-left-radius: 12px; }}
  th:last-child {{ border-top-right-radius: 12px; }}
  tbody tr:last-child td:first-child {{ border-bottom-left-radius: 12px; }}
  tbody tr:last-child td:last-child {{ border-bottom-right-radius: 12px; }}
  td {{
    padding: 14px 16px; border-bottom: 1px solid var(--outline);
    font-size: 15px; line-height: 1.55;
  }}
  tbody tr:last-child td {{ border-bottom: none; }}
  /* Tint, never a border change — a border would shift layout on hover. */
  tbody tr:hover {{ background: var(--tertiary-subtle); }}

  .word {{ font-weight: 600; font-size: 18px; letter-spacing: -.01em; }}
  .pos {{ color: var(--secondary); font-style: italic; font-size: 13.5px; }}
  .syn, .exen {{ color: var(--secondary); font-style: italic; font-size: 13.5px; }}
  .native {{ font-family: var(--native); }}
  /* Native script is set LARGER and looser than the Latin around it:
     conjuncts carry more detail per glyph and collide at Latin leading. */
  .translation {{ font-size: 19px; font-weight: 500; line-height: 1.7; }}
  .synnative {{ color: var(--secondary); font-style: italic;
                font-size: 15px; line-height: 1.75; }}
  .exnative {{ color: var(--secondary); font-style: italic;
               font-size: 15px; line-height: 1.75; }}
  /* No white-space:nowrap here. With it, "13 Aug 2026" needed 93px of a
     84px cell and spilled 8px past the table's right edge — nowrap means
     the text simply cannot fit, at any window size. Allowing it to wrap
     makes overflow impossible; the widened columns below mean it rarely
     has to. */
  .lang, .date {{ color: var(--secondary); font-size: 13px; }}

  /* Type sizes never shrink with the window — shrinking the native column
     is the one thing that genuinely hurts legibility. Only padding gives,
     and below each breakpoint the least-scanned columns drop out. */
  @media (max-width: 1400px) {{
    td {{ padding: 13px; }} th {{ padding: 0 13px; }}
  }}
  @media (max-width: 1000px) {{
    body {{ padding: 24px 14px 48px; }}
    .lang, .date, th.h-lang, th.h-date {{ display: none; }}
    td {{ padding: 12px 11px; }} th {{ padding: 0 11px; }}
  }}
  @media (max-width: 720px) {{
    .syn, .exen, th.h-syn, th.h-exen {{ display: none; }}
  }}
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
  <!-- Percentages, not pixels: every column grows with the window, so no
       single column swallows the slack on a wide monitor. Weighted by how
       much text each actually holds. -->
  <colgroup>
    <col style="width:11%"><col style="width:18%"><col style="width:16%">
    <col style="width:10%"><col style="width:15%"><col style="width:16%">
    <col style="width:7%"><col style="width:7%">
  </colgroup>
  <thead><tr>
    <th>Word</th><th>Meaning</th><th class="h-exen">English example</th>
    <th class="h-syn">Synonyms</th>
    <th>Translation</th><th>Native example</th>
    <th class="h-lang">Language</th><th class="h-date">Added</th>
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
          <div class="synnative">{synonyms_native}</div></td>
      <td class="native exnative">{example_native}</td>
      <td class="lang">{language}</td>
      <td class="date">{date}</td>
    </tr>"""


def generate(store: LookupStore | None = None, out_path: Path | None = None) -> Path:
    """Write the register and return its path.

    Filename carries a timestamp (register-<epoch>.html) instead of the
    fixed `register.html` this used to be. Windows resolves a file:// URL
    for an .html path through the file-type association handler, which
    invokes the browser as `browser.exe --single-argument <path>` - the
    URL wrapper (and any ?query cache-buster on it) never reaches the
    browser at all, only the bare path. With a constant filename every
    open was therefore byte-identical from the browser's point of view,
    so it kept reusing its cached render no matter how fresh the file on
    disk actually was. A path that changes on every generate() is the
    only part of this Windows won't silently discard.

    Stale copies are deleted after the new one is written (not before -
    deleting first would leave a moment with no valid file to open).
    """
    store = store or LookupStore()
    if out_path is None:
        out_path = _unique_path()
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
                synonyms_native=e(r.synonyms_native),
                example_native=e(r.example_native),
                language=e(entry["language"]),
                date=time.strftime("%d %b %Y", time.localtime(entry["created_at"])),
            )
        )
    page = _PAGE.format(
        count=len(entries),
        generated=time.strftime("%d %b %Y %H:%M"),
        rows="\n".join(rows) if rows else
        '    <tr><td colspan="8">No lookups yet — select a word and press '
        "the Forward button.</td></tr>",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    _clean_stale(out_path)
    return out_path


def _unique_path() -> Path:
    """A filename never used before in this process.

    Two generate() calls can land in the same millisecond, so a bare
    timestamp is not enough. Checking `exists()` instead is worse than it
    looks: _clean_stale deletes the previous file, so a name from an
    earlier click is "free" again and could be handed out a second time -
    and the browser may still hold *that* name in its cache, which is the
    whole failure being designed out.

    The monotonic counter never yields the same name twice for the life of
    the process, which is exactly the window a browser's cache spans here.
    """
    return OUT_DIR / f"{_STEM}-{int(time.time() * 1000)}-{next(_counter)}.html"


def _clean_stale(current: Path) -> None:
    """Remove earlier register-*.html files, keeping only the one just
    written. Best-effort: a locked file (still open in a browser tab from
    a previous click) is left for next time rather than raising - a
    leftover file is harmless, an unhandled exception here would take
    down the whole "open register" action over cache hygiene."""
    for old in current.parent.glob(f"{_STEM}-*.html"):
        if old != current:
            try:
                old.unlink()
            except OSError:
                pass


def generate_and_open(store: LookupStore | None = None) -> Path:
    """Regenerate the register and open it. This is the whole "Open word
    register" action; main.py's tray handler is a one-line call to this so
    the browser-launch behaviour is testable without constructing App
    (which needs live mouse/keyboard hooks in __init__).

    Opens the raw filesystem path, NEVER a file:// URI
    (webbrowser.open(str(path)), not a QUrl/pathlib .as_uri()). Reproduced
    live on a real machine: QDesktopServices.openUrl(QUrl.fromLocalFile(...))
    returned success but opened nothing, and feeding the IDENTICAL file://
    string to plain os.startfile() also opened nothing - so this isn't a
    Qt bug, it's Windows' `file:` URL-protocol resolution being unreliable
    independent of the `.html` extension association a raw path uses.
    os.startfile() on the bare path succeeded every time in the same test.
    webbrowser.open() on Windows calls os.startfile() with whatever string
    it receives, so passing the raw path here is what avoids the broken
    codepath - building a URI at any point in this call defeats the fix.
    """
    import webbrowser

    path = generate(store)
    webbrowser.open(str(path))
    return path
