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
