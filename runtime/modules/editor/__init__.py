"""
modules/editor/__init__.py
Script and config editing helpers. Read-only inspection and safe diff.

Planned capabilities (not yet implemented):
  - List editable scripts in scripts/ and exec/
  - Show script contents with line numbers
  - Diff current script against snapshot version
  - Config file viewer with validation hints
  - Safe open in $EDITOR (never auto-edits)
"""


def is_available() -> bool:
    """Returns True — no external dependencies required."""
    return True


def commands() -> dict:
    return {
        "list":   "List editable scripts and config files",
        "show":   "Show contents of a script or config file",
        "diff":   "Compare current file with snapshot version",
        "config": "View and validate a config file",
        "open":   "Open a file in $EDITOR (never auto-saves)",
    }


def help_text() -> str:
    return (
        "editor module\n"
        "\n"
        "Read-only inspection and safe diff tools for runtime scripts\n"
        "and config files. Never modifies files automatically.\n"
        "\n"
        "Commands:\n"
        "  list    -- show all scripts in scripts/ and exec/ folders\n"
        "  show    -- display a file with line numbers\n"
        "  diff    -- side-by-side diff against snapshot version\n"
        "  config  -- view a config file with validation hints\n"
        "  open    -- open a file in $EDITOR (user controls any saves)\n"
        "\n"
        "All file writes require explicit user confirmation.\n"
        "Snapshot must exist before any diff is available.\n"
    )


def diagnostics() -> list:
    import os, shutil
    from pathlib import Path
    results = []
    runtime = Path(__file__).resolve().parent.parent.parent

    # Check scripts/ and exec/ present
    for folder in ("scripts", "exec"):
        path   = runtime / folder
        exists = path.exists()
        count  = len(list(path.glob("*"))) if exists else 0
        results.append({
            "key":    folder,
            "value":  f"{count} files" if exists else "missing",
            "status": "ok" if exists and count > 0 else "warn",
        })

    # Check $EDITOR set
    editor = os.environ.get("EDITOR", "")
    results.append({
        "key":    "$EDITOR",
        "value":  editor or "not set",
        "status": "ok" if editor else "warn",
    })

    # Check snapshot present beside runtime
    parent    = runtime.parent
    snapshots = [d.name for d in parent.iterdir()
                 if d.is_dir() and "snapshot" in d.name.lower()] if parent.exists() else []
    results.append({
        "key":    "snapshot",
        "value":  snapshots[0] if snapshots else "not found",
        "status": "ok" if snapshots else "warn",
    })

    return results
