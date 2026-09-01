# Private Cloud Messages

The app can fetch a short private text message and show it in
`HOME` -> `MEMOS`.

## GitHub Private Repo Setup

1. Create a private GitHub repo.
2. Add a text file, for example `message.txt`.
3. Create a fine-grained GitHub token with read-only access to that repo.
4. Set the app URL in `settings.json`:

```json
{
  "volume": 100,
  "sfx_enabled": true,
  "cloud_message_url": "https://raw.githubusercontent.com/USER/REPO/main/message.txt"
}
```

5. Put the token in `.cloud_message_token`:

```bash
printf '%s\n' 'github_pat_...' > /home/pi/app/.cloud_message_token
chmod 600 /home/pi/app/.cloud_message_token
```

6. Restart the app the same way you normally do. A reboot is fine.

The token is treated specifically as a GitHub credential. The app only sends it
to `github.com`, `api.github.com`, or `raw.githubusercontent.com`; configuring a
non-GitHub memo URL will not forward this token.

You can also use an environment variable instead of the token file:

```bash
export CLOUD_MESSAGE_TOKEN="github_pat_..."
```

The app fetches once after startup, then every 60 seconds. Unchanged
messages are not rewritten locally, which avoids unnecessary SD-card writes
and keeps the memo's cached receive timestamp stable.

Keep messages short. The app displays at most 1200 Unicode characters.
Each changed message is saved locally in `/home/pi/app/memos.json`, with
the newest memo shown first in `HOME` -> `MEMOS`. The current-message cache
stores its receive timestamp in `.cloud_message_meta.json`.
