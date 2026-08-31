from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
VIDEO_DIR = APP_DIR / "normalized_videos"
ORDER_FILE = APP_DIR / "order.txt"
SELECTION_FILE = APP_DIR / ".selected_video"
MPV_LOG_FILE = APP_DIR / "mpv.log"
SOUND_DIR = APP_DIR / ".cache" / "sounds"
SETTINGS_FILE = APP_DIR / "settings.json"
NOTE_FILE = APP_DIR / "note.txt"
CLOUD_MESSAGE_FILE = APP_DIR / ".cloud_message.txt"
CLOUD_MEMOS_FILE = APP_DIR / "memos.json"
READ_MEMOS_FILE = APP_DIR / ".read_memos.json"
CLOUD_MESSAGE_TOKEN_FILE = APP_DIR / ".cloud_message_token"

ANIMATION_STEPS = 4
ANIMATION_STEP_MS = 55

DEFAULT_SETTINGS = {
    "volume": 80,
    "sfx_enabled": True,
    "cloud_message_url": "",
}

DEFAULT_NOTE = (
    "Dear Autumn,\n\n"
    "This is placeholder text for now. It is intentionally long so "
    "the message screen can test scrolling.\n\n"
    "Line 01: a small archive boots in the dark.\n"
    "Line 02: the screen hums, the buttons wait.\n"
    "Line 03: every clip is a little saved signal.\n"
    "Line 04: every saved signal points back to you.\n"
    "Line 05: left and right should move through this note.\n"
    "Line 06: select should close it and return to config.\n"
    "Line 07: the scrollbar should move as the text moves.\n"
    "Line 08: this line exists mostly for testing.\n"
    "Line 09: so does this one.\n"
    "Line 10: and this one, honestly.\n"
    "Line 11: replace all of this with the real note later.\n"
    "Line 12: there should still be room for more.\n"
    "Line 13: if this appears, scrolling is working.\n"
    "Line 14: end of placeholder transmission.\n\n"
    "- Adityan"
)
