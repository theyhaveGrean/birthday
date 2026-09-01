from argparse import Namespace
from pathlib import Path

import tools.normalize_videos as normalizer


def _args(input_dir, output_dir, *, force=False, dry_run=False):
    return Namespace(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        width=1024,
        height=576,
        video_bitrate="2500k",
        audio_bitrate="160k",
        fps=30,
        force=force,
        dry_run=dry_run,
    )


def test_default_input_and_output_directories_are_separate(monkeypatch):
    monkeypatch.setattr("sys.argv", ["normalize_videos.py"])
    args = normalizer.parse_args()
    assert Path(args.input_dir).name == "videos_raw"
    assert Path(args.output_dir).name == "normalized_videos"
    assert Path(args.input_dir) != Path(args.output_dir)


def test_normalizer_refuses_to_transcode_file_onto_itself(monkeypatch, tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    called = []
    monkeypatch.setattr(normalizer.subprocess, "run", lambda *a, **k: called.append(a))

    result = normalizer.normalize_videos(_args(tmp_path, tmp_path, force=True))

    assert result == 1
    assert called == []


def test_normalizer_detects_output_stem_collisions(monkeypatch, tmp_path):
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    source_dir.mkdir()
    (source_dir / "clip.mov").write_bytes(b"a")
    (source_dir / "clip.mp4").write_bytes(b"b")
    monkeypatch.setattr(normalizer.subprocess, "run", lambda *a, **k: None)

    # dry-run prevents ffmpeg execution; the second source still collides.
    result = normalizer.normalize_videos(
        _args(source_dir, output_dir, force=True, dry_run=True)
    )

    assert result == 1
