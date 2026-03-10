#!/bin/bash
# terminal_manager.sh | v1.1.0
# Opens prompt_manager in interactive terminal mode.
# Run manually — not part of the daily hotkey loop.
#
# PORTABLE: self-relative paths
# --noclose keeps konsole open if script exits with error
#
# Location: runtime_core/exec/
# Calls:    runtime_core/scripts/manager.py
#
# USAGE:
#   bash terminal_manager.sh
#   or assign a KDE shortcut if desired (no hotkey assigned by default)
#
# SETUP:
# 1. chmod +x this file
# 2. Run directly from terminal or assign a KDE shortcut

SCRIPT_DIR="$( cd "$(dirname "$0")" && pwd )"
konsole --noclose -e /usr/bin/python3 "$SCRIPT_DIR/../modules/prompt_manager.py"
