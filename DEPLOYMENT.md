# Raspberry Pi deployment dependencies

The app is intentionally operated only through the three GPIO buttons. No external keyboard or mouse is required.

Python dependencies are listed in `requirements.txt`.

Required OS packages/services:

- Xorg (`startx` launches the configured X session/app)
- `mpv`
- NetworkManager / `nmcli`
- ALSA utilities / `aplay`

GPIO mapping:

- left / previous: GPIO 27
- select: GPIO 17
- right / next: GPIO 22


## LCD USB brightness permissions

The LCDWiki 5inch HDMI Display-D is controlled through its QDtech MPI5001
USB HID interface (`0484:5750`). Install the repository's udev rule once:

```sh
cd /home/pi/app
sudo ./deployment/install_display_brightness.sh
```

Reboot once after installation so the `pi` user's `plugdev` membership is
active. The rule grants only this display's hidraw device to `plugdev`; do not
run the whole GUI as root. The application discovers the correct `/dev/hidrawN`
by VID/PID on every connection and automatically re-discovers it after a
disconnect/reconnect.

## Recommended crash recovery

For deployment, point the X session at `run_app.sh` instead of invoking
`python3 main.py` directly. The wrapper restarts the app after an unexpected
non-zero exit, waits 2 seconds between attempts, and stops after 5 consecutive short-lived
crashes; a run lasting at least 5 minutes resets the crash streak so a broken install cannot spin forever.

Example `~/.xinitrc`:

```sh
xset s off
xset -dpms
xset s noblank
exec /home/pi/app/run_app.sh
```

The `xset` lines are important because the physical GPIO buttons are not X11
keyboard/mouse events. `run_app.sh` repeats these safeguards when `xset` is
available so Xorg cannot independently blank the panel behind the app's own
sleep/wake system.

The wrapper captures stdout/stderr through `tools/log_runner.py`. `xsession.log`
is capped at 2 MiB while the app is running; when it fills, the previous chunk
is retained as `xsession.log.old`. This keeps logging bounded even during very
long uptimes. Repeated cloud fetch errors are also rate-limited by the app.


## Running the test suite

Install the normal application requirements plus pytest, then run tests with the
Qt offscreen platform. The test configuration sets `QT_QPA_PLATFORM=offscreen`
automatically, so no physical display is required:

```sh
python3 -m pip install -r requirements.txt -r requirements-test.txt
python3 -m pytest -q
```

PySide6 is intentionally a hard requirement for the GUI tests. Missing PySide6
now fails test collection instead of silently skipping the UI/state-machine
coverage.


## Video normalization

`normalize_videos.py` now uses separate folders by default: put source media in
`videos_raw/` and normalized playback files are written to `normalized_videos/`.
This avoids accidentally transcoding a file onto itself.
