#!/bin/sh
set -u

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LOG_FILE="$APP_DIR/xsession.log"
CRASH_COUNT=0
STABLE_RUN_SECONDS=300

# GPIO buttons are not X input events, so Xorg's own screensaver/DPMS would
# otherwise blank independently of the app and could not be woken by a memo.
# Make the application the sole owner of display-idle behavior.
if command -v xset >/dev/null 2>&1; then
    xset s off >/dev/null 2>&1 || true
    xset -dpms >/dev/null 2>&1 || true
    xset s noblank >/dev/null 2>&1 || true
fi

while true; do
    cd "$APP_DIR" || exit 1
    start_epoch=$(date +%s 2>/dev/null || printf '0')
    python3 tools/log_runner.py "$LOG_FILE" python3 main.py
    status=$?
    end_epoch=$(date +%s 2>/dev/null || printf '0')

    if [ "$status" -eq 0 ]; then
        exit 0
    fi

    runtime=0
    case "$start_epoch:$end_epoch" in
        *[!0-9:]*|'':*) ;;
        *) runtime=$((end_epoch - start_epoch)) ;;
    esac
    if [ "$runtime" -ge "$STABLE_RUN_SECONDS" ]; then
        CRASH_COUNT=0
    fi

    CRASH_COUNT=$((CRASH_COUNT + 1))
    printf '%s app exited with status %s (restart %s)\n' "$(date -Is 2>/dev/null || date)" "$status" "$CRASH_COUNT" >>"$LOG_FILE"

    if [ "$CRASH_COUNT" -ge 5 ]; then
        printf '%s crash loop limit reached; not restarting\n' "$(date -Is 2>/dev/null || date)" >>"$LOG_FILE"
        exit "$status"
    fi

    sleep 2
done
