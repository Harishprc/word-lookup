"""Re-fetch cached lookups that predate the synonyms_native column (v4).

Words already in the cache are served from cache and never hit the API
again, so they would keep an empty native-synonyms row forever. This walks
the cache and re-asks the provider for each affected word.

Re-fetching rather than deleting is deliberate: deleting would empty the
word register, which is the whole point of keeping the history. An
in-place refresh keeps every row and fills the new field. It also picks up
the current model and prompt, so any older wrong-script translation gets
corrected on the way through.

Safe to interrupt and re-run: it only touches rows whose synonyms_native
is still empty, so a second run resumes where the first stopped.

    python scripts/backfill_native_synonyms.py            # the exe's cache
    python scripts/backfill_native_synonyms.py --dry-run  # list only
    python scripts/backfill_native_synonyms.py --db PATH  # a specific cache
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kannada_lookup import config  # noqa: E402
from kannada_lookup.store import LookupStore  # noqa: E402
from kannada_lookup.translator import GeminiProvider, LookupFailed  # noqa: E402

# Gap between calls. The binding limit here is requests-per-MINUTE, not
# per-day: the default flash-class model allows only a handful per minute
# on the free tier, and a first attempt at 1s spacing failed 80 of 93
# words on 429s. ~7s keeps a bulk pass under that ceiling. Normal use is
# nowhere near it — this only matters when sweeping the whole cache.
_PAUSE_S = 7.0

# On a 429, wait this long before retrying the same word. Per-minute
# limits clear on their own, so a couple of patient retries rescues a run
# that would otherwise abandon most of the cache.
_BACKOFF_S = 45.0
_MAX_RETRIES = 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    args = parser.parse_args()

    store = LookupStore(args.db) if args.db else LookupStore()

    # all_entries() hides tombstones, which is what we want: a deleted word
    # should stay deleted rather than being resurrected by a refresh.
    stale = [
        e for e in store.all_entries() if not e["result"].synonyms_native.strip()
    ]
    if args.limit:
        stale = stale[: args.limit]

    print(f"cache: {len(store.all_entries())} live rows")
    print(f"missing native synonyms: {len(stale)}")
    if not stale:
        print("nothing to do")
        return 0

    if args.dry_run:
        for e in stale:
            print(f"  would refresh: {e['result'].original}  [{e['language']}]")
        return 0

    if not config.GEMINI_API_KEY:
        print("No GEMINI_API_KEY set — nothing to call.", file=sys.stderr)
        return 1

    providers: dict[str, GeminiProvider] = {}
    done = failed = 0

    for i, entry in enumerate(stale, 1):
        word = entry["result"].original
        language = entry["language"]
        provider = providers.get(language)
        if provider is None:
            provider = providers[language] = GeminiProvider(
                config.GEMINI_API_KEY, config.GEMINI_MODEL, language
            )

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = provider.lookup(word)
                store.put(result, language, provider=type(provider).__name__)
                done += 1
                extra = result.synonyms_native or "(none returned)"
                print(
                    f"[{i}/{len(stale)}] {word} -> {result.translation}   {extra}",
                    flush=True,
                )
                break
            except LookupFailed as e:
                # Rate limits clear on their own; anything else will not,
                # so only the former is worth waiting out.
                retryable = "rate limit" in str(e).lower() or "quota" in str(e).lower()
                if retryable and attempt < _MAX_RETRIES:
                    print(
                        f"[{i}/{len(stale)}] {word}: rate limited, "
                        f"waiting {_BACKOFF_S:.0f}s (attempt {attempt})",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(_BACKOFF_S)
                    continue
                failed += 1
                print(f"[{i}/{len(stale)}] {word}: {e}", file=sys.stderr, flush=True)
                break
            except Exception as e:  # never abort the whole run on one word
                failed += 1
                print(
                    f"[{i}/{len(stale)}] {word}: unexpected: {e}",
                    file=sys.stderr,
                    flush=True,
                )
                break

        time.sleep(_PAUSE_S)

    print(f"\nrefreshed {done}, failed {failed}")
    if failed:
        print("re-run to retry the failures — already-refreshed rows are skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
