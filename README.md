# Word Lookup

Select an English word or phrase in **any** app (PDF reader, Word, Slack, browser…), press the **Forward side button** on your mouse, and a floating card appears at the cursor: part of speech, English meaning, synonyms, an example sentence, plus the translation and its own example **in a language you pick on first run**.

## Supported languages

26 targets, chosen on first run, switchable from tray menu → **Translation language**. The tray icon becomes a native glyph of the current language.

**Indian:** Kannada (ಕ), Hindi (अ), Tamil (த), Telugu (త), Malayalam (മ), Marathi (म), Bengali (ব), Gujarati (ગ), Punjabi (ਪ), Odia (ଓ), Urdu (ا)

**World:** Spanish (Ñ), French (Ç), German (ß), Swedish (Å), Japanese (あ), Korean (한), Chinese Simplified (中), Arabic (ع), Russian (Я), Portuguese (Ã), Italian (È), Turkish (Ş), Vietnamese (ơ), Thai (ท), Indonesian (ᬅ)

The list is only a dropdown. The language name is interpolated into the Gemini prompt, so any language the model knows works. Add yours in [`kannada_lookup/languages.py`](kannada_lookup/languages.py).

## Which mouse works

Any mouse whose side button sends the standard **Forward** (XButton2) signal, i.e. any ordinary 5-button mouse. No vendor software needed (built and tested on an ASUS MW203, which ships with no remap utility). Gaming mice with non-standard extra buttons: map one to "Forward" first. The tool listens for the signal, not the hardware.

## On a laptop (no Forward button)

Bind a **keyboard shortcut** instead. You pick it; there is no default and nothing changes until you set one.

- **New install:** first-run dialog → *Lookup shortcut* box → press your keys.
- **Already installed:** tray menu → **Change shortcuts…**

**The shortcut is swallowed** on Windows and macOS. The focused app never sees it, so `Ctrl+Alt+D` won't also insert an endnote in Word. Same mechanism that stops the Forward button navigating. X11 Linux can't suppress it (see platform notes).

The recorder warns on costly picks (`Ctrl+W` closes documents, `Ctrl+Q` quits apps, `Ctrl+C` is Copy) but never blocks you.

## How it works

1. A low-level global mouse hook watches the Forward button; while ON the click is **swallowed** (Windows/macOS) so the app underneath doesn't also navigate.
2. The tool snapshots your clipboard, sends a synthetic copy, waits for the clipboard to actually change (proof the copy landed), reads the selection, then **restores your clipboard**.
3. The text goes to the **Gemini API** (free Google AI Studio key), which returns the whole card in one call.
4. A frameless, always-on-top popup appears at the cursor without stealing focus and auto-dismisses after 6 s (or click it).

## First run

A one-time dialog asks for:

1. Your **target language** from the dropdown.
2. A **Gemini API key**, if `.env` doesn't have one.

Saved to `data/settings.json` + `.env`; never shown again unless you delete `data/settings.json`. Running from source those live in the project folder; running the .exe, in `%LOCALAPPDATA%\WordLookup\`. The key is written to a gitignored `.env` and never leaves your machine.

## Install

### ⬇ Option A: download `WordLookup.exe` (no Python needed)

> ### **[Download WordLookup.exe →](https://github.com/Harishprc/word-lookup/releases/latest/download/WordLookup.exe)**
>
> Single file, ~50 MB, no installer. Double-click and it runs: a tray icon appears and the first-run dialog asks for your language and API key. All other builds and the SHA256 hashes are on the [Releases](https://github.com/Harishprc/word-lookup/releases/latest) page.

Settings, key and register live in `%LOCALAPPDATA%\WordLookup\`.

> **Windows will warn you twice.** The build is unsigned (certificates cost hundreds a year) and installs a global low-level mouse hook, a combination antivirus heuristics dislike. Both are *reputation* checks, not malware detections.
>
> 1. **On download:** "WordLookup.exe isn't commonly downloaded" → Edge **⋯** → **Keep**; Chrome **⌄** → **Keep**.
> 2. **On first run:** SmartScreen → **More info** → **Run anyway**.
>
> **Verify the download.** Every release lists its SHA256 in the release notes:
>
> ```powershell
> Get-FileHash .\WordLookup.exe -Algorithm SHA256
> ```
>
> A match means the file is exactly what [`.github/workflows/release.yml`](.github/workflows/release.yml) built from the tagged source. Your own builds won't match, because PyInstaller embeds timestamps and build paths, so builds aren't byte-reproducible.
>
> Rather not trust a binary at all? Use Option B.

### Option B: run from source

Requires Python 3.10+. The route to take if you'd rather not run an unsigned binary, want to change the code, or aren't on Windows (there is no mac/Linux build).

```powershell
git clone https://github.com/Harishprc/word-lookup.git
cd word-lookup
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

The first-run dialog handles the API key (manual alternative: `copy .env.example .env` and paste `GEMINI_API_KEY=...`).

**Get a key (free, ~1 min):** [aistudio.google.com](https://aistudio.google.com) → sign in → **Get API key** → **Create API key**. No credit card, no cloud console.

**Cost:** free, permanently, roughly 1,500 lookups/day on the default model. Repeat words come from the local cache without touching the API.

**Speed:** default `gemini-flash-lite-latest`, measured 1.4-3.1 s per lookup against the real API. `gemini-flash-latest` measured 2-4x slower (4.4 s to over 10 s, occasionally timing out). Flash-lite does invent wrong-script answers more often on its own, but every reply is now checked against the target script and retried once on a miss (see `languages.uses_expected_script`), so accuracy is handled structurally instead of by paying the slower model's latency on every lookup. Set `GEMINI_MODEL=gemini-flash-latest` in `.env` to trade the other way.

Caveats: Google may use free-tier prompts to improve its models. Fine for word lookups, but don't select passwords. If model names rotate (a "model not found" popup), set `GEMINI_MODEL=gemini-2.5-flash` in `.env`.

## Run

**Recommended, install the shortcuts once:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_startup.ps1
```

Creates a **desktop icon** and a **Startup entry** (auto-starts on every Windows login, survives reboots). Undo with `scripts\uninstall_startup.ps1`.

Manual alternative: `.venv\Scripts\pythonw.exe run.pyw` (Windows) or `python -m kannada_lookup` (macOS/Linux, experimental, see below).

Either way a tray icon appears (a native glyph of your language: ಕ, अ, த…). Launching twice is safe; the second instance says "already running" and exits.

## Use

| Action | Effect |
|---|---|
| Select text → **Forward button** | Dictionary card at cursor |
| Select text → **your lookup shortcut** | Same, for laptops. Set it yourself, see above |
| **Ctrl+Alt+K** or tray → *Enabled* | Toggle ON/OFF globally |
| Tray → *Change shortcuts…* | Rebind the lookup and toggle keys |
| Tray → *Translation language* | Switch target language, takes effect next lookup |
| Tray → *Open word register* | Browse every word you've looked up |
| Tray → *Quit* | Exit |

Lookups fire only on the button press, never on selection alone. The toggle shortcut keeps working while the tool is OFF (otherwise there'd be no way back on from the keyboard); when OFF the Forward button works normally again and the icon turns gray. Both shortcuts are stored in `data/settings.json`.

## Word register

Every lookup is saved. Tray → **Open word register** opens a self-contained HTML page in your browser: word, part of speech, English meaning and example, synonyms, translation, native example, searchable and newest first.

The page is written to `data/register-<timestamp>.html`, a fresh filename each time, and the previous one is deleted. The timestamp is load-bearing: Windows resolves a `file://` URL for an `.html` path through the file-type handler, which launches the browser with the bare path and discards any cache-busting query. With a constant filename the browser kept serving its cached render while the file on disk was current, and changing the *filename* is the only part of that Windows preserves.

## Offline cache

Every successful lookup is saved to `data/lookups.db` (SQLite), keyed per language. Repeats are **instant, free, and work with no internet**; the API is only called for words new to that language. No expiry. Delete `data/lookups.db` to clear it (this also wipes the register).

**Bring your own dictionary PDF?** Evaluated and rejected for now: a generic parser can't safely extract clean word→meaning pairs from an arbitrary PDF's layout (many "dictionaries" are thesauruses or metaphor collections with no clean definition line, verified against a real example), and dictionary content is typically copyrighted, so nothing PDF-derived should leave your machine. If you want the fallback anyway, drop a PDF in the project root. `*.pdf` and `data/` are already gitignored, so it and anything parsed from it stay device-local.

## Providers

Selected via `PROVIDER=` in `.env`; the factory in `kannada_lookup/translator.py` is the swap point.

| Provider | `.env` value | Cost | Returns |
|---|---|---|---|
| **Gemini** (default) | `gemini` | Free (AI Studio key, no card) | Full card: part of speech, meaning, synonyms, both examples, translation |
| Google Cloud Translation | `google` | Free 500k chars/month, **needs GCP billing card** | Translation only |
| Claude / GPT (future) | n/a | Paid ($5 min credit) | Same full card, no training on your data |

## Permissions & caveats

- **No admin rights needed** on Windows. Exception: elevated apps don't receive synthetic input from a non-elevated process, so run as admin only if you need lookups inside those.
- Some corporate antivirus/EDR flags global input hooks; whitelist `pythonw.exe` if the hook silently stops working.
- Clipboard restore is **text-only**, so a lookup replaces images or files held on the clipboard. Toggle OFF during copy-heavy work.
- The API key lives only in `.env` (gitignored), never hardcoded.
- Selections are capped at 500 characters (word-boundary truncation) to bound API quota use.

## macOS / Linux (EXPERIMENTAL, never run on real hardware)

All OS-specific code lives in `kannada_lookup/platforms/` (clipboard + mouse hook); everything else is portable. The mac/Linux backends are written against documented APIs but the author had no non-Windows machine to test on, so expect to debug. Run with `python -m kannada_lookup` (no `.pyw` outside Windows).

- **macOS:** grant the terminal/Python **Accessibility** and **Input Monitoring** permissions (System Settings → Privacy & Security), else the hook sees nothing. Copy chord is Cmd+C; Forward click is swallowed via a Quartz event tap. Autostart: a LaunchAgent plist in `~/Library/LaunchAgents/`.
- **Linux:** install `xclip` (X11) or `wl-clipboard` (Wayland). **Neither the Forward click nor the keyboard shortcut can be swallowed on X11**, so the focused app receives them too (pynput limitation, documented in `platforms/linux.py`). Pick a shortcut that's inert in the apps you read in; the recorder warns about this on Linux. Autostart: a `.desktop` file in `~/.config/autostart/`.

## Roadmap (not built)

- **Dictionary dataset import:** a proper word→definition source (not a PDF thesaurus) for the offline layer.
- **Paid LLM provider:** Claude/GPT via the same `TranslationProvider` ABC, for when no-training-on-prompts matters.
- **Signed installer:** single-exe is done (see Releases); signing needs a paid code-signing certificate.
- **Android:** separate app (this codebase can't run there), floating-bubble lookup via `ACTION_PROCESS_TEXT` + overlay, same Gemini prompt.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

Unit tests mock the HTTP layer, so no API key or network is needed.
