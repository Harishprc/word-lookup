"""Unit tests for sync.py - HTTP mocked, no token/network needed. The
merge tests pin the algebraic properties the design depends on
(commutative, idempotent, associative), so any future client written
against this wire format can be checked against the same rule."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kannada_lookup import sync  # noqa: E402
from kannada_lookup.store import LookupStore  # noqa: E402
from kannada_lookup.translator import LookupResult  # noqa: E402


def _entry(key="sky", translation="a", updated_at=1000, deleted=False, language="Kannada"):
    return {
        "language": language,
        "key": key,
        "original": key,
        "translation": translation,
        "partOfSpeech": "",
        "meaning": "",
        "synonyms": "",
        "exampleEn": "",
        "exampleNative": "",
        "provider": "",
        "createdAt": updated_at,
        "updatedAt": updated_at,
        "deleted": deleted,
    }


# --- merge_entries -----------------------------------------------------------


def test_disjoint_keys_union_without_loss():
    a, b = _entry(key="sky"), _entry(key="moon")
    result = sync.merge_entries([a], [b])
    assert {e["key"] for e in result} == {"sky", "moon"}


def test_same_key_newer_updated_at_wins():
    older = _entry(translation="old", updated_at=1000)
    newer = _entry(translation="new", updated_at=2000)
    assert sync.merge_entries([older], [newer]) == [newer]
    assert sync.merge_entries([newer], [older]) == [newer]


def test_tombstone_beats_older_live_row_even_with_equal_updated_at():
    live = _entry(deleted=False, updated_at=1000)
    tombstone = _entry(deleted=True, updated_at=1000)
    assert sync.merge_entries([live], [tombstone]) == [tombstone]


def test_strictly_newer_live_row_beats_older_tombstone():
    tombstone = _entry(deleted=True, updated_at=1000)
    revived = _entry(deleted=False, updated_at=2000, translation="back")
    assert sync.merge_entries([tombstone], [revived]) == [revived]


def test_merge_is_commutative():
    a = [_entry(translation="x", updated_at=5), _entry(key="moon", updated_at=1)]
    b = [_entry(translation="y", updated_at=5), _entry(key="sun", updated_at=1)]
    left = {e["key"]: e for e in sync.merge_entries(a, b)}
    right = {e["key"]: e for e in sync.merge_entries(b, a)}
    assert left == right


def test_merge_is_idempotent():
    a = [_entry(key="sky"), _entry(key="moon")]
    result = {e["key"]: e for e in sync.merge_entries(a, a)}
    assert result == {e["key"]: e for e in a}


def test_different_languages_never_collapsed():
    kn = _entry(language="Kannada")
    hi = _entry(language="Hindi")
    assert len(sync.merge_entries([kn], [hi])) == 2


def test_three_way_merge_order_does_not_matter():
    a, b, c = _entry(translation="a", updated_at=1), _entry(translation="b", updated_at=2), _entry(translation="c", updated_at=3)
    left_first = sync.merge_entries(sync.merge_entries([a], [b]), [c])
    right_first = sync.merge_entries([a], sync.merge_entries([b], [c]))
    assert left_first == right_first
    assert left_first[0]["translation"] == "c"


# --- wire format round trip ---------------------------------------------------


def test_to_wire_and_from_wire_round_trip():
    row = {
        "language": "Kannada", "key": "sky", "original": "Sky",
        "translation": "ಆಕಾಶ", "part_of_speech": "noun", "meaning": "the sky",
        "synonyms": "heavens", "example_en": "Look at the sky.",
        "example_native": "ಆಕಾಶ ನೋಡಿ.", "provider": "GeminiProvider",
        "created_at": 1_700_000_000.5, "updated_at": 1_700_000_100.25, "deleted": False,
    }
    wire = sync._to_wire(row)
    assert wire["exampleEn"] == "Look at the sky."
    assert wire["createdAt"] == round(1_700_000_000.5 * 1000)
    back = sync._from_wire(wire)
    assert back["example_en"] == row["example_en"]
    assert abs(back["created_at"] - row["created_at"]) < 0.001


# --- GistClient ----------------------------------------------------------------


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.json.return_value = payload or {}
    return resp


def test_pull_blank_gist_id_makes_no_request():
    client = sync.GistClient("token")
    with patch("kannada_lookup.sync.requests.get") as get:
        assert client.pull("") is None
        get.assert_not_called()


def test_pull_missing_token_raises():
    client = sync.GistClient("")
    with pytest.raises(sync.SyncFailed, match="No GitHub token"):
        client.pull("abc123")


def test_pull_parses_embedded_json():
    payload = {"version": 1, "entries": [_entry()]}
    import json as _json

    gist_response = {"files": {"lookups.json": {"content": _json.dumps(payload)}}}
    with patch("kannada_lookup.sync.requests.get", return_value=_response(200, gist_response)):
        result = sync.GistClient("token").pull("abc123")
    assert result == payload


def test_pull_404_returns_none():
    with patch("kannada_lookup.sync.requests.get", return_value=_response(404)):
        assert sync.GistClient("token").pull("missing") is None


def test_push_blank_gist_id_posts_and_returns_new_id():
    with patch(
        "kannada_lookup.sync.requests.post", return_value=_response(200, {"id": "new-id"})
    ) as post:
        new_id = sync.GistClient("token").push("", {"version": 1, "entries": []})
    assert new_id == "new-id"
    post.assert_called_once()


def test_push_existing_id_patches():
    with patch(
        "kannada_lookup.sync.requests.patch", return_value=_response(200, {"id": "abc123"})
    ) as patch_call:
        new_id = sync.GistClient("token").push("abc123", {"version": 1, "entries": []})
    assert new_id == "abc123"
    patch_call.assert_called_once()
    assert "abc123" in patch_call.call_args.args[0]


def test_push_409_is_retryable_sync_failure():
    with patch("kannada_lookup.sync.requests.patch", return_value=_response(409)):
        with pytest.raises(sync.SyncFailed, match="concurrently"):
            sync.GistClient("token").push("abc123", {"version": 1, "entries": []})


# --- store.py v3: sync columns, tombstones, raw upsert ------------------------


_RESULT = LookupResult(original="Strength", translation="ಶಕ್ತಿ")


def test_v2_install_migrates_to_v3_columns(tmp_path):
    db = tmp_path / "v2.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE lookups_v2 (language TEXT, key TEXT, original TEXT, "
            "translation TEXT, part_of_speech TEXT DEFAULT '', meaning TEXT DEFAULT '', "
            "synonyms TEXT DEFAULT '', example_en TEXT DEFAULT '', "
            "example_native TEXT DEFAULT '', provider TEXT DEFAULT '', "
            "created_at REAL, PRIMARY KEY (language, key))"
        )
        con.execute(
            "INSERT INTO lookups_v2 VALUES ('Kannada', 'strength', 'Strength', "
            "'ಶಕ್ತಿ', '', '', '', '', '', 'g', 1000.0)"
        )
    store = LookupStore(db)
    got = store.get("strength", "Kannada")
    assert got is not None and got.translation == "ಶಕ್ತಿ"
    rows = store.all_including_deleted()
    assert rows[0]["updated_at"] == 1000.0  # backfilled from created_at
    assert rows[0]["deleted"] is False or rows[0]["deleted"] == 0


def test_soft_delete_hides_from_get_and_register_but_not_all_including_deleted(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada")
    store.soft_delete("Strength", "Kannada")

    assert store.get("strength", "Kannada") is None
    assert store.all_entries() == []
    all_rows = store.all_including_deleted()
    assert len(all_rows) == 1
    assert all_rows[0]["deleted"] in (True, 1)


def test_upsert_raw_preserves_caller_supplied_timestamps(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.upsert_raw({
        "language": "Kannada", "key": "sky", "original": "Sky", "translation": "ಆಕಾಶ",
        "part_of_speech": "", "meaning": "", "synonyms": "", "example_en": "",
        "example_native": "", "provider": "sync", "created_at": 500.0,
        "updated_at": 999.0, "deleted": False,
    })
    rows = store.all_including_deleted()
    assert rows[0]["created_at"] == 500.0
    assert rows[0]["updated_at"] == 999.0


# --- sync_now orchestration ----------------------------------------------------


def test_sync_now_skips_without_a_token(monkeypatch, tmp_path):
    monkeypatch.setattr("kannada_lookup.config.GITHUB_PAT", "")
    assert sync.sync_now(store=LookupStore(tmp_path / "t.db")) is False


def test_sync_now_pushes_local_words_on_first_sync(monkeypatch, tmp_path):
    monkeypatch.setattr("kannada_lookup.config.GITHUB_PAT", "token")
    monkeypatch.setattr("kannada_lookup.config.SETTINGS_PATH", tmp_path / "settings.json")
    store = LookupStore(tmp_path / "t.db")
    store.put(_RESULT, "Kannada")

    fake_client = MagicMock()
    fake_client.pull.return_value = None  # no gist yet
    fake_client.push.return_value = "new-gist-id"

    ran = sync.sync_now(store=store, client=fake_client)

    assert ran is True
    fake_client.push.assert_called_once()
    pushed_entries = fake_client.push.call_args.args[1]["entries"]
    assert any(e["original"] == "Strength" for e in pushed_entries)


# --- native synonyms across the wire (v4 field) ------------------------------


def test_native_synonyms_survive_a_wire_round_trip():
    store_row = {
        "language": "Kannada",
        "key": "strength",
        "original": "Strength",
        "translation": "ಶಕ್ತಿ",
        "part_of_speech": "noun",
        "meaning": "physical power",
        "synonyms": "power, might",
        "example_en": "She has great strength.",
        "example_native": "ಅವನಿಗೆ ಶಕ್ತಿ ಇದೆ.",
        "synonyms_native": "ಬಲ, ಸಾಮರ್ಥ್ಯ",
        "provider": "test",
        "created_at": 1.0,
        "updated_at": 2.0,
        "deleted": 0,
    }
    back = sync._from_wire(sync._to_wire(store_row))
    assert back["synonyms_native"] == "ಬಲ, ಸಾಮರ್ಥ್ಯ"


def test_payload_from_a_pre_v4_device_still_merges():
    """A machine on the older schema sends no synonymsNative key at all.
    That must degrade to an empty string, not abort the whole sync."""
    legacy = _entry(key="sky")
    assert "synonymsNative" not in legacy
    row = sync._from_wire(legacy)
    assert row["synonyms_native"] == ""


def test_pre_v4_payload_can_be_written_to_the_store(tmp_path):
    store = LookupStore(tmp_path / "t.db")
    store.upsert_raw(sync._from_wire(_entry(key="sky", translation="ಆಕಾಶ")))
    assert store.get("sky", "Kannada").synonyms_native == ""


def test_native_synonyms_participate_in_the_tiebreak():
    """Two rows identical but for their native synonyms must not be
    treated as the same row by the equal-timestamp tiebreak, or one
    device's synonyms would silently win at random."""
    a = _entry(updated_at=1000)
    b = _entry(updated_at=1000)
    a["synonymsNative"] = "ಬಲ"
    b["synonymsNative"] = "ಸಾಮರ್ಥ್ಯ"
    assert sync._tiebreak_key(a) != sync._tiebreak_key(b)
