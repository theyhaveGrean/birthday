from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "run_app.sh").read_text()


def test_launcher_has_bounded_restart_loop():
    assert "CRASH_COUNT" in LAUNCHER
    assert "-ge 5" in LAUNCHER
    assert "sleep 2" in LAUNCHER
    assert "python3 main.py" in LAUNCHER


def test_launcher_resets_crash_streak_after_stable_run():
    assert "STABLE_RUN_SECONDS=300" in LAUNCHER
    assert 'if [ "$runtime" -ge "$STABLE_RUN_SECONDS" ]' in LAUNCHER
    assert "CRASH_COUNT=0" in LAUNCHER


def test_launcher_disables_x11_screensaver_and_dpms():
    assert "xset s off" in LAUNCHER
    assert "xset -dpms" in LAUNCHER
    assert "xset s noblank" in LAUNCHER
