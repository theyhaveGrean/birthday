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
    from PySide6.QtTest import QSignalSpy

    import video_archive.input as input_module

    monkeypatch.setattr(input_module, "Button", FakeButton)
    controller = input_module.InputController()
    left_spy = QSignalSpy(controller.left_pressed)
    select_spy = QSignalSpy(controller.select_pressed)

    controller._left_pressed()
    controller._select_released()

    assert left_spy.count() == 0
    assert select_spy.count() == 0
    assert left_spy.wait(100)
    assert select_spy.wait(100)


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
