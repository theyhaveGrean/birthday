from pathlib import Path

from video_archive.display import DisplayController


class RecordingDisplay(DisplayController):
    def __init__(self, brightness=80):
        self.writes = []
        super().__init__(brightness)

    def _write_brightness(self, brightness):
        self.writes.append(brightness)
        return True


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


def test_usb_packet_matches_manufacturer_protocol():
    packet = DisplayController._encode_packet(50)

    assert len(packet) == 64
    assert packet[:7] == bytes([0x04, 0xAA, 0x01, 0, 0, 0, 45])
    assert packet[7:] == bytes(57)


def test_usb_packet_brightness_range_and_scaling():
    assert DisplayController._encode_packet(100)[6] == 90
    assert DisplayController._encode_packet(10)[6] == 9
    # The manufacturer utility's safe minimum is 5%.
    assert DisplayController._encode_packet(1)[6] == 4


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
