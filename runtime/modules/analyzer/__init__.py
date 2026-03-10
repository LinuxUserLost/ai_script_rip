"""
modules/analyzer/__init__.py
Vault and session diagnostics, health reports, and usage statistics.

Planned capabilities (not yet implemented):
  - Vault folder scan (missing indexes, orphaned files)
  - Session count by month
  - Prompt usage frequency analysis
  - Tag cooccurrence tracking (moved from cleaner)
  - Health report generation
"""


def is_available() -> bool:
    """Returns True — no external dependencies required."""
    return True


def commands() -> dict:
    return {
        "scan":    "Scan vault folders for structural issues",
        "report":  "Generate a health report for prompts and sessions",
        "stats":   "Show session and prompt usage statistics",
        "tags":    "Analyse tag cooccurrence and suggest related tags",
        "diff":    "Compare session counts across months",
    }


def help_text() -> str:
    return (
        "analyzer module\n"
        "\n"
        "Provides read-only diagnostics and health reporting for the vault.\n"
        "Never modifies files. Always reads current state from disk.\n"
        "\n"
        "Commands:\n"
        "  scan    -- check vault folder structure for gaps or orphaned files\n"
        "  report  -- build a prompt health report (status, missing fields)\n"
        "  stats   -- usage counts, last-used dates, most-used prompts\n"
        "  tags    -- show which tags appear together most often\n"
        "  diff    -- compare session file counts across months\n"
        "\n"
        "Output is terminal-only. No file writes.\n"
    )


def diagnostics() -> list:
    from pathlib import Path
    results = []
    runtime = Path(__file__).resolve().parent.parent.parent
    vault   = _resolve_vault(runtime)

    # Check index files
    for label, rel in [
        ("session_index", "000_indexes/session_index.md"),
        ("prompt_index",  "004_prompts/prompt_index.md"),
        ("prompt_index_json", "004_prompts/prompt_index.json"),
    ]:
        path   = vault / rel if vault else None
        exists = path.exists() if path else False
        results.append({
            "key":    label,
            "value":  str(path) if path else "vault not found",
            "status": "ok" if exists else "warn",
        })

    # Check sessions folder
    sess_dir = vault / "002_sessions" if vault else None
    if sess_dir and sess_dir.exists():
        month_dirs = [d for d in sess_dir.iterdir() if d.is_dir()]
        results.append({
            "key":    "session_months",
            "value":  str(len(month_dirs)),
            "status": "ok",
        })
    else:
        results.append({"key": "session_months", "value": "0", "status": "warn"})

    return results


def _resolve_vault(runtime):
    try:
        import json
        conf_file = runtime / "configs" / "system_config.json"
        if conf_file.exists():
            conf = json.loads(conf_file.read_text())
            rel  = conf.get("vault_root", "../ai-vault")
            return (runtime / rel).resolve()
    except Exception:
        pass
    return (runtime.parent / "ai-vault").resolve()
