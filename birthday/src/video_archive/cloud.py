import hashlib
import json
import os
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import (
    CLOUD_MEMOS_FILE,
    CLOUD_MESSAGE_FILE,
    CLOUD_MESSAGE_TOKEN_FILE,
    READ_MEMOS_FILE,
)
from .storage import atomic_write_json, atomic_write_text

MAX_MESSAGE_CHARS = 1200
FETCH_TIMEOUT_SECONDS = 6
MAX_MEMOS = 100


def memo_key(memo):
    date = str(memo.get("date", "")).strip()
    message = str(memo.get("message", "")).strip()
    payload = f"{date}\0{message}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_read_memo_keys():
    if not READ_MEMOS_FILE.exists():
        return set()

    try:
        loaded = json.loads(READ_MEMOS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return set()

    if not isinstance(loaded, list):
        return set()

    return {str(item) for item in loaded if item}


def _save_read_memo_keys(keys):
    atomic_write_json(READ_MEMOS_FILE, sorted(keys))


def mark_memo_read(memo):
    keys = load_read_memo_keys()
    keys.add(memo_key(memo))
    _save_read_memo_keys(keys)


def prune_read_memo_keys(memos):
    if not READ_MEMOS_FILE.exists():
        return

    keys = load_read_memo_keys()
    valid_keys = {memo_key(memo) for memo in memos}
    pruned = keys & valid_keys
    if pruned != keys:
        _save_read_memo_keys(pruned)


def unread_memo_count(memos):
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


def load_cached_message_date():
    if not CLOUD_MESSAGE_FILE.exists():
        return ""

    try:
        timestamp = CLOUD_MESSAGE_FILE.stat().st_mtime
    except OSError:
        return ""

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def _memo_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_memos():
    memos = []
    if CLOUD_MEMOS_FILE.exists():
        try:
            loaded = json.loads(CLOUD_MEMOS_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            loaded = []

        if isinstance(loaded, list):
            for item in loaded:
                if not isinstance(item, dict):
                    continue

                message = str(item.get("message", "")).strip()
                if not message:
                    continue

                memos.append(
                    {
                        "date": str(item.get("date", "")).strip() or "--",
                        "message": message,
                    }
                )

    cached = load_cached_message()
    if cached and not any(item["message"] == cached for item in memos):
        memos.insert(
            0,
            {
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
    memos = list(memos)[:MAX_MEMOS]
    atomic_write_json(CLOUD_MEMOS_FILE, memos)
    prune_read_memo_keys(memos)


def archive_memo(message):
    message = message.strip()
    if not message:
        return load_memos()

    memos = load_memos()
    if memos and memos[0]["message"] == message:
        return memos

    memos.insert(
        0,
        {
            "date": _memo_timestamp(),
            "message": message,
        },
    )
    save_memos(memos)
    return memos


def save_cached_message(message):
    atomic_write_text(CLOUD_MESSAGE_FILE, message.strip() + "\n")


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


def fetch_cloud_message(url):
    headers = {
        "User-Agent": "4autumn-video-archive/1.0",
    }
    token = load_cloud_message_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(
        url,
        headers=headers,
    )

    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_MESSAGE_CHARS + 1)
    except (OSError, URLError) as error:
        return None, str(error)

    message = raw.decode("utf-8", errors="replace").strip()
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS].rstrip()

    try:
        save_cached_message(message)
        archive_memo(message)
    except OSError as error:
        return message, str(error)

    return message, ""
