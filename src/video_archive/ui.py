from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .cloud import memo_key
from .config import (
    ANIMATION_STEP_MS,
    ANIMATION_STEPS,
)

# =========================================================
# COLORS
# =========================================================

BG = QColor("#050805")
BG_STRIPE = QColor("#070D07")

GREEN_BRIGHT = QColor("#7CFF6B")
GREEN_MAIN = QColor("#56D94F")
GREEN_MUTED = QColor("#2F7330")
GREEN_DIM = QColor("#173B19")

TEXT_MAIN = QColor("#A8DFA3")
TEXT_DIM = QColor("#577A55")


# =========================================================
# LAYOUT
# =========================================================

GALLERY_CENTER_Y = 390

SLOT_WIDTH = 300
SLOT_HEIGHT = 100

SPACING = 330

MAX_TITLE_FONT_SIZE = 34
MIN_TITLE_FONT_SIZE = 18

CONFIG_TILE_TITLE = "APPS"

BOOT_LINES = (
    "POWER BUS ........ OK",
    "MEMORY CHECK ..... OK",
    "MOUNT ARCHIVE .... OK",
    "SYNC FIELD ....... LOCK",
    "VIDEO BUS ........ READY",
)


def draw_text_glow(painter, rect, flags, text, font, color, glow_color):
    painter.setFont(font)
    painter.setPen(glow_color)
    painter.drawText(rect.adjusted(-2, 0, -2, 0), flags, text)
    painter.drawText(rect.adjusted(2, 0, 2, 0), flags, text)
    painter.setPen(color)
    painter.drawText(rect, flags, text)


def draw_tracking_glitch(painter, width, height, phase):
    if phase not in (11, 29):
        return

    y = 72 + (phase * 37) % max(1, height - 160)
    painter.fillRect(38, y, width - 76, 1, GREEN_MUTED)


def draw_global_flicker(painter, width, height, phase):
    pulse = (phase * 17 + 9) % 43
    if pulse in (0, 1):
        painter.fillRect(0, 0, width, 2, GREEN_DIM)

    speck_y = 64 + (phase * 41) % max(1, height - 128)
    if phase % 13 == 0:
        painter.fillRect(72, speck_y, width - 144, 1, BG_STRIPE)


def draw_random_screen_flicker(painter, width, height, phase):
    seed = (phase * 1664525 + 1013904223) & 0xFFFFFFFF
    burst = (seed >> 24) & 0xFF

    if burst < 22:
        painter.fillRect(
            0,
            0,
            width,
            height,
            QColor(124, 255, 107, 12),
        )

    if burst in (42, 83, 121, 166, 197):
        y = 34 + ((seed >> 8) % max(1, height - 68))
        offset = ((seed >> 19) % 31) - 15
        painter.fillRect(
            max(0, offset),
            y,
            width - abs(offset),
            2 + (burst % 3),
            GREEN_DIM,
        )
        painter.fillRect(
            max(0, -offset),
            min(height - 1, y + 5),
            width - abs(offset),
            1,
            GREEN_MUTED,
        )

    if burst in (9, 57, 143, 221):
        for band in range(3):
            seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
            y = (seed >> 9) % max(1, height)
            x_shift = ((seed >> 21) % 45) - 22
            painter.fillRect(
                max(0, x_shift),
                y,
                width - abs(x_shift),
                1,
                GREEN_MUTED if band == 0 else BG_STRIPE,
            )

    if phase % 17 == 0:
        for index in range(10):
            seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
            x = (seed >> 16) % max(1, width)
            y = (seed >> 8) % max(1, height)
            painter.fillRect(
                x,
                y,
                2,
                1,
                GREEN_MUTED,
            )


def draw_signal_acquisition_flicker(
    painter,
    width,
    height,
    phase,
    intro_only=False,
):
    flicker_phase = phase % 8 if intro_only else phase % 32

    if flicker_phase == 5:
        painter.fillRect(
            0,
            0,
            width,
            height,
            QColor("#060A06"),
        )

    if flicker_phase == 3 and (not intro_only or phase < 10):
        painter.fillRect(
            52,
            int(height * 0.32),
            width - 104,
            1,
            GREEN_MUTED,
        )
        painter.fillRect(
            52,
            int(height * 0.71),
            width - 104,
            1,
            GREEN_DIM,
        )


class StartScreenWidget(QWidget):
    started = Signal()
    boot_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.flicker_phase = 0
        self.boot_tick = 0
        self.boot_complete = False

        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.BlankCursor)

        self.flicker_timer = QTimer(self)
        self.flicker_timer.timeout.connect(self._advance_flicker)
        self.flicker_timer.start(90)

        self.boot_timer = QTimer(self)
        self.boot_timer.setSingleShot(True)
        self.boot_timer.timeout.connect(self._finish_boot)
        self.boot_timer.start(5000)

    def _advance_flicker(self):
        self.flicker_phase = (self.flicker_phase + 1) % 32
        if not self.boot_complete:
            self.boot_tick += 1
        self.update()

    def _finish_boot(self):
        self.boot_complete = True
        self.boot_finished.emit()
        self.update()

    def can_start(self):
        return self.boot_complete

    def keyPressEvent(self, event):
        if self.can_start():
            self.started.emit()

    def mousePressEvent(self, event):
        if self.can_start():
            self.started.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        painter.fillRect(self.rect(), BG)

        for y in range(0, self.height(), 16):
            painter.fillRect(0, y, self.width(), 5, BG_STRIPE)

        scan_y = 80 + (self.flicker_phase * 19) % max(1, self.height() - 160)
        painter.fillRect(42, scan_y, self.width() - 84, 1, GREEN_DIM)

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

        pen = QPen(GREEN_MUTED)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(26, 26, self.width() - 52, self.height() - 52)

        pen = QPen(GREEN_DIM)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(36, 36, self.width() - 72, self.height() - 72)

        draw_tracking_glitch(
            painter,
            self.width(),
            self.height(),
            self.flicker_phase,
        )

        title_font = QFont("DejaVu Sans Mono", 46, QFont.Bold)
        draw_text_glow(
            painter,
            QRect(70, 112, self.width() - 140, 82),
            Qt.AlignCenter,
            "4AUTUMN.EXE",
            title_font,
            GREEN_BRIGHT,
            GREEN_DIM,
        )

        painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(
            QRect(self.width() - 300, 55, 240, 35),
            Qt.AlignRight | Qt.AlignVCenter,
            "STANDBY // READY",
        )

        painter.setPen(GREEN_DIM)
        painter.drawLine(60, 210, self.width() - 60, 210)

        pulse_on = self.flicker_phase % 18 < 12

        if self.boot_complete:
            prompt_font = QFont("DejaVu Sans Mono", 32, QFont.Bold)
            draw_text_glow(
                painter,
                QRect(80, self.height() // 2 + 10, self.width() - 160, 70),
                Qt.AlignCenter,
                "PRESS ANY KEY TO START",
                prompt_font,
                GREEN_BRIGHT if pulse_on else GREEN_MAIN,
                GREEN_DIM,
            )

            painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
            painter.setPen(TEXT_DIM)
            painter.drawText(
                QRect(80, self.height() // 2 + 83, self.width() - 160, 30),
                Qt.AlignCenter,
                "ARCHIVE AWAITING INPUT  []",
            )

        else:
            visible_boot_lines = min(
                len(BOOT_LINES),
                self.boot_tick * len(BOOT_LINES) // 56 + 1,
            )
            painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
            for index, line in enumerate(BOOT_LINES[:visible_boot_lines]):
                color = TEXT_MAIN if index == visible_boot_lines - 1 else TEXT_DIM
                painter.setPen(color)
                painter.drawText(
                    QRect(120, 250 + index * 30, self.width() - 240, 24),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    line,
                )

            progress_width = min(
                self.width() - 240,
                int((self.width() - 240) * min(self.boot_tick, 55) / 55),
            )
            painter.setPen(GREEN_DIM)
            painter.drawRect(120, self.height() - 110, self.width() - 240, 12)
            painter.fillRect(
                122,
                self.height() - 108,
                max(1, progress_width - 4),
                8,
                GREEN_MAIN if pulse_on else GREEN_MUTED,
            )

        led_y = self.height() - 72
        painter.fillRect(
            self.width() // 2 - 24,
            led_y,
            7,
            7,
            GREEN_BRIGHT if pulse_on else GREEN_DIM,
        )
        painter.fillRect(self.width() // 2 - 9, led_y, 7, 7, GREEN_MAIN)
        painter.fillRect(self.width() // 2 + 6, led_y, 7, 7, GREEN_DIM)


class GalleryWidget(QWidget):
    play_requested = Signal(int)

    def __init__(self, titles, unread_memo_count=0):
        super().__init__()

        self.titles = titles
        self.selected_index = 0
        self.unread_memo_count = max(0, int(unread_memo_count))

        self.animation_direction = 0
        self.animation_step = 0
        self.animating = False

        self.setFocusPolicy(
            Qt.StrongFocus
        )

        # No mouse cursor at all.
        self.setCursor(
            Qt.BlankCursor
        )

        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self._advance_animation
        )

        # Subtle continuous CRT activity. This is intentionally
        # deterministic and low-key rather than random flashing.
        self.flicker_phase = 0
        self.flicker_timer = QTimer(self)
        self.flicker_timer.timeout.connect(
            self._advance_flicker
        )
        self.flicker_timer.start(90)

    # =====================================================
    # INDEXING
    # =====================================================

    def wrapped_index(self, offset):
        return (
            self.selected_index + offset
        ) % len(self.titles)

    # =====================================================
    # NAVIGATION
    # =====================================================

    def move_left(self):
        if (
            self.titles
            and not self.animating
        ):
            self._start_animation(-1)

    def move_right(self):
        if (
            self.titles
            and not self.animating
        ):
            self._start_animation(1)

    def _start_animation(
        self,
        direction,
    ):
        self.animation_direction = direction
        self.animation_step = 0
        self.animating = True

        self.timer.start(
            ANIMATION_STEP_MS
        )

    def _advance_animation(self):
        self.animation_step += 1

        if (
            self.animation_step
            >= ANIMATION_STEPS
        ):
            self.selected_index = (
                self.selected_index
                + self.animation_direction
            ) % len(self.titles)

            self.timer.stop()

            self.animating = False
            self.animation_step = 0
            self.animation_direction = 0

        self.update()

    def _advance_flicker(self):
        self.flicker_phase = (
            self.flicker_phase + 1
        ) % 24

        self.update()

    def set_unread_memo_count(self, count):
        self.unread_memo_count = max(0, int(count))
        self.update()

    # =====================================================
    # TEMP KEYBOARD CONTROLS
    # =====================================================

    def keyPressEvent(
        self,
        event,
    ):
        if event.key() == Qt.Key_Left:
            self.move_left()

        elif event.key() == Qt.Key_Right:
            self.move_right()

        elif event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter,
        ):
            if self.titles:
                self.play_requested.emit(
                    self.selected_index
                )

        elif event.key() == Qt.Key_Escape:
            self.close()

    # =====================================================
    # FONT FITTING
    # =====================================================

    def fitted_title_font(
        self,
        painter,
        title,
        max_width,
    ):
        """
        Shrink long titles until they fit in their slot.
        Short titles stay at the full 34 px size.
        """

        size = MAX_TITLE_FONT_SIZE

        while size >= MIN_TITLE_FONT_SIZE:

            font = QFont(
                "DejaVu Sans Mono",
                size,
                QFont.Bold,
            )

            painter.setFont(font)

            width = (
                painter
                .fontMetrics()
                .horizontalAdvance(title)
            )

            if width <= max_width:
                return font

            size -= 1

        return QFont(
            "DejaVu Sans Mono",
            MIN_TITLE_FONT_SIZE,
            QFont.Bold,
        )

    # =====================================================
    # PAINT
    # =====================================================

    def paintEvent(
        self,
        event,
    ):
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            False,
        )

        painter.setRenderHint(
            QPainter.TextAntialiasing,
            True,
        )

        # =================================================
        # BACKGROUND
        # =================================================

        painter.fillRect(
            self.rect(),
            BG,
        )

        # Very subtle CRT-ish bands.
        for y in range(
            0,
            self.height(),
            16,
        ):
            painter.fillRect(
                0,
                y,
                self.width(),
                5,
                BG_STRIPE,
            )

        # A faint moving scan line gives the screen a little
        # life without making the UI hard to read.
        scan_y = (
            118
            + (self.flicker_phase * 17)
            % max(1, self.height() - 180)
        )

        painter.fillRect(
            42,
            scan_y,
            self.width() - 84,
            1,
            GREEN_DIM,
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
        draw_tracking_glitch(
            painter,
            self.width(),
            self.height(),
            self.flicker_phase,
        )

        # =================================================
        # FRAME
        # =================================================

        pen = QPen(
            GREEN_MUTED
        )

        pen.setWidth(3)

        painter.setPen(pen)

        painter.drawRect(
            26,
            26,
            self.width() - 52,
            self.height() - 52,
        )

        pen = QPen(
            GREEN_DIM
        )

        pen.setWidth(1)

        painter.setPen(pen)

        painter.drawRect(
            36,
            36,
            self.width() - 72,
            self.height() - 72,
        )

        # =================================================
        # HEADER
        # =================================================

        painter.setFont(
            QFont(
                "DejaVu Sans Mono",
                15,
                QFont.Bold,
            )
        )

        painter.setPen(
            GREEN_MAIN
        )

        painter.drawText(
            60,
            82,
            "4AUTUMN.EXE",
        )

        painter.setPen(
            TEXT_DIM
        )

        painter.drawText(
            QRect(
                self.width() - 300,
                55,
                240,
                35,
            ),
            Qt.AlignRight
            | Qt.AlignVCenter,
            "LOCAL // READY",
        )

        painter.setPen(
            GREEN_DIM
        )

        painter.drawLine(
            60,
            105,
            self.width() - 60,
            105,
        )

        # =================================================
        # UNREAD MEMO ALERT
        # =================================================

        if self.unread_memo_count:
            pulse_on = self.flicker_phase % 8 < 5
            alert_rect = QRect(
                82,
                128,
                self.width() - 164,
                64,
            )

            painter.fillRect(
                alert_rect,
                GREEN_BRIGHT if pulse_on else GREEN_MAIN,
            )

            alert_pen = QPen(GREEN_BRIGHT)
            alert_pen.setWidth(4)
            painter.setPen(alert_pen)
            painter.drawRect(alert_rect.adjusted(-5, -5, 5, 5))

            painter.setFont(
                QFont(
                    "DejaVu Sans Mono",
                    23,
                    QFont.Bold,
                )
            )
            painter.setPen(BG)
            label = (
                "!! NEW MEMO — APPS > MEMOS !!"
                if self.unread_memo_count == 1
                else f"!! {self.unread_memo_count} NEW MEMOS — APPS > MEMOS !!"
            )
            painter.drawText(
                alert_rect,
                Qt.AlignCenter,
                label,
            )

        # =================================================
        # NO MEDIA
        # =================================================

        if not self.titles:

            painter.setFont(
                QFont(
                    "DejaVu Sans Mono",
                    30,
                    QFont.Bold,
                )
            )

            painter.setPen(
                GREEN_BRIGHT
            )

            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "NO MEDIA",
            )

            return

        # =================================================
        # GALLERY MOTION
        # =================================================

        offset = 0

        if self.animating:

            fraction = (
                self.animation_step
                / ANIMATION_STEPS
            )

            offset = int(
                -self.animation_direction
                * SPACING
                * fraction
            )

        # =================================================
        # GALLERY ITEMS
        # =================================================

        # =================================================
        # CLIP GALLERY TO INNER FRAME
        # =================================================

        gallery_clip = QRect(
            48,
            125,
            self.width() - 96,
            520,
        )

        painter.save()
        painter.setClipRect(gallery_clip)
        for relative_position in range(
            -2,
            3,
        ):

            index = self.wrapped_index(
                relative_position
            )

            title = self.titles[index]
            is_config_tile = title == CONFIG_TILE_TITLE

            center_x = (
                self.width() // 2
                + relative_position
                * SPACING
                + offset
            )

            slot = QRect(
                center_x
                - SLOT_WIDTH // 2,

                GALLERY_CENTER_Y
                - SLOT_HEIGHT // 2,

                SLOT_WIDTH,
                SLOT_HEIGHT,
            )

            selected = (
                relative_position == 0
                and not self.animating
            )

            # =============================================
            # SELECTED ITEM
            # =============================================

            if selected:

                selection_box = QRect(
                    slot.left() + 8,
                    slot.top() + 9,
                    slot.width() - 16,
                    slot.height() - 18,
                )

                painter.fillRect(
                    selection_box,
                    GREEN_DIM,
                )

                pen = QPen(
                    GREEN_BRIGHT
                )

                pen.setWidth(4)

                painter.setPen(pen)

                painter.drawRect(
                    selection_box
                )

                # little side bars
                painter.fillRect(
                    selection_box.left()
                    - 12,

                    selection_box.top()
                    + 12,

                    6,

                    selection_box.height()
                    - 24,

                    GREEN_BRIGHT,
                )

                painter.fillRect(
                    selection_box.right()
                    + 7,

                    selection_box.top()
                    + 12,

                    6,

                    selection_box.height()
                    - 24,

                    GREEN_BRIGHT,
                )

                painter.setPen(
                    GREEN_BRIGHT
                )

            # =============================================
            # IMMEDIATE NEIGHBORS
            # =============================================

            elif abs(
                relative_position
            ) == 1:

                painter.setPen(
                    GREEN_MAIN if is_config_tile else TEXT_MAIN
                )

            # =============================================
            # FAR ITEMS
            # =============================================

            else:

                painter.setPen(
                    GREEN_MUTED
                )

            # =============================================
            # FIT TITLE
            # =============================================

            # Leave some breathing room inside the slot.
            title_font = (
                self.fitted_title_font(
                    painter,
                    title,
                    SLOT_WIDTH - 50,
                )
            )

            painter.setFont(
                title_font
            )

            if is_config_tile:
                painter.setFont(
                    QFont(
                        "DejaVu Sans Mono",
                        11,
                        QFont.Bold,
                    )
                )
                painter.setPen(
                    GREEN_BRIGHT if selected else GREEN_MUTED
                )
                painter.drawText(
                    slot.adjusted(0, 16, 0, 0),
                    Qt.AlignHCenter | Qt.AlignTop,
                    "SYSTEM",
                )
                painter.setFont(
                    title_font
                )
                painter.setPen(
                    GREEN_BRIGHT if selected else GREEN_MAIN
                )

            # Qt handles both horizontal + vertical
            # centering, so text stays centered perfectly.
            painter.drawText(
                slot.adjusted(0, 26 if is_config_tile else 0, 0, 0),
                Qt.AlignCenter,
                title,
            )

        painter.restore()

        # =================================================
        # SUBTLE CENTER MARKERS
        # =================================================

        painter.setPen(
            GREEN_DIM
        )

        center_x = (
            self.width() // 2
        )

        painter.drawLine(
            center_x,
            265,
            center_x,
            285,
        )

        painter.drawLine(
            center_x,
            495,
            center_x,
            515,
        )

        # =================================================
        # FOOTER
        # =================================================

        painter.setPen(
            GREEN_DIM
        )

        painter.drawLine(
            60,
            self.height() - 125,
            self.width() - 60,
            self.height() - 125,
        )

        painter.setFont(
            QFont(
                "DejaVu Sans Mono",
                14,
                QFont.Bold,
            )
        )

        painter.setPen(
            TEXT_DIM
        )

        painter.drawText(
            QRect(
                60,
                self.height() - 98,
                300,
                50,
            ),
            Qt.AlignLeft
            | Qt.AlignVCenter,
            "ROTATE  < / >",
        )

        selected_title = self.titles[self.selected_index]
        action_label = (
            "PRESS // APPS"
            if selected_title == CONFIG_TILE_TITLE
            else "PRESS // PLAY"
        )

        painter.drawText(
            QRect(
                self.width() - 360,
                self.height() - 98,
                300,
                50,
            ),
            Qt.AlignRight
            | Qt.AlignVCenter,
            action_label,
        )

        # =============================================
        # COUNTER
        # =============================================

        painter.setPen(
            GREEN_MAIN
        )

        counter = (
            f"{self.selected_index + 1:02}"
            f" // "
            f"{len(self.titles):02}"
        )

        painter.drawText(
            QRect(
                self.width() // 2 - 100,
                self.height() - 98,
                200,
                50,
            ),
            Qt.AlignCenter,
            counter,
        )


class ConfigWidget(QWidget):
    back_requested = Signal()
    reboot_requested = Signal()
    volume_changed = Signal(int)
    sfx_changed = Signal(bool)
    wifi_scan_requested = Signal()
    wifi_connect_requested = Signal(str, str)
    wifi_disconnect_requested = Signal()
    memo_read = Signal(object)

    def __init__(self, note, memo, memo_date, memos, volume, sfx_enabled):
        super().__init__()

        self.note = note
        self.memo = memo
        self.memo_date = memo_date
        self.memos = memos or []
        self.read_memo_keys = set()
        self.memo_selected_index = 0
        self.memo_reading = False
        self.volume = volume
        self.sfx_enabled = bool(sfx_enabled)
        self.selected_index = 0
        self.app_index = 0
        self.app_mode = "apps"
        self.showing_info = False
        self.showing_memos = False
        self.editing_volume = False
        self.confirming_reboot = False
        self.showing_wifi = False
        self.wifi_stage = "networks"
        self.wifi_networks = []
        self.wifi_selected_index = 0
        self.wifi_password = ""
        self.wifi_key_row = 0
        self.wifi_key_col = 0
        self.wifi_status = "select to scan networks"
        self.wifi_current = {}
        self.info_scroll = 0
        self.memo_scroll = 0
        self.flicker_phase = 0

        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.BlankCursor)

        self.flicker_timer = QTimer(self)
        self.flicker_timer.timeout.connect(self._advance_flicker)
        self.flicker_timer.start(90)

    def set_note(self, note):
        self.note = note
        self.info_scroll = 0
        self.update()

    def set_memo(self, memo, memo_date=""):
        self.memo = memo
        self.memo_date = memo_date or self.memo_date
        self.memo_scroll = 0
        self.update()

    def set_memos(self, memos):
        self.memos = memos or []
        self.memo_selected_index = min(
            self.memo_selected_index,
            max(0, len(self.memos) - 1),
        )
        self.update()

    def set_read_memo_keys(self, keys):
        self.read_memo_keys = set(keys or [])
        self.update()

    def show_apps_home(self):
        self.app_mode = "apps"
        self.app_index = 0
        self.selected_index = 0
        self.showing_info = False
        self.showing_memos = False
        self.showing_wifi = False
        self.editing_volume = False
        self.confirming_reboot = False
        self.update()

    def set_volume(self, volume):
        self.volume = max(0, min(100, int(volume)))
        self.update()

    def set_sfx_enabled(self, enabled):
        self.sfx_enabled = bool(enabled)
        self.update()

    def set_wifi_status(self, status):
        self.wifi_status = status
        self.update()

    def set_wifi_current(self, current):
        self.wifi_current = current or {}
        self.update()

    def set_wifi_networks(self, networks):
        self.wifi_networks = networks
        self.wifi_selected_index = 0
        self.wifi_stage = "networks"
        self.wifi_status = (
            "select network"
            if networks
            else "no networks found"
        )
        self.update()

    def _wifi_keys(self):
        return self._wifi_key_rows()[self.wifi_key_row]

    def _wifi_key_rows(self):
        return [
            [*list("1234567890"), "NEXT"],
            [*list("abcdefghijklmnopqrstuvwxyz"), "NEXT"],
            [*list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), "NEXT"],
            [*list("!\"#$%&'()*+"), "NEXT"],
            [*list(",-./:;<=>?"), "NEXT"],
            [*list("@[\\]^_`{|}~"), "NEXT"],
            ["SPACE", "DEL", "CANCEL", "CONNECT"],
        ]

    def _clamp_wifi_key_col(self):
        row = self._wifi_key_rows()[self.wifi_key_row]
        self.wifi_key_col = min(self.wifi_key_col, len(row) - 1)

    def _advance_wifi_key_row(self):
        self.wifi_key_row = (
            self.wifi_key_row + 1
        ) % len(self._wifi_key_rows())
        self._clamp_wifi_key_col()

    def _wifi_choice_count(self):
        return len(self.wifi_networks) + 3

    def move_left(self):
        if self.showing_info:
            self.info_scroll = max(0, self.info_scroll - 1)
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_scroll = max(0, self.memo_scroll - 1)
            elif self.memos:
                # Include a BACK item after the memo list so the physical
                # left/right/select controls can leave this page.
                self.memo_selected_index = (
                    self.memo_selected_index - 1
                ) % (len(self.memos) + 1)
                self.memo_scroll = 0
        elif self.showing_wifi:
            if self.wifi_stage == "password":
                self.wifi_key_col = (
                    self.wifi_key_col - 1
                ) % len(self._wifi_keys())
            else:
                self.wifi_selected_index = (
                    self.wifi_selected_index - 1
                ) % self._wifi_choice_count()
        elif self.editing_volume:
            self.set_volume(self.volume - 5)
            self.volume_changed.emit(self.volume)
        elif self.app_mode == "apps":
            self.app_index = (
                self.app_index - 1
            ) % 4
        else:
            self.confirming_reboot = False
            self.selected_index = (
                self.selected_index - 1
            ) % 5
        self.update()

    def move_right(self):
        if self.showing_info:
            self.info_scroll += 1
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_scroll += 1
            elif self.memos:
                # Include a BACK item after the memo list so the physical
                # left/right/select controls can leave this page.
                self.memo_selected_index = (
                    self.memo_selected_index + 1
                ) % (len(self.memos) + 1)
                self.memo_scroll = 0
        elif self.showing_wifi:
            if self.wifi_stage == "password":
                self.wifi_key_col = (
                    self.wifi_key_col + 1
                ) % len(self._wifi_keys())
            else:
                self.wifi_selected_index = (
                    self.wifi_selected_index + 1
                ) % self._wifi_choice_count()
        elif self.editing_volume:
            self.set_volume(self.volume + 5)
            self.volume_changed.emit(self.volume)
        elif self.app_mode == "apps":
            self.app_index = (
                self.app_index + 1
            ) % 4
        else:
            self.confirming_reboot = False
            self.selected_index = (
                self.selected_index + 1
            ) % 5
        self.update()

    def select(self):
        if self.showing_info:
            self.showing_info = False
            self.info_scroll = 0
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_reading = False
                self.memo_scroll = 0
            elif self.memos:
                if self.memo_selected_index == len(self.memos):
                    self.showing_memos = False
                    self.memo_selected_index = 0
                    self.memo_scroll = 0
                else:
                    self.memo_reading = True
                    self.memo_scroll = 0
                    self.memo_read.emit(
                        self.memos[self.memo_selected_index]
                    )
            else:
                self.showing_memos = False
        elif self.showing_wifi:
            self._select_wifi()
        elif self.app_mode == "apps":
            if self.app_index == 0:
                self.app_mode = "settings"
                self.selected_index = 0
            elif self.app_index == 1:
                self.showing_wifi = True
                self.wifi_stage = "networks"
                self.wifi_status = "scanning networks..."
                self.wifi_selected_index = 0
                self.wifi_scan_requested.emit()
            elif self.app_index == 2:
                self.showing_memos = True
                self.memo_reading = False
                self.memo_scroll = 0
            else:
                self.back_requested.emit()
        elif self.selected_index == 0:
            self.showing_info = True
            self.info_scroll = 0
        elif self.selected_index == 1:
            self.editing_volume = not self.editing_volume
        elif self.selected_index == 2:
            self.sfx_enabled = not self.sfx_enabled
            self.sfx_changed.emit(self.sfx_enabled)
        elif self.selected_index == 3:
            if self.confirming_reboot:
                self.reboot_requested.emit()
            else:
                self.confirming_reboot = True
        else:
            self.app_mode = "apps"
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.move_left()
        elif event.key() == Qt.Key_Right:
            self.move_right()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.select()
        elif event.key() == Qt.Key_Escape:
            if self.showing_info:
                self.showing_info = False
                self.info_scroll = 0
                self.update()
            elif self.showing_memos:
                if self.memo_reading:
                    self.memo_reading = False
                    self.memo_scroll = 0
                else:
                    self.showing_memos = False
                self.update()
            elif self.showing_wifi:
                if self.wifi_stage == "password":
                    self.wifi_stage = "networks"
                    self.wifi_password = ""
                else:
                    self.showing_wifi = False
                self.update()
            elif self.editing_volume:
                self.editing_volume = False
                self.update()
            elif self.confirming_reboot:
                self.confirming_reboot = False
                self.update()
            elif self.app_mode == "settings":
                self.app_mode = "apps"
                self.update()
            else:
                self.back_requested.emit()
        elif self.showing_wifi and self.wifi_stage == "password":
            if event.key() == Qt.Key_Backspace:
                self.wifi_password = self.wifi_password[:-1]
                self.update()
            else:
                text = event.text()
                if text and text.isprintable():
                    self.wifi_password += text
                    self.update()

    def _select_wifi(self):
        if self.wifi_stage == "networks":
            if self.wifi_selected_index == len(self.wifi_networks):
                self.wifi_status = "scanning networks..."
                self.wifi_scan_requested.emit()
                return

            if self.wifi_selected_index == len(self.wifi_networks) + 1:
                self.wifi_status = "disconnecting..."
                self.wifi_disconnect_requested.emit()
                return

            if self.wifi_selected_index == len(self.wifi_networks) + 2:
                self.showing_wifi = False
                return

            if not self.wifi_networks:
                return

            network = self.wifi_networks[self.wifi_selected_index]
            if network.get("security"):
                self.wifi_stage = "password"
                self.wifi_password = ""
                self.wifi_key_row = 0
                self.wifi_key_col = 0
                self.wifi_status = "enter password"
            else:
                self.wifi_status = "connecting..."
                self.wifi_connect_requested.emit(network["ssid"], "")
            return

        key = self._wifi_keys()[self.wifi_key_col]
        if key == "DEL":
            self.wifi_password = self.wifi_password[:-1]
        elif key == "CANCEL":
            self.wifi_stage = "networks"
            self.wifi_password = ""
        elif key == "NEXT":
            self._advance_wifi_key_row()
        elif key == "CONNECT":
            network = self.wifi_networks[self.wifi_selected_index]
            self.wifi_status = "connecting..."
            self.wifi_connect_requested.emit(network["ssid"], self.wifi_password)
        elif key == "SPACE":
            self.wifi_password += " "
            self.wifi_key_col = (
                self.wifi_key_col + 1
            ) % len(self._wifi_keys())
        else:
            self.wifi_password += key
            self.wifi_key_col = (
                self.wifi_key_col + 1
            ) % len(self._wifi_keys())

    def _advance_flicker(self):
        self.flicker_phase = (self.flicker_phase + 1) % 32
        self.update()

    def _draw_shell(self, painter):
        painter.fillRect(self.rect(), BG)

        for y in range(0, self.height(), 16):
            painter.fillRect(0, y, self.width(), 5, BG_STRIPE)

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
        draw_tracking_glitch(
            painter,
            self.width(),
            self.height(),
            self.flicker_phase,
        )

        pen = QPen(GREEN_MUTED)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(26, 26, self.width() - 52, self.height() - 52)

        pen = QPen(GREEN_DIM)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(36, 36, self.width() - 72, self.height() - 72)

        painter.setFont(QFont("DejaVu Sans Mono", 17, QFont.Bold))
        painter.setPen(GREEN_MAIN)
        section = "SETTINGS" if self.app_mode == "settings" else "APPS"
        if self.showing_memos:
            section = "MEMOS"
        if self.showing_wifi:
            section = "WIFI"
        painter.drawText(60, 82, f"4AUTUMN.EXE // {section}")

        painter.setPen(TEXT_DIM)
        painter.drawText(
            QRect(self.width() - 330, 55, 270, 35),
            Qt.AlignRight | Qt.AlignVCenter,
            f"LOCAL // {section}",
        )

        painter.setPen(GREEN_DIM)
        painter.drawLine(60, 105, self.width() - 60, 105)
        painter.drawLine(
            60,
            self.height() - 75,
            self.width() - 60,
            self.height() - 75,
        )

    def _draw_option(
        self,
        painter,
        index,
        rect,
        label,
        value,
        selected_index=None,
    ):
        if selected_index is None:
            selected_index = self.selected_index
        selected = index == selected_index
        editing = index == 1 and self.editing_volume

        if selected:
            painter.fillRect(
                rect.left(),
                rect.top() + 6,
                6,
                rect.height() - 12,
                GREEN_BRIGHT,
            )
            painter.setPen(GREEN_BRIGHT)
        else:
            painter.setPen(TEXT_MAIN)

        label_size = max(17, min(24, rect.height() - 17))
        painter.setFont(QFont("DejaVu Sans Mono", label_size, QFont.Bold))
        painter.drawText(
            rect.adjusted(24, 0, -24, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            label,
        )

        value_size = max(12, min(16, rect.height() - 25))
        painter.setFont(QFont("DejaVu Sans Mono", value_size, QFont.Bold))
        value_color = TEXT_DIM
        if selected:
            value_color = GREEN_MAIN
        if editing:
            value_color = GREEN_BRIGHT

        painter.setPen(value_color)
        painter.drawText(
            rect.adjusted(24, 0, -24, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            value,
        )

    def _draw_text_panel(self, painter, title, text, scroll_attr):
        panel = QRect(88, 145, self.width() - 176, self.height() - 265)
        text_rect = panel.adjusted(30, 86, -52, -58)

        painter.fillRect(panel, QColor("#071007"))
        pen = QPen(GREEN_BRIGHT)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(panel)

        painter.setFont(QFont("DejaVu Sans Mono", 24, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        painter.drawText(
            panel.adjusted(30, 24, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            title,
        )

        painter.setFont(QFont("DejaVu Sans Mono", 17, QFont.Bold))
        painter.setPen(TEXT_MAIN)
        metrics = painter.fontMetrics()
        line_height = metrics.lineSpacing()
        lines = text.splitlines() or [""]
        visible_lines = max(1, text_rect.height() // line_height)
        max_scroll = max(0, len(lines) - visible_lines)
        scroll = min(getattr(self, scroll_attr), max_scroll)
        setattr(self, scroll_attr, scroll)
        visible_text = "\n".join(
            lines[scroll : scroll + visible_lines]
        )
        painter.drawText(
            text_rect,
            Qt.AlignLeft | Qt.AlignTop,
            visible_text,
        )

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(TEXT_DIM)
        scroll_text = (
            f"< / > scroll   {scroll + 1:02}"
            f" / {max_scroll + 1:02}   select closes"
        )
        painter.drawText(
            panel.adjusted(30, 0, -30, -24),
            Qt.AlignLeft | Qt.AlignBottom,
            scroll_text,
        )

        if max_scroll > 0:
            track = QRect(panel.right() - 30, text_rect.top(), 4, text_rect.height())
            thumb_height = max(
                24,
                int(track.height() * visible_lines / len(lines)),
            )
            thumb_top = track.top()
            if max_scroll:
                thumb_top += int(
                    (track.height() - thumb_height)
                    * scroll
                    / max_scroll
                )

            painter.fillRect(track, GREEN_DIM)
            painter.fillRect(
                QRect(track.left(), thumb_top, track.width(), thumb_height),
                GREEN_BRIGHT,
            )

    def _draw_info(self, painter):
        self._draw_text_panel(
            painter,
            "MESSAGE.TXT",
            self.note,
            "info_scroll",
        )

    def _draw_memos(self, painter):
        memos = self.memos
        if not memos and self.memo:
            memos = [
                {
                    "date": self.memo_date or "--",
                    "message": self.memo,
                }
            ]

        back_selected = bool(memos) and self.memo_selected_index == len(memos)
        selected_memo = (
            memos[self.memo_selected_index]
            if memos and not back_selected
            else {
                "date": "--",
                "message": (
                    "Press SELECT to return to APPS."
                    if back_selected
                    else "No cloud memo received yet."
                ),
            }
        )
        memo = selected_memo["message"]
        panel = QRect(70, 108, self.width() - 140, self.height() - 205)
        left = QRect(
            panel.left() + 30,
            panel.top() + 68,
            188,
            panel.height() - 118,
        )
        right = QRect(
            left.right() + 28,
            left.top(),
            panel.right() - left.right() - 76,
            left.height(),
        )

        painter.fillRect(panel, QColor("#071007"))
        pen = QPen(GREEN_BRIGHT)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(panel)

        painter.setFont(QFont("DejaVu Sans Mono", 24, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        painter.drawText(
            panel.adjusted(30, 24, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            "MEMOS",
        )

        painter.setPen(GREEN_DIM)
        painter.drawLine(left.right() + 14, left.top(), left.right() + 14, left.bottom())

        painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        metrics = painter.fontMetrics()
        memo_rows = list(memos) + ([{"date": "< BACK", "message": ""}] if memos else [])
        visible_memos = max(1, left.height() // 42)
        start = max(
            0,
            min(
                self.memo_selected_index - 2,
                max(0, len(memo_rows) - visible_memos),
            ),
        )
        for index, item in enumerate(memo_rows[start : start + visible_memos], start=start):
            selected = index == self.memo_selected_index
            y = left.top() + (index - start) * 42
            if selected:
                painter.fillRect(
                    QRect(left.left() - 8, y - 2, left.width(), 34),
                    GREEN_DIM,
                )
            painter.setPen(GREEN_BRIGHT if selected else TEXT_MAIN)
            date = metrics.elidedText(item.get("date", "--"), Qt.ElideRight, left.width() - 8)
            painter.drawText(
                QRect(left.left(), y, left.width(), 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                date,
            )
            painter.setPen(GREEN_MAIN if selected else TEXT_DIM)
            if index == len(memos):
                row_label = "RETURN TO APPS"
            else:
                unread = memo_key(item) not in self.read_memo_keys
                row_label = "!! NEW MEMO !!" if unread else "PRIVATE MEMO"
                if unread:
                    painter.setPen(GREEN_BRIGHT)
            painter.drawText(
                QRect(left.left(), y + 17, left.width(), 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                row_label,
            )

        painter.setFont(QFont("DejaVu Sans Mono", 16, QFont.Bold))
        painter.setPen(TEXT_MAIN)
        metrics = painter.fontMetrics()
        line_height = metrics.lineSpacing()

        # Wrap memo paragraphs to the actual pixel width of the reader.
        # Previously scrolling only worked when the message itself contained
        # newline characters, so a long cloud memo could be clipped into one
        # unscrollable line.
        lines = []
        wrap_width = max(1, right.width() - 16)
        paragraphs = memo.splitlines() or [""]
        for paragraph in paragraphs:
            if not paragraph:
                lines.append("")
                continue

            current = ""
            for word in paragraph.split():
                candidate = word if not current else f"{current} {word}"
                if metrics.horizontalAdvance(candidate) <= wrap_width:
                    current = candidate
                    continue

                if current:
                    lines.append(current)
                    current = ""

                # Handle a single token that is wider than the memo pane.
                remaining = word
                while remaining and metrics.horizontalAdvance(remaining) > wrap_width:
                    cut = 1
                    while (
                        cut < len(remaining)
                        and metrics.horizontalAdvance(remaining[: cut + 1]) <= wrap_width
                    ):
                        cut += 1
                    lines.append(remaining[:cut])
                    remaining = remaining[cut:]
                current = remaining

            if current:
                lines.append(current)

        lines = lines or [""]
        visible_lines = max(1, right.height() // line_height)
        max_scroll = max(0, len(lines) - visible_lines)
        self.memo_scroll = min(self.memo_scroll, max_scroll)
        visible_text = "\n".join(
            lines[self.memo_scroll : self.memo_scroll + visible_lines]
        )
        painter.drawText(
            right.adjusted(0, 0, -16, 0),
            Qt.AlignLeft | Qt.AlignTop,
            visible_text,
        )

        if max_scroll > 0:
            track = QRect(right.right() - 5, right.top(), 4, right.height())
            thumb_height = max(24, int(track.height() * visible_lines / len(lines)))
            thumb_top = track.top() + int(
                (track.height() - thumb_height) * self.memo_scroll / max_scroll
            )
            painter.fillRect(track, GREEN_DIM)
            painter.fillRect(
                QRect(track.left(), thumb_top, track.width(), thumb_height),
                GREEN_BRIGHT,
            )

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(TEXT_DIM)
        if self.memo_reading:
            if max_scroll == 0 or self.memo_scroll >= max_scroll:
                scroll_state = "END OF MEMO"
            else:
                scroll_state = "v MORE"
            mode_text = (
                f"< / > scroll   {self.memo_scroll + 1:02} / {max_scroll + 1:02}"
                f"   {scroll_state}   select list"
            )
        else:
            mode_text = "< / > memo/back   select open"
        painter.drawText(
            panel.adjusted(30, 0, -30, -24),
            Qt.AlignLeft | Qt.AlignBottom,
            mode_text,
        )

    def _draw_wifi(self, painter):
        panel = QRect(70, 120, self.width() - 140, self.height() - 205)
        painter.fillRect(panel, QColor("#071007"))
        pen = QPen(GREEN_BRIGHT)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(panel)

        painter.setFont(QFont("DejaVu Sans Mono", 24, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        painter.drawText(
            panel.adjusted(30, 24, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            "WIFI SETUP",
        )

        painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        painter.setPen(TEXT_DIM)
        current_ssid = self.wifi_current.get("ssid") or "not connected"
        current_ip = self.wifi_current.get("ip") or "no ip"
        current_device = self.wifi_current.get("device") or "wifi"
        current_line = f"{current_device}: {current_ssid} // {current_ip}"
        metrics = painter.fontMetrics()
        current_line = metrics.elidedText(
            current_line,
            Qt.ElideRight,
            panel.width() - 60,
        )
        painter.drawText(
            panel.adjusted(30, 60, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            current_line,
        )

        painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        painter.setPen(TEXT_DIM)
        status_line = painter.fontMetrics().elidedText(
            self.wifi_status,
            Qt.ElideRight,
            panel.width() - 60,
        )
        painter.drawText(
            panel.adjusted(30, 78, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            status_line,
        )

        body = panel.adjusted(24, 102, -24, -42)

        if self.wifi_stage == "password" and self.wifi_networks:
            network = self.wifi_networks[self.wifi_selected_index]
            masked = "*" * len(self.wifi_password)
            painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
            painter.setPen(TEXT_MAIN)
            metrics = painter.fontMetrics()
            ssid = metrics.elidedText(
                network["ssid"],
                Qt.ElideRight,
                body.width() - 70,
            )
            painter.drawText(
                body,
                Qt.AlignLeft | Qt.AlignTop,
                f"SSID: {ssid}\nPASS: {masked}",
            )

            key_top = body.top() + 48
            key_h = 18
            key_gap = 3
            painter.setFont(QFont("DejaVu Sans Mono", 8, QFont.Bold))
            for row_index, row in enumerate(self._wifi_key_rows()):
                active_row = row_index == self.wifi_key_row
                row_y = key_top + row_index * (key_h + key_gap)
                row_width = 0
                widths = []
                for key in row:
                    width = 50 if key == "NEXT" else (68 if len(key) > 1 else 19)
                    widths.append(width)
                    row_width += width + key_gap
                row_width -= key_gap
                row_x = body.left() + max(0, (body.width() - row_width) // 2)

                for col_index, (key, key_w) in enumerate(zip(row, widths)):
                    selected = (
                        active_row
                        and col_index == self.wifi_key_col
                    )
                    rect = QRect(row_x, row_y, key_w, key_h)
                    painter.fillRect(
                        rect,
                        GREEN_DIM if selected else QColor("#071007"),
                    )
                    painter.setPen(
                        GREEN_BRIGHT
                        if selected
                        else (GREEN_MAIN if active_row else GREEN_MUTED)
                    )
                    painter.drawRect(rect)
                    painter.setPen(
                        GREEN_BRIGHT
                        if selected
                        else (TEXT_MAIN if active_row else TEXT_DIM)
                    )
                    painter.drawText(
                        rect,
                        Qt.AlignCenter,
                        key,
                    )
                    row_x += key_w + key_gap
        else:
            painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
            choices = [
                *self.wifi_networks,
                {"ssid": "RESCAN", "security": "", "signal": ""},
                {"ssid": "DISCONNECT", "security": "", "signal": ""},
                {"ssid": "BACK", "security": "", "signal": ""},
            ]
            visible_count = 6
            start = max(
                0,
                min(
                    self.wifi_selected_index - 3,
                    max(0, len(choices) - visible_count),
                ),
            )
            visible = choices[start : start + visible_count]
            metrics = painter.fontMetrics()
            for index, network in enumerate(visible, start=start):
                selected = index == self.wifi_selected_index
                y = body.top() + (index - start) * 27
                painter.setPen(GREEN_BRIGHT if selected else TEXT_MAIN)
                prefix = ">" if selected else " "
                is_action = index >= len(self.wifi_networks)
                ssid_width = body.width() - 112
                ssid = metrics.elidedText(
                    network["ssid"],
                    Qt.ElideRight,
                    ssid_width,
                )
                painter.drawText(
                    QRect(body.left(), y, ssid_width, 24),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    f"{prefix} {ssid}",
                )
                if not is_action:
                    signal = network.get("signal", "")
                    security = "LOCK" if network.get("security") else "OPEN"
                    painter.setPen(GREEN_MAIN if selected else TEXT_DIM)
                    painter.drawText(
                        QRect(body.right() - 135, y, 135, 30),
                        Qt.AlignRight | Qt.AlignVCenter,
                        f"{signal}% {security}",
                    )

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(TEXT_DIM)
        footer = (
            "< / > key   select type   NEXT changes row"
            if self.wifi_stage == "password"
            else "< / > choose   select"
        )
        painter.drawText(
            panel.adjusted(30, 0, -30, -24),
            Qt.AlignLeft | Qt.AlignBottom,
            footer,
        )

    def _draw_apps(self, painter):
        menu_left = 118
        menu_top = 190
        row_height = 64
        detail = QRect(455, 178, self.width() - 565, 345)

        apps = ("SETTINGS", "WIFI", "MEMOS", "BACK")
        for index, label in enumerate(apps):
            self._draw_option(
                painter,
                index,
                QRect(menu_left, menu_top + index * 78, 270, row_height),
                label,
                "",
                selected_index=self.app_index,
            )

        painter.setPen(GREEN_DIM)
        painter.drawLine(410, 178, 410, 508)

        painter.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        if self.app_index == 0:
            detail_title = "SETTINGS"
            detail_text = "volume, sfx, reboot"
        elif self.app_index == 1:
            detail_title = "WIFI"
            detail_text = "connect or disconnect network"
        elif self.app_index == 2:
            detail_title = "MEMOS"
            detail_text = "latest private cloud memo"
        else:
            detail_title = "RETURN"
            detail_text = "select to return to archive"

        painter.drawText(
            detail,
            Qt.AlignLeft | Qt.AlignTop,
            detail_title,
        )

        painter.setFont(QFont("DejaVu Sans Mono", 15, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(
            detail.adjusted(0, 48, 0, 0),
            Qt.AlignLeft | Qt.AlignTop,
            detail_text,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self._draw_shell(painter)

        if self.showing_info:
            self._draw_info(painter)
        elif self.showing_memos:
            self._draw_memos(painter)
        elif self.showing_wifi:
            self._draw_wifi(painter)
        elif self.app_mode == "apps":
            self._draw_apps(painter)
        else:
            menu_left = 118
            menu_top = 142
            footer_rule_y = self.height() - 75
            content_bottom = footer_rule_y - 18
            row_gap = 10
            row_height = max(
                36,
                min(
                    64,
                    (content_bottom - menu_top - (row_gap * 4)) // 5,
                ),
            )
            row_step = row_height + row_gap
            detail_top = menu_top
            detail = QRect(
                455,
                detail_top,
                self.width() - 565,
                max(120, content_bottom - detail_top),
            )

            self._draw_option(
                painter,
                0,
                QRect(menu_left, menu_top, 270, row_height),
                "INFO",
                "",
            )
            self._draw_option(
                painter,
                1,
                QRect(menu_left, menu_top + row_step, 270, row_height),
                "VOLUME",
                "",
            )
            self._draw_option(
                painter,
                2,
                QRect(menu_left, menu_top + (row_step * 2), 270, row_height),
                "SFX",
                "",
            )
            self._draw_option(
                painter,
                3,
                QRect(menu_left, menu_top + (row_step * 3), 270, row_height),
                "REBOOT",
                "",
            )
            self._draw_option(
                painter,
                4,
                QRect(menu_left, menu_top + (row_step * 4), 270, row_height),
                "BACK",
                "",
            )

            painter.setPen(GREEN_DIM)
            painter.drawLine(410, detail_top, 410, content_bottom)

            painter.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
            painter.setPen(GREEN_BRIGHT)
            if self.selected_index == 0:
                detail_title = "MESSAGE.TXT"
            elif self.selected_index == 1:
                detail_title = "OUTPUT LEVEL"
            elif self.selected_index == 2:
                detail_title = "SFX AUDIO"
            elif self.selected_index == 3:
                detail_title = "SYSTEM REBOOT"
            else:
                detail_title = "RETURN"

            painter.drawText(
                detail,
                Qt.AlignLeft | Qt.AlignTop,
                detail_title,
            )

            painter.setFont(QFont("DejaVu Sans Mono", 15, QFont.Bold))
            painter.setPen(TEXT_DIM)
            if self.selected_index == 0:
                detail_text = "select to read the note"
            elif self.selected_index == 1 and self.editing_volume:
                detail_text = "< / > adjust   select saves"
            elif self.selected_index == 1:
                detail_text = f"current volume {self.volume:03}%"
            elif self.selected_index == 2:
                detail_text = (
                    "sound effects enabled"
                    if self.sfx_enabled
                    else "sound effects muted"
                )
            elif self.selected_index == 3 and self.confirming_reboot:
                detail_text = "are you sure you want to reboot?"
            elif self.selected_index == 3:
                detail_text = "select to reboot"
            else:
                detail_text = "select to return to archive"

            painter.drawText(
                detail.adjusted(0, 48, 0, 0),
                Qt.AlignLeft | Qt.AlignTop,
                detail_text,
            )

            if self.selected_index == 1:
                bar = QRect(detail.left(), detail.top() + 125, detail.width(), 18)
                fill_width = int(bar.width() * self.volume / 100)
                painter.setPen(GREEN_DIM)
                painter.drawRect(bar)
                fill_color = (
                    GREEN_BRIGHT
                    if self.editing_volume
                    else GREEN_MAIN
                )
                painter.fillRect(
                    bar.adjusted(
                        2,
                        2,
                        -bar.width() + fill_width,
                        -2,
                    ),
                    fill_color,
                )

            if self.selected_index == 2:
                toggle = QRect(detail.left(), detail.top() + 122, 116, 34)
                painter.setPen(GREEN_DIM)
                painter.drawRect(toggle)
                if self.sfx_enabled:
                    painter.fillRect(
                        toggle.adjusted(58, 4, -4, -4),
                        GREEN_BRIGHT,
                    )
                else:
                    painter.fillRect(
                        toggle.adjusted(4, 4, -58, -4),
                        GREEN_MUTED,
                    )

                painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
                painter.setPen(GREEN_MAIN)
                painter.drawText(
                    toggle.adjusted(134, 0, 0, 0),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    "select toggles",
                )

            if self.selected_index == 3:
                painter.setFont(QFont("DejaVu Sans Mono", 14, QFont.Bold))
                painter.setPen(
                    GREEN_BRIGHT
                    if self.confirming_reboot
                    else GREEN_MUTED
                )
                painter.drawText(
                    detail.adjusted(0, 120, 0, 0),
                    Qt.AlignLeft | Qt.AlignTop,
                    "SELECT TO CONFIRM"
                    if self.confirming_reboot
                    else "WAITING",
                )

        painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(
            QRect(60, self.height() - 98, self.width() - 120, 50),
            Qt.AlignCenter,
            "built with \u2665 by adityan for autumn",
        )


class TransitionWidget(QWidget):
    """
    Full-screen overlay used while mpv loads behind it.

    PLAY:
      - stays visible for at least ~500 ms
      - keeps animating if mpv needs longer
      - main.py hides it only when BOTH the minimum animation time
        has elapsed and mpv has reported file-loaded

    RETURN:
      - briefly covers the last video frame
      - then main.py switches back to the gallery underneath it
    """

    minimum_elapsed = Signal()
    return_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title = ""
        self.mode = "play"
        self.frame = 0
        self.minimum_sent = False

        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setCursor(Qt.BlankCursor)
        self.setFocusPolicy(Qt.NoFocus)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

    def start_play(self, title):
        self.title = title
        self.mode = "play"
        self.frame = 0
        self.minimum_sent = False

        self.show()
        self.raise_()
        self.update()

        # 9 frames * 55 ms ~= 495 ms minimum.
        # If mpv is slower, the animation simply keeps cycling.
        self.timer.start(55)

    def start_return(self, title=""):
        self.title = title
        self.mode = "return"
        self.frame = 0
        self.minimum_sent = False

        self.show()
        self.raise_()
        self.update()

        # Shorter return transition.
        self.timer.start(45)

    def stop_transition(self):
        self.timer.stop()
        self.hide()

    def _advance(self):
        self.frame += 1
        self.update()

        if self.mode == "play":
            if self.frame >= 9 and not self.minimum_sent:
                self.minimum_sent = True
                self.minimum_elapsed.emit()

            # Deliberately keep running after minimum_elapsed.
            # That means this screen remains alive if mpv is
            # still loading in the background.

        else:
            if self.frame >= 7:
                self.timer.stop()
                self.return_finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        painter.fillRect(self.rect(), BG)

        phase = self.frame % 8

        # Subtle scan bands to match the gallery.
        for y in range(0, self.height(), 16):
            painter.fillRect(
                0,
                y,
                self.width(),
                5,
                BG_STRIPE,
            )

        # Quick signal-acquisition flicker, kept deliberately faint.
        draw_signal_acquisition_flicker(
            painter,
            self.width(),
            self.height(),
            self.frame,
            intro_only=True,
        )

        draw_global_flicker(painter, self.width(), self.height(), self.frame)
        draw_tracking_glitch(painter, self.width(), self.height(), self.frame % 32)
        draw_random_screen_flicker(
            painter,
            self.width(),
            self.height(),
            self.frame,
        )

        # Same frame language as the gallery.
        pen = QPen(GREEN_MUTED)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(
            26,
            26,
            self.width() - 52,
            self.height() - 52,
        )

        pen = QPen(GREEN_DIM)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(
            36,
            36,
            self.width() - 72,
            self.height() - 72,
        )

        if self.mode == "play":
            main_text = f"LOADING TAPE // {self.title}"
            sub_text = "TRACKING / SYNC / FIELD LOCK"
        else:
            main_text = "SIGNAL // RESTORED"
            sub_text = "REWIND BUFFER CLEAR"

        main_rect = QRect(
            80,
            self.height() // 2 - 55,
            self.width() - 160,
            46,
        )
        jitter = -1 if phase == 6 and self.frame < 10 else 0
        draw_text_glow(
            painter,
            main_rect.adjusted(jitter, 0, jitter, 0),
            Qt.AlignCenter,
            main_text,
            QFont(
                "DejaVu Sans Mono",
                18,
                QFont.Bold,
            ),
            GREEN_BRIGHT,
            GREEN_DIM,
        )

        painter.setFont(
            QFont(
                "DejaVu Sans Mono",
                11,
                QFont.Bold,
            )
        )
        painter.setPen(TEXT_DIM)

        sub_rect = QRect(
            80,
            self.height() // 2 + 2,
            self.width() - 160,
            30,
        )
        painter.drawText(
            sub_rect,
            Qt.AlignCenter,
            sub_text,
        )

        # Animated signal blocks. They are not a fake percentage;
        # they simply move continuously while the real player loads.
        block_count = 9
        block_width = 20
        gap = 7
        total_width = block_count * block_width + (block_count - 1) * gap
        start_x = (self.width() - total_width) // 2
        block_y = self.height() // 2 + 62

        active = phase % block_count

        for i in range(block_count):
            distance = (i - active) % block_count

            if distance == 0:
                color = GREEN_BRIGHT
            elif distance in (1, block_count - 1):
                color = GREEN_MAIN
            else:
                color = GREEN_DIM

            painter.fillRect(
                start_x + i * (block_width + gap),
                block_y,
                block_width,
                5,
                color,
            )
