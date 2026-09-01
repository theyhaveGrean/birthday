from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "src/video_archive/app.py").read_text()
UI_SOURCE = (ROOT / "src/video_archive/ui.py").read_text()


def test_deployment_has_no_external_keyboard_handlers():
    forbidden = (
        "keyPressEvent",
        "eventFilter",
        "Qt.Key_",
        "QEvent.KeyPress",
        "Key_Escape",
        "Key_Return",
        "Key_Enter",
        "Key_Backspace",
    )
    source = APP_SOURCE + "\n" + UI_SOURCE
    for token in forbidden:
        assert token not in source


def test_ui_does_not_advertise_pc_keyboard_controls():
    upper = UI_SOURCE.upper()
    for token in (
        "ESCAPE", " ESC ", "ENTER KEY", "ARROW KEY", "KEYBOARD", "ANY KEY",
    ):
        assert token not in upper


def test_ui_instructions_name_physical_controls():
    assert "LEFT/RIGHT // BROWSE" in UI_SOURCE
    assert "LEFT/RIGHT CHOOSE   SELECT" in UI_SOURCE


def test_gallery_copy_names_select_button():
    assert "SELECT // PLAY" in UI_SOURCE
    assert "SELECT // APPS" not in UI_SOURCE
    assert "PRESS // PLAY" not in UI_SOURCE
    assert "PRESS // APPS" not in UI_SOURCE


def test_home_has_three_apps_and_global_hold_home():
    assert 'HOME_APPS = ("GALLERY", "MEMOS", "SETTINGS")' in UI_SOURCE
    assert 'def go_home(self):' in APP_SOURCE
    assert 'self.input_controller.select_held.connect(' in APP_SOURCE
    held = APP_SOURCE.split('def _physical_select_held(self):', 1)[1].split('def _physical_right(self):', 1)[0]
    assert 'self.go_home()' in held


def test_wifi_password_has_reasonable_input_cap():
    assert "len(self.wifi_password) < 128" in UI_SOURCE


def test_gallery_navigation_is_queued_not_dropped():
    assert "self.pending_navigation = deque()" in UI_SOURCE
    assert "self.pending_navigation.append(direction)" in UI_SOURCE
    assert "self.pending_navigation.popleft()" in UI_SOURCE


def test_gallery_queue_is_cancelable():
    assert "self.pending_navigation.clear()" in UI_SOURCE
    assert "def cancel_navigation(self):" in UI_SOURCE


def test_wifi_offline_status_is_red_classified():
    assert '"offline"' in UI_SOURCE


def test_short_select_exits_memo_reader_to_memo_list():
    select_block = UI_SOURCE.split('def select(self):', 1)[1].split('def hold_select(self):', 1)[0]
    assert 'elif self.showing_memos:' in select_block
    assert 'if self.memo_reading:' in select_block
    assert 'self.memo_reading = False' in select_block
    assert 'self.memo_scroll = 0' in select_block
    assert 'SELECT BACK TO LIST' in UI_SOURCE
