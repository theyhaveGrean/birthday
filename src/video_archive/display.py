"""USB hardware brightness control for the LCDWiki 5inch HDMI Display-D.

The Display-D exposes its backlight control through the QDtech MPI5001 USB
HID interface (VID 0x0484, PID 0x5750).  The manufacturer's Windows utility
uses HID output report 4 with a 64-byte packet.  Keeping the protocol here
isolates all hardware-specific behavior from the UI.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

from .storage import clamp_int


class DisplayController:
    """Own the configured brightness and write it to the physical backlight."""

    MIN_BRIGHTNESS = 5
    MAX_BRIGHTNESS = 100

    USB_VENDOR_ID = 0x0484
    USB_PRODUCT_ID = 0x5750
    HID_REPORT_ID = 0x04
    HID_PACKET_SIZE = 64
    DEVICE_MAX_BRIGHTNESS = 90

    # Useful for development/tests and as an escape hatch if sysfs layout ever
    # changes.  Normally this is intentionally unset and the device is found by
    # VID/PID, so /dev/hidraw numbering may change safely across boots.
    DEVICE_PATH_ENV = "VIDEO_ARCHIVE_DISPLAY_HID_PATH"

    def __init__(self, brightness=80):
        self._brightness = clamp_int(
            brightness, self.MIN_BRIGHTNESS, self.MAX_BRIGHTNESS
        )
        self._sleeping = False
        self._device_path: Path | None = None
        self._last_error: tuple[str, str] | None = None
        self.apply_brightness(self._brightness)

    @property
    def brightness(self):
        return self._brightness

    @property
    def sleeping(self):
        return self._sleeping

    @property
    def device_path(self):
        """Return the cached hidraw path, if one has been discovered."""
        return str(self._device_path) if self._device_path is not None else None

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
        return self._write_brightness(value)

    @classmethod
    def _encode_packet(cls, brightness):
        """Encode one manufacturer-compatible brightness output report."""
        percent = clamp_int(brightness, cls.MIN_BRIGHTNESS, cls.MAX_BRIGHTNESS)
        device_value = int(percent * cls.DEVICE_MAX_BRIGHTNESS / 100)

        packet = bytearray(cls.HID_PACKET_SIZE)
        packet[:7] = bytes(
            [
                cls.HID_REPORT_ID,
                0xAA,
                0x01,
                0x00,
                0x00,
                0x00,
                device_value,
            ]
        )
        return bytes(packet)

    @classmethod
    def _matches_mpi5001(cls, uevent_text):
        """Return True when a hidraw uevent belongs to VID 0484 / PID 5750."""
        expected = f"0003:{cls.USB_VENDOR_ID:08X}:{cls.USB_PRODUCT_ID:08X}"
        for line in uevent_text.splitlines():
            if line.strip().upper() == f"HID_ID={expected}":
                return True
        return False

    @classmethod
    def _discover_device(cls):
        override = os.environ.get(cls.DEVICE_PATH_ENV)
        if override:
            return Path(override)

        hidraw_root = Path("/sys/class/hidraw")
        try:
            candidates = sorted(hidraw_root.glob("hidraw*"))
        except OSError:
            return None

        for candidate in candidates:
            try:
                uevent_text = (candidate / "device" / "uevent").read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            if cls._matches_mpi5001(uevent_text):
                return Path("/dev") / candidate.name
        return None

    def _report_error_once(self, kind, message):
        signature = (kind, message)
        if signature == self._last_error:
            return
        self._last_error = signature
        print(f"display brightness: {message}", file=sys.stderr, flush=True)

    def _write_brightness(self, brightness):
        """Write physical backlight brightness without making app startup fatal.

        A disconnected display or a missing udev permission should not crash the
        whole UI.  The next brightness change/wake will try discovery again.
        """
        packet = self._encode_packet(brightness)

        for attempt in range(2):
            if self._device_path is None:
                self._device_path = self._discover_device()
            if self._device_path is None:
                self._report_error_once(
                    "missing",
                    "QDtech MPI5001 USB device (0484:5750) was not found",
                )
                return False

            path = self._device_path
            try:
                with path.open("wb", buffering=0) as device:
                    written = device.write(packet)
                if written != len(packet):
                    raise OSError(errno.EIO, f"short HID write ({written}/64 bytes)")
                self._last_error = None
                return True
            except PermissionError:
                self._report_error_once(
                    "permission",
                    f"permission denied for {path}; install the included udev rule",
                )
                return False
            except OSError as error:
                # hidraw numbers can change after unplug/replug.  Drop the cache
                # and rediscover once before giving up.
                self._device_path = None
                if attempt == 0 and error.errno in {
                    errno.ENOENT,
                    errno.ENODEV,
                    errno.EIO,
                }:
                    continue
                self._report_error_once("io", f"USB brightness write failed: {error}")
                return False

        return False
