from gpiozero import Button
from PySide6.QtCore import QObject, Signal


class InputController(QObject):
    left_pressed = Signal()
    select_pressed = Signal()
    select_held = Signal()
    right_pressed = Signal()

    def __init__(self):
        super().__init__()

        self.left_button = Button(
            27,
            pull_up=True,
            bounce_time=0.05,
        )

        self.select_button = Button(
            17,
            pull_up=True,
            bounce_time=0.05,
            hold_time=0.8,
            hold_repeat=False,
        )
        self._select_was_held = False

        self.right_button = Button(
            22,
            pull_up=True,
            bounce_time=0.05,
        )

        self.left_button.when_pressed = self._left_pressed
        self.select_button.when_pressed = self._select_press_started
        self.select_button.when_held = self._select_held
        self.select_button.when_released = self._select_released
        self.right_button.when_pressed = self._right_pressed

    def _left_pressed(self):
        self.left_pressed.emit()

    def _select_press_started(self):
        self._select_was_held = False

    def _select_held(self):
        self._select_was_held = True
        self.select_held.emit()

    def _select_released(self):
        if not self._select_was_held:
            self.select_pressed.emit()
        self._select_was_held = False

    def _right_pressed(self):
        self.right_pressed.emit()

    def close(self):
        self.left_button.close()
        self.select_button.close()
        self.right_button.close()