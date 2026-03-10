#!/bin/bash
# terminal_cleaner.sh | v4.1.0
# Opens cleaner in interactive terminal mode.
# KDE Hotkey: Meta+Shift+C
#
# PORTABLE: self-relative paths
# --noclose keeps konsole open if script exits with error
#
# Location: runtime_core/exec/
# Calls:    runtime_core/scripts/cleaner.py
#
# SETUP:
# 1. chmod +x this file
# 2. KDE Shortcuts → New → Global Shortcut → Command/URL
# 3. Assign Meta+Shift+C

SCRIPT_DIR="$( cd "$(dirname "$0")" && pwd )"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
konsole --noclose -e /usr/bin/python3 "$SCRIPT_DIR/../modules/cleaner.py"
