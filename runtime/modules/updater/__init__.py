"""
modules/updater/__init__.py
Drop-in update pack handler — deferred until foundation is stable.

Planned capabilities (not yet implemented):
  - Detect update_pack/ folder beside runtime
  - Read update manifest (version, files, checksums)
  - Compare update files against current versions
  - Show diff before any apply
  - Backup replaced files before apply
  - Never auto-applies — always requires explicit user confirmation
"""


def is_available() -> bool:
    """Returns True — no external dependencies required."""
    return True


def commands() -> dict:
    return {
        "check":    "Check for an update pack beside the runtime",
        "inspect":  "Show what an update pack would change",
        "apply":    "Apply an update pack after user confirmation",
        "rollback": "Restore files from pre-update backups",
    }


def help_text() -> str:
    return (
        "updater module\n"
        "\n"
        "Handles drop-in update packs for the runtime. An update pack is a\n"
        "folder named update_pack/ placed beside runtime_core/.\n"
        "\n"
        "Commands:\n"
        "  check    -- detect and validate an update pack\n"
        "  inspect  -- show which files would be added, changed, or removed\n"
        "  apply    -- apply the update after showing diff and confirming\n"
        "  rollback -- restore any file replaced during the last apply\n"
        "\n"
        "Safety rules:\n"
        "  Snapshot must exist before apply is permitted.\n"
        "  Every replaced file is backed up before overwrite.\n"
        "  Apply never touches the vault.\n"
        "  No network access. No auto-apply. User confirms every change.\n"
    )


def diagnostics() -> list:
    from pathlib import Path
    results = []
    runtime     = Path(__file__).resolve().parent.parent.parent
    update_pack = runtime.parent / "update_pack"

    results.append({
        "key":    "update_pack",
        "value":  str(update_pack) if update_pack.exists() else "not present",
        "status": "ok" if update_pack.exists() else "warn",
    })

    # Check snapshot present (required for apply)
    parent    = runtime.parent
    snapshots = [d.name for d in parent.iterdir()
                 if d.is_dir() and "snapshot" in d.name.lower()] if parent.exists() else []
    results.append({
        "key":    "snapshot_for_apply",
        "value":  snapshots[0] if snapshots else "not found",
        "status": "ok" if snapshots else "warn",
    })

    return results
