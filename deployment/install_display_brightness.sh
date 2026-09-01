#!/bin/sh
set -eu

RULE_SRC="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/99-mpi5001-brightness.rules"
RULE_DST="/etc/udev/rules.d/99-mpi5001-brightness.rules"
TARGET_USER="${SUDO_USER:-$(id -un)}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this once with sudo: sudo ./deployment/install_display_brightness.sh" >&2
    exit 1
fi

install -m 0644 "$RULE_SRC" "$RULE_DST"
if getent group plugdev >/dev/null 2>&1; then
    usermod -aG plugdev "$TARGET_USER"
else
    groupadd plugdev
    usermod -aG plugdev "$TARGET_USER"
fi

udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw

echo "Installed MPI5001 brightness permissions for user: $TARGET_USER"
echo "Log out/reboot once so the plugdev group membership is active."
