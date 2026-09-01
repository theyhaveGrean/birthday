from video_archive.display import DisplayController


class RecordingDisplay(DisplayController):
    def __init__(self, brightness=80):
        self.writes = []
        super().__init__(brightness)

    def _write_brightness(self, brightness):
        self.writes.append(brightness)


def test_sleep_dims_to_minimum_and_wake_restores_brightness():
    display = RecordingDisplay(75)
    assert display.writes[-1] == 75

    display.sleep()
    assert display.sleeping is True
    assert display.writes[-1] == display.MIN_BRIGHTNESS

    assert display.wake() is True
    assert display.sleeping is False
    assert display.writes[-1] == 75


def test_brightness_change_while_asleep_is_restored_on_wake():
    display = RecordingDisplay(80)
    display.sleep()
    display.set_brightness(45)
    assert display.writes[-1] == display.MIN_BRIGHTNESS

    display.wake()
    assert display.writes[-1] == 45
