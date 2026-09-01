import pytest

pytestmark = pytest.mark.usefixtures("qapp")

# PySide6 is an application dependency, so GUI tests must fail collection if it
# is missing rather than silently skipping the most important behavioral tests.
import PySide6  # noqa: F401
import video_archive.app as app


def test_load_videos_honors_order_and_appends_remaining(monkeypatch, tmp_path):
    video_dir = tmp_path / "normalized_videos"
    video_dir.mkdir()
    (video_dir / "B.mp4").write_bytes(b"")
    (video_dir / "a.mov").write_bytes(b"")
    (video_dir / "ignored.txt").write_text("x")
    order_file = tmp_path / "order.txt"
    order_file.write_text("B.mp4\n")

    monkeypatch.setattr(app, "VIDEO_DIR", video_dir)
    monkeypatch.setattr(app, "ORDER_FILE", order_file)

    assert [p.name for p in app.load_videos()] == ["B.mp4", "a.mov"]


def test_load_videos_survives_unreadable_directory(monkeypatch, tmp_path):
    impossible = tmp_path / "not-a-dir"
    impossible.write_text("file")
    monkeypatch.setattr(app, "VIDEO_DIR", impossible)
    monkeypatch.setattr(app, "ORDER_FILE", tmp_path / "order.txt")
    assert app.load_videos() == []


def test_load_note_falls_back_when_path_is_unusable(monkeypatch, tmp_path):
    parent_file = tmp_path / "parent"
    parent_file.write_text("x")
    impossible = parent_file / "note.txt"
    monkeypatch.setattr(app, "NOTE_FILE", impossible)
    assert app.load_note() == app.DEFAULT_NOTE


def _config_widget(qapp=None):
    from video_archive.ui import ConfigWidget

    return ConfigWidget(
        "note",
        "",
        "",
        [{"id": "1", "date": "2026-08-31 10:00", "message": "hello"}],
        80,
        True,
        True,
        True,
        80,
        5,
    )


def test_corrupt_brightness_and_booleans_fall_back_safely(monkeypatch, tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        '{"brightness": null, "volume": "nope", "sfx_enabled": "false", '
        '"memo_chime_enabled": "on", "wake_on_memo": "garbage", '
        '"cloud_message_url": null}'
    )
    monkeypatch.setattr(app, "SETTINGS_FILE", settings_file)

    settings = app.load_settings()
    assert settings["brightness"] == app.DEFAULT_SETTINGS["brightness"]
    assert settings["volume"] == app.DEFAULT_SETTINGS["volume"]
    assert settings["sfx_enabled"] is False
    assert settings["memo_chime_enabled"] is True
    assert settings["wake_on_memo"] == app.DEFAULT_SETTINGS["wake_on_memo"]
    assert settings["cloud_message_url"] == ""


def test_runtime_memo_select_returns_to_list():
    widget = _config_widget()
    widget.show_memos_home()
    widget.select()
    assert widget.memo_reading is True
    widget.select()
    assert widget.memo_reading is False
    assert widget.memo_scroll == 0


def test_admin_chord_is_blocked_while_display_values_are_editing():
    widget = _config_widget()
    widget.show_settings_home()
    widget.settings_section = "display"
    widget.editing_brightness = True
    assert widget.can_open_admin() is False
    widget.editing_brightness = False
    widget.editing_sleep_timeout = True
    assert widget.can_open_admin() is False


def test_about_uses_system_status_data():
    widget = _config_widget()
    widget.set_about_data({"wifi": "HOME", "ip": "192.0.2.1", "videos": 4})
    assert widget.about_page.data["wifi"] == "HOME"
    assert widget.about_page.data["ip"] == "192.0.2.1"
    assert widget.about_page.data["videos"] == 4


def test_about_open_emits_live_refresh_request():
    widget = _config_widget()
    widget.show_settings_home()
    widget.selected_index = 4
    emitted = []
    widget.about_opened.connect(lambda: emitted.append(True))
    widget.select()
    assert widget.showing_about is True
    assert emitted == [True]


def test_info_page_wraps_long_lines_to_panel_width():
    from PySide6.QtGui import QFont, QFontMetrics
    from video_archive.ui import TextPanelPage

    metrics = QFontMetrics(QFont("DejaVu Sans Mono", 17, QFont.Bold))
    lines = TextPanelPage._wrap_lines("THIS IS A VERY LONG LINE THAT MUST WRAP", metrics, 120)
    assert len(lines) > 1
    assert all(metrics.horizontalAdvance(line) <= 120 for line in lines)


def test_info_scroll_never_accumulates_past_bottom():
    from PySide6.QtGui import QImage, QPainter
    from video_archive.ui import TextPanelPage

    page = TextPanelPage("INFO", "\n".join(f"LINE {i:02}" for i in range(80)))
    image = QImage(1024, 600, QImage.Format_ARGB32)
    painter = QPainter(image)
    page.draw(painter, 1024, 600)
    painter.end()

    assert page.max_scroll > 0
    for _ in range(page.max_scroll + 50):
        page.move(1)
    assert page.scroll == page.max_scroll
    page.move(-1)
    assert page.scroll == page.max_scroll - 1


def test_config_screen_state_is_exclusive():
    from video_archive.ui import ConfigScreen

    widget = _config_widget()
    widget.show_settings_home()
    widget.showing_wifi = True
    assert widget.screen == ConfigScreen.WIFI
    assert widget.showing_wifi is True
    assert widget.showing_memos is False
    assert widget.showing_about is False

    widget.showing_about = True
    assert widget.screen == ConfigScreen.ABOUT
    assert widget.showing_wifi is False
    assert widget.showing_about is True


def test_settings_sounds_and_display_back_navigation():
    widget = _config_widget()
    widget.show_settings_home()

    widget.selected_index = 2
    widget.select()
    assert widget.settings_section == "sounds"
    widget.selected_index = 3
    widget.select()
    assert widget.settings_section is None
    assert widget.selected_index == 2

    widget.selected_index = 3
    widget.select()
    assert widget.settings_section == "display"
    widget.selected_index = 3
    widget.select()
    assert widget.settings_section is None
    assert widget.selected_index == 3


def test_wifi_back_returns_to_settings_screen():
    from video_archive.ui import ConfigScreen

    widget = _config_widget()
    widget.show_settings_home()
    widget.selected_index = 1
    widget.select()
    assert widget.screen == ConfigScreen.WIFI

    widget.set_wifi_networks([])
    widget.wifi_selected_index = len(widget.wifi_networks) + 2
    widget.select()
    assert widget.screen == ConfigScreen.SETTINGS


def test_memo_reader_select_and_global_screen_state():
    from video_archive.ui import ConfigScreen

    widget = _config_widget()
    widget.show_memos_home()
    assert widget.screen == ConfigScreen.MEMOS
    widget.select()
    assert widget.memo_reading is True
    widget.select()
    assert widget.memo_reading is False
    assert widget.screen == ConfigScreen.MEMOS


def test_physical_select_hold_calls_global_home():
    calls = []

    class FakeAudio:
        def play(self, name):
            calls.append(("sound", name))

    class FakeWindow:
        audio = FakeAudio()
        def _note_activity(self):
            calls.append(("activity", None))
        def go_home(self):
            calls.append(("home", None))

    app.VideoArchiveWindow._physical_select_held(FakeWindow())
    assert calls == [("activity", None), ("sound", "select"), ("home", None)]


def test_memo_refresh_preserves_reader_selection_by_id_and_scroll():
    widget = _config_widget()
    widget.memos = [
        {"id": "a", "date": "2026-08-31 10:00", "message": "A"},
        {"id": "b", "date": "2026-08-31 10:01", "message": "B"},
    ]
    widget.memo_selected_index = 1
    widget.memo_reading = True
    widget.memo_scroll = 4
    widget.memo_max_scroll = 10

    widget.set_memo("current", "2026-08-31 10:02")
    assert widget.memo_scroll == 4

    widget.set_memos([
        {"id": "c", "date": "2026-08-31 10:03", "message": "C"},
        {"id": "a", "date": "2026-08-31 10:00", "message": "A"},
        {"id": "b", "date": "2026-08-31 10:01", "message": "B"},
    ])

    assert widget.memo_selected_index == 2
    assert widget.memos[widget.memo_selected_index]["id"] == "b"
    assert widget.memo_reading is True
    assert widget.memo_scroll == 4


def test_cloud_message_finished_updates_memos_without_name_error(monkeypatch):
    memo = {"id": "fresh", "date": "2026-08-31 10:03", "message": "fresh"}
    calls = []

    class FakeDisplay:
        def wake(self):
            calls.append("wake")

    class FakeCounter:
        def set_unread_memo_count(self, count):
            calls.append(("unread", count))

    class FakeConfig:
        showing_admin = False
        showing_about = False

        def set_memo(self, message, memo_date):
            calls.append(("memo", message, memo_date))

        def set_memos(self, memos):
            calls.append(("memos", memos))

        def set_read_memo_keys(self, keys):
            calls.append(("read", keys))

        def set_cloud_status(self, status, error=""):
            calls.append(("cloud", status, error))

    class FakeTimer:
        def setInterval(self, interval):
            calls.append(("interval", interval))

    class FakeWindow:
        _wake_display_for_memo = app.VideoArchiveWindow._wake_display_for_memo
        _play_memo_chime = lambda self: calls.append("chime")
        _restart_memo_chime_interval = lambda self: calls.append("restart_chime")
        _update_memo_chime_timer = lambda self: calls.append("update_chime")

        def __init__(self):
            self.cloud_message_running = True
            self.memo_reset_pending = False
            self.memos = []
            self.settings = {"wake_on_memo": True, "memo_chime_enabled": False}
            self.gallery = FakeCounter()
            self.home = FakeCounter()
            self.config_page = FakeConfig()
            self.display = FakeDisplay()
            self.cloud_message_timer = FakeTimer()
            self.cloud_last_logged_error = ""
            self.cloud_last_error_log_monotonic = 0.0

    monkeypatch.setattr(app, "load_cached_message_date", lambda: memo["date"])
    monkeypatch.setattr(app, "load_memos", lambda: [memo])
    monkeypatch.setattr(app, "load_read_memo_keys", lambda: set())
    monkeypatch.setattr(app, "unread_memo_count", lambda memos: len(memos))

    fake = FakeWindow()
    app.VideoArchiveWindow._cloud_message_finished(fake, memo["message"], "")

    assert fake.cloud_message_running is False
    assert fake.cloud_status == "SYNCED"
    assert fake.memos == [memo]
    assert ("memos", [memo]) in calls


def test_wifi_scan_clears_stale_results_and_late_result_does_not_eject_password():
    widget = _config_widget()
    widget.showing_wifi = True
    widget.wifi_networks = [{"ssid": "OLD", "security": "WPA2", "signal": "50"}]
    widget.begin_wifi_scan()
    assert widget.wifi_networks == []
    assert widget.wifi_stage == "networks"

    widget.wifi_stage = "password"
    widget.wifi_password = "visible-password"
    widget.set_wifi_networks([{"ssid": "NEW", "security": "WPA2", "signal": "90"}])
    assert widget.wifi_stage == "password"
    assert widget.wifi_password == "visible-password"


def test_playback_page_effect_timer_only_runs_when_explicitly_started():
    from video_archive.app import PlaybackPage

    page = PlaybackPage()
    assert page.flicker_timer.isActive() is False
    page.start_effects()
    assert page.flicker_timer.isActive() is True
    page.stop_effects()
    assert page.flicker_timer.isActive() is False


def test_memo_chime_restart_restarts_full_interval():
    class FakeTimer:
        def __init__(self):
            self.starts = 0
            self.stops = 0
        def start(self):
            self.starts += 1
        def stop(self):
            self.stops += 1

    class FakeWindow:
        settings = {"memo_chime_enabled": True}
        unread_memos = 2
        memo_chime_timer = FakeTimer()
        _memo_chime_should_run = app.VideoArchiveWindow._memo_chime_should_run

    fake = FakeWindow()
    app.VideoArchiveWindow._restart_memo_chime_interval(fake)
    assert fake.memo_chime_timer.starts == 1
    assert fake.memo_chime_timer.stops == 0


def test_reboot_busy_state_ignores_repeat_select():
    widget = _config_widget()
    widget.show_settings_home()
    widget.selected_index = 5
    calls = []
    widget.reboot_requested.connect(lambda: calls.append(True))
    widget.select()
    assert widget.confirming_reboot is True
    widget.select()
    assert widget.reboot_busy is True
    assert widget.reboot_status == "rebooting..."
    widget.select()
    assert calls == [True]
    assert widget.reboot_status == "rebooting..."


def test_reboot_worker_uses_no_wall(monkeypatch):
    commands = []

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    def fake_run(command, **kwargs):
        commands.append(command)
        return FakeResult()

    class FakeSignal:
        def emit(self, *args):
            pass

    fake_window = type("FakeWindow", (), {"reboot_finished": FakeSignal()})()
    monkeypatch.setattr(app.subprocess, "run", fake_run)

    app.VideoArchiveWindow._reboot_worker(fake_window)

    assert commands == [
        ["systemctl", "reboot", "--no-block", "--no-wall"],
        ["sudo", "-n", "systemctl", "reboot", "--no-block", "--no-wall"],
    ]


def test_admin_busy_state_ignores_repeat_select_until_finished():
    widget = _config_widget()
    widget.show_settings_home()
    assert widget.enter_admin({}) is True
    widget.admin_index = 1
    calls = []
    widget.admin_reset_wifi_requested.connect(lambda: calls.append(True))
    widget.select()
    assert widget.admin_confirm_action == "RESET WIFI"
    widget.select()
    assert widget.admin_busy is True
    widget.select()
    assert calls == [True]
    widget.finish_admin_action("done")
    assert widget.admin_busy is False
    assert widget.admin_status == "done"
