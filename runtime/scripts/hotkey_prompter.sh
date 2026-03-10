#!/bin/bash
# hotkey_prompter.sh | v6.1.0
# Silent hotkey mode — builds SESSION block and copies to clipboard instantly.
# KDE Hotkey: Meta+A
#
# PORTABLE: self-relative path — works from USB, any mount point.
# KDE hotkeys MUST point to this .sh file, NOT prompter.py directly.
#
# Location: runtime_core/exec/
# Calls:    runtime_core/scripts/prompter.py

SCRIPT_DIR="$( cd "$(dirname "$0")" && pwd )"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
/usr/bin/python3 "$SCRIPT_DIR/../modules/prompter.py" --hotkey
