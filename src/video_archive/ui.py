from collections import deque
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
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

# Red is reserved for attention/destructive/error states so the UI stays
# predominantly monochrome green.
RED_BRIGHT = QColor("#FF5A5F")
RED_MAIN = QColor("#D94248")
RED_DIM = QColor("#5C1F22")
RED_BG = QColor("#16090A")

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

HOME_APPS = ("GALLERY", "MEMOS", "SETTINGS")
SETTINGS_MENU = ("INFO", "WIFI", "SOUNDS", "DISPLAY", "ABOUT", "REBOOT", "BACK")
SOUNDS_MENU = ("MASTER VOLUME", "SFX", "MEMO CHIME", "BACK")
DISPLAY_MENU = ("BRIGHTNESS", "SLEEP AFTER", "WAKE ON MEMO", "BACK")
ADMIN_ACTIONS = ("STATUS", "RESET WIFI", "RESET MEMOS", "BACK")
WIFI_SAVED_ACTIONS = ("CONNECT", "FORGET", "BACK")

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

        self.setFocusPolicy(Qt.NoFocus)
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
                "PRESS ANY BUTTON TO START",
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


class HomeWidget(QWidget):
    app_requested = Signal(str)

    def __init__(self, unread_memo_count=0):
        super().__init__()
        self.selected_index = 0
        self.unread_memo_count = max(0, int(unread_memo_count))
        self.flicker_phase = 0
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.BlankCursor)

        self.flicker_timer = QTimer(self)
        self.flicker_timer.timeout.connect(self._advance_flicker)
        self.flicker_timer.start(90)

    def _advance_flicker(self):
        self.flicker_phase = (self.flicker_phase + 1) % 32
        self.update()

    def set_unread_memo_count(self, count):
        self.unread_memo_count = max(0, int(count))
        self.update()

    def reset_selection(self):
        self.selected_index = 0
        self.update()

    def move_left(self):
        self.selected_index = (self.selected_index - 1) % len(HOME_APPS)
        self.update()

    def move_right(self):
        self.selected_index = (self.selected_index + 1) % len(HOME_APPS)
        self.update()

    def select(self):
        self.app_requested.emit(HOME_APPS[self.selected_index].lower())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.fillRect(self.rect(), BG)
        for y in range(0, self.height(), 16):
            painter.fillRect(0, y, self.width(), 5, BG_STRIPE)
        draw_global_flicker(painter, self.width(), self.height(), self.flicker_phase)

        painter.setPen(QPen(GREEN_MUTED, 3))
        painter.drawRect(26, 26, self.width() - 52, self.height() - 52)
        painter.setPen(QPen(GREEN_DIM, 1))
        painter.drawRect(36, 36, self.width() - 72, self.height() - 72)

        painter.setFont(QFont("DejaVu Sans Mono", 20, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        painter.drawText(QRect(60, 62, self.width()-120, 44), Qt.AlignCenter, "HOME")
        painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(QRect(60, 106, self.width()-120, 28), Qt.AlignCenter, "SELECT AN APP")

        tile_w = 250
        tile_h = 190
        gap = 35
        total = tile_w * 3 + gap * 2
        start_x = (self.width() - total) // 2
        top = 185
        descriptions = ("VIDEO ARCHIVE", "PRIVATE MESSAGES", "DEVICE CONTROL")
        for i, label in enumerate(HOME_APPS):
            rect = QRect(start_x + i * (tile_w + gap), top, tile_w, tile_h)
            selected = i == self.selected_index
            painter.setPen(QPen(GREEN_BRIGHT if selected else GREEN_DIM, 3 if selected else 1))
            if selected:
                painter.fillRect(rect.adjusted(4,4,-4,-4), QColor(23,59,25,90))
            painter.drawRect(rect)
            painter.setFont(QFont("DejaVu Sans Mono", 22, QFont.Bold))
            painter.setPen(GREEN_BRIGHT if selected else GREEN_MAIN)
            painter.drawText(rect.adjusted(12, 35, -12, -70), Qt.AlignCenter, label)
            painter.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
            painter.setPen(TEXT_MAIN if selected else TEXT_DIM)
            desc = descriptions[i]
            if label == "MEMOS" and self.unread_memo_count:
                desc += f"  [{self.unread_memo_count} NEW]"
            painter.drawText(rect.adjusted(12, 105, -12, -18), Qt.AlignCenter, desc)

        painter.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(QRect(60, self.height()-96, self.width()-120, 30), Qt.AlignCenter, "LEFT/RIGHT CHOOSE   SELECT OPEN")
        painter.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
        painter.setPen(GREEN_MUTED)
        painter.drawText(
            QRect(60, self.height()-64, self.width()-120, 20),
            Qt.AlignCenter,
            "built with \u2665 by adityan for autumn",
        )


class GalleryWidget(QWidget):
    play_requested = Signal(int)

    def __init__(self, titles, unread_memo_count=0, cloud_status="DISABLED"):
        super().__init__()

        self.titles = titles
        self.selected_index = 0
        self.unread_memo_count = max(0, int(unread_memo_count))
        self.cloud_status = str(cloud_status or "DISABLED").upper()

        self.animation_direction = 0
        self.animation_step = 0
        self.animating = False
        self.pending_navigation = deque()

        self.setFocusPolicy(
            Qt.NoFocus
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
        self._queue_navigation(-1)

    def move_right(self):
        self._queue_navigation(1)

    def cancel_navigation(self):
        self.timer.stop()
        self.animating = False
        self.animation_step = 0
        self.animation_direction = 0
        self.pending_navigation.clear()
        self.update()

    def _queue_navigation(self, direction):
        if not self.titles:
            return
        direction = -1 if direction < 0 else 1
        if self.animating:
            # Preserve physical presses in order rather than collapsing or
            # dropping them while the current tape-scroll animation finishes.
            self.pending_navigation.append(direction)
            return
        self._start_animation(direction)

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

            if self.pending_navigation:
                self._start_animation(self.pending_navigation.popleft())

        self.update()

    def _advance_flicker(self):
        self.flicker_phase = (
            self.flicker_phase + 1
        ) % 24

        self.update()

    def set_unread_memo_count(self, count):
        self.unread_memo_count = max(0, int(count))
        self.update()

    def set_cloud_status(self, status):
        self.cloud_status = str(status or "DISABLED").upper()
        self.update()

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
                48,
                240,
                26,
            ),
            Qt.AlignRight
            | Qt.AlignVCenter,
            "LOCAL // READY",
        )

        cloud_color = (
            GREEN_MAIN
            if self.cloud_status == "SYNCED"
            else GREEN_BRIGHT
            if self.cloud_status == "CHECKING"
            else RED_MAIN
            if self.cloud_status in ("OFFLINE", "ERROR")
            else TEXT_DIM
        )
        painter.setPen(cloud_color)
        painter.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        painter.drawText(
            QRect(self.width() - 300, 72, 240, 22),
            Qt.AlignRight | Qt.AlignVCenter,
            f"CLOUD // {self.cloud_status}",
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
                RED_BG,
            )

            alert_pen = QPen(RED_BRIGHT if pulse_on else RED_MAIN)
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
            painter.setPen(RED_BRIGHT if pulse_on else RED_MAIN)
            label = (
                "!! NEW MEMO — HOME > MEMOS !!"
                if self.unread_memo_count == 1
                else f"!! {self.unread_memo_count} NEW MEMOS — HOME > MEMOS !!"
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
                    TEXT_MAIN
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
            title_metrics = painter.fontMetrics()
            display_title = title_metrics.elidedText(
                title, Qt.ElideMiddle, max(1, SLOT_WIDTH - 50)
            )

            # Qt handles both horizontal + vertical centering. Extremely long
            # filenames keep their extension visible via middle elision.
            painter.drawText(
                slot,
                Qt.AlignCenter,
                display_title,
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
            "LEFT/RIGHT // BROWSE",
        )

        action_label = "SELECT // PLAY"

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


class TextPanelPage:
    """State + rendering for a scrollable text page."""

    def __init__(self, title, text=""):
        self.title = title
        self.text = text or ""
        self.scroll = 0
        self.max_scroll = 0

    def set_text(self, text):
        self.text = text or ""
        self.scroll = 0
        self.max_scroll = 0

    def move(self, delta):
        self.scroll = max(0, min(self.max_scroll, self.scroll + delta))

    @staticmethod
    def _wrap_lines(text, metrics, width):
        wrapped = []
        for raw_line in (text.splitlines() or [""]):
            if not raw_line:
                wrapped.append("")
                continue
            words = raw_line.split(" ")
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if metrics.horizontalAdvance(candidate) <= width:
                    current = candidate
                    continue
                if current:
                    wrapped.append(current)
                    current = ""
                # Break a single token that is wider than the panel.
                while word and metrics.horizontalAdvance(word) > width:
                    cut = 1
                    while cut < len(word) and metrics.horizontalAdvance(word[: cut + 1]) <= width:
                        cut += 1
                    wrapped.append(word[:cut])
                    word = word[cut:]
                current = word
            wrapped.append(current)
        return wrapped or [""]

    def draw(self, painter, width, height):
        panel = QRect(88, 145, width - 176, height - 265)
        text_rect = panel.adjusted(30, 86, -52, -58)

        painter.fillRect(panel, QColor("#071007"))
        pen = QPen(GREEN_BRIGHT)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(panel)

        painter.setFont(QFont("DejaVu Sans Mono", 24, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)
        painter.drawText(panel.adjusted(30, 24, -30, -24), Qt.AlignLeft | Qt.AlignTop, self.title)

        painter.setFont(QFont("DejaVu Sans Mono", 17, QFont.Bold))
        painter.setPen(TEXT_MAIN)
        metrics = painter.fontMetrics()
        line_height = metrics.lineSpacing()
        lines = self._wrap_lines(self.text, metrics, max(1, text_rect.width()))
        visible_lines = max(1, text_rect.height() // line_height)
        max_scroll = max(0, len(lines) - visible_lines)
        self.max_scroll = max_scroll
        self.scroll = max(0, min(self.scroll, max_scroll))
        scroll = self.scroll
        visible_text = "\n".join(lines[scroll : scroll + visible_lines])
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, visible_text)

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(TEXT_DIM)
        scroll_text = f"LEFT/RIGHT SCROLL   {scroll + 1:02} / {max_scroll + 1:02}   SELECT CLOSES"
        painter.drawText(panel.adjusted(30, 0, -30, -24), Qt.AlignLeft | Qt.AlignBottom, scroll_text)

        if max_scroll > 0:
            track = QRect(panel.right() - 30, text_rect.top(), 4, text_rect.height())
            thumb_height = max(24, int(track.height() * visible_lines / len(lines)))
            thumb_top = track.top() + int((track.height() - thumb_height) * scroll / max_scroll)
            painter.fillRect(track, GREEN_DIM)
            painter.fillRect(QRect(track.left(), thumb_top, track.width(), thumb_height), GREEN_BRIGHT)


class AboutPage(TextPanelPage):
    """System-status page kept separate from the personal INFO note."""

    def __init__(self):
        super().__init__("ABOUT")
        self.data = {}

    def set_data(self, data):
        self.data = dict(data or {})
        d = self.data
        self.text = "\n".join([
            f"WIFI      {d.get('wifi', 'not connected')}",
            f"IP        {d.get('ip', '--')}",
            f"VIDEOS    {d.get('videos', 0)}",
            f"MEMOS     {d.get('memos', 0)} ({d.get('unread', 0)} unread)",
            f"FREE      {d.get('storage_free', '--')}",
            f"CLOUD     {d.get('cloud', 'UNKNOWN')}",
            f"UPTIME    {d.get('uptime', '--')}",
        ])

class SettingsRenderer:
    """Renderer for the Settings/Sounds/Display menus.

    Keeping this out of ConfigWidget makes the top-level controller responsible
    for navigation/state while this class owns the settings presentation.
    """

    def draw(self, painter, widget):
        menu = widget._settings_menu()
        menu_left = 118
        menu_top = 160
        footer_rule_y = widget.height() - 75
        content_bottom = footer_rule_y - 18
        row_gap = 10
        row_height = max(40, min(60, (content_bottom - menu_top - row_gap * (len(menu) - 1)) // len(menu)))
        row_step = row_height + row_gap
        detail_top = menu_top
        detail = QRect(455, detail_top, widget.width() - 565, max(120, content_bottom - detail_top))

        for index, label in enumerate(menu):
            widget._draw_option(painter, index, QRect(menu_left, menu_top + index * row_step, 300, row_height), label, "")

        painter.setPen(GREEN_DIM)
        painter.drawLine(410, detail_top, 410, content_bottom)
        painter.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
        painter.setPen(GREEN_BRIGHT)

        if widget.settings_section == "sounds":
            detail_title = ("OUTPUT LEVEL", "SFX AUDIO", "MEMO NOTIFICATION", "RETURN")[widget.selected_index]
            if widget.selected_index == 0:
                detail_text = "LEFT/RIGHT ADJUST   SELECT DONE" if widget.editing_volume else f"CURRENT VOLUME // {widget.volume:03}%"
            elif widget.selected_index == 1:
                detail_text = "SFX // ENABLED" if widget.sfx_enabled else "SFX // MUTED"
            elif widget.selected_index == 2:
                detail_text = "MEMO CHIME // EVERY 15 SEC" if widget.memo_chime_enabled else "MEMO CHIME // DISABLED"
            else:
                detail_text = "SELECT TO RETURN TO SETTINGS"
        elif widget.settings_section == "display":
            detail_title = ("DISPLAY LEVEL", "DISPLAY SLEEP", "DISPLAY WAKE", "RETURN")[widget.selected_index]
            if widget.selected_index == 0:
                detail_text = "LEFT/RIGHT ADJUST   SELECT DONE" if widget.editing_brightness else f"BRIGHTNESS // {widget.brightness:03}%"
            elif widget.selected_index == 1:
                detail_text = "LEFT/RIGHT ADJUST   SELECT DONE" if widget.editing_sleep_timeout else f"SLEEP AFTER // {widget.sleep_timeout_minutes} MIN"
            elif widget.selected_index == 2:
                detail_text = "WAKE ON MEMO // ENABLED" if widget.wake_on_memo else "WAKE ON MEMO // DISABLED"
            else:
                detail_text = "SELECT TO RETURN TO SETTINGS"
        else:
            detail_title = ("MESSAGE.TXT", "WIFI SETUP", "SOUND SETTINGS", "DISPLAY SETTINGS", "ABOUT", "SYSTEM REBOOT", "RETURN")[widget.selected_index]
            if widget.selected_index == 0:
                detail_text = "SELECT TO READ THE NOTE"
            elif widget.selected_index == 1:
                ssid = widget.wifi_current.get("ssid") or "not connected"
                detail_text = f"NETWORK // {ssid}\nSELECT TO MANAGE WIFI"
            elif widget.selected_index == 2:
                detail_text = "MASTER VOLUME // SFX // MEMO CHIME"
            elif widget.selected_index == 3:
                detail_text = "BRIGHTNESS // SLEEP // WAKE ON MEMO"
            elif widget.selected_index == 4:
                detail_text = "DEVICE // NETWORK // STORAGE // CLOUD"
            elif widget.selected_index == 5 and widget.reboot_status:
                detail_text = widget.reboot_status
            elif widget.selected_index == 5 and widget.confirming_reboot:
                detail_text = "CONFIRM SYSTEM REBOOT?\nSELECT AGAIN TO CONTINUE"
            elif widget.selected_index == 5:
                detail_text = "SELECT TO REBOOT"
            else:
                detail_text = "SELECT TO RETURN HOME"

        painter.drawText(detail, Qt.AlignLeft | Qt.AlignTop, detail_title)
        painter.setFont(QFont("DejaVu Sans Mono", 15, QFont.Bold))
        painter.setPen(TEXT_DIM)
        if widget.settings_section is None and widget.selected_index == 5:
            if widget.reboot_status and not widget.reboot_status.lower().startswith("rebooting"):
                painter.setPen(RED_BRIGHT)
            elif widget.confirming_reboot:
                painter.setPen(RED_MAIN)
        painter.drawText(detail.adjusted(0, 48, 0, 0), Qt.AlignLeft | Qt.AlignTop, detail_text)

        if widget.settings_section == "sounds" and widget.selected_index == 0:
            bar = QRect(detail.left(), detail.top() + 125, detail.width(), 18)
            fill_width = int(bar.width() * widget.volume / 100)
            painter.setPen(GREEN_DIM)
            painter.drawRect(bar)
            if fill_width > 0:
                painter.fillRect(bar.adjusted(2, 2, -bar.width() + fill_width, -2), GREEN_BRIGHT if widget.editing_volume else GREEN_MAIN)
        elif widget.settings_section == "display" and widget.selected_index == 0:
            bar = QRect(detail.left(), detail.top() + 125, detail.width(), 18)
            fill_width = int(bar.width() * widget.brightness / 100)
            painter.setPen(GREEN_DIM)
            painter.drawRect(bar)
            if fill_width > 0:
                painter.fillRect(bar.adjusted(2, 2, -bar.width() + fill_width, -2), GREEN_BRIGHT if widget.editing_brightness else GREEN_MAIN)
        elif widget.settings_section == "sounds" and widget.selected_index in (1, 2):
            widget._draw_settings_toggle(painter, detail, widget.sfx_enabled if widget.selected_index == 1 else widget.memo_chime_enabled)
        elif widget.settings_section == "display" and widget.selected_index == 2:
            widget._draw_settings_toggle(painter, detail, widget.wake_on_memo)

        if widget.settings_section is None and widget.selected_index == 5:
            painter.setFont(QFont("DejaVu Sans Mono", 14, QFont.Bold))
            reboot_failed = bool(widget.reboot_status and not widget.reboot_status.lower().startswith("rebooting"))
            painter.setPen(RED_BRIGHT if reboot_failed else RED_MAIN if widget.confirming_reboot else GREEN_BRIGHT if widget.reboot_status else GREEN_MUTED)
            painter.drawText(
                detail.adjusted(0, 120, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                "REBOOTING" if widget.reboot_status.lower().startswith("rebooting") else "REBOOT FAILED" if widget.reboot_status else "SELECT TO CONFIRM" if widget.confirming_reboot else "WAITING",
            )


class ConfigScreen:
    SETTINGS = "settings"
    INFO = "info"
    ABOUT = "about"
    MEMOS = "memos"
    WIFI = "wifi"
    ADMIN = "admin"


class MemoRenderer:
    """Rendering for the Memo screen."""
    def draw(self, painter, host):
        memos = host.memos
        if not memos and host.memo:
            memos = [
                {
                    "date": host.memo_date or "--",
                    "message": host.memo,
                }
            ]

        selected_memo = (
            memos[host.memo_selected_index]
            if memos
            else {
                "date": "--",
                "message": "",
            }
        )
        memo = selected_memo["message"]
        selected_unread = bool(
            memos and memo_key(selected_memo) not in host.read_memo_keys
        )
        if selected_unread and not host.memo_reading:
            memo = "NEW MEMO // UNREAD\n\nSELECT TO OPEN"
        panel = QRect(70, 108, host.width() - 140, host.height() - 205)
        left = QRect(
            panel.left() + 30,
            panel.top() + 68,
            230,
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

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(
            GREEN_MAIN if host.cloud_status == "SYNCED"
            else GREEN_BRIGHT if host.cloud_status == "CHECKING"
            else TEXT_DIM
        )
        painter.drawText(
            panel.adjusted(30, 24, -30, -24),
            Qt.AlignRight | Qt.AlignTop,
            f"CLOUD // {host.cloud_status}",
        )

        painter.setPen(GREEN_DIM)
        painter.drawLine(left.right() + 14, left.top(), left.right() + 14, left.bottom())

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        metrics = painter.fontMetrics()
        memo_rows = list(memos)
        visible_memos = max(1, left.height() // 42)
        start = max(
            0,
            min(
                host.memo_selected_index - 2,
                max(0, len(memo_rows) - visible_memos),
            ),
        )
        for index, item in enumerate(memo_rows[start : start + visible_memos], start=start):
            selected = index == host.memo_selected_index
            y = left.top() + (index - start) * 42
            unread = memo_key(item) not in host.read_memo_keys
            if selected:
                painter.fillRect(
                    QRect(left.left() - 8, y - 2, left.width(), 34),
                    RED_DIM if unread else GREEN_DIM,
                )
            painter.setPen(
                RED_BRIGHT if selected and unread
                else GREEN_BRIGHT if selected
                else TEXT_MAIN
            )
            date = metrics.elidedText(item.get("date", "--"), Qt.ElideRight, left.width() - 8)
            painter.drawText(
                QRect(left.left(), y, left.width(), 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                date,
            )
            painter.setPen(GREEN_MAIN if selected else TEXT_DIM)
            row_label = "!! NEW MEMO !!" if unread else "PRIVATE MEMO"
            if unread:
                painter.setPen(RED_BRIGHT)
            painter.drawText(
                QRect(left.left(), y + 17, left.width(), 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                row_label,
            )

        painter.setFont(QFont("DejaVu Sans Mono", 16, QFont.Bold))
        painter.setPen(TEXT_MAIN)
        metrics = painter.fontMetrics()
        line_height = metrics.lineSpacing()

        if not memos:
            if host.cloud_status == "OFFLINE":
                memo = "NO MEMOS // CLOUD OFFLINE\n\nRETRYING AUTOMATICALLY"
                if host.cloud_error:
                    detail = metrics.elidedText(
                        host.cloud_error, Qt.ElideRight, max(1, right.width() - 16)
                    )
                    memo += f"\n\n{detail}"
            elif host.cloud_status == "ERROR":
                memo = "NO MEMOS // CLOUD ERROR\n\nRETRYING AUTOMATICALLY"
            elif host.cloud_status == "CHECKING":
                memo = "NO MEMOS YET\n\nCHECKING CLOUD..."
            elif host.cloud_status == "DISABLED":
                memo = "NO MEMOS YET\n\nCLOUD NOT CONFIGURED"
            else:
                memo = "NO MEMOS YET\n\nCLOUD CONNECTED"

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
        host.memo_max_scroll = max_scroll
        host.memo_scroll = min(host.memo_scroll, max_scroll)
        visible_text = "\n".join(
            lines[host.memo_scroll : host.memo_scroll + visible_lines]
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
                (track.height() - thumb_height) * host.memo_scroll / max_scroll
            )
            painter.fillRect(track, GREEN_DIM)
            painter.fillRect(
                QRect(track.left(), thumb_top, track.width(), thumb_height),
                GREEN_BRIGHT,
            )

        painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        painter.setPen(TEXT_DIM)
        if host.memo_reading:
            if max_scroll == 0 or host.memo_scroll >= max_scroll:
                scroll_state = "END OF MEMO"
            else:
                scroll_state = "v MORE"
            mode_text = (
                f"LEFT/RIGHT SCROLL   {host.memo_scroll + 1:02} / {max_scroll + 1:02}"
                f"   {scroll_state}   SELECT BACK TO LIST"
            )
        else:
            mode_text = "LEFT/RIGHT MEMO   SELECT OPEN   HOLD SELECT: HOME"
        painter.drawText(
            panel.adjusted(30, 0, -30, -24),
            Qt.AlignLeft | Qt.AlignBottom,
            mode_text,
        )


class WifiRenderer:
    """Rendering for the Wifi screen."""
    def draw(self, painter, host):
        panel = QRect(70, 120, host.width() - 140, host.height() - 205)
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
        current_ssid = host.wifi_current.get("ssid") or "not connected"
        current_ip = host.wifi_current.get("ip") or "no ip"
        current_device = host.wifi_current.get("device") or "wifi"
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

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        wifi_status_lower = host.wifi_status.lower()
        wifi_status_is_error = any(
            token in wifi_status_lower
            for token in (
                "failed", "error", "denied", "unable", "timeout",
                "not found", "authentication", "permission", "offline",
            )
        )
        painter.setPen(RED_MAIN if wifi_status_is_error else TEXT_DIM)
        status_line = painter.fontMetrics().elidedText(
            host.wifi_status,
            Qt.ElideRight,
            panel.width() - 60,
        )
        painter.drawText(
            panel.adjusted(30, 78, -30, -24),
            Qt.AlignLeft | Qt.AlignTop,
            status_line,
        )

        body = panel.adjusted(24, 102, -24, -42)

        if host.wifi_stage == "saved" and host.wifi_networks:
            network = host.wifi_networks[host.wifi_selected_index]
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
                f"SSID: {ssid}\nSAVED PROFILE",
            )
            actions = WIFI_SAVED_ACTIONS
            y = body.top() + 70
            for index, action in enumerate(actions):
                selected = index == host.wifi_saved_action_index
                rect = QRect(body.left(), y + index * 36, body.width(), 28)
                painter.setPen(GREEN_BRIGHT if selected else TEXT_MAIN)
                prefix = ">" if selected else " "
                painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, f"{prefix} {action}")

        elif host.wifi_stage == "password" and host.wifi_networks:
            network = host.wifi_networks[host.wifi_selected_index]
            painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
            painter.setPen(TEXT_MAIN)
            metrics = painter.fontMetrics()
            ssid = metrics.elidedText(
                network["ssid"],
                Qt.ElideRight,
                body.width() - 70,
            )
            visible_password = metrics.elidedText(
                host.wifi_password,
                Qt.ElideLeft,
                body.width() - 70,
            )
            painter.drawText(
                body,
                Qt.AlignLeft | Qt.AlignTop,
                f"SSID: {ssid}\nPASS: {visible_password}",
            )

            key_top = body.top() + 48
            key_h = 20
            key_gap = 3
            painter.setFont(QFont("DejaVu Sans Mono", 9, QFont.Bold))
            for row_index, row in enumerate(host._wifi_key_rows()):
                active_row = row_index == host.wifi_key_row
                row_y = key_top + row_index * (key_h + key_gap)
                row_width = 0
                widths = []
                for key in row:
                    width = 50 if key in ("PREV", "NEXT") else (68 if len(key) > 1 else 19)
                    widths.append(width)
                    row_width += width + key_gap
                row_width -= key_gap
                row_x = body.left() + max(0, (body.width() - row_width) // 2)

                for col_index, (key, key_w) in enumerate(zip(row, widths)):
                    selected = (
                        active_row
                        and col_index == host.wifi_key_col
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
                *host.wifi_networks,
                {"ssid": "RESCAN", "security": "", "signal": ""},
                {"ssid": "DISCONNECT", "security": "", "signal": ""},
                {"ssid": "BACK", "security": "", "signal": ""},
            ]
            visible_count = 6
            start = max(
                0,
                min(
                    host.wifi_selected_index - 3,
                    max(0, len(choices) - visible_count),
                ),
            )
            visible = choices[start : start + visible_count]
            metrics = painter.fontMetrics()
            for index, network in enumerate(visible, start=start):
                selected = index == host.wifi_selected_index
                y = body.top() + (index - start) * 27
                painter.setPen(GREEN_BRIGHT if selected else TEXT_MAIN)
                prefix = ">" if selected else " "
                is_action = index >= len(host.wifi_networks)
                ssid_width = max(120, body.width() - 215)
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
                    profile = "SAVED " if network.get("saved") else ""
                    painter.setPen(GREEN_MAIN if selected else TEXT_DIM)
                    painter.drawText(
                        QRect(body.right() - 200, y, 200, 30),
                        Qt.AlignRight | Qt.AlignVCenter,
                        f"{signal}% {profile}{security}",
                    )

        painter.setFont(QFont("DejaVu Sans Mono", 12, QFont.Bold))
        painter.setPen(TEXT_DIM)
        if host.wifi_stage == "password":
            footer = "LEFT/RIGHT CHOOSE   SELECT TYPE   HOLD SELECT: HOME"
        elif host.wifi_stage == "saved":
            footer = "LEFT/RIGHT CHOOSE   SELECT"
        else:
            footer = "LEFT/RIGHT CHOOSE   SELECT"
        painter.drawText(
            panel.adjusted(30, 0, -30, -24),
            Qt.AlignLeft | Qt.AlignBottom,
            footer,
        )


class AdminRenderer:
    """Rendering for the Admin screen."""
    def draw(self, painter, host):
        menu_left = 100
        menu_top = 166
        row_height = 58
        row_step = 72
        detail = QRect(450, 158, host.width() - 555, 360)
        actions = ADMIN_ACTIONS

        for index, label in enumerate(actions):
            action_rect = QRect(
                menu_left, menu_top + index * row_step, 300, row_height
            )
            host._draw_option(
                painter,
                index,
                action_rect,
                label,
                "",
                selected_index=host.admin_index,
            )
            # Destructive admin actions get a restrained red treatment only
            # while focused; ordinary navigation remains green.
            if index == host.admin_index and label in ("RESET WIFI", "RESET MEMOS"):
                painter.fillRect(action_rect.adjusted(2, 2, -2, -2), RED_BG)
                pen = QPen(RED_BRIGHT)
                pen.setWidth(3)
                painter.setPen(pen)
                painter.drawRect(action_rect)
                painter.setFont(QFont("DejaVu Sans Mono", 17, QFont.Bold))
                painter.setPen(RED_BRIGHT)
                painter.drawText(
                    action_rect.adjusted(18, 0, -12, 0),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    f"> {label}",
                )

        painter.setPen(GREEN_DIM)
        painter.drawLine(420, 158, 420, 518)
        painter.setFont(QFont("DejaVu Sans Mono", 18, QFont.Bold))
        destructive_admin = host.admin_index in (1, 2)
        painter.setPen(RED_BRIGHT if destructive_admin else GREEN_BRIGHT)

        if host.admin_index == 0:
            title = "SYSTEM STATUS"
            d = host.admin_diagnostics
            raw_lines = [
                f"WIFI    {d.get('wifi', 'unknown')}",
                f"IP      {d.get('ip', '--')}",
                f"VIDEOS  {d.get('videos', 0)}",
                f"MEMOS   {d.get('memos', 0)} ({d.get('unread', 0)} unread)",
                f"FREE    {d.get('storage_free', '--')}",
                f"CLOUD   {d.get('cloud', 'UNKNOWN')}",
            ]
            metrics = painter.fontMetrics()
            detail_text = "\n".join(
                metrics.elidedText(line, Qt.ElideRight, detail.width())
                for line in raw_lines
            )
        elif host.admin_index == 1:
            title = "RESET WIFI"
            detail_text = (
                "deletes every saved Wi-Fi profile\n"
                "and disconnects the wireless device"
            )
        elif host.admin_index == 2:
            title = "RESET MEMOS"
            detail_text = (
                "deletes local memo archive, cache,\n"
                "timestamps, and read state"
            )
        else:
            title = "RETURN"
            detail_text = "return to settings"

        painter.drawText(detail, Qt.AlignLeft | Qt.AlignTop, title)
        painter.setFont(QFont("DejaVu Sans Mono", 14, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(
            detail.adjusted(0, 48, 0, 0),
            Qt.AlignLeft | Qt.AlignTop,
            detail_text,
        )

        if host.admin_status:
            painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
            status_lower = host.admin_status.lower()
            status_is_error = any(
                token in status_lower
                for token in ("failed", "error", "denied", "incomplete")
            )
            painter.setPen(
                RED_BRIGHT
                if host.admin_confirm_action or status_is_error
                else GREEN_MAIN
            )
            painter.drawText(
                detail.adjusted(0, 235, 0, 0),
                Qt.AlignLeft | Qt.AlignTop,
                host.admin_status.upper(),
            )

        painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        painter.setPen(TEXT_DIM)
        painter.drawText(
            QRect(60, host.height() - 130, host.width() - 120, 28),
            Qt.AlignCenter,
            "LEFT/RIGHT CHOOSE   SELECT",
        )


class ConfigWidget(QWidget):
    """Router/controller for the Settings, Memos, Wi-Fi and admin surfaces.

    Screen-specific painting lives in renderer/state objects above; this class
    owns the shared three-button routing and emits application-level actions.
    """
    back_requested = Signal()
    reboot_requested = Signal()
    volume_changed = Signal(int)
    sfx_changed = Signal(bool)
    memo_chime_changed = Signal(bool)
    wake_on_memo_changed = Signal(bool)
    brightness_changed = Signal(int)
    sleep_timeout_changed = Signal(int)
    wifi_scan_requested = Signal()
    wifi_connect_requested = Signal(str, str)
    wifi_connect_saved_requested = Signal(object)
    wifi_disconnect_requested = Signal()
    wifi_forget_requested = Signal(object)
    admin_reset_wifi_requested = Signal()
    admin_reset_memos_requested = Signal()
    memo_read = Signal(object)
    about_opened = Signal()

    def __init__(self, note, memo, memo_date, memos, volume, sfx_enabled, memo_chime_enabled, wake_on_memo, brightness, sleep_timeout_minutes):
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
        self.memo_chime_enabled = bool(memo_chime_enabled)
        self.wake_on_memo = bool(wake_on_memo)
        self.brightness = max(1, min(100, int(brightness)))
        self.sleep_timeout_minutes = max(1, min(60, int(sleep_timeout_minutes)))
        self.screen = ConfigScreen.SETTINGS
        self.selected_index = 0
        self.settings_section = None
        self.editing_volume = False
        self.editing_brightness = False
        self.editing_sleep_timeout = False
        self.confirming_reboot = False
        self.reboot_status = ""
        self.reboot_busy = False
        self.wifi_stage = "networks"
        self.wifi_networks = []
        self.wifi_selected_index = 0
        self.wifi_password = ""
        self.wifi_saved_action_index = 0
        self.wifi_key_row = 0
        self.wifi_key_col = 0
        self.wifi_status = "SELECT TO SCAN NETWORKS"
        self.wifi_current = {}
        self.admin_index = 0
        self.admin_confirm_action = ""
        self.admin_status = ""
        self.admin_busy = False
        self.admin_diagnostics = {}
        self.info_page = TextPanelPage("MESSAGE.TXT", note)
        self.about_page = AboutPage()
        self.settings_renderer = SettingsRenderer()
        self.memo_renderer = MemoRenderer()
        self.wifi_renderer = WifiRenderer()
        self.admin_renderer = AdminRenderer()
        self.cloud_status = "DISABLED"
        self.cloud_error = ""
        self.memo_scroll = 0
        self.memo_max_scroll = 0
        self.flicker_phase = 0

        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.BlankCursor)

        self.flicker_timer = QTimer(self)
        self.flicker_timer.timeout.connect(self._advance_flicker)
        self.flicker_timer.start(90)

    @property
    def showing_info(self):
        return self.screen == ConfigScreen.INFO

    @showing_info.setter
    def showing_info(self, value):
        if value:
            self.screen = ConfigScreen.INFO
        elif self.screen == ConfigScreen.INFO:
            self.screen = ConfigScreen.SETTINGS

    @property
    def showing_about(self):
        return self.screen == ConfigScreen.ABOUT

    @showing_about.setter
    def showing_about(self, value):
        if value:
            self.screen = ConfigScreen.ABOUT
        elif self.screen == ConfigScreen.ABOUT:
            self.screen = ConfigScreen.SETTINGS

    @property
    def showing_memos(self):
        return self.screen == ConfigScreen.MEMOS

    @showing_memos.setter
    def showing_memos(self, value):
        if value:
            self.screen = ConfigScreen.MEMOS
        elif self.screen == ConfigScreen.MEMOS:
            self.screen = ConfigScreen.SETTINGS

    @property
    def showing_wifi(self):
        return self.screen == ConfigScreen.WIFI

    @showing_wifi.setter
    def showing_wifi(self, value):
        if value:
            self.screen = ConfigScreen.WIFI
        elif self.screen == ConfigScreen.WIFI:
            self.screen = ConfigScreen.SETTINGS

    @property
    def showing_admin(self):
        return self.screen == ConfigScreen.ADMIN

    @showing_admin.setter
    def showing_admin(self, value):
        if value:
            self.screen = ConfigScreen.ADMIN
        elif self.screen == ConfigScreen.ADMIN:
            self.screen = ConfigScreen.SETTINGS

    def set_note(self, note):
        self.note = note
        self.info_page.set_text(note)
        self.update()

    def set_memo(self, memo, memo_date=""):
        # Cloud polling updates the current remote memo independently of the
        # reader. Do not reset reader scroll for an unchanged background poll.
        self.memo = memo
        self.memo_date = memo_date or self.memo_date
        self.update()

    def set_memos(self, memos):
        incoming = list(memos or [])
        selected_key = None
        if self.memos and 0 <= self.memo_selected_index < len(self.memos):
            selected_key = memo_key(self.memos[self.memo_selected_index])

        self.memos = incoming
        if not self.memos:
            self.memo_selected_index = 0
            self.memo_reading = False
            self.memo_scroll = 0
            self.memo_max_scroll = 0
            self.update()
            return

        if selected_key is not None:
            for index, item in enumerate(self.memos):
                if memo_key(item) == selected_key:
                    self.memo_selected_index = index
                    break
            else:
                self.memo_selected_index = min(
                    self.memo_selected_index, len(self.memos) - 1
                )
                self.memo_reading = False
                self.memo_scroll = 0
        else:
            self.memo_selected_index = min(
                self.memo_selected_index, len(self.memos) - 1
            )

        self.update()

    def clear_memo_data(self):
        self.memo = ""
        self.memo_date = ""
        self.memos = []
        self.read_memo_keys = set()
        self.memo_selected_index = 0
        self.memo_reading = False
        self.memo_scroll = 0
        self.memo_max_scroll = 0
        self.update()

    def set_read_memo_keys(self, keys):
        self.read_memo_keys = set(keys or [])
        self.update()

    def show_settings_home(self):
        self.screen = ConfigScreen.SETTINGS
        self.selected_index = 0
        self.settings_section = None
        self.editing_volume = False
        self.editing_brightness = False
        self.editing_sleep_timeout = False
        self.confirming_reboot = False
        self.update()

    def show_memos_home(self):
        self.screen = ConfigScreen.MEMOS
        self.settings_section = None
        self.editing_volume = False
        self.editing_brightness = False
        self.editing_sleep_timeout = False
        self.confirming_reboot = False
        self.memo_reading = False
        self.memo_selected_index = min(
            self.memo_selected_index, max(0, len(self.memos) - 1)
        )
        self.memo_scroll = 0
        self.update()

    def can_open_admin(self):
        return (
            self.screen == ConfigScreen.SETTINGS
            and not self.editing_volume
            and not self.editing_brightness
            and not self.editing_sleep_timeout
            and not self.confirming_reboot
        )

    def enter_admin(self, diagnostics=None):
        if not self.can_open_admin():
            return False
        self.showing_admin = True
        self.admin_index = 0
        self.admin_confirm_action = ""
        self.admin_status = ""
        if diagnostics is not None:
            self.admin_diagnostics = dict(diagnostics)
        self.update()
        return True

    def set_admin_diagnostics(self, diagnostics):
        self.admin_diagnostics = dict(diagnostics or {})
        self.update()

    def set_about_data(self, info):
        self.about_page.set_data(info)
        self.update()

    def set_admin_status(self, status):
        self.admin_status = str(status or "").strip()
        self.update()

    def finish_admin_action(self, status):
        self.admin_busy = False
        self.admin_confirm_action = ""
        self.admin_status = str(status or "").strip()
        self.update()

    def exit_admin(self):
        self.showing_admin = False
        self.admin_index = 0
        self.admin_confirm_action = ""
        self.admin_status = ""
        self.update()

    def set_volume(self, volume):
        self.volume = max(0, min(100, int(volume)))
        self.update()

    def set_sfx_enabled(self, enabled):
        self.sfx_enabled = bool(enabled)
        self.update()

    def set_memo_chime_enabled(self, enabled):
        self.memo_chime_enabled = bool(enabled)
        self.update()

    def set_wake_on_memo(self, enabled):
        self.wake_on_memo = bool(enabled)
        self.update()

    def set_brightness(self, brightness):
        self.brightness = max(1, min(100, int(brightness)))
        self.update()

    def set_sleep_timeout(self, minutes):
        self.sleep_timeout_minutes = max(1, min(60, int(minutes)))
        self.update()

    def set_wifi_status(self, status):
        self.wifi_status = status
        self.update()

    def wifi_connection_succeeded(self):
        self.wifi_password = ""
        if self.wifi_stage in {"password", "saved"}:
            self.wifi_stage = "networks"
        self.update()

    def set_reboot_status(self, status):
        self.reboot_status = str(status or "").strip()
        self.reboot_busy = self.reboot_status.lower().startswith("rebooting")
        self.update()

    def set_wifi_current(self, current):
        self.wifi_current = current or {}
        self.update()

    def set_cloud_status(self, status, error=""):
        self.cloud_status = str(status or "DISABLED").upper()
        self.cloud_error = str(error or "").strip()
        self.update()

    def begin_wifi_scan(self):
        # Never leave a previous scan selectable while a fresh scan is active.
        # A late scan result must also never eject the user from password/saved
        # profile screens.
        self.wifi_networks = []
        self.wifi_selected_index = 0
        self.wifi_stage = "networks"
        self.wifi_status = "scanning networks..."
        self.update()

    def set_wifi_networks(self, networks):
        self.wifi_networks = list(networks or [])
        if self.wifi_stage == "networks":
            self.wifi_selected_index = min(
                self.wifi_selected_index,
                max(0, len(self.wifi_networks) + 2),
            )
            self.wifi_status = (
                "SELECT NETWORK"
                if self.wifi_networks
                else "no networks found"
            )
        self.update()

    def _wifi_keys(self):
        return self._wifi_key_rows()[self.wifi_key_row]

    def _wifi_key_rows(self):
        return [
            ["PREV", *list("1234567890"), "NEXT"],
            ["PREV", *list("abcdefghijklmnopqrstuvwxyz"), "NEXT"],
            ["PREV", *list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), "NEXT"],
            ["PREV", *list("!\"#$%&'()*+"), "NEXT"],
            ["PREV", *list(",-./:;<=>?"), "NEXT"],
            ["PREV", *list("@[\\]^_`{|}~"), "NEXT"],
            ["PREV", "SPACE", "DEL", "CANCEL", "CONNECT"],
        ]

    def _clamp_wifi_key_col(self):
        row = self._wifi_key_rows()[self.wifi_key_row]
        self.wifi_key_col = min(self.wifi_key_col, len(row) - 1)


    def _advance_wifi_key_row(self):
        self.wifi_key_row = (
            self.wifi_key_row + 1
        ) % len(self._wifi_key_rows())
        self.wifi_key_col = len(self._wifi_keys()) - 1

    def _previous_wifi_key_row(self):
        self.wifi_key_row = (
            self.wifi_key_row - 1
        ) % len(self._wifi_key_rows())
        self.wifi_key_col = 0

    def _wifi_choice_count(self):
        return len(self.wifi_networks) + 3

    def _settings_menu(self):
        if self.settings_section == "sounds":
            return SOUNDS_MENU
        if self.settings_section == "display":
            return DISPLAY_MENU
        return SETTINGS_MENU

    def move_left(self):
        if self.showing_admin:
            self.admin_index = (self.admin_index - 1) % len(ADMIN_ACTIONS)
            self.admin_confirm_action = ""
            self.admin_status = ""
        elif self.showing_info:
            self.info_page.move(-1)
        elif self.showing_about:
            self.about_page.move(-1)
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_scroll = max(0, self.memo_scroll - 1)
            elif self.memos:
                self.memo_selected_index = (
                    self.memo_selected_index - 1
                ) % len(self.memos)
                self.memo_scroll = 0
        elif self.showing_wifi:
            if self.wifi_stage == "password":
                self.wifi_key_col = (
                    self.wifi_key_col - 1
                ) % len(self._wifi_keys())
            elif self.wifi_stage == "saved":
                self.wifi_saved_action_index = (
                    self.wifi_saved_action_index - 1
                ) % len(WIFI_SAVED_ACTIONS)
            else:
                self.wifi_selected_index = (
                    self.wifi_selected_index - 1
                ) % self._wifi_choice_count()
        elif self.editing_volume:
            self.set_volume(self.volume - 5)
            self.volume_changed.emit(self.volume)
        elif self.editing_brightness:
            self.set_brightness(self.brightness - 5)
            self.brightness_changed.emit(self.brightness)
        elif self.editing_sleep_timeout:
            self.set_sleep_timeout(self.sleep_timeout_minutes - 1)
            self.sleep_timeout_changed.emit(self.sleep_timeout_minutes)
        else:
            self.confirming_reboot = False
            self.selected_index = (
                self.selected_index - 1
            ) % len(self._settings_menu())
        self.update()

    def move_right(self):
        if self.showing_admin:
            self.admin_index = (self.admin_index + 1) % len(ADMIN_ACTIONS)
            self.admin_confirm_action = ""
            self.admin_status = ""
        elif self.showing_info:
            self.info_page.move(1)
        elif self.showing_about:
            self.about_page.move(1)
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_scroll = min(
                    self.memo_scroll + 1, self.memo_max_scroll
                )
            elif self.memos:
                self.memo_selected_index = (
                    self.memo_selected_index + 1
                ) % len(self.memos)
                self.memo_scroll = 0
        elif self.showing_wifi:
            if self.wifi_stage == "password":
                self.wifi_key_col = (
                    self.wifi_key_col + 1
                ) % len(self._wifi_keys())
            elif self.wifi_stage == "saved":
                self.wifi_saved_action_index = (
                    self.wifi_saved_action_index + 1
                ) % len(WIFI_SAVED_ACTIONS)
            else:
                self.wifi_selected_index = (
                    self.wifi_selected_index + 1
                ) % self._wifi_choice_count()
        elif self.editing_volume:
            self.set_volume(self.volume + 5)
            self.volume_changed.emit(self.volume)
        elif self.editing_brightness:
            self.set_brightness(self.brightness + 5)
            self.brightness_changed.emit(self.brightness)
        elif self.editing_sleep_timeout:
            self.set_sleep_timeout(self.sleep_timeout_minutes + 1)
            self.sleep_timeout_changed.emit(self.sleep_timeout_minutes)
        else:
            self.confirming_reboot = False
            self.selected_index = (
                self.selected_index + 1
            ) % len(self._settings_menu())
        self.update()

    def select(self):
        if self.showing_admin:
            action = ADMIN_ACTIONS[self.admin_index]
            if self.admin_busy:
                return
            if action == "BACK":
                self.exit_admin()
                return
            if action == "STATUS":
                self.admin_confirm_action = ""
                self.admin_status = ""
                self.update()
                return
            if self.admin_confirm_action != action:
                self.admin_confirm_action = action
                self.admin_status = "SELECT AGAIN TO CONFIRM"
                self.update()
                return
            self.admin_confirm_action = ""
            self.admin_busy = True
            if action == "RESET WIFI":
                self.admin_status = "resetting wifi..."
                self.admin_reset_wifi_requested.emit()
            else:
                self.admin_status = "resetting memos..."
                self.admin_reset_memos_requested.emit()
            self.update()
        elif self.showing_info:
            self.showing_info = False
            self.info_page.scroll = 0
        elif self.showing_about:
            self.showing_about = False
            self.about_page.scroll = 0
        elif self.showing_memos:
            if self.memo_reading:
                self.memo_reading = False
                self.memo_scroll = 0
            elif self.memos:
                self.memo_reading = True
                self.memo_scroll = 0
                self.memo_read.emit(self.memos[self.memo_selected_index])
        elif self.showing_wifi:
            self._select_wifi()
        elif self.settings_section == "sounds":
            if self.selected_index == 0:
                self.editing_volume = not self.editing_volume
            elif self.selected_index == 1:
                self.sfx_enabled = not self.sfx_enabled
                self.sfx_changed.emit(self.sfx_enabled)
            elif self.selected_index == 2:
                self.memo_chime_enabled = not self.memo_chime_enabled
                self.memo_chime_changed.emit(self.memo_chime_enabled)
            else:
                self.settings_section = None
                self.selected_index = 2
        elif self.settings_section == "display":
            if self.selected_index == 0:
                self.editing_brightness = not self.editing_brightness
            elif self.selected_index == 1:
                self.editing_sleep_timeout = not self.editing_sleep_timeout
            elif self.selected_index == 2:
                self.wake_on_memo = not self.wake_on_memo
                self.wake_on_memo_changed.emit(self.wake_on_memo)
            else:
                self.settings_section = None
                self.selected_index = 3
        elif self.selected_index == 0:
            self.showing_info = True
            self.info_page.scroll = 0
        elif self.selected_index == 1:
            self.showing_wifi = True
            self.begin_wifi_scan()
            self.wifi_scan_requested.emit()
        elif self.selected_index == 2:
            self.settings_section = "sounds"
            self.selected_index = 0
        elif self.selected_index == 3:
            self.settings_section = "display"
            self.selected_index = 0
        elif self.selected_index == 4:
            self.showing_about = True
            self.about_page.scroll = 0
            self.about_opened.emit()
        elif self.selected_index == 5:
            if self.reboot_busy:
                return
            if self.confirming_reboot:
                self.reboot_busy = True
                self.reboot_status = "rebooting..."
                self.reboot_requested.emit()
            else:
                self.reboot_status = ""
                self.confirming_reboot = True
        else:
            self.settings_section = None
            self.back_requested.emit()
        self.update()

    def _select_wifi(self):
        if self.wifi_stage == "networks":
            if self.wifi_selected_index == len(self.wifi_networks):
                self.begin_wifi_scan()
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
            if network.get("saved"):
                self.wifi_stage = "saved"
                self.wifi_saved_action_index = 0
                self.wifi_status = "saved profile"
            elif network.get("security"):
                self.wifi_stage = "password"
                self.wifi_password = ""
                self.wifi_key_row = 0
                self.wifi_key_col = 0
                self.wifi_status = "enter password"
            else:
                self.wifi_status = "connecting..."
                self.wifi_connect_requested.emit(network["ssid"], "")
            return

        if self.wifi_stage == "saved":
            network = self.wifi_networks[self.wifi_selected_index]
            action = WIFI_SAVED_ACTIONS[self.wifi_saved_action_index]
            if action == "CONNECT":
                self.wifi_status = "connecting..."
                self.wifi_connect_saved_requested.emit(
                    list(network.get("profile_uuids", []))
                )
            elif action == "FORGET":
                self.wifi_status = "forgetting profile..."
                self.wifi_forget_requested.emit(
                    list(network.get("profile_uuids", []))
                )
            else:
                self.wifi_stage = "networks"
            return

        key = self._wifi_keys()[self.wifi_key_col]
        if key == "DEL":
            self.wifi_password = self.wifi_password[:-1]
        elif key == "CANCEL":
            self.wifi_stage = "networks"
            self.wifi_password = ""
        elif key == "PREV":
            self._previous_wifi_key_row()
        elif key == "NEXT":
            self._advance_wifi_key_row()
        elif key == "CONNECT":
            network = self.wifi_networks[self.wifi_selected_index]
            self.wifi_status = "connecting..."
            self.wifi_connect_requested.emit(network["ssid"], self.wifi_password)
        elif key == "SPACE":
            if len(self.wifi_password) < 128:
                self.wifi_password += " "
            else:
                self.wifi_status = "password limit reached"
        else:
            if len(self.wifi_password) < 128:
                self.wifi_password += key
            else:
                self.wifi_status = "password limit reached"

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
        # Settings intentionally omits the tracking-glitch effect so text
        # remains calm and readable while retaining scanlines/flicker.

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
        section = "SETTINGS"
        if self.showing_admin:
            section = "ADMIN"
        elif self.showing_memos:
            section = "MEMOS"
        elif self.showing_wifi:
            section = "WIFI"
        elif self.showing_info:
            section = "INFO"
        elif self.showing_about:
            section = "ABOUT"
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

    def _draw_info(self, painter):
        self.info_page.draw(painter, self.width(), self.height())

    def _draw_about(self, painter):
        self.about_page.draw(painter, self.width(), self.height())

    def _draw_memos(self, painter):
        self.memo_renderer.draw(painter, self)

    def _draw_wifi(self, painter):
        self.wifi_renderer.draw(painter, self)

    def _draw_admin(self, painter):
        self.admin_renderer.draw(painter, self)

    def _draw_settings_toggle(self, painter, detail, enabled):
        toggle = QRect(detail.left(), detail.top() + 122, 116, 34)
        painter.setPen(GREEN_DIM)
        painter.drawRect(toggle)
        if enabled:
            painter.fillRect(toggle.adjusted(58, 4, -4, -4), GREEN_BRIGHT)
        else:
            painter.fillRect(toggle.adjusted(4, 4, -58, -4), GREEN_MUTED)
        painter.setFont(QFont("DejaVu Sans Mono", 13, QFont.Bold))
        painter.setPen(GREEN_MAIN)
        label_rect = QRect(
            toggle.right() + 18, toggle.top(),
            max(1, detail.right() - toggle.right() - 18), toggle.height(),
        )
        painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, "SELECT TO TOGGLE")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self._draw_shell(painter)

        if self.showing_admin:
            self._draw_admin(painter)
        elif self.showing_info:
            self._draw_info(painter)
        elif self.showing_about:
            self._draw_about(painter)
        elif self.showing_memos:
            self._draw_memos(painter)
        elif self.showing_wifi:
            self._draw_wifi(painter)
        else:
            self.settings_renderer.draw(painter, self)


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
            prefix = "LOADING TAPE // "
            title_font = QFont("DejaVu Sans Mono", 18, QFont.Bold)
            metrics = QFontMetrics(title_font)
            available = max(40, self.width() - 160 - metrics.horizontalAdvance(prefix))
            display_title = metrics.elidedText(self.title, Qt.ElideMiddle, available)
            main_text = prefix + display_title
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
