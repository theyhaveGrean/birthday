# Requested pre-release fixes

Target display: **1024×600**.

| Review issue | Change |
|---:|---|
| 3 | The first button action while sleeping only wakes the display. Pending reboot/admin confirmations are cleared when entering sleep. |
| 4 | Cloud notes merge by stable ID. Missing remote rows and empty responses preserve local history/read state. The existing newest-100 retention policy remains. |
| 6 | Wi-Fi activation uses an explicit 90-second nmcli wait and a 105-second outer timeout. Timeout paths reconcile the actual connected profile/SSID before reporting failure. |
| 7 | Only an accepted scan clears the network list and advances its session. Busy Rescan leaves selection, list, and connection context intact. |
| 8 | Forget completion refreshes profile metadata without rescanning/resetting another password editor. Failures stay visible in the originating session; partial deletion reports incomplete. |
| 9 | Connect completion includes refreshed profile UUIDs, making CONNECT/FORGET available immediately. A failed metadata query asks for a rescan instead of pretending metadata was refreshed. |
| 10 | Scanned SSIDs preserve leading/trailing spaces and nmcli escapes are decoded without changing the actual name. |
| 15 | Gallery rows use fitted/elided single-line names. Detail filenames are bounded to two lines with separate space for playback instructions. |
| 20 | Clock and memo dates share the configured timezone, defaulting to Los Angeles. Original offset-bearing timestamps are retained; legacy naive dates are preserved rather than guessed. |
| 21 | Home and Settings/Sounds/Display have consistent footer hints for selection, editing, confirmation, and holding Select for Home. |

Validation:

- 38 new regression cases pass in `tests/test_shipping_fixes.py`.
- 127 focused and related regression cases pass.
- Real Qt widgets rendered and inspected at 1024×600: Home, Settings,
  volume editing, screensaver editing, reboot confirmation, ordinary/very
  long Gallery filenames, and saved Wi-Fi actions.
- Existing Wi-Fi tests were repaired to use the current constructor so their
  session checks execute. Cloud expectations now include preserved timestamps.
- The full suite retains nine pre-existing failures in display tests/hardware
  isolation, media-tool defaults/assertions, and packaging ignore rules.
  These are separate from the selected fixes.

On-device checks still needed: real Wi-Fi association/reconnect, GPIO press
and hold timing, cold boot, USB brightness, ALSA output, and native mpv/X11
playback. No live network profiles or cloud data were changed during testing.

Other numbered review findings were not included in this requested patch.
