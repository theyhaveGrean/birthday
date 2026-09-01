from gpiozero import Button
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, Signal, Slot

INPUT_SIGNAL_EVENT = QEvent.Type(QEvent.registerEventType())


class InputSignalEvent(QEvent):
    def __init__(self, method_name):
        super().__init__(INPUT_SIGNAL_EVENT)
        self.method_name = method_name


class InputController(QObject):
    left_pressed = Signal()
    left_released = Signal()
    select_pressed = Signal()
    select_held = Signal()
    right_pressed = Signal()
    right_released = Signal()

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
        self.left_button.when_released = self._left_released
        self.select_button.when_pressed = self._select_press_started
        self.select_button.when_held = self._select_held
        self.select_button.when_released = self._select_released
        self.right_button.when_pressed = self._right_pressed
        self.right_button.when_released = self._right_released

    def _left_pressed(self):
        self._post_signal("_emit_left_pressed")

    def _left_released(self):
        self._post_signal("_emit_left_released")

    def _select_press_started(self):
        self._select_was_held = False

    def _select_held(self):
        self._select_was_held = True
        self._post_signal("_emit_select_held")

    def _select_released(self):
        if not self._select_was_held:
            self._post_signal("_emit_select_pressed")
        self._select_was_held = False

    def _right_pressed(self):
        self._post_signal("_emit_right_pressed")

    def _right_released(self):
        self._post_signal("_emit_right_released")

    def _post_signal(self, method_name):
        QCoreApplication.postEvent(
            self,
            InputSignalEvent(method_name),
            Qt.HighEventPriority.value,
        )

    def event(self, event):
        if event.type() == INPUT_SIGNAL_EVENT:
            getattr(self, event.method_name)()
            return True
        return super().event(event)

    @Slot()
    def _emit_left_pressed(self):
        self.left_pressed.emit()

    @Slot()
    def _emit_left_released(self):
        self.left_released.emit()

    @Slot()
    def _emit_select_pressed(self):
        self.select_pressed.emit()

    @Slot()
    def _emit_select_held(self):
        self.select_held.emit()

    @Slot()
    def _emit_right_pressed(self):
        self.right_pressed.emit()

    @Slot()
    def _emit_right_released(self):
        self.right_released.emit()

    def close(self):
        self.left_button.close()
        self.select_button.close()
        self.right_button.close()
