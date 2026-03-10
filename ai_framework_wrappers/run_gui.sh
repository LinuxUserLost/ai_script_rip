#!/usr/bin/env bash
# run_gui.sh | ai_framework
# Launch the Tkinter dashboard (app.py).
# Safe to double-click from KDE file manager.
# Falls back to DISPLAY=:0 if no display is set.

# ── Resolve paths from this script's location ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP="$RUNTIME_DIR/app.py"

# ── Display environment ────────────────────────────────────────────────────────
# Wayland session: WAYLAND_DISPLAY is usually already set.
# X11 session: DISPLAY is usually set.
# Double-click from file manager may strip environment — fall back to :0.
if [[ -z "$DISPLAY" && -z "$WAYLAND_DISPLAY" ]]; then
    export DISPLAY=:0
fi

# ── Guard: app.py must exist ──────────────────────────────────────────────────
if [[ ! -f "$APP" ]]; then
    kdialog --error "ai_framework: app.py not found at:\n$APP" 2>/dev/null || \
    zenity --error --text="ai_framework: app.py not found at:\n$APP" 2>/dev/null || \
    echo "ERROR: app.py not found at: $APP" >&2
    exit 1
fi

# ── Guard: python3 must be available ─────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    kdialog --error "ai_framework: python3 not found in PATH." 2>/dev/null || \
    zenity --error --text="ai_framework: python3 not found." 2>/dev/null || \
    echo "ERROR: python3 not found." >&2
    exit 1
fi

# ── Launch ────────────────────────────────────────────────────────────────────
exec python3 "$APP"
