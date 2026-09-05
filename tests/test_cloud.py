import json
import os
import time

from video_archive import cloud


def _redirect_cloud_files(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud, "CLOUD_MESSAGE_FILE", tmp_path / ".cloud_message.txt")
    monkeypatch.setattr(cloud, "CLOUD_MESSAGE_META_FILE", tmp_path / ".cloud_message_meta.json")
    monkeypatch.setattr(cloud, "CLOUD_MEMOS_FILE", tmp_path / "memos.json")
    monkeypatch.setattr(cloud, "READ_MEMOS_FILE", tmp_path / ".read_memos.json")


def test_cached_message_is_not_rewritten_when_unchanged(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    assert cloud.save_cached_message("hello", "2026-08-31 09:00") is True
    first_mtime = cloud.CLOUD_MESSAGE_FILE.stat().st_mtime_ns
    first_meta = cloud.CLOUD_MESSAGE_META_FILE.read_text()

    time.sleep(0.01)
    assert cloud.save_cached_message("hello", "2026-08-31 10:00") is False

    assert cloud.CLOUD_MESSAGE_FILE.stat().st_mtime_ns == first_mtime
    assert cloud.CLOUD_MESSAGE_META_FILE.read_text() == first_meta
    assert cloud.load_cached_message_date() == "2026-08-31 09:00"


def test_changed_cached_message_updates_persisted_timestamp(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    cloud.save_cached_message("first", "2026-08-31 09:00")
    cloud.save_cached_message("second", "2026-08-31 09:15")

    assert cloud.load_cached_message() == "second"
    assert cloud.load_cached_message_date() == "2026-08-31 09:15"
    assert json.loads(cloud.CLOUD_MESSAGE_META_FILE.read_text()) == {
        "received_at": "2026-08-31 09:15"
    }


def test_cached_message_date_migrates_from_old_mtime(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    cloud.CLOUD_MESSAGE_FILE.write_text("legacy\n")
    timestamp = 1_800_000_000
    os.utime(cloud.CLOUD_MESSAGE_FILE, (timestamp, timestamp))

    assert cloud.load_cached_message_date() == cloud._format_sane_datetime(
        cloud.datetime.fromtimestamp(timestamp)
    )


def test_malformed_cloud_url_returns_error_instead_of_raising(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    message, error = cloud.fetch_cloud_message("http://[::1")

    assert message is None
    assert error


def test_archive_memo_does_not_duplicate_same_payload(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    cloud.archive_memo("same", memo_date="2026-08-31 09:00")
    cloud.archive_memo("same", memo_date="2026-08-31 10:00")

    memos = cloud.load_memos()
    assert len(memos) == 1
    assert memos[0]["date"] == "2026-08-31 09:00"
    assert memos[0]["message"] == "same"
    assert memos[0]["id"]


def test_corrupt_memo_files_degrade_safely(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)
    cloud.CLOUD_MEMOS_FILE.write_text("{not json")
    cloud.READ_MEMOS_FILE.write_text("{also bad")

    assert cloud.load_memos() == []
    assert cloud.load_read_memo_keys() == set()


def test_same_text_can_return_after_an_intervening_memo(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    cloud.archive_memo("same", memo_date="2026-08-31 09:00")
    cloud.archive_memo("different", memo_date="2026-08-31 09:05")
    cloud.archive_memo("same", memo_date="2026-08-31 09:10")

    assert [memo["message"] for memo in cloud.load_memos()] == [
        "same",
        "different",
        "same",
    ]


def test_empty_cached_message_clears_current_without_erasing_archive(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    cloud.archive_memo("historical", memo_date="2026-08-31 09:00")
    cloud.save_cached_message("historical", "2026-08-31 09:00")
    cloud.save_cached_message("", "2026-08-31 09:05")

    assert cloud.load_cached_message() == ""
    assert [memo["message"] for memo in cloud.load_memos()] == ["historical"]


def test_new_memos_get_unique_ids_even_with_same_text_and_minute(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)
    cloud.archive_memo("same", memo_date="2026-08-31 09:00")
    cloud.archive_memo("different", memo_date="2026-08-31 09:00")
    cloud.archive_memo("same", memo_date="2026-08-31 09:00")
    memos = cloud.load_memos()
    assert [memo["message"] for memo in memos] == ["same", "different", "same"]
    ids = [memo["id"] for memo in memos]
    assert len(ids) == len(set(ids)) == 3


def test_legacy_memo_read_key_survives_id_migration(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)
    legacy = {"date": "2026-08-31 09:00", "message": "legacy"}
    old_key = cloud._legacy_memo_key(legacy)
    cloud.CLOUD_MEMOS_FILE.write_text(json.dumps([legacy]))
    cloud.READ_MEMOS_FILE.write_text(json.dumps([old_key]))
    memos = cloud.load_memos()
    assert memos[0]["id"] == old_key
    assert cloud.unread_memo_count(memos) == 0


def test_supabase_notes_are_synced_to_local_memos(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)
    captured = {}

    payload = json.dumps([
        {
            "id": "note-2",
            "name": "Autumn",
            "message": "newest",
            "created_at": "2026-08-31T23:00:00+00:00",
        },
        {
            "id": "note-1",
            "name": "Adityan",
            "message": "older",
            "created_at": "2026-08-31T22:59:00+00:00",
        },
    ]).encode("utf-8")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return payload

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return Response()

    monkeypatch.setattr(cloud, "urlopen", fake_urlopen)
    message, error = cloud.fetch_cloud_message()

    assert error == ""
    assert message == "newest"
    assert captured["url"] == (
        "https://rrwyqfddvijgimcslqkl.supabase.co/rest/v1/notes?"
        "select=id%2Cname%2Cmessage%2Ccreated_at&order=created_at.desc"
    )
    assert captured["headers"]["Apikey"] == cloud.SUPABASE_PUBLISHABLE_KEY
    assert captured["headers"]["Authorization"] == (
        f"Bearer {cloud.SUPABASE_PUBLISHABLE_KEY}"
    )
    assert cloud.load_cached_message() == "newest"
    assert cloud.load_cached_message_date() == (
        cloud._format_note_date("2026-08-31T23:00:00+00:00")
    )
    assert cloud.load_memos() == [
        {
            "id": "note-2",
            "date": cloud._format_note_date("2026-08-31T23:00:00+00:00"),
            "message": "newest",
            "name": "Autumn",
        },
        {
            "id": "note-1",
            "date": cloud._format_note_date("2026-08-31T22:59:00+00:00"),
            "message": "older",
            "name": "Adityan",
        },
    ]


def test_supabase_message_limit_is_in_characters(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1):
            return json.dumps([
                {
                    "id": "note-1",
                    "message": "😀" * 1300,
                    "created_at": "2026-08-31T23:00:00+00:00",
                },
            ]).encode("utf-8")

    monkeypatch.setattr(cloud, "urlopen", lambda request, timeout: Response())
    message, error = cloud.fetch_cloud_message()

    assert error == ""
    assert len(message) == cloud.MAX_MESSAGE_CHARS
    assert message == "😀" * cloud.MAX_MESSAGE_CHARS
    assert "�" not in message


def test_same_text_after_explicit_blank_can_be_new_occurrence(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)
    cloud.archive_memo("same", memo_date="2026-08-31 09:00")
    cloud.save_cached_message("", "2026-08-31 09:05")
    cloud.archive_memo(
        "same",
        memo_date="2026-08-31 09:10",
        allow_duplicate_top=True,
    )

    memos = cloud.load_memos()
    assert [memo["message"] for memo in memos] == ["same", "same"]
    assert len({memo["id"] for memo in memos}) == 2


def test_invalid_supabase_json_returns_error(monkeypatch, tmp_path):
    _redirect_cloud_files(monkeypatch, tmp_path)

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size=-1): return b"{not json"

    monkeypatch.setattr(cloud, "urlopen", lambda request, timeout: Response())
    message, error = cloud.fetch_cloud_message()

    assert message is None
    assert "invalid JSON response" in error
