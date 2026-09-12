from video_archive.display import DisplayController


class RecordingDisplay(DisplayController):
    def __init__(self, brightness=80, led=None):
        self.writes = []
        super().__init__(brightness, led=led)

    def _write_brightness(self, brightness):
        self.writes.append(brightness)
        return True


class RecordingLED:
    def __init__(self):
        self.values = []
        self.closed = False

    @property
    def value(self):
        return self.values[-1]

    @value.setter
    def value(self, value):
        self.values.append(value)

    def close(self):
        self.closed = True


def test_status_led_tracks_display_brightness_and_sleep_state():
    led = RecordingLED()
    display = RecordingDisplay(75, led=led)
    assert led.values[-1] == 0.5

    display.set_brightness(40)
    assert led.values[-1] == 0.5

    display.sleep()
    assert led.values[-1] == 0

    display.wake()
    assert led.values[-1] == 0.5

    display.close()
    assert led.values[-1] == 0
    assert led.closed is True


def test_sleep_brightness_only_applies_to_display():
    led = RecordingLED()
    display = RecordingDisplay(75, led=led, sleep_brightness=20)

    display.sleep()
    assert display.writes[-1] == 20
    assert led.values[-1] == 0

    display.set_sleep_brightness(0)
    assert display.writes[-1] == 0
    assert led.values[-1] == 0


def test_screen_brightness_does_not_change_led_brightness():
    led = RecordingLED()
    display = RecordingDisplay(75, led=led, led_brightness=20)

    assert led.values[-1] == 0.2
    display.set_brightness(40)
    assert led.values[-1] == 0.2


def test_sleep_dims_to_minimum_and_wake_restores_brightness():
    display = RecordingDisplay(75)
    assert display.writes[-1] == 75

    display.sleep()
    assert display.sleeping is True
    assert display.writes[-1] == 0

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


def test_usb_packet_matches_manufacturer_protocol():
    packet = DisplayController._encode_packet(50)

    assert len(packet) == 64
    assert packet[:7] == bytes([0x04, 0xAA, 0x01, 0, 0, 0, 45])
    assert packet[7:] == bytes(57)


def test_usb_packet_brightness_range_and_scaling():
    assert DisplayController._encode_packet(100)[6] == 90
    assert DisplayController._encode_packet(10)[6] == 9
    assert DisplayController._encode_packet(0)[6] == 0
    assert DisplayController._encode_packet(1)[6] == 0


def test_device_path_override_writes_packet(monkeypatch, tmp_path):
    hidraw = tmp_path / "hidraw-test"
    hidraw.write_bytes(b"")
    monkeypatch.setenv(DisplayController.DEVICE_PATH_ENV, str(hidraw))

    display = DisplayController(50)

    assert display.device_path == str(hidraw)
    assert hidraw.read_bytes() == DisplayController._encode_packet(50)


def test_vid_pid_matcher():
    assert DisplayController._matches_mpi5001(
        "DRIVER=hid-generic\nHID_ID=0003:00000484:00005750\nHID_NAME=QDtech MPI5001\n"
    )
    assert not DisplayController._matches_mpi5001(
        "HID_ID=0003:0000248A:00008327\n"
    )
