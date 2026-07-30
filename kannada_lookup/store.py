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
    PRIMARY KEY (language, key)
)
"""

_RESULT_COLS = (
    "original, translation, part_of_speech, meaning, synonyms, "
    "example_en, example_native"
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

    def get(self, text: str, language: str) -> LookupResult | None:
        with self._connect() as con:
            row = con.execute(
                f"SELECT {_RESULT_COLS} FROM lookups_v2 "
                "WHERE language = ? AND key = ?",
                (language, _normalize(text)),
            ).fetchone()
        if row is None:
            return None
        return LookupResult(*row)

    def put(self, result: LookupResult, language: str, provider: str = "") -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO lookups_v2 "
                "(language, key, original, translation, part_of_speech, "
                " meaning, synonyms, example_en, example_native, provider, "
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    time.time(),
                ),
            )

    def all_entries(self) -> list[dict]:
        """Every cached lookup, newest first — feeds the HTML register."""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT {_RESULT_COLS}, language, created_at "
                "FROM lookups_v2 ORDER BY created_at DESC"
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
