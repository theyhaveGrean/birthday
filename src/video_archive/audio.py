import math
import shutil
import struct
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from .config import SOUND_DIR

SAMPLE_RATE = 22050
RETURN_FLICKER_DURATION = 0.11
MAX_SFX_VOLUME = 150


class AudioController:
    def __init__(self, volume=100, sfx_enabled=True):
        self.player = shutil.which("aplay")
        self.available = self.player is not None
        self.enabled = bool(sfx_enabled)
        self.volume = max(0, min(150, int(volume)))
        self.sounds = {}

        if self.available:
            self._prepare_sounds()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_volume(self, volume):
        self.volume = max(0, min(MAX_SFX_VOLUME, int(volume)))

    def play(self, name):
        if (
            not self.available
            or not self.enabled
            or self.volume <= 0
            or name not in self.sounds
        ):
            return

        threading.Thread(
            target=self._play_file,
            args=(name, self.sounds[name]),
            daemon=True,
        ).start()

    def _play_file(self, name, path):
        playback_path = path
        scaled_path = None

        if self.volume != 100:
            scaled_path = self._scaled_sound_path(path)
            playback_path = scaled_path or path

        result = subprocess.run(
            [self.player, "-q", str(playback_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if scaled_path is not None:
            try:
                scaled_path.unlink()
            except OSError:
                pass

        if result.returncode != 0:
            print(
                f"audio failed for {name}: {result.stderr.strip()}",
                flush=True,
            )

    def _scaled_sound_path(self, path):
        factor = self.volume / 100

        try:
            with wave.open(str(path), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                frame_rate = source.getframerate()
                frames = source.readframes(source.getnframes())

            if sample_width != 2:
                return None

            samples = struct.unpack(
                f"<{len(frames) // 2}h",
                frames,
            )
            scaled = [
                max(
                    -32768,
                    min(32767, int(sample * factor)),
                )
                for sample in samples
            ]

            with tempfile.NamedTemporaryFile(
                prefix="video-archive-sfx-",
                suffix=".wav",
                delete=False,
            ) as temp:
                temp_path = Path(temp.name)

            with wave.open(str(temp_path), "wb") as target:
                target.setnchannels(channels)
                target.setsampwidth(sample_width)
                target.setframerate(frame_rate)
                target.writeframes(
                    b"".join(
                        struct.pack("<h", sample)
                        for sample in scaled
                    )
                )

            return temp_path

        except (OSError, wave.Error, struct.error):
            return None

    def _prepare_sounds(self):
        SOUND_DIR.mkdir(parents=True, exist_ok=True)

        specs = {
            "boot": ((160, 0.05), (240, 0.06), (420, 0.08)),
            "click": ((900, 0.018), (420, 0.018)),
            "select": ((300, 0.035), (560, 0.045), (840, 0.035)),
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
