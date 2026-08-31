import json
import subprocess
import sys
import threading

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
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
    unread_memo_count,
)
from .config import (
    DEFAULT_NOTE,
    DEFAULT_SETTINGS,
    NOTE_FILE,
    ORDER_FILE,
    SETTINGS_FILE,
    VIDEO_DIR,
)
from .input import InputController
from .player import MpvController
from .storage import atomic_write_json
from .ui import (
    ConfigWidget,
    GalleryWidget,
    StartScreenWidget,
    TransitionWidget,
    draw_global_flicker,
    draw_random_screen_flicker,
    draw_signal_acquisition_flicker,
)

VIDEO_EXTENSIONS = {".mp4", ".mov"}
CONFIG_TITLE = "APPS"
MAX_MPV_VOLUME = 150


def load_videos():
    VIDEO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    available = {
        file.name: file
        for file in VIDEO_DIR.iterdir()
        if (
            file.is_file()
            and file.suffix.lower() in VIDEO_EXTENSIONS
        )
    }

    ordered = []

    if ORDER_FILE.exists():
        for line in ORDER_FILE.read_text().splitlines():
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
            loaded = json.loads(
                SETTINGS_FILE.read_text()
            )
        except (OSError, json.JSONDecodeError):
            loaded = {}

        if isinstance(loaded, dict):
            settings.update(loaded)

    try:
        volume = int(
            settings.get("volume", DEFAULT_SETTINGS["volume"])
        )
    except (TypeError, ValueError):
        volume = DEFAULT_SETTINGS["volume"]

    settings["volume"] = max(
        0,
        min(100, volume),
    )
    settings["sfx_enabled"] = bool(
        settings.get(
            "sfx_enabled",
            DEFAULT_SETTINGS["sfx_enabled"],
        )
    )
    settings["cloud_message_url"] = str(
        settings.get("cloud_message_url", "")
    ).strip()

    return settings


def save_settings(settings):
    atomic_write_json(SETTINGS_FILE, settings)


def load_note():
    if not NOTE_FILE.exists():
        NOTE_FILE.write_text(DEFAULT_NOTE + "\n")

    return NOTE_FILE.read_text().strip()


def mpv_volume_from_setting(volume):
    return round(
        max(0, min(100, int(volume)))
        * MAX_MPV_VOLUME
        / 100
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

        self.setCursor(
            Qt.BlankCursor
        )

        self.flicker_timer = QTimer(self)

        self.flicker_timer.timeout.connect(
            self._advance_flicker
        )

        self.flicker_timer.start(
            80
        )

    def _advance_flicker(self):
        self.flicker_phase = (
            self.flicker_phase + 1
        ) % 32

        self.update()

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

        painter.drawText(
            QRect(
                self.width() // 2,
                42,
                self.width() // 2 - 42,
                30,
            ),
            Qt.AlignRight | Qt.AlignVCenter,
            self.current_title,
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
            "PRESS // RETURN",
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
    cloud_message_finished = Signal(str, str)

    def __init__(self):
        super().__init__()

        self.videos = load_videos()
        self.settings = load_settings()
        self.note = load_note()
        self.memo = load_cached_message()
        self.memo_date = load_cached_message_date()
        self.memos = load_memos()
        self.unread_memos = unread_memo_count(self.memos)

        # Preserve the actual extension in the gallery:
        # AUTUMN.mp4, TRIP.mov, etc.
        self.titles = [
            path.name
            for path in self.videos
        ]
        self.gallery_titles = [
            *self.titles,
            CONFIG_TITLE,
        ]

        self.mode = "start"
        self.pending_index = None

        self.mpv_ready = False
        self.mpv_started = False
        self.transition_minimum_elapsed = False
        self.return_pending = False
        self.wifi_scan_running = False
        self.wifi_connect_running = False
        self.wifi_status_running = False
        self.wifi_disconnect_running = False
        self.wifi_device = "wlan0"
        self.cloud_message_running = False

        self.setWindowTitle(
            "Video Archive"
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

        self.gallery = GalleryWidget(
            self.gallery_titles,
            self.unread_memos,
        )

        self.config_page = ConfigWidget(
            self.note,
            self.memo,
            self.memo_date,
            self.memos,
            self.settings["volume"],
            self.settings["sfx_enabled"],
        )
        self.config_page.set_read_memo_keys(load_read_memo_keys())

        self.playback_page = PlaybackPage()

        self.pages = QStackedWidget()

        self.pages.addWidget(
            self.start_screen
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

        # =================================================
        # SIGNALS
        # =================================================

        self.start_screen.started.connect(
            self.start_gallery
        )

        self.start_screen.boot_finished.connect(
            self._boot_finished
        )

        self.gallery.play_requested.connect(
            self.play_selected
        )

        self.config_page.back_requested.connect(
            self._return_to_gallery
        )

        self.config_page.reboot_requested.connect(
            self._reboot_system
        )

        self.config_page.volume_changed.connect(
            self._set_volume
        )

        self.config_page.sfx_changed.connect(
            self._set_sfx_enabled
        )

        self.config_page.wifi_scan_requested.connect(
            self._scan_wifi
        )

        self.config_page.wifi_connect_requested.connect(
            self._connect_wifi
        )

        self.config_page.wifi_disconnect_requested.connect(
            self._disconnect_wifi
        )

        self.config_page.memo_read.connect(
            self._memo_read
        )

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

        self.input_controller.select_pressed.connect(
            self._physical_select
        )

        self.input_controller.right_pressed.connect(
            self._physical_right
        )       

        self.cloud_message_timer = QTimer(self)
        self.cloud_message_timer.timeout.connect(
            self._refresh_cloud_message
        )
        if self.settings["cloud_message_url"]:
            self.cloud_message_timer.start(60000)
            QTimer.singleShot(3000, self._refresh_cloud_message)

    def _physical_left(self):
        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_gallery()
            return

        if self.mode == "gallery":
            self.audio.play("click")
            self.gallery.move_left()

        elif self.mode == "config":
            self.audio.play("click")
            self.config_page.move_left()


    def _physical_select(self):
        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_gallery()
            return

        if self.mode == "gallery":
            self.audio.play("select")
            self.play_selected(
                self.gallery.selected_index
            )

        elif self.mode == "playing":
            self.stop_video()

        elif self.mode == "config":
            self.audio.play("select")
            self.config_page.select()


    def _physical_right(self):
        if self.mode == "start":
            if self.start_screen.can_start():
                self.start_gallery()
            return

        if self.mode == "gallery":
            self.audio.play("click")
            self.gallery.move_right()

        elif self.mode == "config":
            self.audio.play("click")
            self.config_page.move_right()

    def _boot_finished(self):
        self.audio.play("boot")

    def start_gallery(self):
        if self.mode != "start":
            return

        if not self.start_screen.can_start():
            return

        self.audio.play("select")
        self.mode = "gallery"
        self.pages.setCurrentWidget(self.gallery)
        self.gallery.setFocus()

    # =====================================================
    # START VIDEO
    # =====================================================

    def play_selected(
        self,
        index,
    ):
        if index >= len(self.videos):
            self.show_config()
            return

        if not self.videos:
            return

        if self.mode != "gallery":
            return

        self.mode = "loading"
        self.pending_index = index

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

        self.player.preload(
            video_path,
            wid,
            mpv_volume_from_setting(
                self.settings["volume"]
            ),
        )

    def show_config(self):
        if self.mode != "gallery":
            return

        self.mode = "config"
        self.config_page.set_note(self.note)
        self.config_page.set_memo(self.memo, self.memo_date)
        self.config_page.set_memos(self.memos)
        self.config_page.set_volume(self.settings["volume"])
        self.config_page.set_sfx_enabled(
            self.settings["sfx_enabled"]
        )
        self.config_page.show_apps_home()
        self.pages.setCurrentWidget(self.config_page)
        self.config_page.setFocus()

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
        self.config_page.set_read_memo_keys(load_read_memo_keys())

    def _set_volume(self, volume):
        self.settings["volume"] = volume
        save_settings(self.settings)
        self.player.set_volume(
            mpv_volume_from_setting(volume)
        )
        self.audio.set_volume(
            mpv_volume_from_setting(volume)
        )

    def _set_sfx_enabled(self, enabled):
        self.settings["sfx_enabled"] = enabled
        save_settings(self.settings)
        self.audio.set_enabled(enabled)
        if enabled:
            self.audio.play("select")

    def _refresh_cloud_message(self):
        url = self.settings.get("cloud_message_url", "")
        if not url or self.cloud_message_running:
            return

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
        if message:
            self.memo = message
            self.memo_date = load_cached_message_date()
            self.memos = load_memos()
            self.unread_memos = unread_memo_count(self.memos)
            self.gallery.set_unread_memo_count(self.unread_memos)
            self.config_page.set_memo(message, self.memo_date)
            self.config_page.set_memos(self.memos)
            self.config_page.set_read_memo_keys(load_read_memo_keys())
        elif error:
            print(
                f"cloud message fetch failed: {error}",
                flush=True,
            )

    def _scan_wifi(self):
        self._refresh_wifi_status()

        if self.wifi_scan_running:
            return

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
                output[-80:] if output else "wifi scan failed"
            )
            return

        networks = []
        seen = set()
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if not parts:
                continue

            ssid = parts[0].replace(r"\:", ":").strip()
            if not ssid or ssid in seen:
                continue

            security = parts[1].strip() if len(parts) > 1 else ""
            signal = parts[2].strip() if len(parts) > 2 else ""
            networks.append(
                {
                    "ssid": ssid,
                    "security": security,
                    "signal": signal,
                }
            )
            seen.add(ssid)

        self.wifi_scan_finished.emit(networks, "")

    def _wifi_scan_finished(self, networks, error):
        self.wifi_scan_running = False
        self.config_page.set_wifi_networks(networks)
        if error:
            self.config_page.set_wifi_status(error)
        self._refresh_wifi_status()

    def _refresh_wifi_status(self):
        if self.wifi_status_running:
            return

        self.wifi_status_running = True
        thread = threading.Thread(
            target=self._wifi_status_worker,
            daemon=True,
        )
        thread.start()

    def _wifi_status_worker(self):
        current = {
            "device": "wifi",
            "ssid": "",
            "ip": "",
        }

        try:
            status = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "DEVICE,TYPE,STATE,CONNECTION",
                    "device",
                    "status",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.wifi_status_finished.emit(current)
            return

        wifi_device = ""
        for line in status.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 4 or parts[1] != "wifi":
                continue

            wifi_device = parts[0]
            current["device"] = wifi_device
            if parts[2] == "connected":
                current["ssid"] = parts[3].replace(r"\:", ":")
            break

        if wifi_device:
            try:
                details = subprocess.run(
                    [
                        "nmcli",
                        "-t",
                        "-f",
                        "IP4.ADDRESS",
                        "device",
                        "show",
                        wifi_device,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                details = None

            if details and details.returncode == 0:
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
        if current.get("device"):
            self.wifi_device = current["device"]
        self.config_page.set_wifi_current(current)

    def _connect_wifi(self, ssid, password):
        if self.wifi_connect_running:
            return

        self.wifi_connect_running = True
        thread = threading.Thread(
            target=self._connect_wifi_worker,
            args=(ssid, password),
            daemon=True,
        )
        thread.start()

    def _connect_wifi_worker(self, ssid, password):
        command = [
            "nmcli",
            "device",
            "wifi",
            "connect",
            ssid,
        ]
        if password:
            command.extend(["password", password])

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.wifi_connect_finished.emit(False, f"connect failed: {error}")
            return

        output = (result.stdout or result.stderr).strip()
        if result.returncode == 0:
            self.wifi_connect_finished.emit(True, "connected")
        else:
            self.wifi_connect_finished.emit(
                False,
                output[-80:] if output else "connect failed",
            )

    def _wifi_connect_finished(self, connected, status):
        self.wifi_connect_running = False
        self.config_page.set_wifi_status(status)
        self._refresh_wifi_status()

    def _disconnect_wifi(self):
        if self.wifi_disconnect_running:
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
                output[-80:] if output else "disconnect failed",
            )

    def _wifi_disconnect_finished(self, disconnected, status):
        self.wifi_disconnect_running = False
        self.config_page.set_wifi_status(status)
        self._refresh_wifi_status()

    def _return_to_gallery(self):
        if self.mode != "config":
            return

        self.mode = "gallery"
        self.pages.setCurrentWidget(self.gallery)
        self.gallery.setFocus()

    def _reboot_system(self):
        self.audio.play("select")
        self.player.stop(silent=True)
        subprocess.Popen(["sudo", "reboot"])
        QApplication.quit()

    def _mpv_ready(self):
        print(
            "mpv: file-loaded",
            flush=True,
        )

        self.mpv_ready = True
        self._maybe_start_video()

    def _mpv_started(self):
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
        QTimer.singleShot(
            700,
            self._maybe_reveal_video,
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

    def _maybe_reveal_video(self):
        """
        Hide the transition only after mpv reports playback-restart,
        meaning playback has actually resumed and the video renderer has
        a real frame ready underneath us.
        """
        if self.mode != "loading":
            return

        if not self.mpv_started:
            return

        print(
            "first playback frames active -> reveal video + audio",
            flush=True,
        )

        self.playback_page.hide_transition()
        self.player.unmute()

        self.mode = "playing"

    # =====================================================
    # STOP / END VIDEO
    # =====================================================

    def stop_video(self):
        if self.mode != "playing":
            return

        self.player.pause()
        self._begin_return()

    def _video_ended(self):
        if self.mode == "playing":
            self._begin_return()

    def _begin_return(self):
        if self.return_pending:
            return

        self.return_pending = True
        self.mode = "returning"

        title = ""

        if self.pending_index is not None:
            title = self.titles[
                self.pending_index
            ]

        # Cover the last video frame before anything else changes.
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
        self.pages.setCurrentWidget(
            self.gallery
        )

        self.playback_page.hide_transition()

        self.return_pending = False
        self.mode = "gallery"

        self.gallery.setFocus()

    # =====================================================
    # ERROR
    # =====================================================

    def _playback_failed(
        self,
        message,
    ):
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

    # =====================================================
    # GLOBAL KEYBOARD INPUT
    # =====================================================

    def eventFilter(
        self,
        obj,
        event,
    ):
        if event.type() == QEvent.KeyPress:
            key = event.key()

            if self.mode == "start":
                if self.start_screen.can_start():
                    self.start_gallery()
                return True

            if self.mode == "gallery":
                if key == Qt.Key_Left:
                    self.gallery.move_left()
                    self.audio.play("click")
                    return True

                if key == Qt.Key_Right:
                    self.gallery.move_right()
                    self.audio.play("click")
                    return True

                if key in (
                    Qt.Key_Return,
                    Qt.Key_Enter,
                ):
                    self.audio.play("select")
                    self.play_selected(
                        self.gallery.selected_index
                    )
                    return True

                if key == Qt.Key_Escape:
                    self.close()
                    return True

            elif self.mode == "config":
                if key == Qt.Key_Left:
                    self.config_page.move_left()
                    self.audio.play("click")
                    return True

                if key == Qt.Key_Right:
                    self.config_page.move_right()
                    self.audio.play("click")
                    return True

                if key in (
                    Qt.Key_Return,
                    Qt.Key_Enter,
                ):
                    self.config_page.select()
                    self.audio.play("select")
                    return True

                if key == Qt.Key_Escape:
                    self._return_to_gallery()
                    return True

            elif self.mode == "playing":
                if key in (
                    Qt.Key_Return,
                    Qt.Key_Enter,
                    Qt.Key_Escape,
                    Qt.Key_Space,
                ):
                    self.stop_video()
                    return True

        return super().eventFilter(
            obj,
            event,
        )

    def closeEvent(
        self,
        event,
    ):
        self.player.stop(
            silent=True
        )

        event.accept()


def main():
    app = QApplication(
        sys.argv
    )

    window = VideoArchiveWindow()

    app.installEventFilter(
        window
    )

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
    window.setFocus()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
