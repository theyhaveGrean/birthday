"""Run the app while keeping xsession.log bounded during long uptimes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_BYTES = 2 * 1024 * 1024


def rotate_log(log_path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    try:
        if not log_path.exists() or log_path.stat().st_size < max_bytes:
            return
    except OSError:
        return

    old_path = log_path.with_name(log_path.name + ".old")
    try:
        old_path.unlink(missing_ok=True)
        log_path.replace(old_path)
    except OSError:
        # Logging should never prevent the application from running.
        return


def run_logged(command: list[str], log_path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rotate_log(log_path, max_bytes)

    child = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )

    def forward_signal(signum, _frame):
        if child.poll() is None:
            try:
                child.send_signal(signum)
            except OSError:
                pass

    old_handlers = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        old_handlers[signum] = signal.signal(signum, forward_signal)

    output = None
    try:
        output = log_path.open("ab", buffering=0)
        while True:
            chunk = child.stdout.read(8192) if child.stdout is not None else b""
            if chunk:
                try:
                    view = memoryview(chunk)
                    while view:
                        remaining = max(0, max_bytes - output.tell())
                        if remaining == 0:
                            output.close()
                            rotate_log(log_path, 1)
                            output = log_path.open("ab", buffering=0)
                            remaining = max_bytes
                        piece = view[:remaining]
                        output.write(piece)
                        view = view[len(piece):]
                except OSError:
                    pass
            elif child.poll() is not None:
                break
        return child.wait()
    finally:
        if output is not None:
            try:
                output.close()
            except OSError:
                pass
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        if child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    child.kill()
                except OSError:
                    pass


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: log_runner.py LOG_FILE COMMAND [ARG ...]", file=sys.stderr)
        return 2
    log_path = Path(sys.argv[1]).resolve()
    command = sys.argv[2:]
    return run_logged(command, log_path)


if __name__ == "__main__":
    raise SystemExit(main())
