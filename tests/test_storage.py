import json

from video_archive.storage import atomic_write_json, atomic_write_text


def test_atomic_write_text_replaces_contents(tmp_path):
    path = tmp_path / "state.txt"
    atomic_write_text(path, "one\n")
    atomic_write_text(path, "two\n")
    assert path.read_text() == "two\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_json_writes_valid_json(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"ok": True, "value": 3})
    assert json.loads(path.read_text()) == {"ok": True, "value": 3}


def test_clamp_int_limits_and_coerces_values():
    from video_archive.storage import clamp_int

    assert clamp_int(-5, 0, 100) == 0
    assert clamp_int("42", 0, 100) == 42
    assert clamp_int(150, 0, 100) == 100


def test_safe_setting_coercion_handles_corrupt_values():
    from video_archive.storage import clamp_int_or_default, coerce_bool

    assert clamp_int_or_default("bad", 1, 100, 80) == 80
    assert clamp_int_or_default(None, 1, 60, 5) == 5
    assert coerce_bool("false", True) is False
    assert coerce_bool("ON", False) is True
    assert coerce_bool(object(), True) is True
