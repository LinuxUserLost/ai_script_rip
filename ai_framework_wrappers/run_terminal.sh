#!/usr/bin/env bash
# run_terminal.sh | ai_framework
# Open a new terminal window and launch app.py inside it.
# Tries konsole (KDE) first, then xterm as fallback.
# Safe to double-click from KDE file manager.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP="$RUNTIME_DIR/app.py"

# ── Display environment ────────────────────────────────────────────────────────
if [[ -z "$DISPLAY" && -z "$WAYLAND_DISPLAY" ]]; then
    export DISPLAY=:0
fi

# ── Guard: app.py must exist ──────────────────────────────────────────────────
if [[ ! -f "$APP" ]]; then
    echo "ERROR: app.py not found at: $APP" >&2
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found." >&2
    exit 1
fi

# ── Pick terminal ─────────────────────────────────────────────────────────────
LAUNCH_CMD=""

if command -v konsole &>/dev/null; then
    # konsole: --noclose keeps window open if python3 exits with error
    LAUNCH_CMD="konsole --noclose -e python3 $APP"

elif command -v xterm &>/dev/null; then
    # xterm fallback
    LAUNCH_CMD="xterm -hold -e python3 $APP"

else
    # Last resort: run directly in current shell (no new window)
    echo "WARNING: No terminal emulator found (tried konsole, xterm)."
    echo "Running app.py in current shell..."
    exec python3 "$APP"
fi

exec $LAUNCH_CMD
