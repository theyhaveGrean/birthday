# Private Cloud Messages

The app fetches guestbook notes from the Supabase REST API described in
`README_GPT.md` and shows them in `HOME` -> `MEMOS`.

## Supabase Notes Setup

The configured endpoint is:

```text
https://rrwyqfddvijgimcslqkl.supabase.co/rest/v1/notes
```

The app requests:

```text
GET /notes?select=id,name,message,created_at&order=created_at.desc
```

using the publishable Supabase key as both the `apikey` header and bearer
token. No GitHub token or private raw GitHub file is used.

`settings.json` should contain:

```json
{
  "cloud_message_url": "https://rrwyqfddvijgimcslqkl.supabase.co/rest/v1/notes"
}
```

The app fetches once after startup, then every 60 seconds. Each returned note is
saved locally in `/home/pi/app/memos.json`, newest first. The Supabase `id`
becomes the memo id, so unread state stays stable across polls.

Keep messages short. The app displays at most 1200 Unicode characters per memo.
The current newest memo is cached in `.cloud_message.txt`, and its receive date
is stored in `.cloud_message_meta.json`.

## Local history and timestamps

Cloud results are merged into the local archive by memo ID. An empty response,
remote deletion, or a filtered response does not erase previously received
memos or their read state. The existing retention limit remains the newest
100 archived memos. Reset Memos explicitly clears local history; subsequent
cloud polls can download currently published notes again.

Memo timestamps and the screensaver clock share `VIDEO_ARCHIVE_TIMEZONE`,
defaulting to `America/Los_Angeles`. New timestamps retain their original
UTC offset so they can be displayed correctly after a timezone change.
Invalid timezone names fall back to UTC for both screens. Old cached dates
without an offset retain their original wall time because the original
source timezone cannot be recovered reliably; notes returned by the server
are refreshed using their original timestamp.
