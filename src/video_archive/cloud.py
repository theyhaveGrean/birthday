import hashlib
import json
import os
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import uuid
import threading

from .config import (
    CLOUD_MEMOS_FILE,
    CLOUD_MESSAGE_FILE,
    CLOUD_MESSAGE_META_FILE,
    CLOUD_MESSAGE_TOKEN_FILE,
    READ_MEMOS_FILE,
)
from .storage import atomic_write_json, atomic_write_text

MAX_MESSAGE_CHARS = 1200
FETCH_TIMEOUT_SECONDS = 6
MAX_MEMOS = 100
GITHUB_TOKEN_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com"}
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
    payload = f"{date}\0{message}".encode("utf-8")
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
        value = datetime.fromtimestamp(timestamp)
    except (OSError, ValueError, OverflowError):
        return ""

    return _format_sane_datetime(value)


def _memo_timestamp(value=None):
    return _format_sane_datetime(value or datetime.now())


def _response_timestamp(response):
    # Prefer the server's HTTP Date header. This avoids bogus 1970-era
    # timestamps when a Raspberry Pi boots before NTP has synchronized.
    raw_date = response.headers.get("Date", "").strip()
    if raw_date:
        try:
            return _memo_timestamp(parsedate_to_datetime(raw_date))
        except (TypeError, ValueError, OverflowError):
            pass
    return _memo_timestamp()


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


def archive_memo(message, memo_date=None, allow_duplicate_top=False):
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

        memos.insert(
            0,
            {
                "id": uuid.uuid4().hex,
                "date": memo_date or _memo_timestamp(),
                "message": message,
            },
        )
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


def load_cloud_message_token():
    token = os.environ.get("CLOUD_MESSAGE_TOKEN", "").strip()
    if token:
        return token

    if not CLOUD_MESSAGE_TOKEN_FILE.exists():
        return ""

    try:
        return CLOUD_MESSAGE_TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def _fresh_fetch_url(url):
    """Bypass intermediary caches for GitHub raw content.

    The app uses raw.githubusercontent.com for memo delivery. A successful
    HTTP request can otherwise still return a recently cached version of the
    file. A unique query value forces each poll to be a distinct CDN request.
    Other endpoints are left unchanged so arbitrary configured APIs do not
    receive an unexpected query parameter.
    """
    parts = urlsplit(url)
    if parts.hostname != "raw.githubusercontent.com":
        return url

    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("_memo_poll", uuid.uuid4().hex))
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def fetch_cloud_message(url):
    headers = {
        "User-Agent": "4autumn-video-archive/1.0",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    }
    token = load_cloud_message_token()
    try:
        hostname = (urlsplit(url).hostname or "").lower()
    except ValueError as error:
        return None, str(error)
    # .cloud_message_token is documented as a GitHub credential. Never send
    # it to arbitrary configured endpoints. Generic authenticated APIs should
    # use a separate credential mechanism instead.
    if token and hostname in GITHUB_TOKEN_HOSTS:
        headers["Authorization"] = f"Bearer {token}"

    try:
        request = Request(
            _fresh_fetch_url(url),
            headers=headers,
        )
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            # UTF-8 can use up to four bytes per Unicode code point. Read
            # enough bytes to enforce the documented limit by characters after
            # decoding rather than accidentally treating bytes as characters.
            raw = response.read(MAX_MESSAGE_CHARS * 4 + 4)
            received_at = _response_timestamp(response)
    except (OSError, URLError, ValueError) as error:
        return None, str(error)

    message = raw.decode("utf-8", errors="replace").strip()
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS].rstrip()

    try:
        cache_existed = CLOUD_MESSAGE_FILE.exists()
        previous_message = load_cached_message()
        if message and message != previous_message:
            # If the cache explicitly held an empty remote state, reposting
            # identical text is a new occurrence even when the archive's top
            # historical memo has the same body. A missing cache on first boot
            # does not force a duplicate.
            archive_memo(
                message,
                memo_date=received_at,
                allow_duplicate_top=cache_existed and previous_message == "",
            )
        save_cached_message(message, received_at)
    except OSError as error:
        return message, str(error)

    return message, ""
