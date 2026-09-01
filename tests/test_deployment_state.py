from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "src/video_archive/app.py").read_text()
AUDIO_SOURCE = (ROOT / "src/video_archive/audio.py").read_text()
PLAYER_SOURCE = (ROOT / "src/video_archive/player.py").read_text()


def test_wifi_status_requests_are_queued():
    assert "self.wifi_status_refresh_pending = True" in APP_SOURCE
    assert "if self.wifi_status_refresh_pending:" in APP_SOURCE


def test_select_can_cancel_loading():
    assert 'elif self.mode == "loading":' in APP_SOURCE
    assert "self._begin_return()" in APP_SOURCE


def test_sfx_prepare_failure_is_nonfatal():
    assert "SFX disabled: failed to prepare sounds" in AUDIO_SOURCE
    assert "self.available = False" in AUDIO_SOURCE


def test_mpv_spawn_failure_closes_log():
    assert "self._log_file.close()" in PLAYER_SOURCE


def test_playback_reveal_is_generation_guarded():
    assert "self.playback_generation += 1" in APP_SOURCE
    assert "generation != self.playback_generation" in APP_SOURCE
    assert "lambda g=generation: self._maybe_reveal_video(g)" in APP_SOURCE


def test_cloud_errors_are_rate_limited():
    assert "cloud_last_logged_error" in APP_SOURCE
    assert ">= 3600" in APP_SOURCE
    assert "cloud message fetch recovered" in APP_SOURCE


def test_player_events_are_generation_tagged_at_app_boundary():
    assert "ready = Signal(int)" in PLAYER_SOURCE
    assert "started = Signal(int)" in PLAYER_SOURCE
    assert "ended = Signal(int)" in PLAYER_SOURCE
    assert "failed = Signal(int, str)" in PLAYER_SOURCE
    assert 'generation != self.playback_generation' in APP_SOURCE


def test_wifi_status_is_refreshed_without_opening_wifi_settings():
    assert "self.wifi_status_timer.start()" in APP_SOURCE
    assert "QTimer.singleShot(250, self._refresh_wifi_status)" in APP_SOURCE


def test_about_refresh_timer_is_not_started_globally():
    block = APP_SOURCE.split("self.about_refresh_timer = QTimer(self)", 1)[1].split(
        "self.wifi_scan_finished.connect", 1
    )[0]
    assert "self.about_refresh_timer.start()" not in block


def test_return_completion_is_state_guarded_and_restarts_idle_timer():
    assert 'if self.mode != "returning" or not self.return_pending:' in APP_SOURCE
    finish_block = APP_SOURCE.split("def _finish_return(self):", 1)[1].split("# =====================================================", 1)[0]
    assert "self._restart_display_sleep_timer()" in finish_block
    assert "if not self.display.sleeping:" in finish_block


def test_memo_wake_resumes_effects_after_display_sleep():
    wake_block = APP_SOURCE.split("def _wake_display_for_memo(self):", 1)[1].split("def _play_memo_chime", 1)[0]
    assert "was_sleeping = self.display.sleeping" in wake_block
    assert "self._resume_visible_effects()" in wake_block


def test_returning_mode_is_exempt_from_sleep_mid_transition():
    sleep_block = APP_SOURCE.split("def _sleep_display(self):", 1)[1].split("def _physical_left", 1)[0]
    assert '"returning"' in sleep_block


def test_wifi_status_failure_preserves_last_known_state():
    worker = APP_SOURCE.split("def _wifi_status_worker(self):", 1)[1].split("def _wifi_status_finished", 1)[0]
    assert "self.wifi_status_finished.emit(None)" in worker
    finished = APP_SOURCE.split("def _wifi_status_finished(self, current):", 1)[1].split("def _connect_wifi", 1)[0]
    assert "if current is None:" in finished


def test_wifi_status_poll_does_not_scan_all_access_points():
    worker = APP_SOURCE.split("def _wifi_status_worker(self):", 1)[1].split("def _wifi_status_finished", 1)[0]
    assert '"wifi", "list"' not in worker


def test_global_home_is_shown_before_blocking_player_stop():
    block = APP_SOURCE.split("def go_home(self):", 1)[1].split("def play_selected", 1)[0]
    assert block.index("self.pages.setCurrentWidget(self.home)") < block.index("self.player.stop(silent=True)")


def test_device_uptime_prefers_proc_uptime():
    diagnostics = APP_SOURCE.split("def _system_diagnostics(self):", 1)[1].split("def _about_opened", 1)[0]
    assert '/proc/uptime' in diagnostics
