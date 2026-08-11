# Word Lookup — Android

Select text in any app; see a dictionary card — meaning, synonyms, an example, and the
translation into whatever language you picked. Same Gemini prompt and card layout as the
Windows app in [`../kannada_lookup/`](../kannada_lookup), reimplemented natively since none
of that Python (pynput, PySide6, sqlite3) runs on Android.

## Two trigger paths

Android has no simple "text was selected" callback for a normal app — the only real-time
signal (`TYPE_VIEW_TEXT_SELECTION_CHANGED`) requires an `AccessibilityService`, which must be
enabled by hand in Settings. So the app ships two ways to the same card:

- **Menu** (`ProcessTextActivity`) — select text anywhere → "Word Lookup" appears next to
  Copy/Share in the toolbar. No special permission. Works almost everywhere.
- **Instant** (`SelectionAccessibilityService` + `OverlayHost`) — the card appears the moment
  you select text, no tap. Needs **Accessibility** + **Display over other apps** granted by
  hand (see below). Occasionally returns nothing in Chrome/WebView; Menu is the fallback.

Pick a mode in the app's home screen (Instant / Menu only / Both — default Both).

## Permissions walkthrough

1. **Display over other apps** — Home screen → Permissions → tap "Open Settings" next to it,
   or Settings → Apps → Word Lookup → "Display over other apps" → Allow.
2. **Accessibility service** — same screen, "Open Settings" next to Accessibility. On
   **Android 13+**, a sideloaded (non-Play-Store) app is blocked from Accessibility until you
   first do: Settings → Apps → Word Lookup → **⋮ (top right)** → **Allow restricted settings**.
   Do this *before* trying the Accessibility toggle — it's the single most common place to
   get stuck. The home screen has a shortcut button straight to App Info for this.
3. **Notifications** — requested automatically on first open (Android 13+ only); used for the
   low-importance background-sync notification channel, nothing else.

Play Store distribution isn't viable for the Instant path (their policy restricts
Accessibility-API usage to accessibility-purpose apps), so this is sideload-only by design.

## Building

No Gradle wrapper jar is committed — it's a compiled binary, can't be authored as plain
text. Two ways to get one:

- **Android Studio (recommended for local dev):** File → Open → select `android/`. Studio
  detects the missing wrapper and regenerates `gradle/wrapper/gradle-wrapper.jar`
  automatically on first sync.
- **CI (GitHub Actions):** [`../.github/workflows/android.yml`](../.github/workflows/android.yml)
  installs Gradle directly via `gradle/actions/setup-gradle` and calls `gradle`, not
  `./gradlew` — it never needs the wrapper jar at all.

```powershell
# from android/, once you have a wrapper (or substitute a system `gradle`):
.\gradlew.bat :app:test            # JVM unit tests — no device/emulator needed
.\gradlew.bat :app:assembleDebug   # debug APK, installable without any signing setup
```

## Signing (why it matters before your first real install)

Sign with **one fixed keystore**, not the auto-generated debug key. A CI runner (or a fresh
`./gradlew` invocation with no keystore configured) creates a new debug key every time, and
Android refuses to install an APK over one signed by a *different* key — every rebuild would
mean uninstalling and losing your local word cache.

```powershell
keytool -genkeypair -v -keystore release.jks -alias wordlookup -keyalg RSA -keysize 2048 -validity 10000
```

Copy `keystore.properties.example` → `keystore.properties` (gitignored) and fill in the path
and passwords for **local** release builds. For **CI** builds, base64-encode the same `.jks`
and add these as repo secrets (Settings → Secrets and variables → Actions):
`WORDLOOKUP_KEYSTORE_B64`, `WORDLOOKUP_KEYSTORE_PASSWORD`, `WORDLOOKUP_KEY_ALIAS`,
`WORDLOOKUP_KEY_PASSWORD`. Without these, the release build type quietly falls back to debug
signing so the workflow still goes green on a fresh clone — just don't expect in-place
updates to install cleanly until the real keystore is wired in.

## Installing

Download `WordLookup-apk` from the [Android workflow](../.github/workflows/android.yml)'s
latest run (Actions tab → Android → latest green run → Artifacts), transfer it to the phone,
and tap to install — you'll need to allow installs from that source once (Settings prompts
you automatically the first time). Then walk through the Permissions section above.

## Sync with the desktop app

Both apps cache every lookup forever (SQLite on desktop, Room on Android, same schema).
Optionally, both can sync that cache through **one private GitHub Gist**, so a word looked up
on your phone shows up in the desktop word register and vice versa.

1. Create a GitHub [personal access token](https://github.com/settings/tokens) with only the
   **`gist`** scope.
2. Paste it into the app's Settings screen (and into desktop `.env` as `GITHUB_PAT=...`, see
   the root README).
3. That's it — Android syncs automatically when connected (a WorkManager job constrained to
   `NetworkType.CONNECTED`, so it never fires on a dead connection and never blocks a lookup
   waiting for one), plus a manual "Sync now" if you don't want to wait. Desktop syncs on
   startup and via the tray menu.

No PAT set → sync is simply inactive; nothing else about either app changes. See
[`../kannada_lookup/sync.py`](../kannada_lookup/sync.py) and
`app/src/main/java/com/harish/wordlookup/data/sync/` for the merge protocol (last-write-wins
by `updated_at`, tombstones for deletions).

## Project layout

```
android/
  app/src/main/java/com/harish/wordlookup/
    data/            Gemini client, Room cache, settings, sync — no Android UI deps
    ui/               Compose screens + the shared LookupCard
    service/          ProcessTextActivity, SelectionAccessibilityService, LookupTileService
  app/src/test/       JVM unit tests (Robolectric + MockWebServer, no device needed)
```

## Known limitation

`minSdk 24` (the `TileService` floor) but the adaptive launcher icon
(`mipmap-anydpi-v26/`) has no legacy PNG fallback for API 24–25 devices — raster launcher
icons are binary files this toolchain can't author as text. Low-impact in practice (this app
targets Android 13+), but a real gap if you sideload onto an API 24/25 device: add
`mipmap-hdpi/ic_launcher.png` etc. yourself, or raise `minSdk` to 26.
