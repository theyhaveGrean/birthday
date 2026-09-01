"""Display brightness abstraction.

The current backend is intentionally a no-op placeholder. Replace the body of
``DisplayController._write_brightness`` once the LCD's USB-dimming protocol is
known. Keeping hardware access here means the rest of the application and its
settings UI do not need to change later.
"""

from .storage import clamp_int


class DisplayController:
    MIN_BRIGHTNESS = 1
    MAX_BRIGHTNESS = 100

    def __init__(self, brightness=80):
        self._brightness = clamp_int(brightness, self.MIN_BRIGHTNESS, self.MAX_BRIGHTNESS)
        self._sleeping = False
        self.apply_brightness(self._brightness)

    @property
    def brightness(self):
        return self._brightness

    @property
    def sleeping(self):
        return self._sleeping

    def set_brightness(self, brightness):
        self._brightness = clamp_int(
            brightness, self.MIN_BRIGHTNESS, self.MAX_BRIGHTNESS
        )
        if not self._sleeping:
            self.apply_brightness(self._brightness)

    def sleep(self):
        self._sleeping = True
        self.apply_brightness(self.MIN_BRIGHTNESS)

    def wake(self):
        was_sleeping = self._sleeping
        self._sleeping = False
        self.apply_brightness(self._brightness)
        return was_sleeping

    def apply_brightness(self, brightness):
        value = clamp_int(brightness, self.MIN_BRIGHTNESS, self.MAX_BRIGHTNESS)
        self._write_brightness(value)

    def _write_brightness(self, brightness):
        # TODO: Replace this no-op with the LCD's USB dimming backend.
        # ``brightness`` is normalized to the inclusive range 1..100.
        return None
