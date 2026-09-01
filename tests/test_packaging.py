from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_state_and_rotated_logs_are_gitignored():
    ignore = (ROOT / ".gitignore").read_text()
    assert ".read_memos.json" in ignore
    assert "*.log.*" in ignore
    assert "videos_raw/" in ignore
    assert "normalized_videos/*" in ignore


def test_cloud_docs_use_current_home_navigation_and_unicode_limit():
    docs = (ROOT / "CLOUD_MESSAGES.md").read_text()
    assert "`HOME` -> `MEMOS`" in docs
    assert "`APPS` -> `MEMOS`" not in docs
    assert "1200 Unicode characters" in docs


def test_readme_is_packaged():
    assert (ROOT / "README.md").exists()


def test_user_intentional_media_and_volume_behaviors_are_preserved():
    app_source = (ROOT / "src/video_archive/app.py").read_text()
    ui_source = (ROOT / "src/video_archive/ui.py").read_text()
    assert 'VIDEO_EXTENSIONS = {".mp4", ".mov"}' in app_source
    assert "path.name" in app_source
    assert "MAX_MPV_VOLUME = 150" in app_source
    assert "PASS:" in ui_source
