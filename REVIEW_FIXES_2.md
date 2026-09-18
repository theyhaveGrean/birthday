# Second review — requested fixes

Target display: 1024×600. Numbers refer to Birthday_Fixed_ZIP_Review.md.

| Finding | Change |
|---:|---|
| 1 | Abort stale playback startup after every Qt event-processing boundary, using both mode and generation checks. Cancel/Home no longer overwrites the return transition or starts a cancelled video. |
| 5 | Recover from invalid UTF-8 settings, memo JSON/cache, note and order files. Numeric settings fall back to defaults for infinity/NaN and invalid values. Settings loading leaves original bytes intact. |
| 6 | Recover the cached memo when the archive is missing, malformed or has the wrong top-level type. A valid empty archive stays empty. Recovered content remains available if storage rejects the migration write. |
| 7 | Bound IPC lock acquisition and socket operations to 0.2 seconds each. Failed writes shut down the stream rather than risking partial-command reuse. Idle receive timeouts are harmless. Stop can reach process termination, reap after kill, and wake the reader. |
| 8 | Check radio-enable and rescan results before listing networks; failures are displayed rather than presented as a successful fresh scan. |
| 11 | Widen playback footer to 470 pixels at 1024×600. Both Return and Home controls remain visible on one line. |
| 14 | Apply a 5-second timeout to each aplay invocation. subprocess.run kills and reaps a timed-out child; the sound worker proceeds to the next queued sound. |
| 20 | Use destination-neutral RETURNING text for the return transition. |

## Verification

28 new regression cases pass. Combined new, previous shipping, and review regressions: 87 passed. Full suite: 188 passed, 9 failed, 12 warnings. The nine failures match the prior review: six display tests (stale fixtures/assumptions and absent GPIO hardware), two normalization tests, and one packaging test. Existing socket test doubles were updated for timeout support.

Actual Qt playback and return widgets were rendered and visually checked at 1024×600. Footer width is also checked through the actual paint path. Cancellation is tested at all three startup boundaries for Gallery and Home. IPC tests use saturated real socket pairs, plus idle-timeout coverage. Wi-Fi command results and audio timeout recovery are simulated.

Real Pi GPIO, router association, ALSA output, and native X11/mpv video are not verified here. Other findings from the review remain outstanding, including script permissions, media content, normalization safety, sleep LED duty, Settings/Admin dynamic clipping, and the existing failing tests. This patch is not a claim of zero wrapping/clipping across every screen.
