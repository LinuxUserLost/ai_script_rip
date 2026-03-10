#!/bin/bash
# hotkey_cleaner.sh | v4.1.0
# Silent hotkey mode — reads clipboard, parses session, saves to vault.
# KDE Hotkey: Meta+C
#
# PORTABLE: self-relative path — works from USB, any mount point.
# KDE hotkeys MUST point to this .sh file, NOT cleaner.py directly.
#
# Location: runtime_core/exec/
# Calls:    runtime_core/scripts/cleaner.py

SCRIPT_DIR="$( cd "$(dirname "$0")" && pwd )"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
/usr/bin/python3 "$SCRIPT_DIR/../modules/cleaner.py" --hotkey
