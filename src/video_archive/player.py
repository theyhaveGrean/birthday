import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import MPV_LOG_FILE


class MpvController(QObject):
    ready = Signal()
    started = Signal()
    ended = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()

        self.process = None
        self.socket_path = f"/tmp/video-archive-mpv-{os.getpid()}.sock"
        self.log_path = MPV_LOG_FILE

        self._sock = None
        self._send_lock = threading.Lock()
        self._reader_thread = None
        self._stopping = False
        self._started_sent = False
        self._log_file = None

    def preload(self, path, wid, volume=100):
        self.stop(silent=True)

        path = Path(path)

        if not path.exists():
            self.failed.emit(f"FILE NOT FOUND: {path.name}")
            return

        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        self._stopping = False
        self._started_sent = False

        # Keep this command intentionally minimal while debugging X11
        # embedding. These options are enough for:
        #  - embedding into the Qt native child window
        #  - loading paused behind the transition
        #  - IPC control
        volume = max(
            0,
            min(150, int(volume)),
        )

        args = [
            "mpv",
            f"--wid={int(wid)}",
            "--no-config",
            "--pause=yes",
            "--mute=yes",
            "--keep-open=yes",
            "--keepaspect=yes",
            "--loop-file=no",
            f"--input-ipc-server={self.socket_path}",
            "--force-window=yes",
            "--volume-max=150",
            f"--volume={volume}",
            "--af=lavfi=[highpass=f=180,dynaudnorm=f=250:g=15:p=0.95:m=20]",
            str(path),
        ]

        try:
            self._log_file = open(  # noqa: SIM115
                self.log_path,
                "w",
                buffering=1,
            )

            self._log_file.write(
                "COMMAND:\n"
                + " ".join(args)
                + "\n\n"
            )

            self.process = subprocess.Popen(
                args,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
            )

        except OSError as exc:
            self.failed.emit(str(exc))
            return

        self._reader_thread = threading.Thread(
            target=self._ipc_reader,
            daemon=True,
        )
        self._reader_thread.start()

    def play(self):
        self.command(
            ["set_property", "pause", False]
        )

    def unmute(self):
        self.command(
            ["set_property", "mute", False]
        )

    def set_volume(self, volume):
        volume = max(
            0,
            min(150, int(volume)),
        )

        self.command(
            ["set_property", "volume-max", 150]
        )
        self.command(
            ["set_property", "volume", volume]
        )

    def mute(self):
        self.command(
            ["set_property", "mute", True]
        )

    def pause(self):
        self.command(
            ["set_property", "pause", True]
        )

    def command(self, command):
        payload = (
            json.dumps(
                {"command": command}
            )
            + "\n"
        )

        with self._send_lock:
            if self._sock is None:
                return False

            try:
                self._sock.sendall(
                    payload.encode("utf-8")
                )
                return True
            except OSError:
                return False

    def stop(self, silent=False):
        self._stopping = True

        if self._sock is not None:
            self.command(["quit"])

        if self.process is not None:
            try:
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        self.process.kill()
                    except OSError:
                        pass

        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

        self._sock = None
        self.process = None

        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

        if not silent:
            self._stopping = False

    def _fail_with_log(self, message):
        detail = ""

        try:
            if self.log_path.exists():
                lines = self.log_path.read_text(
                    errors="replace"
                ).splitlines()

                # Include the final few lines directly in xsession.log.
                detail = "\n".join(
                    lines[-12:]
                )
        except OSError:
            pass

        if detail:
            message = (
                f"{message}\n"
                f"--- mpv log tail ---\n"
                f"{detail}"
            )

        self.failed.emit(message)

    def _ipc_reader(self):
        deadline = (
            time.monotonic() + 8.0
        )

        while time.monotonic() < deadline:
            if self.process is None:
                return

            return_code = self.process.poll()

            if return_code is not None:
                if not self._stopping:
                    self._fail_with_log(
                        f"mpv exited with code {return_code}"
                    )
                return

            if os.path.exists(
                self.socket_path
            ):
                break

            time.sleep(0.02)

        else:
            if not self._stopping:
                self._fail_with_log(
                    "mpv IPC did not become ready"
                )
            return

        sock = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        try:
            sock.connect(
                self.socket_path
            )

        except OSError as exc:
            if not self._stopping:
                self._fail_with_log(
                    f"mpv IPC connection failed: {exc}"
                )
            return

        self._sock = sock

        # Ask mpv to report both EOF and playback position. playback-restart
        # fires too early for the UI handoff; time-pos advancing confirms
        # playback is actually moving while still muted behind the transition.
        try:
            for command in (
                [
                    "observe_property",
                    1,
                    "eof-reached",
                ],
                [
                    "observe_property",
                    2,
                    "time-pos",
                ],
            ):
                sock.sendall(
                    (
                        json.dumps(
                            {
                                "command": command,
                            }
                        )
                        + "\n"
                    ).encode("utf-8")
                )
        except OSError:
            pass

        buffer = b""

        try:
            while True:
                chunk = sock.recv(4096)

                if not chunk:
                    break

                buffer += chunk

                while b"\n" in buffer:
                    raw, buffer = (
                        buffer.split(b"\n", 1)
                    )

                    if not raw.strip():
                        continue

                    try:
                        message = json.loads(
                            raw.decode("utf-8")
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

                    event = message.get(
                        "event"
                    )

                    if event == "file-loaded":
                        self.ready.emit()

                    elif event == "playback-restart":
                        pass

                    elif event == "property-change":
                        if (
                            message.get("name") == "eof-reached"
                            and message.get("data") is True
                            and not self._stopping
                        ):
                            self.ended.emit()
                        elif (
                            message.get("name") == "time-pos"
                            and not self._started_sent
                            and not self._stopping
                        ):
                            position = message.get(
                                "data"
                            )

                            if (
                                isinstance(position, (int, float))
                                and position >= 0.15
                            ):
                                self._started_sent = True
                                self.started.emit()

                    elif event == "end-file":
                        # Fallback for mpv versions/configurations that
                        # still emit end-file normally with keep-open.
                        reason = message.get(
                            "reason",
                            "",
                        )

                        if (
                            reason == "eof"
                            and not self._stopping
                        ):
                            self.ended.emit()

        except OSError:
            pass

        finally:
            try:
                sock.close()
            except OSError:
                pass

            if self._sock is sock:
                self._sock = None
