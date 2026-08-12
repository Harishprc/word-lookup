"""Share the lookup cache between machines via one private GitHub Gist.

The dataset (every lookup ever made) is single-user, append-only, and
keyed by (language, key) with deterministic values — a shared JSON blob
with merge-on-pull, not a database and not realtime sync.

Auth is a GitHub personal access token with only the "gist" scope
(config.GITHUB_PAT) — no OAuth, no expiring refresh tokens. Unset =
`sync_now` becomes a no-op; nothing else about the app changes, which is
the default state: sync is opt-in and off until a token is set.

Status: this is currently the only client of the format. It works
desktop-to-desktop today (same account, two machines), and the wire
format below is deliberately client-agnostic so a second implementation
can be added later without a migration.

Wire format (`lookups.json` inside the gist)::

    {"version": 1, "entries": [
      {"language": "Kannada", "key": "sky", "original": "Sky",
       "translation": "ಆಕಾಶ", "partOfSpeech": "noun", "meaning": "...",
       "synonyms": "...", "exampleEn": "...", "exampleNative": "...",
       "provider": "GeminiProvider",
       "createdAt": 1739000000000, "updatedAt": 1739000000000,
       "deleted": false}, ...
    ]}

Field names are camelCase and timestamps are epoch **milliseconds**,
even though the rest of this codebase is snake_case and stores epoch
seconds. Both are deliberate: the wire format is meant to be readable by
clients on other platforms, where those are the native conventions. The
mismatch is contained in this module — `_to_wire` / `_from_wire` convert
at the boundary, so store.py never sees it.
"""

import json
import time

import requests

from . import config
from .store import LookupStore

_API_BASE = "https://api.github.com"
_FILENAME = "lookups.json"
_DESCRIPTION = "Word Lookup sync cache (private, auto-managed)"


class SyncFailed(Exception):
    """User-presentable sync failure — mirrors LookupFailed's role, but
    sync is never allowed to interrupt a lookup, so callers should log
    and swallow this rather than surface it as a popup."""


# --- wire format <-> store row conversion -----------------------------------


def _to_wire(row: dict) -> dict:
    """Store row (snake_case, epoch-seconds float) -> wire entry
    (camelCase, epoch-ms int) — mirrors `SyncEntry.fromEntity`."""
    return {
        "language": row["language"],
        "key": row["key"],
        "original": row["original"],
        "translation": row["translation"],
        "partOfSpeech": row["part_of_speech"],
        "meaning": row["meaning"],
        "synonyms": row["synonyms"],
        "exampleEn": row["example_en"],
        "exampleNative": row["example_native"],
        "provider": row["provider"],
        "createdAt": round(row["created_at"] * 1000),
        "updatedAt": round(row["updated_at"] * 1000),
        "deleted": bool(row["deleted"]),
    }


def _from_wire(entry: dict) -> dict:
    """Wire entry -> store row — mirrors `SyncEntry.toEntity`."""
    return {
        "language": entry["language"],
        "key": entry["key"],
        "original": entry["original"],
        "translation": entry["translation"],
        "part_of_speech": entry.get("partOfSpeech", ""),
        "meaning": entry.get("meaning", ""),
        "synonyms": entry.get("synonyms", ""),
        "example_en": entry.get("exampleEn", ""),
        "example_native": entry.get("exampleNative", ""),
        "provider": entry.get("provider", ""),
        "created_at": entry["createdAt"] / 1000,
        "updated_at": entry["updatedAt"] / 1000,
        "deleted": bool(entry.get("deleted", False)),
    }


# --- merge -------------------------------------------------------------------


def _tiebreak_key(entry: dict) -> str:
    return "|".join(
        str(entry.get(f, ""))
        for f in ("original", "translation", "meaning", "synonyms", "exampleEn", "exampleNative")
    )


def _winner(a: dict, b: dict) -> dict:
    """Total order over two candidate rows for the same (language, key):
    higher updatedAt, then a tombstone over a live row, then a
    deterministic tie-break. Kept commutative, idempotent and associative
    so both sides converge regardless of which one syncs first."""
    if a["updatedAt"] != b["updatedAt"]:
        return a if a["updatedAt"] > b["updatedAt"] else b
    if bool(a["deleted"]) != bool(b["deleted"]):
        return a if a["deleted"] else b
    return a if _tiebreak_key(a) >= _tiebreak_key(b) else b


def merge_entries(local: list[dict], remote: list[dict]) -> list[dict]:
    """Union of both lists by (language, key), each key resolved by
    `_winner`. Commutative, idempotent, associative — see
    SyncMergerTest.kt's kdoc for why that's what makes independent syncs
    from both devices converge regardless of who goes first."""
    by_key: dict[tuple, dict] = {}
    for entry in local + remote:
        k = (entry["language"], entry["key"])
        by_key[k] = entry if k not in by_key else _winner(by_key[k], entry)
    return list(by_key.values())


# --- Gist HTTP client ----------------------------------------------------


class GistClient:
    def __init__(self, pat: str, api_base: str = _API_BASE):
        self._pat = pat
        self._api_base = api_base

    def _headers(self) -> dict:
        if not self._pat:
            raise SyncFailed("No GitHub token set — add GITHUB_PAT to .env to enable sync.")
        return {
            "Authorization": f"Bearer {self._pat}",
            "Accept": "application/vnd.github+json",
        }

    def pull(self, gist_id: str) -> dict | None:
        """Fetches and parses the payload for an existing gist, or None
        if `gist_id` is blank (no gist created yet) or the gist is gone."""
        if not gist_id:
            return None
        try:
            resp = requests.get(
                f"{self._api_base}/gists/{gist_id}",
                headers=self._headers(),
                timeout=config.API_TIMEOUT_S,
            )
        except requests.exceptions.RequestException as e:
            raise SyncFailed(f"Gist fetch failed: {e}")
        if resp.status_code == 404:
            return None
        if not resp.ok:
            raise SyncFailed(f"Gist fetch failed ({resp.status_code}).")
        try:
            content = resp.json()["files"][_FILENAME]["content"]
            return json.loads(content)
        except (KeyError, ValueError):
            raise SyncFailed("Could not parse sync gist — is lookups.json valid JSON?")

    def push(self, gist_id: str, payload: dict) -> str:
        """Creates the gist on first use, or PATCHes the existing one.
        Returns the (possibly newly created) gist ID."""
        body = {
            "description": _DESCRIPTION,
            "public": False,
            "files": {_FILENAME: {"content": json.dumps(payload)}},
        }
        try:
            if not gist_id:
                resp = requests.post(
                    f"{self._api_base}/gists",
                    headers=self._headers(),
                    json=body,
                    timeout=config.API_TIMEOUT_S,
                )
            else:
                resp = requests.patch(
                    f"{self._api_base}/gists/{gist_id}",
                    headers=self._headers(),
                    json=body,
                    timeout=config.API_TIMEOUT_S,
                )
        except requests.exceptions.RequestException as e:
            raise SyncFailed(f"Gist sync failed: {e}")
        if resp.status_code == 409:
            raise SyncFailed("Gist changed concurrently — retry.")
        if not resp.ok:
            action = "create" if not gist_id else "update"
            raise SyncFailed(f"Gist {action} failed ({resp.status_code}).")
        return resp.json().get("id", gist_id)


# --- orchestration -------------------------------------------------------


def sync_now(store: LookupStore | None = None, client: GistClient | None = None) -> bool:
    """One sync round-trip: pull, merge, push-if-changed, write merged
    rows back locally, remember any newly created gist ID. Returns True
    if a sync actually ran (token present), False if skipped (no token —
    not an error, sync is opt-in).

    Never raises on network/API failure — matches the "sync never blocks
    or breaks a lookup" rule from the sync design; callers (tray "Sync
    now", startup) should call this and not worry about exceptions, but
    SyncFailed is still raised for genuine misconfiguration (e.g. this
    function is *called* without ever checking GITHUB_PAT first) so tests
    can assert on it directly.
    """
    if not config.GITHUB_PAT:
        return False

    store = store or LookupStore()
    client = client or GistClient(config.GITHUB_PAT)
    settings = config.load_settings() or {}
    gist_id = settings.get("gist_id", "")

    local_wire = [_to_wire(row) for row in store.all_including_deleted()]
    remote_payload = client.pull(gist_id)
    remote_wire = remote_payload.get("entries", []) if remote_payload else []

    merged = merge_entries(local_wire, remote_wire)

    if remote_payload is None or _entries_differ(merged, remote_wire):
        new_gist_id = client.push(gist_id, {"version": 1, "entries": merged})
        if new_gist_id != gist_id:
            config.update_settings(gist_id=new_gist_id)

    for entry in merged:
        store.upsert_raw(_from_wire(entry))

    config.update_settings(last_sync_at=time.time())
    return True


def _entries_differ(a: list[dict], b: list[dict]) -> bool:
    key = lambda e: json.dumps(e, sort_keys=True)  # noqa: E731
    return {key(e) for e in a} != {key(e) for e in b}
