import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import MPV_LOG_FILE
from .storage import clamp_int


class MpvController(QObject):
    ready = Signal(int)
    started = Signal(int)
    ended = Signal(int)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()

        self.process = None
        self.socket_path = f"/tmp/video-archive-mpv-{os.getpid()}.sock"
        self.log_path = MPV_LOG_FILE

        self._sock = None
        self._send_lock = threading.Lock()
        self._reader_thread = None
        self._generation = 0
        self._stopping = False
        self._started_sent = False
        self._log_file = None

    def preload(self, path, wid, volume=100, event_generation=0):
        self.stop(silent=True)

        path = Path(path)

        if not path.exists():
            self.failed.emit(int(event_generation), f"FILE NOT FOUND: {path.name}")
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
        volume = clamp_int(volume, 0, 100)

        args = [
            "mpv",
            f"--wid={int(wid)}",
            "--no-config",
            "--pause=yes",
            "--mute=yes",
            "--keep-open=yes",
            "--keepaspect=yes",
            "--loop-file=no",
            "--ao=alsa",
            "--audio-device=alsa/default",
            f"--input-ipc-server={self.socket_path}",
            "--force-window=yes",
            "--volume-max=100",
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
            if self._log_file is not None:
                try:
                    self._log_file.close()
                except OSError:
                    pass
                self._log_file = None
            self.process = None
            self.failed.emit(int(event_generation), str(exc))
            return

        self._generation += 1
        generation = self._generation
        process = self.process
        socket_path = self.socket_path
        self._reader_thread = threading.Thread(
            target=self._ipc_reader,
            args=(generation, int(event_generation), process, socket_path),
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
        volume = clamp_int(volume, 0, 100)

        self.command(
            ["set_property", "volume-max", 100]
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
        self._generation += 1
        reader_thread = self._reader_thread

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

        if (
            reader_thread is not None
            and reader_thread is not threading.current_thread()
            and reader_thread.is_alive()
        ):
            reader_thread.join(timeout=0.75)
        self._reader_thread = None

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

    def _fail_with_log(self, event_generation, message):
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

        self.failed.emit(int(event_generation), message)

    def _ipc_reader(self, generation, event_generation, process, socket_path):
        deadline = (
            time.monotonic() + 8.0
        )

        while time.monotonic() < deadline:
            if generation != self._generation:
                return

            return_code = process.poll()

            if return_code is not None:
                if not self._stopping and generation == self._generation:
                    self._fail_with_log(
                        event_generation, f"mpv exited with code {return_code}"
                    )
                return

            if os.path.exists(
                socket_path
            ):
                break

            time.sleep(0.02)

        else:
            if not self._stopping and generation == self._generation:
                self._fail_with_log(
                    event_generation, "mpv IPC did not become ready"
                )
            return

        sock = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM,
        )

        try:
            sock.connect(
                socket_path
            )

        except OSError as exc:
            if not self._stopping and generation == self._generation:
                self._fail_with_log(
                    event_generation, f"mpv IPC connection failed: {exc}"
                )
            return

        if generation != self._generation:
            try:
                sock.close()
            except OSError:
                pass
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
            while generation == self._generation:
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

                    if event == "file-loaded" and generation == self._generation:
                        self.ready.emit(event_generation)

                    elif event == "playback-restart":
                        pass

                    elif event == "property-change":
                        if (
                            message.get("name") == "eof-reached"
                            and message.get("data") is True
                            and not self._stopping
                            and generation == self._generation
                        ):
                            self.ended.emit(event_generation)
                        elif (
                            message.get("name") == "time-pos"
                            and not self._started_sent
                            and not self._stopping
                            and generation == self._generation
                        ):
                            position = message.get(
                                "data"
                            )

                            if (
                                isinstance(position, (int, float))
                                and position >= 0.15
                            ):
                                self._started_sent = True
                                self.started.emit(event_generation)

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
                            and generation == self._generation
                        ):
                            self.ended.emit(event_generation)

        except OSError:
            pass

        finally:
            try:
                sock.close()
            except OSError:
                pass

            if self._sock is sock:
                self._sock = None
