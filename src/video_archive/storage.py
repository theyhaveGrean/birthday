import json
import os
import tempfile
from pathlib import Path


def clamp_int(value, minimum, maximum):
    return max(minimum, min(maximum, int(value)))


def clamp_int_or_default(value, minimum, maximum, default):
    try:
        return clamp_int(value, minimum, maximum)
    except (TypeError, ValueError):
        return clamp_int(default, minimum, maximum)


def coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(default)


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path, value):
    atomic_write_text(path, json.dumps(value, indent=2) + "\n")
