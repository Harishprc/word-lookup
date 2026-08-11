"""Persistent lookup cache — the offline layer and register data source.

Every successful lookup is saved to a small SQLite file. Repeat lookups
are then instant, cost zero API quota, and work with no internet. The
cache is keyed per target language, so switching languages never serves
stale entries from another language.

Schema history:
  v1 — single-language columns (kannada, example), key TEXT PK
  v2 — generic columns (translation, example_native, example_en,
       part_of_speech), PK (language, key). _migrate_v1() carries v1 rows
       over as language='Kannada' so existing users keep their cache.
  v3 — adds `updated_at` (backfilled from created_at) and `deleted`
       (tombstone flag). Both exist purely for Gist sync with the Android
       app (see sync.py) — a v2-only install never touches either column
       differently than before. _migrate_v2_add_sync_columns() ALTERs an
       existing table in place rather than copy-and-drop, since SQLite's
       ADD COLUMN is enough here and there's no column removal or type
       change to reconcile.

Thread-safety: lookups run on short-lived worker threads (one at a time,
guarded by App._busy), but sqlite3 connections are cheap — we open one
per call rather than sharing a connection across threads.
"""

import sqlite3
import time
from pathlib import Path

from .config import PROJECT_ROOT
from .translator import LookupResult

# data/ lives under the app root — the project root in a source checkout
# (gitignored), or %LOCALAPPDATA%\WordLookup in a frozen .exe. See
# config._app_root().
DB_PATH = PROJECT_ROOT / "data" / "lookups.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups_v2 (
    language        TEXT NOT NULL,
    key             TEXT NOT NULL,   -- normalized (lowercased, trimmed) text
    original        TEXT NOT NULL,
    translation     TEXT NOT NULL,
    part_of_speech  TEXT NOT NULL DEFAULT '',
    meaning         TEXT NOT NULL DEFAULT '',
    synonyms        TEXT NOT NULL DEFAULT '',
    example_en      TEXT NOT NULL DEFAULT '',
    example_native  TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL DEFAULT 0,   -- v3: sync merge key
    deleted         INTEGER NOT NULL DEFAULT 0, -- v3: tombstone for sync
    PRIMARY KEY (language, key)
)
"""

_RESULT_COLS = (
    "original, translation, part_of_speech, meaning, synonyms, "
    "example_en, example_native"
)

# Full row shape the sync layer needs (register/get only need _RESULT_COLS).
_SYNC_COLS = (
    "language, key, original, translation, part_of_speech, meaning, "
    "synonyms, example_en, example_native, provider, created_at, "
    "updated_at, deleted"
)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


class LookupStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(_SCHEMA)
            self._migrate_v1(con)
            self._migrate_v2_add_sync_columns(con)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _migrate_v1(con: sqlite3.Connection) -> None:
        """Carry rows from the pre-multi-language table into v2, then drop
        it. All v1 rows were Kannada by definition."""
        old = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lookups'"
        ).fetchone()
        if old is None:
            return
        con.execute(
            "INSERT OR IGNORE INTO lookups_v2 "
            "(language, key, original, translation, meaning, synonyms, "
            " example_native, provider, created_at) "
            "SELECT 'Kannada', key, original, kannada, meaning, synonyms, "
            "       example, provider, created_at FROM lookups"
        )
        con.execute("DROP TABLE lookups")

    @staticmethod
    def _migrate_v2_add_sync_columns(con: sqlite3.Connection) -> None:
        """Idempotent ALTER for installs created before v3: adds
        updated_at/deleted if missing, backfills updated_at from
        created_at (best guess — the exact last-modified time was never
        recorded pre-v3, and created_at is the closest available fact)."""
        columns = {row[1] for row in con.execute("PRAGMA table_info(lookups_v2)")}
        if "updated_at" not in columns:
            con.execute(
                "ALTER TABLE lookups_v2 ADD COLUMN updated_at REAL NOT NULL DEFAULT 0"
            )
        if "deleted" not in columns:
            con.execute(
                "ALTER TABLE lookups_v2 ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
            )
        # Self-healing, not just one-time: also covers rows that reached
        # lookups_v2 via _migrate_v1 (a v1-only install jumping straight
        # to v3) — that INSERT doesn't set updated_at, so it lands at the
        # column default (0) even though the table always had the column.
        con.execute(
            "UPDATE lookups_v2 SET updated_at = created_at "
            "WHERE updated_at = 0 AND created_at != 0"
        )

    def get(self, text: str, language: str) -> LookupResult | None:
        """A soft-deleted (tombstoned) entry is never served from cache —
        matches the Android side's `LookupDao.get` — so a word deleted on
        one device gets a fresh lookup rather than silently reappearing
        from local cache before the next sync even runs."""
        with self._connect() as con:
            row = con.execute(
                f"SELECT {_RESULT_COLS} FROM lookups_v2 "
                "WHERE language = ? AND key = ? AND deleted = 0",
                (language, _normalize(text)),
            ).fetchone()
        if row is None:
            return None
        return LookupResult(*row)

    def put(self, result: LookupResult, language: str, provider: str = "") -> None:
        now = time.time()
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO lookups_v2 "
                "(language, key, original, translation, part_of_speech, "
                " meaning, synonyms, example_en, example_native, provider, "
                " created_at, updated_at, deleted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    language,
                    _normalize(result.original),
                    result.original,
                    result.translation,
                    result.part_of_speech,
                    result.meaning,
                    result.synonyms,
                    result.example_en,
                    result.example_native,
                    provider,
                    now,
                    now,
                ),
            )

    def soft_delete(self, text: str, language: str) -> None:
        """Tombstone rather than DELETE, so a later sync doesn't resurrect
        the row from another device's older copy — same reasoning as the
        Android side's `LookupDao.softDelete`."""
        with self._connect() as con:
            con.execute(
                "UPDATE lookups_v2 SET deleted = 1, updated_at = ? "
                "WHERE language = ? AND key = ?",
                (time.time(), language, _normalize(text)),
            )

    def all_entries(self) -> list[dict]:
        """Every *live* cached lookup, newest first — feeds the HTML
        register. Tombstones are excluded; use `all_including_deleted`
        for the sync payload, which needs deletions represented too."""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT {_RESULT_COLS}, language, created_at "
                "FROM lookups_v2 WHERE deleted = 0 ORDER BY created_at DESC"
            ).fetchall()
        entries = []
        for row in rows:
            entries.append(
                {
                    "result": LookupResult(*row[:7]),
                    "language": row[7],
                    "created_at": row[8],
                }
            )
        return entries

    def all_including_deleted(self) -> list[dict]:
        """Every row, tombstones included — the sync payload's source of
        truth. Keys match `_SYNC_COLS` order."""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT {_SYNC_COLS} FROM lookups_v2"
            ).fetchall()
        cols = [c.strip() for c in _SYNC_COLS.split(",")]
        return [dict(zip(cols, row)) for row in rows]

    def upsert_raw(self, row: dict) -> None:
        """Writes a full row (as produced by `all_including_deleted` /
        the sync merge) verbatim — unlike `put`, does not touch
        created_at/updated_at, since the caller (sync.py) already decided
        those via the merge, and re-stamping "now" here would defeat the
        whole point of last-write-wins."""
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO lookups_v2 "
                f"({_SYNC_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["language"],
                    row["key"],
                    row["original"],
                    row["translation"],
                    row["part_of_speech"],
                    row["meaning"],
                    row["synonyms"],
                    row["example_en"],
                    row["example_native"],
                    row["provider"],
                    row["created_at"],
                    row["updated_at"],
                    1 if row["deleted"] else 0,
                ),
            )
