import pytest

pytestmark = pytest.mark.usefixtures("qapp")


class FakeButton:
    def __init__(self, *args, **kwargs):
        self.when_pressed = None
        self.when_released = None
        self.when_held = None
        self.closed = False

    def close(self):
        self.closed = True


def test_gpio_callbacks_queue_qt_signals(monkeypatch, qapp):
    from PySide6.QtCore import QCoreApplication

    import video_archive.input as input_module

    monkeypatch.setattr(input_module, "Button", FakeButton)
    controller = input_module.InputController()
    received = []
    controller.left_pressed.connect(lambda: received.append("left"))
    controller.select_pressed.connect(lambda: received.append("select"))

    controller._left_pressed()
    controller._select_released()

    assert received == []
    QCoreApplication.sendPostedEvents(controller, input_module.INPUT_SIGNAL_EVENT)
    assert received == ["left", "select"]


def test_gpio_callbacks_are_prioritized_over_normal_events(monkeypatch, qapp):
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt

    import video_archive.input as input_module

    class Recorder(QObject):
        EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

        def __init__(self):
            super().__init__()
            self.events = []

        def event(self, event):
            if event.type() == self.EVENT_TYPE:
                self.events.append("normal")
                return True
            return super().event(event)

    monkeypatch.setattr(input_module, "Button", FakeButton)
    recorder = Recorder()
    controller = input_module.InputController()
    controller.left_pressed.connect(lambda: recorder.events.append("input"))

    QCoreApplication.postEvent(
        recorder,
        QEvent(Recorder.EVENT_TYPE),
        Qt.NormalEventPriority.value,
    )
    controller._left_pressed()
    qapp.processEvents()

    assert recorder.events == ["input", "normal"]
