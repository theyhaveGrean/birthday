#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from video_archive.config import VIDEO_DIR

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


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


def build_ffmpeg_command(
    source,
    target,
    width,
    height,
    video_bitrate,
    audio_bitrate,
    fps,
):
    scale_filter = (
        f"scale={width}:{height}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )
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
        default=str(VIDEO_DIR.parent / "videos_raw"),
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
