#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from video_archive.config import VIDEO_DIR


ROTATE_FILTERS = {
    "clockwise": "transpose=1",
    "cw": "transpose=1",
    "right": "transpose=1",
    "counterclockwise": "transpose=2",
    "ccw": "transpose=2",
    "left": "transpose=2",
}


def probe_video_size(path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")

    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("no video stream found")

    stream = streams[0]
    return int(stream["width"]), int(stream["height"])


def build_ffmpeg_command(source, target, rotate_filter):
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        rotate_filter,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-profile:v",
        "high",
        "-level",
        "4.0",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "copy",
        str(target),
    ]


def rotate_normalized_video(args):
    source = Path(args.video)
    if not source.is_absolute():
        source = Path(args.video_dir) / source

    if not source.exists():
        print(
            f"Video does not exist: {source}",
            file=sys.stderr,
        )
        return 1

    if not source.is_file():
        print(
            f"Not a file: {source}",
            file=sys.stderr,
        )
        return 1

    width, height = probe_video_size(source)
    expected_width = int(args.width)
    expected_height = int(args.height)

    if (width, height) == (expected_width, expected_height):
        print(
            f"SKIP {source.name}: already {expected_width}x{expected_height}"
        )
        return 0

    if (width, height) != (expected_height, expected_width):
        print(
            (
                f"FAILED {source.name}: found {width}x{height}, expected "
                f"{expected_height}x{expected_width} for a rotated "
                f"{expected_width}x{expected_height} video"
            ),
            file=sys.stderr,
        )
        return 1

    rotate_filter = ROTATE_FILTERS[args.direction]
    target = source.with_name(f".{source.stem}.rotating{source.suffix}")
    command = build_ffmpeg_command(source, target, rotate_filter)

    print(
        f"ROTATE {source.name}: {width}x{height} -> {expected_width}x{expected_height}"
    )
    print(
        " ".join(command)
    )

    if args.dry_run:
        return 0

    try:
        result = subprocess.run(
            command,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"FAILED {source.name}: ffmpeg returned {result.returncode}",
                file=sys.stderr,
            )
            return 1

        target.replace(source)
    finally:
        if target.exists():
            target.unlink()

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rotate one normalized video only when its dimensions match the "
            "expected landscape resolution swapped into portrait orientation."
        )
    )
    parser.add_argument(
        "video",
        help="Video filename inside normalized_videos, or an absolute path.",
    )
    parser.add_argument(
        "--video-dir",
        default=str(VIDEO_DIR),
        help="Directory containing normalized videos.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1024,
        help="Expected final landscape width.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=576,
        help="Expected final landscape height.",
    )
    parser.add_argument(
        "--direction",
        choices=sorted(ROTATE_FILTERS),
        default="clockwise",
        help="Direction to rotate the video.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Probe and print the ffmpeg command without replacing the file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(
        rotate_normalized_video(
            parse_args()
        )
    )
