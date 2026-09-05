import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .config import (
    CLOUD_MEMOS_FILE,
    CLOUD_MESSAGE_FILE,
    CLOUD_MESSAGE_META_FILE,
    READ_MEMOS_FILE,
)
from .storage import atomic_write_json, atomic_write_text

MAX_MESSAGE_CHARS = 1200
FETCH_TIMEOUT_SECONDS = 6
MAX_MEMOS = 100
MAX_RESPONSE_BYTES = 256 * 1024
SUPABASE_NOTES_URL = "https://rrwyqfddvijgimcslqkl.supabase.co/rest/v1/notes"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_2Iurrigf7zF0by-BWoKE3g_IAT76514"
SUPABASE_NOTES_SELECT = "id,name,message,created_at"
MIN_SANE_YEAR = 2020
_MEMO_STATE_LOCK = threading.RLock()


def _load_json_file(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _legacy_memo_key(memo):
    date = str(memo.get("date", "")).strip()
    message = str(memo.get("message", "")).strip()
    payload = f"{date}\0{message}".encode()
    return hashlib.sha256(payload).hexdigest()


def memo_key(memo):
    memo_id = str(memo.get("id", "")).strip()
    if memo_id:
        return memo_id
    return _legacy_memo_key(memo)


def load_read_memo_keys():
    with _MEMO_STATE_LOCK:
        if not READ_MEMOS_FILE.exists():
            return set()

        loaded = _load_json_file(READ_MEMOS_FILE, [])
        if not isinstance(loaded, list):
            return set()

        return {str(item) for item in loaded if item}


def _save_read_memo_keys(keys):
    atomic_write_json(READ_MEMOS_FILE, sorted(keys))


def mark_memo_read(memo):
    with _MEMO_STATE_LOCK:
        keys = load_read_memo_keys()
        keys.add(memo_key(memo))
        _save_read_memo_keys(keys)


def prune_read_memo_keys(memos):
    with _MEMO_STATE_LOCK:
        if not READ_MEMOS_FILE.exists():
            return

        keys = load_read_memo_keys()
        valid_keys = {memo_key(memo) for memo in memos}
        pruned = keys & valid_keys
        if pruned != keys:
            _save_read_memo_keys(pruned)


def unread_memo_count(memos):
    with _MEMO_STATE_LOCK:
        read_keys = load_read_memo_keys()
        return sum(
            1 for memo in memos
            if memo_key(memo) not in read_keys
        )


def load_cached_message():
    if not CLOUD_MESSAGE_FILE.exists():
        return ""

    try:
        return CLOUD_MESSAGE_FILE.read_text().strip()
    except OSError:
        return ""


def _format_sane_datetime(value):
    if not value or value.year < MIN_SANE_YEAR:
        return "TIME UNSYNCED"
    if value.tzinfo:
        value = value.astimezone()
    return value.strftime("%Y-%m-%d %H:%M")


def load_cached_message_date():
    if CLOUD_MESSAGE_META_FILE.exists():
        loaded = _load_json_file(CLOUD_MESSAGE_META_FILE, {})
        if isinstance(loaded, dict):
            received_at = str(loaded.get("received_at", "")).strip()
            if received_at:
                return received_at

    # Migration fallback for installs created before the metadata sidecar
    # existed. The cache mtime was previously used as the memo timestamp.
    if not CLOUD_MESSAGE_FILE.exists():
        return ""

    try:
        timestamp = CLOUD_MESSAGE_FILE.stat().st_mtime
        value = datetime.fromtimestamp(timestamp, timezone.utc)
    except (OSError, ValueError, OverflowError):
        return ""

    return _format_sane_datetime(value)


def _memo_timestamp(value=None):
    return _format_sane_datetime(value or datetime.now(timezone.utc))


def load_memos():
    memos = []
    if CLOUD_MEMOS_FILE.exists():
        loaded = _load_json_file(CLOUD_MEMOS_FILE, [])
        if isinstance(loaded, list):
            seen_keys = set()
            for item in loaded:
                if not isinstance(item, dict):
                    continue

                message = str(item.get("message", "")).strip()
                if not message:
                    continue

                normalized = {
                    "id": str(item.get("id", "")).strip(),
                    "date": str(item.get("date", "")).strip() or "--",
                    "message": message,
                }
                name = str(item.get("name", "")).strip()
                if name:
                    normalized["name"] = name
                if not normalized["id"]:
                    # Stable migration keeps legacy read-state valid.
                    normalized["id"] = _legacy_memo_key(normalized)
                key = memo_key(normalized)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                memos.append(normalized)

    cached = load_cached_message()
    if cached and not any(item["message"] == cached for item in memos):
        memos.insert(
            0,
            {
                "id": uuid.uuid4().hex,
                "date": load_cached_message_date() or _memo_timestamp(),
                "message": cached,
            },
        )
        save_memos(memos)

    if len(memos) > MAX_MEMOS:
        memos = memos[:MAX_MEMOS]
        save_memos(memos)

    return memos


def save_memos(memos):
    with _MEMO_STATE_LOCK:
        memos = list(memos)[:MAX_MEMOS]
        atomic_write_json(CLOUD_MEMOS_FILE, memos)
        prune_read_memo_keys(memos)


def archive_memo(message, memo_date=None, allow_duplicate_top=False, memo_id=None, name=""):
    message = message.strip()
    with _MEMO_STATE_LOCK:
        if not message:
            return load_memos()

        memos = load_memos()
        # Polling the same current payload must not duplicate it, but the same
        # text is allowed again later after a different memo has appeared.
        if (
            not allow_duplicate_top
            and memos
            and memos[0].get("message", "") == message
        ):
            return memos

        item = {
            "id": str(memo_id or uuid.uuid4().hex),
            "date": memo_date or _memo_timestamp(),
            "message": message,
        }
        if name:
            item["name"] = str(name).strip()
        memos.insert(0, item)
        save_memos(memos)
        return memos


def save_cached_message(message, received_at=None):
    normalized = message.strip()
    if load_cached_message() == normalized and CLOUD_MESSAGE_FILE.exists():
        return False

    atomic_write_text(CLOUD_MESSAGE_FILE, normalized + "\n")
    atomic_write_json(
        CLOUD_MESSAGE_META_FILE,
        {"received_at": received_at or _memo_timestamp()},
    )
    return True


def _supabase_notes_url(url=None):
    base = (url or SUPABASE_NOTES_URL).strip() or SUPABASE_NOTES_URL
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["select"] = SUPABASE_NOTES_SELECT
    query["order"] = "created_at.desc"
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def _format_note_date(value):
    value = str(value or "").strip()
    if not value:
        return _memo_timestamp()
    try:
        normalized = value.replace("Z", "+00:00")
        return _memo_timestamp(datetime.fromisoformat(normalized))
    except ValueError:
        return value[:16] or _memo_timestamp()


def _normalize_note_row(row):
    if not isinstance(row, dict):
        return None

    message = str(row.get("message", "")).strip()
    if not message:
        return None
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS].rstrip()

    memo_id = str(row.get("id", "")).strip()
    normalized = {
        "id": memo_id or uuid.uuid4().hex,
        "date": _format_note_date(row.get("created_at")),
        "message": message,
    }
    name = str(row.get("name", "")).strip()
    if name:
        normalized["name"] = name
    return normalized


def _sync_supabase_notes(rows):
    memos = []
    seen_keys = set()
    for row in rows:
        memo = _normalize_note_row(row)
        if not memo:
            continue
        key = memo_key(memo)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        memos.append(memo)
        if len(memos) >= MAX_MEMOS:
            break

    save_memos(memos)
    newest = memos[0] if memos else None
    if newest:
        save_cached_message(newest["message"], newest["date"])
        return newest["message"]

    save_cached_message("", _memo_timestamp())
    return ""


def _http_error_body(error):
    try:
        body = error.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace").strip()
    except OSError:
        body = ""
    return f"HTTP {error.code}: {body}" if body else f"HTTP {error.code}"


def fetch_cloud_message(url=None):
    headers = {
        "User-Agent": "4autumn-video-archive/1.0",
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        request = Request(
            _supabase_notes_url(url),
            headers=headers,
        )
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
    except HTTPError as error:
        return None, _http_error_body(error)
    except (OSError, URLError, ValueError) as error:
        return None, str(error)

    try:
        rows = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        return None, f"invalid JSON response: {error}"

    if not isinstance(rows, list):
        return None, "invalid notes response: expected a JSON array"

    try:
        message = _sync_supabase_notes(rows)
    except OSError as error:
        return None, str(error)

    return message, ""
