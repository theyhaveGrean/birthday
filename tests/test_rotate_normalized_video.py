from argparse import Namespace

import tools.rotate_normalized_video as rotator


def _args(tmp_path, video_name="clip.mp4", *, dry_run=False, direction="clockwise"):
    return Namespace(
        video=video_name,
        video_dir=str(tmp_path),
        direction=direction,
        dry_run=dry_run,
    )


def test_rotator_runs_for_any_resolution(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    commands = []

    monkeypatch.setattr(rotator, "probe_video_size", lambda path: (1024, 576))
    monkeypatch.setattr(
        rotator.subprocess,
        "run",
        lambda command, check: commands.append(command)
        or Namespace(returncode=0),
    )
    monkeypatch.setattr(rotator.Path, "replace", lambda self, target: None)

    result = rotator.rotate_normalized_video(_args(tmp_path))

    assert result == 0
    assert commands
    assert "transpose=1" in commands[0]


def test_rotator_reports_probe_failure(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")

    def fail_probe(path):
        raise RuntimeError("no video stream found")

    monkeypatch.setattr(rotator, "probe_video_size", fail_probe)

    result = rotator.rotate_normalized_video(_args(tmp_path))

    assert result == 1


def test_rotator_uses_requested_direction(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    commands = []

    monkeypatch.setattr(rotator, "probe_video_size", lambda path: (576, 1024))
    monkeypatch.setattr(
        rotator.subprocess,
        "run",
        lambda command, check: commands.append(command)
        or Namespace(returncode=0),
    )
    monkeypatch.setattr(rotator.Path, "replace", lambda self, target: None)

    result = rotator.rotate_normalized_video(_args(tmp_path, direction="left"))

    assert result == 0
    assert commands
    assert "transpose=2" in commands[0]


def test_rotator_dry_run_does_not_run_ffmpeg(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    called = []

    monkeypatch.setattr(rotator, "probe_video_size", lambda path: (576, 1024))
    monkeypatch.setattr(rotator.subprocess, "run", lambda *a, **k: called.append(a))

    result = rotator.rotate_normalized_video(_args(tmp_path, dry_run=True))

    assert result == 0
    assert called == []
