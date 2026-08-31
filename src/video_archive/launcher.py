import json
import os
import subprocess
import time
from pathlib import Path

from .config import APP_DIR, DEFAULT_SETTINGS, SELECTION_FILE, SETTINGS_FILE

SRC_DIR = APP_DIR / "src"
MAX_MPV_VOLUME = 150


def load_volume():
    volume = DEFAULT_SETTINGS["volume"]

    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(
                SETTINGS_FILE.read_text()
            )
        except (OSError, json.JSONDecodeError):
            settings = {}

        if isinstance(settings, dict):
            volume = settings.get("volume", volume)

    try:
        volume = int(volume)
    except (TypeError, ValueError):
        volume = DEFAULT_SETTINGS["volume"]

    volume = max(0, min(100, volume))

    return round(volume * MAX_MPV_VOLUME / 100)


def run_gallery(returning=False, selected_index=0):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "eglfs"
    env["VIDEO_ARCHIVE_SELECTED_INDEX"] = str(selected_index)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC_DIR), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(SRC_DIR)]
    )

    if returning:
        env["VIDEO_ARCHIVE_RETURNING"] = "1"
    else:
        env.pop("VIDEO_ARCHIVE_RETURNING", None)

    result = subprocess.run(
        ["python3", "-m", "video_archive.app"],
        env=env,
        check=False,
    )

    return result.returncode


def play_video(video_path):
    # No artificial pre-play sleep: the transition has already spent its time
    # prefetching the file, and its final frames deliberately fade to the same
    # black shown during the DRM ownership handoff.
    volume = load_volume()

    result = subprocess.run(
        [
            "mpv",
            "--fullscreen",
            "--really-quiet",
            "--keepaspect=yes",
            "--loop-file=no",
            "--keep-open=no",
            "--volume-max=150",
            f"--volume={volume}",
            "--af=lavfi=[highpass=f=180,dynaudnorm=f=250:g=15:p=0.95:m=20]",
            str(video_path),
        ],
        check=False,
    )

    # Tiny release margin before Qt asks EGLFS for DRM again. This is short
    # enough to be visually covered by the black -> return flicker sequence.
    time.sleep(0.03)
    return result.returncode


def main():
    returning = False
    selected_index = 0

    while True:
        return_code = run_gallery(
            returning=returning,
            selected_index=selected_index,
        )

        returning = False

        if return_code == 0:
            break

        if return_code >= 10:
            selected_index = return_code - 10

            if not SELECTION_FILE.exists():
                continue

            video_path = Path(SELECTION_FILE.read_text().strip())

            if not video_path.exists():
                continue

            play_video(video_path)

            # Relaunch Qt into the reverse transition, preserving the same
            # selected title in the gallery behind it.
            returning = True
            continue

        # Unexpected Qt crash: restart the appliance rather than exposing OS.
        time.sleep(0.25)


if __name__ == "__main__":
    main()
