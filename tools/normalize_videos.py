#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from video_archive.config import VIDEO_DIR

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
PADDED_LANDSCAPE_OUTPUT = (1920, 1080)
CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def find_videos(input_dir):
    return sorted(
        (
            path
            for path in input_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def bitrate_to_kbps(value):
    value = value.strip().lower()

    if value.endswith("k"):
        return int(
            float(value[:-1])
        )

    if value.endswith("m"):
        return int(
            float(value[:-1]) * 1000
        )

    return int(
        float(value) / 1000
    )


def _video_dimensions(source):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        width, height = (
            int(value)
            for value in result.stdout.strip().split(",")[:2]
        )
    except (AttributeError, TypeError, ValueError):
        return None
    return width, height


def detect_padded_landscape_crop(source):
    """Return a crop for a landscape image letterboxed in a portrait stream.

    cropdetect needs a higher threshold for some 10-bit/HDR sources whose
    encoded black is not represented as literal 8-bit zero.  The landscape
    aspect-ratio and full-width checks keep ordinary portrait videos intact.
    """
    dimensions = _video_dimensions(source)
    if not dimensions:
        return None
    source_width, source_height = dimensions
    if source_width >= source_height:
        return None

    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(source),
            "-vf",
            "cropdetect=limit=64:round=2:reset=0",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    candidates = []
    for width, height, x, y in CROP_RE.findall(result.stderr or ""):
        width, height, x, y = map(int, (width, height, x, y))
        aspect = width / height if height else 0
        if (
            aspect >= 1.5
            and width >= source_width * 0.8
            and height <= source_height * 0.8
            and x + width <= source_width
            and y + height <= source_height
        ):
            candidates.append((width, height, x, y))

    if not candidates:
        return None
    return Counter(candidates).most_common(1)[0][0]


def build_ffmpeg_command(
    source,
    target,
    width,
    height,
    video_bitrate,
    audio_bitrate,
    fps,
    crop=None,
):
    filters = []
    if crop:
        crop_width, crop_height, crop_x, crop_y = crop
        filters.append(f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}")
    filters.append(
        f"scale={width}:{height}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )
    scale_filter = ",".join(filters)
    buffer_size = f"{bitrate_to_kbps(video_bitrate) * 2}k"

    command = [
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
        scale_filter,
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
        "-b:v",
        video_bitrate,
        "-maxrate",
        video_bitrate,
        "-bufsize",
        buffer_size,
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-ar",
        "48000",
        "-ac",
        "2",
    ]

    if fps:
        command.extend(
            [
                "-r",
                str(fps),
            ]
        )

    command.append(
        str(target)
    )

    return command


def normalize_videos(args):
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(
            f"Input directory does not exist: {input_dir}",
            file=sys.stderr,
        )
        return 1

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    videos = find_videos(input_dir)

    if not videos:
        print(
            f"No videos found in {input_dir}"
        )
        return 0

    failures = 0

    seen_targets = set()
    for source in videos:
        target = output_dir / f"{source.stem}.mp4"
        target_key = target.name.casefold()
        if target_key in seen_targets:
            print(
                f"FAILED {source.name}: output name collision for {target.name}",
                file=sys.stderr,
            )
            failures += 1
            continue
        seen_targets.add(target_key)

        try:
            same_file = source.resolve() == target.resolve()
        except OSError:
            same_file = source.absolute() == target.absolute()
        if same_file:
            print(
                f"FAILED {source.name}: input and output are the same file",
                file=sys.stderr,
            )
            failures += 1
            continue

        if (
            target.exists()
            and not args.force
        ):
            print(
                f"SKIP {source.name} -> {target.name} already exists"
            )
            continue

        command = build_ffmpeg_command(
            source=source,
            target=target,
            width=args.width,
            height=args.height,
            video_bitrate=args.video_bitrate,
            audio_bitrate=args.audio_bitrate,
            fps=args.fps,
        )

        crop = None
        if not args.dry_run:
            crop = detect_padded_landscape_crop(source)
        if crop:
            width, height = PADDED_LANDSCAPE_OUTPUT
            command = build_ffmpeg_command(
                source=source,
                target=target,
                width=width,
                height=height,
                video_bitrate=args.video_bitrate,
                audio_bitrate=args.audio_bitrate,
                fps=args.fps,
                crop=crop,
            )
            print(
                f"CROP {source.name}: {crop[0]}x{crop[1]} at {crop[2]},{crop[3]}"
            )

        print(
            f"ENCODE {source.name} -> {target.name}"
        )
        print(
            " ".join(command)
        )

        if args.dry_run:
            continue

        result = subprocess.run(
            command,
            check=False,
        )

        if result.returncode != 0:
            failures += 1
            print(
                f"FAILED {source.name}",
                file=sys.stderr,
            )

    if failures:
        print(
            f"{failures} video(s) failed",
            file=sys.stderr,
        )
        return 1

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Transcode videos to a consistent landscape H.264/AAC MP4 "
            "format for reliable playback."
        )
    )

    parser.add_argument(
        "--input-dir",
        default=str(VIDEO_DIR.parent / "videos"),
        help="Directory containing source videos.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(VIDEO_DIR.parent / "normalized_videos"),
        help="Directory for normalized MP4 files.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1024,
        help="Output video width.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=576,
        help="Output video height.",
    )
    parser.add_argument(
        "--video-bitrate",
        default="2500k",
        help="Target and max H.264 video bitrate.",
    )
    parser.add_argument(
        "--audio-bitrate",
        default="160k",
        help="AAC audio bitrate.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output frame rate. Use 0 to keep source timing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing normalized files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ffmpeg commands without encoding.",
    )

    args = parser.parse_args()

    if args.fps == 0:
        args.fps = None

    return args


if __name__ == "__main__":
    raise SystemExit(
        normalize_videos(
            parse_args()
        )
    )
