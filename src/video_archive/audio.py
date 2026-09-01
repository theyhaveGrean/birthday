import hashlib
import math
import queue
import shutil
import struct
import subprocess
import threading
import wave
from pathlib import Path

from .config import SOUND_DIR
from .storage import clamp_int

SAMPLE_RATE = 22050
RETURN_FLICKER_DURATION = 0.11
MAX_SFX_VOLUME = 150
SOUND_SCHEMA_VERSION = "2"


class AudioController:
    def __init__(self, volume=100, sfx_enabled=True):
        self.player = shutil.which("aplay")
        self.available = self.player is not None
        self.enabled = bool(sfx_enabled)
        self.volume = clamp_int(volume, 0, MAX_SFX_VOLUME)
        self.sounds = {}
        self._play_queue = queue.Queue(maxsize=1)
        self._worker = None
        self._scaled_cache = {}
        self._scaled_cache_dir = SOUND_DIR / ".scaled"

        if self.available:
            try:
                self._prepare_sounds()
            except (OSError, wave.Error, struct.error) as error:
                # SFX are optional; cache/write problems must not kill startup.
                print(f"SFX disabled: failed to prepare sounds: {error}", flush=True)
                self.available = False
                self.sounds = {}

        if self.available:
            self._worker = threading.Thread(
                target=self._audio_worker,
                daemon=True,
                name="sfx-worker",
            )
            self._worker.start()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_volume(self, volume):
        self.volume = clamp_int(volume, 0, MAX_SFX_VOLUME)

    def play(self, name, ignore_enabled=False):
        if (
            not self.available
            or (not self.enabled and not ignore_enabled)
            or self.volume <= 0
            or name not in self.sounds
        ):
            return

        # Keep one audio worker. Memo notifications outrank ordinary UI SFX:
        # a click/select must never displace a pending notify chime.
        item = (name, self.sounds[name])
        try:
            self._play_queue.put_nowait(item)
            return
        except queue.Full:
            pass

        with self._play_queue.mutex:
            pending = list(self._play_queue.queue)
            if pending and pending[0][0] == "notify" and name != "notify":
                return

        try:
            self._play_queue.get_nowait()
            self._play_queue.task_done()
        except queue.Empty:
            pass

        try:
            self._play_queue.put_nowait(item)
        except queue.Full:
            # The worker may have raced us and another higher-value event won.
            pass

    def _audio_worker(self):
        while True:
            name, path = self._play_queue.get()
            try:
                self._play_file(name, path)
            finally:
                self._play_queue.task_done()

    def _play_file(self, name, path):
        playback_path = path
        if self.volume != 100:
            playback_path = self._scaled_sound_path(name, path, self.volume) or path

        try:
            result = subprocess.run(
                [self.player, "-q", str(playback_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except OSError as error:
            print(f"audio failed for {name}: {error}", flush=True)
            return

        if result.returncode != 0:
            print(
                f"audio failed for {name}: {result.stderr.strip()}",
                flush=True,
            )

    def _scaled_sound_path(self, name, path, volume):
        """Return a cached WAV scaled for this exact master-volume value."""
        try:
            fingerprint = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
        except OSError:
            return None
        key = (name, int(volume), fingerprint)
        cached = self._scaled_cache.get(key)
        if cached is not None and cached.exists():
            return cached

        factor = volume / 100
        try:
            self._scaled_cache_dir.mkdir(parents=True, exist_ok=True)
            target_path = self._scaled_cache_dir / f"{name}-{int(volume):03}-{fingerprint}.wav"
            if target_path.exists():
                self._scaled_cache[key] = target_path
                return target_path

            with wave.open(str(path), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                frame_rate = source.getframerate()
                frames = source.readframes(source.getnframes())

            if sample_width != 2:
                return None

            samples = struct.unpack(f"<{len(frames) // 2}h", frames)
            scaled = [
                max(-32768, min(32767, int(sample * factor)))
                for sample in samples
            ]

            with wave.open(str(target_path), "wb") as target:
                target.setnchannels(channels)
                target.setsampwidth(sample_width)
                target.setframerate(frame_rate)
                target.writeframes(
                    b"".join(struct.pack("<h", sample) for sample in scaled)
                )

            self._scaled_cache[key] = target_path
            return target_path
        except (OSError, wave.Error, struct.error):
            return None

    def _prepare_sounds(self):
        SOUND_DIR.mkdir(parents=True, exist_ok=True)

        schema_file = SOUND_DIR / ".sound-schema"
        try:
            current_schema = schema_file.read_text().strip() if schema_file.exists() else ""
        except OSError:
            current_schema = ""
        if current_schema != SOUND_SCHEMA_VERSION:
            for stale in SOUND_DIR.glob("*.wav"):
                try:
                    stale.unlink()
                except OSError:
                    pass
            shutil.rmtree(self._scaled_cache_dir, ignore_errors=True)
            self._scaled_cache.clear()
            try:
                schema_file.write_text(SOUND_SCHEMA_VERSION + "\n")
            except OSError:
                pass

        specs = {
            "boot": ((160, 0.05), (240, 0.06), (420, 0.08)),
            "click": ((900, 0.018), (420, 0.018)),
            "select": ((300, 0.035), (560, 0.045), (840, 0.035)),
            "notify": ((660, 0.045), (990, 0.060)),
            "load": ((180, 0.045), (120, 0.03), (500, 0.04)),
            "error": ((130, 0.12),),
        }

        for name, tones in specs.items():
            path = SOUND_DIR / f"{name}.wav"
            if not path.exists():
                self._write_tones(path, tones)
            self.sounds[name] = path

        return_path = SOUND_DIR / "return.wav"
        if not self._is_return_flicker(return_path):
            self._write_return_flicker(return_path)
        self.sounds["return"] = return_path

    def _is_return_flicker(self, path):
        if not path.exists():
            return False

        try:
            with wave.open(str(path), "rb") as wav_file:
                return (
                    wav_file.getnchannels() == 1
                    and wav_file.getsampwidth() == 2
                    and wav_file.getframerate() == SAMPLE_RATE
                    and wav_file.getnframes()
                    == int(SAMPLE_RATE * RETURN_FLICKER_DURATION)
                )
        except wave.Error:
            return False

    def _write_tones(self, path, tones):
        samples = []

        for frequency, duration in tones:
            count = int(SAMPLE_RATE * duration)
            for index in range(count):
                fade = min(index / 80, (count - index) / 80, 1)
                value = math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
                samples.append(int(value * fade * 9000))

            samples.extend([0] * int(SAMPLE_RATE * 0.012))

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(
                b"".join(struct.pack("<h", sample) for sample in samples)
            )

    def _write_return_flicker(self, path):
        count = int(SAMPLE_RATE * RETURN_FLICKER_DURATION)
        samples = []
        seed = 0x4C434348
        last_raw = 0.0
        filtered = 0.0

        for index in range(count):
            progress = index / max(1, count - 1)

            seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
            raw = ((seed >> 16) & 0xFFFF) / 32767.5 - 1.0

            high_passed = raw - last_raw
            last_raw = raw
            filtered = filtered * 0.64 + high_passed * 0.36

            attack = min(index / 90, 1.0)
            decay = (1.0 - progress) ** 2.4
            envelope = attack * decay

            if progress > 0.82:
                envelope *= 0.25

            waveform = filtered

            samples.append(
                int(waveform * envelope * 6500)
            )

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(
                b"".join(struct.pack("<h", sample) for sample in samples)
            )
