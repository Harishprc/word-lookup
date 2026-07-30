# Word Lookup

Select any English word or phrase in **any** app (PDF reader, Word, Slack, browser…), press the **Forward side button** on your mouse, and a small floating card near the cursor shows a mini dictionary entry: part of speech, English meaning, synonyms, an example sentence, and the translation (with its own example) **in whatever language you choose on first run** — Kannada, Hindi, Spanish, Japanese, 20+ others.

## Which mouse works

Any mouse whose side buttons send the standard **Forward** (XButton2) signal — i.e. any ordinary 5-button mouse. No vendor software required; built and tested on an **ASUS MW203**, which ships with no remap utility at all, proving the point. If your mouse has no side buttons, or a gaming mouse whose extra buttons need vendor software to map, assign one of them to "Forward" first — this tool listens for that signal, not a specific piece of hardware.

## How it works

1. A low-level global mouse hook watches for the Forward button. While the tool is ON, the click is **swallowed** on Windows (and macOS) so the app underneath never also navigates "Forward"; X11 Linux can't suppress it — the app receives it too, documented below.
2. The tool snapshots your clipboard, sends a synthetic copy shortcut, waits for the clipboard to actually change (proof the copy landed), reads the selection, then **restores your clipboard**.
3. The text goes to the **Gemini API** (free Google AI Studio key), which returns the full dictionary card in one call.
4. A frameless, always-on-top popup — off-white with a faint blue gradient, rounded corners, drop shadow — appears at the cursor without stealing focus, and auto-dismisses after 6 s (or click it).

## First run

The first time you launch, a one-time setup dialog appears:

1. **Pick your target language** from the dropdown (Kannada, Hindi, Tamil, Spanish, French, Japanese, … 25 total).
2. **Paste a Gemini API key** if `.env` doesn't have one yet.

Both are saved (`data/settings.json` + `.env`) — the dialog never appears again unless you delete `data/settings.json`. Running from source, those live in the project folder; running the .exe, they live in `%LOCALAPPDATA%\WordLookup\`.

Your key is yours: it is written to a local `.env` that is gitignored and never leaves your machine.

## Install

### Option A — download the .exe (no Python needed)

Grab `WordLookup.exe` from the [**Releases**](https://github.com/Harishprc/word-lookup/releases/latest) page and run it. Settings, your API key and the word register are stored in `%LOCALAPPDATA%\WordLookup\`.

> **Expect a SmartScreen warning.** The build is unsigned (code-signing certificates cost money), and it installs a global low-level mouse hook — a combination antivirus heuristics dislike. Click *More info → Run anyway*, or use Option B if you'd rather run code you can read. Every line of the source is in this repo, and the workflow that builds the exe is in [`.github/workflows/release.yml`](.github/workflows/release.yml).

### Option B — run from source (recommended)

Requires Python 3.10+.

```powershell
git clone https://github.com/Harishprc/word-lookup.git
cd word-lookup
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

No manual `.env` editing needed — the first-run dialog above handles the API key. (Manual alternative: `copy .env.example .env` and paste `GEMINI_API_KEY=...` yourself.)

**Getting the API key (free, ~1 minute):** [aistudio.google.com](https://aistudio.google.com) → sign in → **Get API key** → **Create API key**. No credit card, no cloud console.

**Cost:** free tier is roughly **1,500 lookups/day**, permanently, no card required. Caveat: Google may use free-tier prompts to improve its models — fine for word lookups, don't select passwords. If Google ever rotates model names (a "model not found" popup), set `GEMINI_MODEL=gemini-2.5-flash` in `.env`.

## Run

**Recommended — install the shortcuts once:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_startup.ps1
```

Creates a **desktop icon** (start it any time) and a **Startup entry** (auto-starts on every Windows login — survives reboots). Undo with `scripts\uninstall_startup.ps1`.

Manual alternative: `.venv\Scripts\pythonw.exe run.pyw` (Windows) or `python -m kannada_lookup` (macOS/Linux, experimental — see below).

Either way a tray icon appears (a native glyph of your chosen language — ಕ, अ, த…). Launching twice is safe — the second instance shows "already running" and exits.

## Use

| Action | Effect |
|---|---|
| Select text → **Forward button** | Dictionary card at cursor |
| **Ctrl+Alt+K** or tray menu → *Enabled* | Toggle ON/OFF globally |
| Tray menu → *Open word register* | Browse every word you've looked up |
| Tray menu → *Quit* | Exit |

**ON/OFF switch:** lookups only ever fire on the button press — never on selection alone. Toggle OFF when you're not reading; the Forward button then works normally again (icon turns gray).

## Word register

Every lookup is saved. Tray menu → **Open word register** opens a self-contained HTML page (`data/register.html`) in your browser: word, part of speech, English meaning, English example, synonyms, translation, and the native example — searchable, newest first. Good for revisiting and actually learning the words you looked up.

## Offline cache

Every successful lookup is saved to `data/lookups.db` (SQLite), keyed per language. Repeat lookups are **instant, free, and work with no internet** — the API is only called for words you've never looked up in that language. No expiry. Delete `data/lookups.db` to clear it (also wipes the register).

**Bring your own dictionary PDF?** We evaluated shipping an offline English-definition fallback from a dictionary PDF and decided against it for now: a generic parser can't safely extract clean word→meaning pairs from an arbitrary PDF's layout (many "dictionaries" are actually thesauruses/metaphor collections with no clean definition line — verified against a real example), and dictionary content is typically copyrighted, so nothing PDF-derived should ever leave your machine. If you want this fallback, drop a PDF in the project root — it's already gitignored (`*.pdf`, plus `data/` where any parsed output would live) so it and anything extracted from it stay device-local, never pushed to GitHub, even by accident.

## Providers

Selected via `PROVIDER=` in `.env`; the factory in `kannada_lookup/translator.py` is the swap point.

| Provider | `.env` value | Cost | Returns |
|---|---|---|---|
| **Gemini** (default) | `gemini` | Free (~1,500/day, AI Studio key) | Full card: part of speech, meaning, synonyms, both examples, translation |
| Google Cloud Translation | `google` | Free 500k chars/month, **needs GCP billing card** | Translation only |
| Claude / GPT (future) | — | Paid ($5 min credit) | Same full card, no training on your data |

## Permissions & caveats

- **No admin rights needed** on Windows. Exception: apps running elevated (admin) don't receive synthetic input from a non-elevated process — run the script as admin only if you need lookups inside such apps.
- Some corporate antivirus/EDR flags global input hooks; whitelist `pythonw.exe` if the hook silently stops working.
- Clipboard restore is **text-only**: if your clipboard held an image or files, a lookup replaces it. Copy-heavy workflows: toggle OFF.
- The API key lives only in `.env` (gitignored) — never hardcoded.
- Selections are capped at 500 characters (word-boundary truncation) to bound API quota use.

## macOS / Linux (EXPERIMENTAL — never run on real hardware)

All OS-specific code lives in `kannada_lookup/platforms/` (clipboard + mouse hook); everything else is portable. The mac/linux backends are written against documented APIs but the author had no non-Windows machine to test on — expect to debug.

Run with `python -m kannada_lookup` (no `.pyw` outside Windows).

- **macOS:** grant the terminal/Python **Accessibility** and **Input Monitoring** permissions (System Settings → Privacy & Security), else the hook sees nothing. Copy chord is Cmd+C; Forward click is swallowed via a Quartz event tap. Autostart: wrap the command in a LaunchAgent plist under `~/Library/LaunchAgents/`.
- **Linux:** install `xclip` (X11) or `wl-clipboard` (Wayland). **The Forward click cannot be swallowed on X11** — the app under the cursor also receives it (pynput limitation, documented in `platforms/linux.py`). Autostart: a `.desktop` file in `~/.config/autostart/`.

## Roadmap (not built)

- **Dictionary dataset import:** a proper word→definition source (not a PDF thesaurus) for the offline layer.
- **Paid LLM provider:** Claude/GPT via the same `TranslationProvider` ABC, for when data-privacy (no training on prompts) matters.
- **Packaging:** single-exe is done (see Releases); a signed installer is not — needs a paid code-signing certificate.
- **Android:** separate app (this codebase can't run on Android) — floating-bubble lookup via `ACTION_PROCESS_TEXT` + overlay, same Gemini prompt.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

Unit tests mock the HTTP layer — no API key or network needed.
