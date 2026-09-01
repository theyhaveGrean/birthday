import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from .audio import AudioController
from .cloud import (
    fetch_cloud_message,
    load_cached_message,
    load_cached_message_date,
    load_memos,
    load_read_memo_keys,
    mark_memo_read,
    memo_key,
    unread_memo_count,
)
from .config import (
    CLOUD_MEMOS_FILE,
    CLOUD_MESSAGE_FILE,
    CLOUD_MESSAGE_META_FILE,
    DEFAULT_NOTE,
    DEFAULT_SETTINGS,
    NOTE_FILE,
    ORDER_FILE,
    READ_MEMOS_FILE,
    SETTINGS_FILE,
    VIDEO_DIR,
)
from .display import DisplayController
from .input import InputController
from .player import MpvController
from .storage import atomic_write_json, clamp_int, clamp_int_or_default, coerce_bool
from .ui import (
    AmbientSleepWidget,
    ConfigWidget,
    GalleryWidget,
    HomeWidget,
    RandomTextFlicker,
    StartScreenWidget,
    TransitionWidget,
    apply_text_flicker,
    draw_global_flicker,
    draw_random_screen_flicker,
    draw_signal_acquisition_flicker,
    draw_static_slices,
)

VIDEO_EXTENSIONS = {".mp4", ".mov"}
MAX_MPV_VOLUME = 150
CLOUD_POLL_MS = 60000
CLOUD_RETRY_MS = 15000


def _split_nmcli_terse(line):
    """Split nmcli -t output while honoring its backslash escaping."""
    fields = []
    current = []
    escaped = False

    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)

    if escaped:
        current.append("\\")

    fields.append("".join(current))
    return fields


def _normalize_wifi_security(value):
    value = (value or "").strip()
    if value in {"", "--"}:
        return ""
    return value


def _friendly_nmcli_error(output, default):
    text = (output or "").strip()
    lower = text.lower()
    permission_markers = (
        "not authorized",
        "not authorised",
        "insufficient privileges",
        "permission denied",
        "authorization",
        "authorisation",
        "polkit",
    )
    if any(marker in lower for marker in permission_markers):
        return "WIFI PERMISSION ERROR"
    if "networkmanager is not running" in lower:
        return "NETWORKMANAGER OFFLINE"
    if "nmcli" in lower and "not found" in lower:
        return "NMCLI NOT FOUND"
    return text[-80:] if text else default


def load_videos():
    try:
        VIDEO_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        files = list(VIDEO_DIR.iterdir())
    except OSError as error:
        print(f"failed to access video directory: {error}", flush=True)
        return []

    available = {
        file.name: file
        for file in files
        if (
            file.is_file()
            and file.suffix.lower() in VIDEO_EXTENSIONS
        )
    }

    ordered = []

    if ORDER_FILE.exists():
        try:
            order_lines = ORDER_FILE.read_text().splitlines()
        except OSError as error:
            print(f"failed to read order file: {error}", flush=True)
            order_lines = []

        for line in order_lines:
            filename = line.strip()

            if not filename:
                continue

            if filename in available:
                ordered.append(
                    available.pop(filename)
                )

    ordered.extend(
        sorted(
            available.values(),
            key=lambda path: path.name.lower(),
        )
    )

    return ordered


def load_settings():
    settings = dict(DEFAULT_SETTINGS)

    if SETTINGS_FILE.exists():
        try:
            loaded = json.loads(SETTINGS_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            loaded = {}

        if isinstance(loaded, dict):
            settings.update(loaded)

    settings["volume"] = clamp_int_or_default(
        settings.get("volume"), 0, 100, DEFAULT_SETTINGS["volume"]
    )
    settings["brightness"] = clamp_int_or_default(
        settings.get("brightness"), 5, 100, DEFAULT_SETTINGS["brightness"]
    )
    settings["sleep_timeout_minutes"] = clamp_int_or_default(
        settings.get("sleep_timeout_minutes"),
        1,
        60,
        DEFAULT_SETTINGS["sleep_timeout_minutes"],
    )
    settings["sfx_enabled"] = coerce_bool(
        settings.get("sfx_enabled"), DEFAULT_SETTINGS["sfx_enabled"]
    )
    settings["memo_chime_enabled"] = coerce_bool(
        settings.get("memo_chime_enabled"),
        DEFAULT_SETTINGS["memo_chime_enabled"],
    )
    settings["wake_on_memo"] = coerce_bool(
        settings.get("wake_on_memo"), DEFAULT_SETTINGS["wake_on_memo"]
    )
    cloud_url = settings.get("cloud_message_url", "")
    settings["cloud_message_url"] = (
        cloud_url.strip() if isinstance(cloud_url, str) else ""
    )
    return settings


def save_settings(settings):
    atomic_write_json(SETTINGS_FILE, settings)


def load_note():
    if not NOTE_FILE.exists():
        try:
            NOTE_FILE.write_text(DEFAULT_NOTE + "\n")
        except OSError as error:
            print(f"failed to create note file: {error}", flush=True)
            return DEFAULT_NOTE

    try:
        return NOTE_FILE.read_text().strip()
    except OSError as error:
        print(f"failed to read note file: {error}", flush=True)
        return DEFAULT_NOTE


def mpv_volume_from_setting(volume):
    return round(
        clamp_int(volume, 0, 100) * MAX_MPV_VOLUME / 100
    )


class VideoSurface(QWidget):
    """
    Native X11 child window that mpv renders into using --wid.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(
            Qt.WA_NativeWindow,
            True,
        )

        self.setFocusPolicy(
            Qt.NoFocus
        )

        self.setAutoFillBackground(
            True
        )

        palette = self.palette()

        palette.setColor(
            self.backgroundRole(),
            QColor("#050805"),
        )

        self.setPalette(
            palette
        )


class PlaybackPage(QWidget):
    """
    Retro playback deck.

    The application still occupies the whole display, but the actual
    video is inset inside a deliberate green/black frame instead of
    filling the panel edge-to-edge. The native video child stays mapped
    so mpv can preload beneath the transition.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.video_surface = VideoSurface(
            self
        )

        self.transition = TransitionWidget(
            self
        )

        self.transition.hide()

        self.current_title = ""
        self.flicker_phase = 0
        self.text_flicker = RandomTextFlicker()

        self.setCursor(
            Qt.BlankCursor
        )

        self.flicker_timer = QTimer(self)

        self.flicker_timer.timeout.connect(
            self._advance_flicker
        )

        # Started only while the playback page is visible.

    def _advance_flicker(self):
        self.flicker_phase = (
            self.flicker_phase + 1
        )
        self.text_flicker.advance()

        self.update()

    def start_effects(self):
        if not self.flicker_timer.isActive():
            self.flicker_timer.start(80)

    def stop_effects(self):
        self.flicker_timer.stop()

    def _video_rect(self):
        """
        Leave room for the retro frame on the landscape display.
        """
        left = 58
        right = 58
        top = 92
        bottom = 66

        return self.rect().adjusted(
            left,
            top,
            -right,
            -bottom,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.video_surface.setGeometry(
            self._video_rect()
        )

        self.transition.setGeometry(
            self.rect()
        )

    def set_title(self, title):
        self.current_title = title
        self.update()

    def show_transition_play(
        self,
        title,
    ):
        self.set_title(title)

        self.transition.setGeometry(
            self.rect()
        )

        self.transition.show()
        self.transition.raise_()

        self.transition.start_play(
            title
        )

    def show_transition_return(
        self,
        title,
    ):
        self.set_title(title)

        self.transition.setGeometry(
            self.rect()
        )

        self.transition.show()
        self.transition.raise_()

        self.transition.start_return(
            title
        )

    def hide_transition(self):
        self.transition.stop_transition()
        self.transition.hide()

    def show_video_surface(self):
        self.video_surface.setGeometry(
            self._video_rect()
        )
        self.video_surface.show()
        self.video_surface.raise_()

    def hide_video_surface(self):
        self.video_surface.hide()

    def paintEvent(self, event):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import (
            QColor,
            QFont,
            QPainter,
            QPen,
        )

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            False,
        )

        bg = QColor("#050805")
        bright = QColor("#7CFF6B")
        main = QColor("#56D94F")
        muted = QColor("#2F7330")
        dim = QColor("#173B19")
        text_dim = QColor("#577A55")

        painter.fillRect(
            self.rect(),
            bg,
        )

        draw_global_flicker(
            painter,
            self.width(),
            self.height(),
            self.flicker_phase,
        )
        if self.text_flicker.active:
            draw_random_screen_flicker(
                painter,
                self.width(),
                self.height(),
                self.flicker_phase,
            )
        draw_signal_acquisition_flicker(
            painter,
            self.width(),
            self.height(),
            self.flicker_phase,
        )

        # CRT-ish horizontal bands in the exposed frame area.
        for y in range(
            0,
            self.height(),
            14,
        ):
            painter.fillRect(
                0,
                y,
                self.width(),
                4,
                QColor("#070D07"),
            )

        # Outer chassis.
        pen = QPen(
            muted
        )
        pen.setWidth(3)
        painter.setPen(
            pen
        )

        painter.drawRect(
            20,
            20,
            self.width() - 40,
            self.height() - 40,
        )

        pen = QPen(
            dim
        )
        pen.setWidth(1)
        painter.setPen(
            pen
        )

        painter.drawRect(
            30,
            30,
            self.width() - 60,
            self.height() - 60,
        )

        video_rect = self._video_rect()

        # Bezel around mpv's native child window.
        bezel = video_rect.adjusted(
            -10,
            -10,
            10,
            10,
        )

        # Occasional tiny pulse in border brightness.
        bezel_color = (
            bright
            if self.flicker_phase in (5, 6)
            else main
        )

        pen = QPen(
            bezel_color
        )
        pen.setWidth(3)
        painter.setPen(
            pen
        )
        painter.drawRect(
            bezel
        )

        pen = QPen(
            dim
        )
        pen.setWidth(1)
        painter.setPen(
            pen
        )
        painter.drawRect(
            bezel.adjusted(
                6,
                6,
                -6,
                -6,
            )
        )

        if self.text_flicker.active:
            draw_static_slices(painter, self.width(), self.height(), self.flicker_phase)
        apply_text_flicker(painter, self.text_flicker, self.flicker_phase)

        # Header.
        painter.setFont(
            QFont(
                "DejaVu Sans Mono",
                13,
                QFont.Bold,
            )
        )

        painter.setPen(
            main
        )

        painter.drawText(
            42,
            61,
            "4AUTUMN.EXE // PLAYBACK",
        )

        painter.setPen(
            text_dim
        )

        title_rect = QRect(
            self.width() // 2,
            42,
            self.width() // 2 - 42,
            30,
        )
        display_title = painter.fontMetrics().elidedText(
            self.current_title, Qt.ElideMiddle, title_rect.width()
        )
        painter.drawText(
            title_rect,
            Qt.AlignRight | Qt.AlignVCenter,
            display_title,
        )

        # Footer / fake machine status.
        painter.setFont(
            QFont(
                "DejaVu Sans Mono",
                10,
                QFont.Bold,
            )
        )

        painter.setPen(
            text_dim
        )

        painter.drawText(
            42,
            self.height() - 39,
            "SIGNAL // LOCKED",
        )

        painter.drawText(
            QRect(
                self.width() - 310,
                self.height() - 54,
                268,
                30,
            ),
            Qt.AlignRight | Qt.AlignVCenter,
            "SELECT // RETURN   HOLD SELECT // HOME",
        )

        # A moving scan line around the chassis. The native X11 video
        # remains untouched for performance, so this effect lives in
        # the surrounding deck/frame.
        scan_top = max(
            76,
            bezel.top(),
        )

        scan_bottom = min(
            self.height() - 62,
            bezel.bottom(),
        )

        if scan_bottom > scan_top:
            scan_y = (
                scan_top
                + (
                    self.flicker_phase * 19
                )
                % (
                    scan_bottom
                    - scan_top
                    + 1
                )
            )

            painter.fillRect(
                30,
                scan_y,
                max(
                    1,
                    video_rect.left() - 42,
                ),
                1,
                dim,
            )

            painter.fillRect(
                video_rect.right() + 12,
                scan_y,
                max(
                    1,
                    self.width()
                    - video_rect.right()
                    - 42,
                ),
                1,
                dim,
            )

        # Small status LEDs.
        led_y = self.height() - 39

        painter.fillRect(
            self.width() // 2 - 24,
            led_y - 7,
            7,
            7,
            bright
            if self.flicker_phase % 8 < 5
            else dim,
        )

        painter.fillRect(
            self.width() // 2 - 9,
            led_y - 7,
            7,
            7,
            main,
        )

        painter.fillRect(
            self.width() // 2 + 6,
            led_y - 7,
            7,
            7,
            dim,
        )


class VideoArchiveWindow(QMainWindow):
    wifi_scan_finished = Signal(object, str)
    wifi_connect_finished = Signal(bool, str)
    wifi_status_finished = Signal(object)
    wifi_disconnect_finished = Signal(bool, str)
    wifi_forget_finished = Signal(bool, str)
    admin_wifi_reset_finished = Signal(bool, str)
    admin_memos_reset_finished = Signal(bool, str)
    cloud_message_finished = Signal(str, str)
    reboot_finished = Signal(bool, str)

    def __init__(self):
        super().__init__()

        self.videos = load_videos()
        self.settings = load_settings()
        self.note = load_note()
        self.memo = load_cached_message()
        self.memo_date = load_cached_message_date()
        self.memos = load_memos()
        self.unread_memos = unread_memo_count(self.memos)
        self.cloud_status = (
            "CHECKING" if self.settings.get("cloud_message_url") else "DISABLED"
        )
        self.cloud_error = ""

        # Preserve the actual extension in the gallery:
        # AUTUMN.mp4, TRIP.mov, etc.
        self.titles = [
            path.name
            for path in self.videos
        ]

        self.mode = "start"
        self.pending_index = None

        self.mpv_ready = False
        self.mpv_started = False
        self.transition_minimum_elapsed = False
        self.return_pending = False
        self.playback_generation = 0
        self.wifi_scan_running = False
        self.wifi_connect_running = False
        self.wifi_status_running = False
        self.wifi_status_refresh_pending = False
        self.wifi_disconnect_running = False
        self.wifi_forget_running = False
        self.admin_wifi_reset_running = False
        self.admin_wifi_reset_pending = False
        self.memo_reset_pending = False
        self.reboot_running = False
        self.left_button_down = False
        self.right_button_down = False
        self.wifi_device = "wlan0"
        self.cloud_message_running = False
        self.cloud_last_logged_error = ""
        self.cloud_last_error_log_monotonic = 0.0
        self.started_monotonic = time.monotonic()

        self.setWindowTitle(
            "Birthday Display"
        )

        # Bare Xorg: no window manager.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.X11BypassWindowManagerHint
        )

        self.setCursor(
            Qt.BlankCursor
        )

        # =================================================
        # PAGES
        # =================================================

        self.start_screen = StartScreenWidget()

        self.home = HomeWidget(self.unread_memos)
        self.ambient_sleep = AmbientSleepWidget()
        self.ambient_sleep.set_unread_memo_count(self.unread_memos)

        self.gallery = GalleryWidget(
            self.titles,
            self.unread_memos,
            self.cloud_status,
        )

        self.config_page = ConfigWidget(
            self.note,
            self.memo,
            self.memo_date,
            self.memos,
            self.settings["volume"],
            self.settings["sfx_enabled"],
            self.settings["memo_chime_enabled"],
            self.settings["wake_on_memo"],
            self.settings["brightness"],
            self.settings["sleep_timeout_minutes"],
        )
        self.config_page.set_read_memo_keys(load_read_memo_keys())
        self.config_page.set_cloud_status(self.cloud_status, self.cloud_error)

        self.playback_page = PlaybackPage()

        # Hidden pages do not need to wake the Pi for CRT-effect timers.
        self.home.flicker_timer.stop()
        self.gallery.flicker_timer.stop()
        self.config_page.flicker_timer.stop()
        self.ambient_sleep.stop()

        self.pages = QStackedWidget()

        self.pages.addWidget(
            self.start_screen
        )

        self.pages.addWidget(
            self.home
        )

        self.pages.addWidget(
            self.ambient_sleep
        )

        self.pages.addWidget(
            self.gallery
        )

        self.pages.addWidget(
            self.config_page
        )

        self.pages.addWidget(
            self.playback_page
        )

        self.setCentralWidget(
            self.pages
        )

        self.pages.setCurrentWidget(
            self.start_screen
        )

        # =================================================
        # PLAYER
        # =================================================

        self.player = MpvController()
        self.audio = AudioController(
            volume=mpv_volume_from_setting(
                self.settings["volume"]
            ),
            sfx_enabled=self.settings["sfx_enabled"],
        )
        self.input_controller = InputController()
        self.display = DisplayController(self.settings["brightness"])

        # =================================================
        # SIGNALS
        # =================================================

        self.start_screen.started.connect(
            self.start_home
        )

        self.home.app_requested.connect(
            self._open_home_app
        )

        self.start_screen.boot_finished.connect(
            self._boot_finished
        )

        self.gallery.play_requested.connect(
            self.play_selected
        )

        self.config_page.back_requested.connect(
            self.go_home
        )

        self.config_page.reboot_requested.connect(
            self._reboot_system
        )

        self.reboot_finished.connect(
            self._reboot_finished
        )

        self.config_page.volume_changed.connect(
            self._set_volume
        )

        self.config_page.sfx_changed.connect(
            self._set_sfx_enabled
        )

        self.config_page.memo_chime_changed.connect(
            self._set_memo_chime_enabled
        )
        self.config_page.wake_on_memo_changed.connect(
            self._set_wake_on_memo
        )

        self.config_page.brightness_changed.connect(
            self._set_brightness
        )

        self.config_page.sleep_timeout_changed.connect(
            self._set_sleep_timeout
        )

        self.config_page.wifi_scan_requested.connect(
            self._scan_wifi
        )

        self.config_page.wifi_connect_requested.connect(
            self._connect_wifi
        )

        self.config_page.wifi_connect_saved_requested.connect(
            self._connect_saved_wifi
        )

        self.config_page.wifi_disconnect_requested.connect(
            self._disconnect_wifi
        )

        self.config_page.wifi_forget_requested.connect(
            self._forget_wifi
        )

        self.config_page.admin_reset_wifi_requested.connect(
            self._admin_reset_wifi
        )

        self.config_page.admin_reset_memos_requested.connect(
            self._admin_reset_memos
        )

        self.config_page.memo_read.connect(
            self._memo_read
        )

        self.config_page.about_opened.connect(
            self._about_opened
        )

        self.about_refresh_timer = QTimer(self)
        self.about_refresh_timer.setInterval(1000)
        self.about_refresh_timer.timeout.connect(self._refresh_about_data)

        # Keep network status current independently of the Wi-Fi settings page.
        self.wifi_status_timer = QTimer(self)
        self.wifi_status_timer.setInterval(30000)
        self.wifi_status_timer.timeout.connect(self._refresh_wifi_status)
        self.wifi_status_timer.start()
        QTimer.singleShot(250, self._refresh_wifi_status)

        self.wifi_scan_finished.connect(
            self._wifi_scan_finished
        )

        self.wifi_connect_finished.connect(
            self._wifi_connect_finished
        )

        self.wifi_status_finished.connect(
            self._wifi_status_finished
        )

        self.wifi_disconnect_finished.connect(
            self._wifi_disconnect_finished
        )

        self.wifi_forget_finished.connect(
            self._wifi_forget_finished
        )

        self.admin_wifi_reset_finished.connect(
            self._admin_wifi_reset_finished
        )

        self.admin_memos_reset_finished.connect(
            self._admin_memos_reset_finished
        )

        self.cloud_message_finished.connect(
            self._cloud_message_finished
        )

        self.playback_page.transition.minimum_elapsed.connect(
            self._transition_minimum_elapsed
        )

        self.playback_page.transition.return_finished.connect(
            self._finish_return
        )

        self.player.ready.connect(
            self._mpv_ready
        )

        self.player.started.connect(
            self._mpv_started
        )

        self.player.ended.connect(
            self._video_ended
        )

        self.player.failed.connect(
            self._playback_failed
        )
        
        self.input_controller.left_pressed.connect(
            self._physical_left
        )

        self.input_controller.left_released.connect(
            self._physical_left_released
        )

        self.input_controller.select_pressed.connect(
            self._physical_select
        )

        self.input_controller.select_held.connect(
            self._physical_select_held
        )

        self.input_controller.right_pressed.connect(
            self._physical_right
        )

        self.input_controller.right_released.connect(
            self._physical_right_released
        )

        self.admin_chord_timer = QTimer(self)
        self.admin_chord_timer.setSingleShot(True)
        self.admin_chord_timer.setInterval(3000)
        self.admin_chord_timer.timeout.connect(self._admin_chord_timeout)

        self.playback_watchdog = QTimer(self)
        self.playback_watchdog.setSingleShot(True)
        self.playback_watchdog.setInterval(15000)
        self.playback_watchdog.timeout.connect(self._playback_start_timeout)

        self.display_sleep_timer = QTimer(self)
        self.display_sleep_timer.setSingleShot(True)
        self.display_sleep_timer.timeout.connect(self._sleep_display)
        self._restart_display_sleep_timer()

        self.memo_chime_timer = QTimer(self)
        self.memo_chime_timer.setInterval(15000)
        self.memo_chime_timer.timeout.connect(self._play_memo_chime)
        self._update_memo_chime_timer()

        self.cloud_message_timer = QTimer(self)
        self.cloud_message_timer.timeout.connect(
            self._refresh_cloud_message
        )
        if self.settings["cloud_message_url"]:
            self.cloud_message_timer.start(CLOUD_POLL_MS)
            QTimer.singleShot(3000, self._refresh_cloud_message)

    def _restart_display_sleep_timer(self):
        timeout_ms = int(self.settings["sleep_timeout_minutes"] * 60 * 1000)
        self.display_sleep_timer.start(max(1000, timeout_ms))

    def _resume_visible_effects(self):
        self.ambient_sleep.stop()
        if self.mode == "start":
            self.start_screen.flicker_timer.start(90)
            self.pages.setCurrentWidget(self.start_screen)
        elif self.mode == "home":
            self.home.flicker_timer.start(90)
            self.pages.setCurrentWidget(self.home)
        elif self.mode == "gallery":
            self.gallery.flicker_timer.start(90)
            self.pages.setCurrentWidget(self.gallery)
        elif self.mode == "config":
            self.config_page.flicker_timer.start(90)
            self.pages.setCurrentWidget(self.config_page)
            if self.config_page.showing_about:
                self.about_refresh_timer.start()

    def _pause_visible_effects(self):
        self.start_screen.flicker_timer.stop()
        self.home.flicker_timer.stop()
        self.gallery.flicker_timer.stop()
        self.config_page.flicker_timer.stop()
        self.ambient_sleep.stop()
        self.about_refresh_timer.stop()

    def _note_activity(self):
        was_sleeping = self.display.sleeping
        self.display.wake()
        if was_sleeping:
            self._resume_visible_effects()
        self._restart_display_sleep_timer()

    def _sleep_display(self):
        # Do not dim while a video is actively loading or playing. The timer
        # is restarted so inactivity is reconsidered after another interval.
        if self.mode in ("loading", "playing", "returning"):
            self._restart_display_sleep_timer()
            return
        self.display.sleep()
        self._pause_visible_effects()
        self.ambient_sleep.set_unread_memo_count(self.unread_memos)
        self.ambient_sleep.start()
        self.pages.setCurrentWidget(self.ambient_sleep)

    def _physical_left(self):
        self._note_activity()
        self.left_button_down = True
        self._start_admin_chord_if_ready()

        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_home()
            return

        if self.mode == "home":
            self.audio.play("click")
            self.home.move_left()

        elif self.mode == "gallery":
            self.audio.play("click")
            self.gallery.move_left()

        elif self.mode == "config":
            self.audio.play("click")
            self.config_page.move_left()


    def _physical_select(self):
        self._note_activity()
        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_home()
            return

        if self.mode == "home":
            self.audio.play("select")
            self.home.select()

        elif self.mode == "gallery":
            # Never activate a stale index while the carousel is moving.
            if self.gallery.animating or self.gallery.pending_navigation:
                return
            self.audio.play("select")
            self.play_selected(
                self.gallery.selected_index
            )

        elif self.mode == "loading":
            self._begin_return()

        elif self.mode == "playing":
            self.stop_video()

        elif self.mode == "config":
            self.audio.play("select")
            self.config_page.select()


    def _physical_select_held(self):
        self._note_activity()
        self.audio.play("select")
        self.go_home()

    def _physical_right(self):
        self._note_activity()
        self.right_button_down = True
        self._start_admin_chord_if_ready()

        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_home()
            return

        if self.mode == "home":
            self.audio.play("click")
            self.home.move_right()

        elif self.mode == "gallery":
            self.audio.play("click")
            self.gallery.move_right()

        elif self.mode == "config":
            self.audio.play("click")
            self.config_page.move_right()

    def _physical_left_released(self):
        self.left_button_down = False
        self.admin_chord_timer.stop()

    def _physical_right_released(self):
        self.right_button_down = False
        self.admin_chord_timer.stop()

    def _start_admin_chord_if_ready(self):
        if not (self.left_button_down and self.right_button_down):
            return
        if self.mode != "config" or not self.config_page.can_open_admin():
            return
        if not self.admin_chord_timer.isActive():
            self.admin_chord_timer.start()

    def _admin_chord_timeout(self):
        if not (self.left_button_down and self.right_button_down):
            return
        if self.mode != "config" or not self.config_page.can_open_admin():
            return
        self.audio.play("select")
        self.config_page.enter_admin(self._system_diagnostics())

    def _system_diagnostics(self):
        try:
            free_bytes = shutil.disk_usage(VIDEO_DIR.parent).free
            free_text = f"{free_bytes / (1024 ** 3):.1f} GB"
        except OSError:
            free_text = "unknown"

        try:
            uptime_seconds = max(0, int(float(Path("/proc/uptime").read_text().split()[0])))
        except (OSError, ValueError, IndexError):
            uptime_seconds = max(0, int(time.monotonic() - self.started_monotonic))
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes = remainder // 60

        return {
            "wifi": self.config_page.wifi_current.get("ssid") or "not connected",
            "ip": self.config_page.wifi_current.get("ip") or "--",
            "videos": len(self.videos),
            "memos": len(self.memos),
            "unread": self.unread_memos,
            "storage_free": free_text,
            "cloud": self.cloud_status,
            "uptime": f"{hours}h {minutes:02}m",
        }

    def _about_opened(self):
        self._refresh_wifi_status()
        self._refresh_about_data()
        if not self.about_refresh_timer.isActive():
            self.about_refresh_timer.start()

    def _refresh_about_data(self):
        if self.mode == "config" and self.config_page.showing_about:
            self.config_page.set_about_data(self._system_diagnostics())
            return
        self.about_refresh_timer.stop()

    def _boot_finished(self):
        self.audio.play("boot")

    def start_home(self):
        if self.mode != "start":
            return
        if not self.start_screen.can_start():
            return

        self.audio.play("select")
        self.start_screen.flicker_timer.stop()
        self.mode = "home"
        self.home.reset_selection()
        self.home.flicker_timer.start(90)
        self.pages.setCurrentWidget(self.home)

    def _open_home_app(self, app_name):
        if self.mode != "home":
            return
        self.home.flicker_timer.stop()
        if app_name == "gallery":
            self.mode = "gallery"
            self.gallery.cancel_navigation()
            self.gallery.flicker_timer.start(90)
            self.pages.setCurrentWidget(self.gallery)
        elif app_name == "memos":
            self._open_memos()
        elif app_name == "settings":
            self._open_settings()

    def _prepare_config_page(self):
        self.config_page.set_note(self.note)
        self.config_page.set_memo(self.memo, self.memo_date)
        self.config_page.set_memos(self.memos)
        self.config_page.set_cloud_status(self.cloud_status, self.cloud_error)
        self.config_page.set_about_data(self._system_diagnostics())
        self.config_page.set_volume(self.settings["volume"])
        self.config_page.set_sfx_enabled(self.settings["sfx_enabled"])
        self.config_page.set_memo_chime_enabled(self.settings["memo_chime_enabled"])
        self.config_page.set_wake_on_memo(self.settings["wake_on_memo"])

    def _open_memos(self):
        self.mode = "config"
        self._prepare_config_page()
        self.config_page.show_memos_home()
        self.config_page.flicker_timer.start(90)
        self.pages.setCurrentWidget(self.config_page)

    def _open_settings(self):
        self.mode = "config"
        self._prepare_config_page()
        self.config_page.show_settings_home()
        self.config_page.flicker_timer.start(90)
        self.pages.setCurrentWidget(self.config_page)

    def go_home(self):
        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_home()
            return

        previous_mode = self.mode
        # Change mode first so asynchronous mpv ended/failed callbacks cannot
        # start a gallery return transition while a global Home jump is active.
        self.mode = "home"

        # Make Home visible immediately. mpv cleanup can take over a second in
        # a wedged process, and the global hold-Select shortcut must still feel
        # instantaneous. Generation/state guards make late player signals safe.
        self.gallery.cancel_navigation()
        self.gallery.flicker_timer.stop()
        self.config_page.flicker_timer.stop()
        self.about_refresh_timer.stop()
        self.home.flicker_timer.start(90)
        self.pages.setCurrentWidget(self.home)
        QApplication.processEvents()

        if previous_mode in ("loading", "playing", "returning"):
            self.playback_generation += 1
            self.playback_watchdog.stop()
            self.playback_page.hide_transition()
            self.playback_page.hide_video_surface()
            self.playback_page.stop_effects()
            self.return_pending = False
            self.pending_index = None
            self.player.stop(silent=True)

    # =====================================================
    # START VIDEO
    # =====================================================

    def play_selected(
        self,
        index,
    ):
        if not self.videos:
            return

        if self.mode != "gallery":
            return

        self.mode = "loading"
        self.gallery.cancel_navigation()
        self.gallery.flicker_timer.stop()
        self.pending_index = index
        self.playback_generation += 1

        self.mpv_ready = False
        self.mpv_started = False
        self.transition_minimum_elapsed = False
        self.return_pending = False

        video_path = self.videos[
            index
        ]

        print(
            f"{video_path.name}: landscape playback",
            flush=True,
        )
        self.audio.play("load")

        self.pages.setCurrentWidget(
            self.playback_page
        )

        QApplication.processEvents()

        # Keep mpv's X11 target mapped from the start; --wid rendering
        # depends on this on the Pi display stack.
        self.playback_page.show_video_surface()

        # Start transition above the mapped video surface.
        self.playback_page.show_transition_play(
            self.titles[index]
        )

        QApplication.processEvents()

        wid = int(
            self.playback_page.video_surface.winId()
        )

        print(
            f"Loading {video_path.name} into X11 window {wid}",
            flush=True,
        )

        self.playback_page.transition.raise_()

        QApplication.processEvents()

        self.playback_watchdog.start()
        self.playback_page.start_effects()
        self.player.preload(
            video_path,
            wid,
            mpv_volume_from_setting(
                self.settings["volume"]
            ),
            self.playback_generation,
        )

    def _memo_read(self, memo):
        try:
            mark_memo_read(memo)
        except OSError as error:
            print(
                f"failed to save memo read state: {error}",
                flush=True,
            )
            return

        self.unread_memos = unread_memo_count(self.memos)
        self.gallery.set_unread_memo_count(self.unread_memos)
        self.home.set_unread_memo_count(self.unread_memos)
        self.ambient_sleep.set_unread_memo_count(self.unread_memos)
        self.config_page.set_read_memo_keys(load_read_memo_keys())
        self._update_memo_chime_timer()

    def _set_volume(self, volume):
        previous = self.settings["volume"]
        self.settings["volume"] = volume
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["volume"] = previous
            self.config_page.set_volume(previous)
            print(f"failed to save volume setting: {error}", flush=True)
            return

        self.player.set_volume(
            mpv_volume_from_setting(volume)
        )
        self.audio.set_volume(
            mpv_volume_from_setting(volume)
        )

    def _set_sfx_enabled(self, enabled):
        previous = self.settings["sfx_enabled"]
        self.settings["sfx_enabled"] = enabled
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["sfx_enabled"] = previous
            self.config_page.set_sfx_enabled(previous)
            print(f"failed to save SFX setting: {error}", flush=True)
            return

        self.audio.set_enabled(enabled)
        if enabled:
            self.audio.play("select")

    def _set_memo_chime_enabled(self, enabled):
        previous = self.settings["memo_chime_enabled"]
        self.settings["memo_chime_enabled"] = bool(enabled)
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["memo_chime_enabled"] = previous
            self.config_page.set_memo_chime_enabled(previous)
            print(f"failed to save memo chime setting: {error}", flush=True)
            return
        self._update_memo_chime_timer()
        if enabled and self.unread_memos > 0:
            self._play_memo_chime()
            self._restart_memo_chime_interval()

    def _set_wake_on_memo(self, enabled):
        previous = self.settings["wake_on_memo"]
        self.settings["wake_on_memo"] = bool(enabled)
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["wake_on_memo"] = previous
            self.config_page.set_wake_on_memo(previous)
            print(f"failed to save wake-on-memo setting: {error}", flush=True)

    def _wake_display_for_memo(self):
        if self.settings.get("wake_on_memo", True):
            was_sleeping = self.display.sleeping
            self.display.wake()
            if was_sleeping:
                self._resume_visible_effects()
            self._restart_display_sleep_timer()

    def _play_memo_chime(self):
        if self.settings.get("memo_chime_enabled", True) and self.unread_memos > 0:
            self.audio.play("notify", ignore_enabled=True)

    def _memo_chime_should_run(self):
        return self.settings.get("memo_chime_enabled", True) and self.unread_memos > 0

    def _update_memo_chime_timer(self):
        if not hasattr(self, "memo_chime_timer"):
            return
        if self._memo_chime_should_run():
            if not self.memo_chime_timer.isActive():
                self.memo_chime_timer.start()
        else:
            self.memo_chime_timer.stop()

    def _restart_memo_chime_interval(self):
        if not hasattr(self, "memo_chime_timer"):
            return
        if self._memo_chime_should_run():
            # QTimer.start() on an active timer restarts the full interval.
            self.memo_chime_timer.start()
        else:
            self.memo_chime_timer.stop()

    def _set_brightness(self, brightness):
        previous = self.settings["brightness"]
        self.settings["brightness"] = clamp_int(brightness, 5, 100)
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["brightness"] = previous
            self.config_page.set_brightness(previous)
            print(f"failed to save brightness setting: {error}", flush=True)
            return
        self.display.set_brightness(self.settings["brightness"])
        self._restart_display_sleep_timer()

    def _set_sleep_timeout(self, minutes):
        previous = self.settings["sleep_timeout_minutes"]
        self.settings["sleep_timeout_minutes"] = clamp_int(minutes, 1, 60)
        try:
            save_settings(self.settings)
        except OSError as error:
            self.settings["sleep_timeout_minutes"] = previous
            self.config_page.set_sleep_timeout(previous)
            print(f"failed to save sleep timeout setting: {error}", flush=True)
            return
        self._restart_display_sleep_timer()

    def _refresh_cloud_message(self):
        url = self.settings.get("cloud_message_url", "")
        if not url or self.cloud_message_running:
            return

        self.cloud_status = "CHECKING"
        self.cloud_error = ""
        self.gallery.set_cloud_status(self.cloud_status)
        self.config_page.set_cloud_status(self.cloud_status)
        self.cloud_message_running = True
        thread = threading.Thread(
            target=self._cloud_message_worker,
            args=(url,),
            daemon=True,
        )
        thread.start()

    def _cloud_message_worker(self, url):
        message, error = fetch_cloud_message(url)
        self.cloud_message_finished.emit(message or "", error or "")

    def _cloud_message_finished(self, message, error):
        self.cloud_message_running = False

        if self.memo_reset_pending:
            self.memo_reset_pending = False
            self._perform_memo_reset()
            return

        if not error:
            # A successful empty response explicitly means there is no current
            # remote memo. Historical archived memos remain available.
            previous_memo_keys = {memo_key(item) for item in self.memos}
            self.memo = message
            self.memo_date = load_cached_message_date() if message else ""
            self.memos = load_memos()
            new_memo_arrived = any(
                memo_key(item) not in previous_memo_keys
                for item in self.memos
            )
            self.unread_memos = unread_memo_count(self.memos)
            self.gallery.set_unread_memo_count(self.unread_memos)
            self.home.set_unread_memo_count(self.unread_memos)
            self.ambient_sleep.set_unread_memo_count(self.unread_memos)
            self.config_page.set_memo(self.memo, self.memo_date)
            self.config_page.set_memos(self.memos)
            self.config_page.set_read_memo_keys(load_read_memo_keys())
            if new_memo_arrived:
                self._wake_display_for_memo()
                self._play_memo_chime()
                self._restart_memo_chime_interval()
            else:
                self._update_memo_chime_timer()

        if error:
            self.cloud_status = "OFFLINE" if not message else "ERROR"
            self.cloud_error = error
            # Retry more aggressively while unavailable. Once a fetch
            # succeeds, the normal one-minute polling cadence resumes.
            self.cloud_message_timer.setInterval(CLOUD_RETRY_MS)
            now = time.monotonic()
            should_log = (
                error != self.cloud_last_logged_error
                or now - self.cloud_last_error_log_monotonic >= 3600
            )
            if should_log:
                print(
                    f"cloud message fetch failed: {error}",
                    flush=True,
                )
                self.cloud_last_logged_error = error
                self.cloud_last_error_log_monotonic = now
        else:
            if self.cloud_last_logged_error:
                print("cloud message fetch recovered", flush=True)
            self.cloud_last_logged_error = ""
            self.cloud_last_error_log_monotonic = 0.0
            self.cloud_status = "SYNCED"
            self.cloud_error = ""
            self.cloud_message_timer.setInterval(CLOUD_POLL_MS)

        self.gallery.set_cloud_status(self.cloud_status)
        self.config_page.set_cloud_status(self.cloud_status, self.cloud_error)
        if self.config_page.showing_admin:
            self.config_page.set_admin_diagnostics(self._system_diagnostics())
        if self.config_page.showing_about:
            self._refresh_about_data()

    def _wifi_busy(self, *, include_scan=True):
        operations = (
            self.wifi_connect_running,
            self.wifi_disconnect_running,
            self.wifi_forget_running,
            self.admin_wifi_reset_pending,
            self.admin_wifi_reset_running,
        )
        return any(operations) or (include_scan and self.wifi_scan_running)

    def _scan_wifi(self):
        self._refresh_wifi_status()

        if self._wifi_busy(include_scan=True):
            if not self.wifi_scan_running:
                self.config_page.set_wifi_status("wifi busy // try again")
            return

        self.config_page.begin_wifi_scan()
        self.wifi_scan_running = True
        thread = threading.Thread(
            target=self._scan_wifi_worker,
            daemon=True,
        )
        thread.start()

    def _scan_wifi_worker(self):
        try:
            subprocess.run(
                ["nmcli", "radio", "wifi", "on"],
                check=False,
                timeout=5,
            )
            subprocess.run(
                ["nmcli", "device", "wifi", "rescan"],
                check=False,
                timeout=8,
            )
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "SSID,SECURITY,SIGNAL",
                    "device",
                    "wifi",
                    "list",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.wifi_scan_finished.emit([], f"wifi scan failed: {error}")
            return

        if result.returncode != 0:
            output = (result.stderr or result.stdout).strip()
            self.wifi_scan_finished.emit(
                [],
                _friendly_nmcli_error(output, "wifi scan failed"),
            )
            return

        saved_profiles = {}
        try:
            profiles = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "UUID,TYPE,NAME,802-11-wireless.ssid",
                    "connection",
                    "show",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            profiles = None

        if profiles and profiles.returncode == 0:
            for line in profiles.stdout.splitlines():
                parts = _split_nmcli_terse(line)
                if len(parts) < 4:
                    continue
                uuid, profile_type, name, profile_ssid = parts[:4]
                if (
                    profile_type in {"802-11-wireless", "wifi"}
                    and uuid
                    and profile_ssid
                ):
                    saved_profiles.setdefault(profile_ssid, []).append(
                        {"uuid": uuid, "name": name}
                    )

        networks = []
        seen = set()
        for line in result.stdout.splitlines():
            parts = _split_nmcli_terse(line)
            if not parts:
                continue

            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue

            security = _normalize_wifi_security(
                parts[1] if len(parts) > 1 else ""
            )
            signal = parts[2].strip() if len(parts) > 2 else ""
            networks.append(
                {
                    "ssid": ssid,
                    "security": security,
                    "signal": signal,
                    "saved": ssid in saved_profiles,
                    "profile_uuids": [
                        profile["uuid"]
                        for profile in saved_profiles.get(ssid, [])
                    ],
                }
            )
            seen.add(ssid)

        self.wifi_scan_finished.emit(networks, "")

    def _wifi_scan_finished(self, networks, error):
        self.wifi_scan_running = False
        # Apply results without forcibly changing password/saved-profile state.
        self.config_page.set_wifi_networks(networks)
        if error:
            self.config_page.set_wifi_status(error)
        self._refresh_wifi_status()
        self._maybe_start_pending_wifi_reset()

    def _refresh_wifi_status(self):
        if self.wifi_status_running:
            self.wifi_status_refresh_pending = True
            return

        self.wifi_status_running = True
        self.wifi_status_refresh_pending = False
        thread = threading.Thread(
            target=self._wifi_status_worker,
            daemon=True,
        )
        thread.start()

    def _wifi_status_worker(self):
        current = {"device": "", "ssid": "", "ip": ""}

        try:
            status = subprocess.run(
                [
                    "nmcli", "-t", "-f",
                    "DEVICE,TYPE,STATE,CONNECTION",
                    "device", "status",
                ],
                check=False, capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.wifi_status_finished.emit(None)
            return

        if status.returncode != 0:
            self.wifi_status_finished.emit(None)
            return

        wifi_device = ""
        connection_name = ""
        for line in status.stdout.splitlines():
            parts = _split_nmcli_terse(line)
            if len(parts) < 4 or parts[1] != "wifi":
                continue
            wifi_device = parts[0]
            current["device"] = wifi_device
            state = parts[2].strip().lower()
            if state.startswith("connected"):
                connection_name = parts[3].strip()
                if connection_name not in {"", "--"}:
                    current["ssid"] = connection_name
            break

        if wifi_device:
            try:
                details = subprocess.run(
                    [
                        "nmcli", "-t", "-f", "IP4.ADDRESS",
                        "device", "show", wifi_device,
                    ],
                    check=False, capture_output=True, text=True, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                details = None

            if details is None or details.returncode != 0:
                # Preserve the last known status rather than falsely reporting
                # a disconnect because one diagnostic query failed.
                self.wifi_status_finished.emit(None)
                return

            for line in details.stdout.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key == "IP4.ADDRESS[1]":
                    current["ip"] = value.split("/", 1)[0]
                    break

        self.wifi_status_finished.emit(current)

    def _wifi_status_finished(self, current):
        self.wifi_status_running = False
        if current is None:
            if self.wifi_status_refresh_pending:
                self.wifi_status_refresh_pending = False
                self._refresh_wifi_status()
            return
        if current.get("device"):
            self.wifi_device = current["device"]
        self.config_page.set_wifi_current(current)
        if self.config_page.showing_admin:
            self.config_page.set_admin_diagnostics(self._system_diagnostics())
        if self.config_page.showing_about:
            self._refresh_about_data()

        if self.wifi_status_refresh_pending:
            self.wifi_status_refresh_pending = False
            self._refresh_wifi_status()

    def _connect_wifi(self, ssid, password):
        if self.admin_wifi_reset_pending or self.admin_wifi_reset_running:
            self.config_page.set_wifi_status("wifi reset pending")
            return
        if self._wifi_busy(include_scan=True):
            self.config_page.set_wifi_status("wifi busy // try again")
            return

        self.wifi_connect_running = True
        thread = threading.Thread(
            target=self._connect_wifi_worker,
            args=(ssid, password),
            daemon=True,
        )
        thread.start()

    def _connect_wifi_worker(self, ssid, password):
        # Keep the password visible in our on-device UI by design, but do not
        # place it in the process argument list where other local processes can
        # inspect it. nmcli --ask accepts the PSK on stdin instead.
        command = ["nmcli"]
        if password:
            command.append("--ask")
        command.extend(["device", "wifi", "connect", ssid])

        def run_connect():
            return subprocess.run(
                command,
                input=f"{password}\n" if password else None,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

        try:
            result = run_connect()
        except (OSError, subprocess.TimeoutExpired) as error:
            self.wifi_connect_finished.emit(False, f"connect failed: {error}")
            return

        output = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()

        # Some NetworkManager versions can leave behind an incomplete Wi-Fi
        # profile after the first connection attempt.  The next activation then
        # fails with "802-11-wireless-security.key-mgmt: property is missing".
        # Recover automatically by deleting ONLY matching Wi-Fi profiles and
        # letting `nmcli device wifi connect` recreate the profile from the AP.
        if result.returncode != 0 and "key-mgmt: property is missing" in output.lower():
            try:
                profiles = subprocess.run(
                    [
                        "nmcli",
                        "-t",
                        "-f",
                        "UUID,TYPE,802-11-wireless.ssid",
                        "connection",
                        "show",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if profiles.returncode == 0:
                    for line in profiles.stdout.splitlines():
                        parts = _split_nmcli_terse(line)
                        if len(parts) < 3:
                            continue
                        uuid, profile_type, profile_ssid = parts[:3]
                        if profile_ssid == ssid and profile_type in {
                            "802-11-wireless",
                            "wifi",
                        }:
                            subprocess.run(
                                ["nmcli", "connection", "delete", "uuid", uuid],
                                check=False,
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )

                    # Make sure the AP is freshly visible before recreating it.
                    subprocess.run(
                        ["nmcli", "device", "wifi", "rescan"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=8,
                    )
                    result = run_connect()
                    output = (
                        (result.stderr or "") + "\n" + (result.stdout or "")
                    ).strip()
            except (OSError, subprocess.TimeoutExpired):
                # Fall through and display the original/last NetworkManager
                # error instead of crashing the UI.
                pass

        if result.returncode == 0:
            self.wifi_connect_finished.emit(True, "connected")
        else:
            self.wifi_connect_finished.emit(
                False,
                _friendly_nmcli_error(output, "connect failed"),
            )

    def _wifi_connect_finished(self, connected, status):
        self.wifi_connect_running = False
        self.config_page.set_wifi_status(status)
        if connected:
            self.config_page.wifi_connection_succeeded()
        self._refresh_wifi_status()
        if connected and self.settings.get("cloud_message_url"):
            QTimer.singleShot(500, self._refresh_cloud_message)
        self._maybe_start_pending_wifi_reset()

    def _connect_saved_wifi(self, profile_uuids):
        if self.admin_wifi_reset_pending or self.admin_wifi_reset_running:
            self.config_page.set_wifi_status("wifi reset pending")
            return
        if self._wifi_busy(include_scan=True):
            self.config_page.set_wifi_status("wifi busy // try again")
            return

        uuids = [str(uuid) for uuid in profile_uuids if uuid]
        if not uuids:
            self.config_page.set_wifi_status("saved profile not found")
            return

        self.wifi_connect_running = True
        threading.Thread(
            target=self._connect_saved_wifi_worker,
            args=(uuids,),
            daemon=True,
        ).start()

    def _connect_saved_wifi_worker(self, profile_uuids):
        errors = []
        for uuid in profile_uuids:
            try:
                result = subprocess.run(
                    ["nmcli", "connection", "up", "uuid", uuid],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                errors.append(str(error))
                continue

            if result.returncode == 0:
                self.wifi_connect_finished.emit(True, "connected")
                return

            output = (result.stderr or result.stdout or "").strip()
            if output:
                errors.append(output)

        self.wifi_connect_finished.emit(
            False,
            _friendly_nmcli_error(" ".join(errors), "connect failed"),
        )

    def _disconnect_wifi(self):
        if self.admin_wifi_reset_pending or self.admin_wifi_reset_running:
            self.config_page.set_wifi_status("wifi reset pending")
            return
        if self._wifi_busy(include_scan=True):
            self.config_page.set_wifi_status("wifi busy // try again")
            return
        if not self.wifi_device:
            self.config_page.set_wifi_status("no wifi device")
            return

        self.wifi_disconnect_running = True
        thread = threading.Thread(
            target=self._disconnect_wifi_worker,
            args=(self.wifi_device,),
            daemon=True,
        )
        thread.start()

    def _disconnect_wifi_worker(self, device):
        try:
            result = subprocess.run(
                ["nmcli", "device", "disconnect", device],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.wifi_disconnect_finished.emit(
                False,
                f"disconnect failed: {error}",
            )
            return

        output = (result.stdout or result.stderr).strip()
        if result.returncode == 0:
            self.wifi_disconnect_finished.emit(True, "disconnected")
        else:
            self.wifi_disconnect_finished.emit(
                False,
                _friendly_nmcli_error(output, "disconnect failed"),
            )

    def _wifi_disconnect_finished(self, disconnected, status):
        self.wifi_disconnect_running = False
        self.config_page.set_wifi_status(status)
        self._refresh_wifi_status()
        self._maybe_start_pending_wifi_reset()

    def _forget_wifi(self, profile_uuids):
        if self.admin_wifi_reset_pending or self.admin_wifi_reset_running:
            self.config_page.set_wifi_status("wifi reset pending")
            return
        if self._wifi_busy(include_scan=True):
            self.config_page.set_wifi_status("wifi busy // try again")
            return

        uuids = [str(uuid) for uuid in profile_uuids if uuid]
        if not uuids:
            self.config_page.set_wifi_status("saved profile not found")
            return

        self.wifi_forget_running = True
        threading.Thread(
            target=self._forget_wifi_worker,
            args=(uuids,),
            daemon=True,
        ).start()

    def _forget_wifi_worker(self, profile_uuids):
        deleted = 0
        errors = []
        for uuid in profile_uuids:
            try:
                result = subprocess.run(
                    ["nmcli", "connection", "delete", "uuid", uuid],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                errors.append(str(error))
                continue

            if result.returncode == 0:
                deleted += 1
            else:
                error = (result.stderr or result.stdout or "").strip()
                if error:
                    errors.append(error)

        if deleted:
            self.wifi_forget_finished.emit(True, "profile forgotten")
        elif errors:
            self.wifi_forget_finished.emit(
                False,
                _friendly_nmcli_error(" ".join(errors), "forget failed"),
            )
        else:
            self.wifi_forget_finished.emit(False, "saved profile not found")

    def _wifi_forget_finished(self, forgotten, status):
        self.wifi_forget_running = False
        self.config_page.set_wifi_status(status)
        self._scan_wifi()
        self._maybe_start_pending_wifi_reset()

    def _admin_reset_wifi(self):
        if self.admin_wifi_reset_running or self.admin_wifi_reset_pending:
            return

        if self._wifi_mutation_running():
            self.admin_wifi_reset_pending = True
            self.config_page.set_admin_status("waiting for wifi operation...")
            return

        self._start_admin_wifi_reset()

    def _wifi_mutation_running(self):
        # Include scans so a pre-reset scan cannot finish afterward and
        # repaint stale SAVED markers over the freshly cleared state.
        return any((
            self.wifi_scan_running,
            self.wifi_connect_running,
            self.wifi_disconnect_running,
            self.wifi_forget_running,
        ))

    def _maybe_start_pending_wifi_reset(self):
        if not self.admin_wifi_reset_pending or self._wifi_mutation_running():
            return
        self.admin_wifi_reset_pending = False
        self._start_admin_wifi_reset()

    def _start_admin_wifi_reset(self):
        if self.admin_wifi_reset_running:
            return
        self.admin_wifi_reset_running = True
        self.config_page.set_admin_status("resetting wifi...")
        threading.Thread(
            target=self._admin_reset_wifi_worker,
            daemon=True,
        ).start()

    def _admin_reset_wifi_worker(self):
        errors = []
        try:
            profiles = subprocess.run(
                [
                    "nmcli", "-t", "-f", "UUID,TYPE",
                    "connection", "show",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.admin_wifi_reset_finished.emit(False, str(exc))
            return

        if profiles.returncode != 0:
            output = (profiles.stderr or profiles.stdout or "").strip()
            self.admin_wifi_reset_finished.emit(
                False,
                _friendly_nmcli_error(output, "wifi reset failed"),
            )
            return

        uuids = []
        for line in profiles.stdout.splitlines():
            parts = _split_nmcli_terse(line)
            if len(parts) < 2:
                continue
            profile_uuid, profile_type = parts[0].strip(), parts[1].strip().lower()
            if profile_uuid and profile_type in {"802-11-wireless", "wifi"}:
                uuids.append(profile_uuid)

        # Disconnect first so no deleted active profile remains attached to
        # the device while NetworkManager removes its saved configuration.
        try:
            subprocess.run(
                ["nmcli", "device", "disconnect", self.wifi_device],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            pass

        deleted = 0
        for profile_uuid in uuids:
            try:
                result = subprocess.run(
                    ["nmcli", "connection", "delete", "uuid", profile_uuid],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
                continue
            if result.returncode == 0:
                deleted += 1
            else:
                errors.append((result.stderr or result.stdout or "").strip())

        if errors:
            self.admin_wifi_reset_finished.emit(
                False,
                _friendly_nmcli_error(" ".join(errors), "wifi reset incomplete"),
            )
        elif uuids:
            self.admin_wifi_reset_finished.emit(
                True,
                f"cleared {deleted} wifi profile{'s' if deleted != 1 else ''}",
            )
        else:
            self.admin_wifi_reset_finished.emit(True, "no saved wifi profiles")

    def _admin_wifi_reset_finished(self, success, status):
        self.admin_wifi_reset_running = False
        self.config_page.finish_admin_action(status)
        self._refresh_wifi_status()
        self._scan_wifi()
        self.config_page.set_admin_diagnostics(self._system_diagnostics())

    def _admin_reset_memos(self):
        if self.cloud_message_running:
            # fetch_cloud_message writes the cache before emitting its result.
            # Defer the reset until that fetch completes so an in-flight poll
            # cannot immediately recreate files that were just deleted.
            self.memo_reset_pending = True
            self.config_page.set_admin_status("waiting for cloud fetch...")
            return
        self._perform_memo_reset()

    def _perform_memo_reset(self):
        paths = (
            CLOUD_MEMOS_FILE,
            CLOUD_MESSAGE_FILE,
            CLOUD_MESSAGE_META_FILE,
            READ_MEMOS_FILE,
        )
        try:
            for path in paths:
                path.unlink(missing_ok=True)
        except OSError as exc:
            self.admin_memos_reset_finished.emit(False, f"memo reset failed: {exc}")
            return

        self.memo = ""
        self.memo_date = ""
        self.memos = []
        self.unread_memos = 0
        self.gallery.set_unread_memo_count(0)
        self.home.set_unread_memo_count(0)
        self.ambient_sleep.set_unread_memo_count(0)
        self.config_page.clear_memo_data()
        self._update_memo_chime_timer()

        # Give the cleared state a full normal polling interval before the
        # currently published remote memo is eligible to arrive again.
        if self.settings.get("cloud_message_url"):
            self.cloud_message_timer.start(CLOUD_POLL_MS)

        self.admin_memos_reset_finished.emit(True, "local memos cleared")

    def _admin_memos_reset_finished(self, success, status):
        self.config_page.finish_admin_action(status)
        self.config_page.set_admin_diagnostics(self._system_diagnostics())

    def _reboot_system(self):
        if self.reboot_running:
            return
        self.reboot_running = True
        self.audio.play("select")
        self.config_page.set_reboot_status("rebooting...")
        threading.Thread(
            target=self._reboot_worker,
            daemon=True,
        ).start()

    def _reboot_worker(self):
        commands = (
            ["systemctl", "reboot", "--no-block", "--no-wall"],
            ["sudo", "-n", "systemctl", "reboot", "--no-block", "--no-wall"],
        )
        errors = []

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
                continue

            if result.returncode == 0:
                # Do not quit Qt ourselves.  A successful system reboot will
                # terminate X and the application.  This avoids leaving the
                # user at a blank X root window if reboot authorization fails.
                return

            error = (result.stderr or result.stdout or "").strip()
            if error:
                errors.append(error)

        message = "reboot permission denied"
        combined = " ".join(errors).lower()
        if combined and not any(
            token in combined
            for token in ("permission", "authentication", "password", "polkit")
        ):
            message = "reboot command failed"
        self.reboot_finished.emit(False, message)

    def _reboot_finished(self, success, status):
        if success:
            return
        self.reboot_running = False
        self.config_page.confirming_reboot = False
        self.config_page.set_reboot_status(status)

    def _mpv_ready(self, generation):
        if generation != self.playback_generation or self.mode != "loading":
            return
        print(
            "mpv: file-loaded",
            flush=True,
        )

        self.mpv_ready = True
        self._maybe_start_video()

    def _mpv_started(self, generation):
        if generation != self.playback_generation or self.mode != "loading":
            return
        print(
            "mpv: playback position advancing",
            flush=True,
        )

        if self.mpv_started:
            return

        self.mpv_started = True
        # Keep the opaque transition up for a few render cycles after
        # playback position advances so the handoff cannot expose a late
        # black clear frame from the native mpv surface.
        generation = self.playback_generation
        QTimer.singleShot(
            700,
            lambda g=generation: self._maybe_reveal_video(g),
        )

    def _transition_minimum_elapsed(self):
        self.transition_minimum_elapsed = True
        self._maybe_start_video()

    def _maybe_start_video(self):
        """
        Start mpv only once BOTH:
          1) mpv has finished loading the file, and
          2) the visible transition has run for its minimum duration.

        The native video surface is already mapped underneath the native
        opaque transition, so mpv can render without exposing its clear frame.
        """
        if self.mode != "loading":
            return

        if not (
            self.mpv_ready
            and self.transition_minimum_elapsed
        ):
            return

        if self.mpv_started:
            return

        print(
            "mpv loaded + transition minimum complete -> unpause behind transition",
            flush=True,
        )

        self.playback_page.transition.raise_()

        QApplication.processEvents()

        self.player.play()

    def _maybe_reveal_video(self, generation=None):
        """
        Hide the transition only after mpv reports playback-restart,
        meaning playback has actually resumed and the video renderer has
        a real frame ready underneath us.
        """
        if generation is not None and generation != self.playback_generation:
            return
        if self.mode != "loading":
            return

        if not self.mpv_started:
            return

        print(
            "first playback frames active -> reveal video + audio",
            flush=True,
        )

        self.playback_watchdog.stop()
        self.playback_page.hide_transition()
        self.player.unmute()

        self.mode = "playing"

    def _playback_start_timeout(self):
        if self.mode == "loading":
            self._playback_failed(self.playback_generation, "playback startup timed out")

    # =====================================================
    # STOP / END VIDEO
    # =====================================================

    def stop_video(self):
        if self.mode != "playing":
            return

        self.player.pause()
        self._begin_return()

    def _video_ended(self, generation):
        if generation != self.playback_generation:
            return
        if self.mode == "playing":
            self._begin_return()

    def _begin_return(self):
        if self.return_pending:
            return

        self.return_pending = True
        self.mode = "returning"
        self.playback_generation += 1
        self.playback_watchdog.stop()

        title = ""

        if self.pending_index is not None:
            title = self.titles[
                self.pending_index
            ]

        # End playback with audio feedback only; no static return overlay.
        self.playback_page.show_transition_return(
            title
        )

        QApplication.processEvents()

        self.player.stop(
            silent=True
        )
        self.playback_page.hide_video_surface()
        self.audio.play("return")

    def _finish_return(self):
        # A queued transition timeout must never override a later global Home
        # jump or other state change.
        if self.mode != "returning" or not self.return_pending:
            return

        self.pages.setCurrentWidget(self.gallery)
        self.playback_page.hide_transition()
        self.playback_page.stop_effects()

        self.return_pending = False
        self.mode = "gallery"
        self.gallery.cancel_navigation()
        self._restart_display_sleep_timer()
        if not self.display.sleeping:
            self.gallery.flicker_timer.start(90)


    # =====================================================
    # ERROR
    # =====================================================

    def _playback_failed(
        self,
        generation,
        message,
    ):
        if generation != self.playback_generation:
            return
        print(
            f"PLAYBACK ERROR: {message}",
            flush=True,
        )
        self.audio.play("error")

        if self.mode in (
            "loading",
            "playing",
        ):
            self._begin_return()

    def closeEvent(
        self,
        event,
    ):
        self.playback_watchdog.stop()
        self.playback_page.stop_effects()
        self.player.stop(
            silent=True
        )
        self.input_controller.close()

        event.accept()


def main():
    app = QApplication(
        sys.argv
    )

    window = VideoArchiveWindow()


    screen_rect = app.primaryScreen().geometry()

    print(
        f"X screen: {screen_rect.width()}x{screen_rect.height()} "
        f"at {screen_rect.x()},{screen_rect.y()}",
        flush=True,
    )

    window.setGeometry(
        screen_rect
    )

    window.move(
        screen_rect.x(),
        screen_rect.y(),
    )

    window.resize(
        screen_rect.width(),
        screen_rect.height(),
    )

    window.show()
    window.raise_()
    window.activateWindow()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
