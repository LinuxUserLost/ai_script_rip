#!/bin/bash
# terminal_prompter.sh | v6.1.0
# Opens prompter in interactive terminal mode.
# KDE Hotkey: Meta+Shift+A
#
# PORTABLE: self-relative paths
# --noclose keeps konsole open if script exits with error
#
# Location: runtime_core/exec/
# Calls:    runtime_core/scripts/prompter.py
#
# SETUP:
# 1. chmod +x this file
# 2. KDE Shortcuts → New → Global Shortcut → Command/URL
# 3. Assign Meta+Shift+A

SCRIPT_DIR="$( cd "$(dirname "$0")" && pwd )"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
konsole --noclose -e /usr/bin/python3 "$SCRIPT_DIR/../modules/prompter.py"
