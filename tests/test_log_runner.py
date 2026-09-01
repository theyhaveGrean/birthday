from pathlib import Path

from tools.log_runner import rotate_log, run_logged


def test_rotate_log_keeps_one_bounded_previous_log(tmp_path):
    log = tmp_path / "xsession.log"
    log.write_bytes(b"x" * 20)

    rotate_log(log, max_bytes=10)

    assert not log.exists()
    assert (tmp_path / "xsession.log.old").read_bytes() == b"x" * 20


def test_run_logged_rotates_while_child_is_still_running(tmp_path):
    log = tmp_path / "xsession.log"
    command = [
        "python3",
        "-c",
        "import sys; [sys.stdout.write('abcdefghij\\n') or sys.stdout.flush() for _ in range(20)]",
    ]

    status = run_logged(command, log, max_bytes=80)

    assert status == 0
    assert log.exists()
    assert log.stat().st_size <= 80
    assert (tmp_path / "xsession.log.old").exists()
