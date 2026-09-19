from types import SimpleNamespace

import pytest

from video_archive.display import DisplayController


@pytest.mark.parametrize("awake_brightness", [0, 50])
@pytest.mark.parametrize("sleep_brightness", [0, 5, 100])
def test_sleep_led_uses_its_percentage_and_wake_restores_awake_level(
    monkeypatch, awake_brightness, sleep_brightness
):
    # Exercise the controller without accessing GPIO or the USB display.
    monkeypatch.setattr(DisplayController, "_write_brightness", lambda *args: True)
    led = SimpleNamespace(value=None)
    display = DisplayController(
        led=led,
        led_brightness=awake_brightness,
        sleep_led_brightness=sleep_brightness,
    )
    assert led.value == awake_brightness / 100

    display.sleep()
    assert led.value == sleep_brightness / 100

    display.set_led_brightness(80)
    assert led.value == sleep_brightness / 100

    display.set_sleep_led_brightness(15)
    assert led.value == 0.15

    display.wake()
    assert led.value == 0.8

    display.set_sleep_led_brightness(sleep_brightness)
    assert led.value == 0.8

    display.sleep()
    assert led.value == sleep_brightness / 100
