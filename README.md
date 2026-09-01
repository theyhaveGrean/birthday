# 4AUTUMN.EXE --- User Guide

A small Raspberry Pi media and memo display designed around three simple
apps:

-   **Gallery** --- browse and play saved videos
-   **Memos** --- receive and read cloud-synced messages
-   **Settings** --- configure Wi-Fi, sound, display behavior, and
    device options

The interface is designed to be operated entirely with the three
physical buttons: **Left**, **Select**, and **Right**.

------------------------------------------------------------------------

## Quick Start

1.  Power on the Raspberry Pi.

2.  The application should launch automatically with the configured X
    session.

3.  If you are starting it manually from the console, run:

    `startx`

4.  The **Home** screen appears with:

    **GALLERY · MEMOS · SETTINGS**

5.  Use **Left** and **Right** to move between items.

6.  Press **Select** to open the highlighted item.

7.  From anywhere in the app, **hold Select for about 0.8 seconds** to
    return directly to Home.

> **Universal shortcut:** Hold **Select** = **Home**

------------------------------------------------------------------------

# Controls

## Left Button

Normally moves the selection left, moves up through a menu, or scrolls
backward depending on the current screen.

## Select Button

A short press selects or activates the highlighted item.

When reading a memo, a short press returns to the **Memos list**.

## Right Button

Normally moves the selection right, moves down through a menu, or
scrolls forward depending on the current screen.

## Hold Select

Holding **Select** for approximately 0.8 seconds returns to **Home from
anywhere**.

This includes Gallery, video playback, Memos, memo reading, Settings,
Wi-Fi setup, Sounds, Display, Info, About, and other nested screens.

------------------------------------------------------------------------

# Home

Home is the top-level screen for the device.

It contains exactly three apps:

1.  **GALLERY**
2.  **MEMOS**
3.  **SETTINGS**

Use Left/Right to highlight an app and Select to open it.

When returning Home, the app remembers the previously selected Home
item.

------------------------------------------------------------------------

# Gallery

Gallery displays the videos stored on the device.

Filenames are intentionally shown with their extensions, including names
such as:

-   `BIRTHDAY.MOV`
-   `VIDEO_01.MP4`

## Browsing

-   **Left / Right** --- move between videos
-   **Select** --- play highlighted video
-   **Hold Select** --- return Home

## During Playback

Video playback prevents the normal inactivity timer from dimming the
display.

Hold **Select** to leave playback and return Home.

------------------------------------------------------------------------

# Memos

Memos are messages fetched from the configured cloud memo service.

The app continues checking for new memos while you use other parts of
the interface.

Unread memos are visually distinguished from messages that have already
been read.

## Memo List

-   **Left / Right** --- move through available memos
-   **Select** --- open highlighted memo
-   **Hold Select** --- return Home

## Reading a Memo

-   **Left / Right** --- scroll through the memo
-   **Select** --- return to the Memos list
-   **Hold Select** --- return directly Home

Opening a memo marks it as read.

------------------------------------------------------------------------

# New Memo Notifications

When a new memo arrives, the app can provide both an audible and visual
notification.

## Memo Chime

When **Memo Chime** is enabled:

1.  A new memo arrives.
2.  The notification chime plays immediately.
3.  If an unread memo remains, the chime repeats every **15 seconds**.
4.  Once there are no unread memos, the repeating chime stops.

Memo Chime is independent of normal interface SFX.

The **Master Volume** controls its output level.

## Wake on Memo

When **Wake on Memo** is enabled, receiving a new memo wakes a dimmed
display back to the configured brightness.

The inactivity countdown then restarts.

If Wake on Memo is disabled, new memos do not change the display's
sleep/dim state.

------------------------------------------------------------------------

# Settings

Settings contains the following top-level menu:

1.  **INFO**
2.  **WIFI**
3.  **SOUNDS**
4.  **DISPLAY**
5.  **ABOUT**
6.  **REBOOT**
7.  **BACK**

------------------------------------------------------------------------

## Info

**INFO** opens the device's original personal `MESSAGE.TXT` / note
screen.

This is separate from the Memos app and from the technical About screen.

Use the normal navigation controls to read and leave the screen.

Hold Select at any time to return Home.

------------------------------------------------------------------------

## Wi-Fi

Wi-Fi configuration is built directly into Settings.

The Wi-Fi interface supports scanning for networks, selecting a network,
entering a password, connecting, and working with saved networks.

### Connecting

1.  Open **Settings → WiFi**.
2.  Scan/select the desired network.
3.  Enter the Wi-Fi password using the on-screen keyboard.
4.  Confirm the connection.

Wi-Fi passwords are **intentionally shown visibly on screen while being
entered**.

This is deliberate behavior for this device.

### Wi-Fi Password Keyboard

Use the physical buttons to move around and select keys on the on-screen
keyboard.

Hold Select at any time to abandon Wi-Fi setup and return Home.

------------------------------------------------------------------------

## Sounds

Open **Settings → Sounds**.

The submenu contains:

1.  **MASTER VOLUME**
2.  **SFX**
3.  **MEMO CHIME**
4.  **BACK**

### Master Volume

Controls the application's overall audio output.

The user-facing range is:

**0--100%**

The output is intentionally boosted internally so that:

**100% setting = 150% internal audio output**

This behavior is deliberate.

### SFX

Turns normal interface sound effects on or off.

This does not disable the Memo Chime setting.

### Memo Chime

Turns the repeating new-memo notification sound on or off.

When enabled, an unread new memo causes a chime every 15 seconds until
no unread memos remain.

------------------------------------------------------------------------

## Display

Open **Settings → Display**.

The submenu contains:

1.  **BRIGHTNESS**
2.  **SLEEP AFTER**
3.  **WAKE ON MEMO**
4.  **BACK**

### Brightness

Sets the desired normal display brightness.

The software-side brightness control and persistence are implemented.

> **Hardware note:** The final display-specific USB dimming backend
> still needs to be connected to the brightness controller. Until that
> backend is implemented, changing the setting may not physically change
> the LCD backlight.

### Sleep After

Controls how long the device waits without user activity before dimming
the display.

The default is:

**5 minutes**

When the inactivity timeout expires, the software requests the display's
minimum brightness.

Any physical button input wakes the display and restores the configured
brightness.

Active video playback prevents the normal inactivity timer from dimming
the screen.

### Wake on Memo

Controls whether a newly received memo wakes the display.

-   **ON** --- new memo restores normal brightness and restarts the
    inactivity timer
-   **OFF** --- memo arrives without changing the display sleep state

------------------------------------------------------------------------

## About

**ABOUT** contains technical device information.

Depending on current state, it can show information such as:

-   connected Wi-Fi network
-   IP address
-   number of videos
-   memo count
-   unread memo count
-   available storage
-   cloud connection/status
-   system uptime

Use this page when checking whether the device is connected and
operating normally.

------------------------------------------------------------------------

## Reboot

**REBOOT** restarts the Raspberry Pi.

The interface requires confirmation before rebooting to reduce
accidental restarts.

------------------------------------------------------------------------

## Back

**BACK** leaves Settings and returns to Home.

Remember that holding Select also returns Home immediately from
anywhere.

------------------------------------------------------------------------

# Display Sleep Behavior

The display inactivity system is designed to dim the screen without
suspending the Raspberry Pi.

This means background functionality continues while the screen is
dimmed, including:

-   cloud memo polling
-   network connectivity
-   unread memo tracking
-   memo notifications

Normal sequence:

1.  No physical input occurs for the configured timeout.
2.  Display brightness is requested at its minimum level.
3.  The Raspberry Pi and application remain running.
4.  A physical button press wakes the display.
5.  Configured brightness is restored.
6.  The inactivity timer starts again.

If Wake on Memo is enabled, a new memo can also perform steps 4--6.

------------------------------------------------------------------------

# Cloud Memos

The application periodically checks its configured memo source for
updates.

A new memo does not require the user to be inside the Memos app.

When a memo is detected:

-   it is added to the local memo archive
-   unread state is tracked
-   the Home/Memos UI can indicate the new message
-   Memo Chime can alert the user
-   Wake on Memo can wake the display

Cloud syncing therefore continues independently of the currently open
app.

------------------------------------------------------------------------

# Starting the App Manually

The Raspberry Pi's X session is configured to launch the application. The
launcher disables X11 screensaver/DPMS blanking so the app's GPIO-aware
Display Sleep / Wake on Memo behavior remains the sole inactivity system.

From the console:

`startx`

Do not normally launch a second copy of the application from another
terminal while the existing instance is running.

------------------------------------------------------------------------

# Basic Troubleshooting

## App is not running

From the Raspberry Pi console, run:

`startx`

If X is already running, check whether an existing application session
is active before starting another one.

## New memo does not appear

Check:

1.  **Settings → About** for network/cloud status.
2.  **Settings → WiFi** to confirm the device is connected.
3.  Wait for the next memo polling cycle.
4.  Confirm the memo endpoint/service is reachable.

## No memo sound

Check:

1.  **Settings → Sounds → Master Volume**
2.  **Settings → Sounds → Memo Chime**
3.  Confirm the memo is actually unread.

Normal SFX and Memo Chime have separate enable/disable settings.

## No interface sounds

Check:

**Settings → Sounds → SFX**

and verify Master Volume is above 0%.

## Screen does not physically dim

The software behavior is implemented, but the final hardware-specific
brightness backend is still a placeholder.

The display's USB dimming protocol/backend must be added before software
brightness commands can physically control the LCD.

## Need to escape a screen

Hold **Select** for approximately 0.8 seconds.

This is the global Home shortcut.

------------------------------------------------------------------------

# Control Cheat Sheet

  Location      Left / Right      Select         Hold Select
  ------------- ----------------- -------------- -------------
  Home          Choose app        Open app       Home
  Gallery       Choose video      Play           Home
  Video         ---               ---            Home
  Memos list    Choose memo       Read memo      Home
  Memo reader   Scroll            Back to list   Home
  Settings      Navigate          Open/change    Home
  Wi-Fi         Navigate          Select         Home
  Sounds        Navigate/change   Select         Home
  Display       Navigate/change   Select         Home
  Info/About    Navigate          Select/back    Home

------------------------------------------------------------------------

# Settings Reference

``` text
SETTINGS
├── INFO
├── WIFI
├── SOUNDS
│   ├── MASTER VOLUME
│   ├── SFX
│   ├── MEMO CHIME
│   └── BACK
├── DISPLAY
│   ├── BRIGHTNESS
│   ├── SLEEP AFTER
│   ├── WAKE ON MEMO
│   └── BACK
├── ABOUT
├── REBOOT
└── BACK
```

------------------------------------------------------------------------

# Design Notes

A few behaviors are intentional:

-   Wi-Fi passwords are displayed visibly.
-   Gallery filenames retain extensions such as `.MOV`.
-   Master Volume's displayed 100% maps to 150% internal audio output.
-   Long Select always means Home.
-   Short Select while reading a memo means Back to Memos.
-   Display sleep dims the display rather than suspending the Raspberry
    Pi.
-   Background memo synchronization continues while using other apps.

------------------------------------------------------------------------

## Hardware Brightness Backend

The display controller already provides the software abstraction for
brightness, sleep, wake, and restoration of the configured brightness.

The final hardware implementation should be added to the display
brightness backend once the correct USB dimming command/protocol for the
installed LCD is confirmed.

The rest of the UI should not need to be redesigned when that backend is
added.


## Preparing Videos

Place source videos in `videos_raw/`, then run `python3 normalize_videos.py`.
Normalized H.264/AAC MP4 files are written to `normalized_videos/`. The Gallery
continues to display filename extensions such as `.MOV` for media placed there.
