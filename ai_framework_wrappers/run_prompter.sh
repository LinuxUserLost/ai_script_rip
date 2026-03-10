#!/usr/bin/env bash
# run_prompter.sh | ai_framework
# Hotkey launcher — runs prompter.py directly in the terminal.
# Assign to a keyboard shortcut in KDE System Settings > Shortcuts.
# Does NOT open a new GUI window.
# All output goes to the calling terminal (or /dev/null if no terminal).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$RUNTIME_DIR/modules/prompter.py"

# ── Guard ─────────────────────────────────────────────────────────────────────
if [[ ! -f "$TARGET" ]]; then
    echo "ERROR: prompter.py not found at: $TARGET" >&2
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found." >&2
    exit 1
fi

# ── Run ───────────────────────────────────────────────────────────────────────
exec python3 "$TARGET" "$@"
