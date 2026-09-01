import queue
import struct
import threading
import time
import wave
from pathlib import Path

from video_archive.audio import AudioController


def _write_test_wav(path: Path):
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"".join(struct.pack("<h", value) for value in (1000, -1000, 2000)))


def test_scaled_sfx_is_cached_for_same_sound_and_volume(tmp_path):
    source = tmp_path / "click.wav"
    _write_test_wav(source)

    controller = AudioController.__new__(AudioController)
    controller._scaled_cache = {}
    controller._scaled_cache_dir = tmp_path / ".scaled"

    first = controller._scaled_sound_path("click", source, 150)
    second = controller._scaled_sound_path("click", source, 150)

    assert first == second
    assert first.exists()
    assert first.parent == controller._scaled_cache_dir


def test_scaled_sfx_uses_distinct_cache_entries_per_volume(tmp_path):
    source = tmp_path / "click.wav"
    _write_test_wav(source)

    controller = AudioController.__new__(AudioController)
    controller._scaled_cache = {}
    controller._scaled_cache_dir = tmp_path / ".scaled"

    loud = controller._scaled_sound_path("click", source, 150)
    quiet = controller._scaled_sound_path("click", source, 50)

    assert loud != quiet
    assert loud.exists()
    assert quiet.exists()


def test_scaled_sfx_cache_invalidates_when_source_changes(tmp_path):
    source = tmp_path / "click.wav"
    _write_test_wav(source)

    controller = AudioController.__new__(AudioController)
    controller._scaled_cache = {}
    controller._scaled_cache_dir = tmp_path / ".scaled"

    first = controller._scaled_sound_path("click", source, 150)
    with wave.open(str(source), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"".join(struct.pack("<h", value) for value in (3000, -3000, 500)))
    second = controller._scaled_sound_path("click", source, 150)

    assert first != second
    assert first.exists()
    assert second.exists()


def _queued_controller(tmp_path):
    controller = AudioController.__new__(AudioController)
    controller.available = True
    controller.enabled = True
    controller.volume = 100
    controller.sounds = {
        "click": tmp_path / "click.wav",
        "notify": tmp_path / "notify.wav",
    }
    controller._play_queue = queue.Queue(maxsize=1)
    return controller


def test_pending_notify_cannot_be_replaced_by_click(tmp_path):
    controller = _queued_controller(tmp_path)
    controller.play("notify", ignore_enabled=True)
    controller.play("click")
    name, _ = controller._play_queue.get_nowait()
    assert name == "notify"


def test_notify_replaces_pending_click(tmp_path):
    controller = _queued_controller(tmp_path)
    controller.play("click")
    controller.play("notify", ignore_enabled=True)
    name, _ = controller._play_queue.get_nowait()
    assert name == "notify"


def test_wait_until_idle_waits_for_active_sfx(monkeypatch, tmp_path):
    monkeypatch.setattr("video_archive.audio.shutil.which", lambda name: name)

    started = threading.Event()
    release = threading.Event()

    class WaitingAudioController(AudioController):
        def _prepare_sounds(self):
            self.sounds = {"click": tmp_path / "click.wav"}

        def _play_file(self, name, path):
            started.set()
            assert release.wait(timeout=1.0)

    controller = WaitingAudioController()
    controller.play("click")
    assert started.wait(timeout=1.0)

    result = []
    waiter = threading.Thread(
        target=lambda: result.append(controller.wait_until_idle(timeout=1.0, settle=0)),
    )
    waiter.start()
    time.sleep(0.05)

    assert result == []

    release.set()
    waiter.join(timeout=1.0)

    assert result == [True]
