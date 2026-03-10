"""
modules/learning/__init__.py
Guided tutorials, knowledge browsing, and ML/prompt engineering help.
Reads from vault folders: 006_knowledge, 007_guides, 008_agents, 009_tutorials.

Planned capabilities (not yet implemented):
  - Step-through tutorial walker (level-2 headings = steps)
  - Full-text search across knowledge folders
  - Learning pack installer (reads install_*.md, never auto-installs)
  - Guide index from metadata.json in each pack folder
"""


def is_available() -> bool:
    """Returns True — no external dependencies required."""
    return True


def commands() -> dict:
    """
    Return available commands exposed by this module.
    Format: {command_name: short_description}
    """
    return {
        "browse":  "Browse knowledge and guide folders in vault",
        "search":  "Search guides and tutorials by keyword",
        "walk":    "Step through a tutorial interactively",
        "install": "Check a learning pack for installation requirements",
        "index":   "Show installed learning pack index",
    }


def help_text() -> str:
    """Return help text shown when user requests module help."""
    return (
        "learning module\n"
        "\n"
        "Provides access to knowledge packs, guides, and step-through\n"
        "tutorials stored in the vault (006-009 folders).\n"
        "\n"
        "Commands:\n"
        "  browse   -- list available guides and knowledge packs\n"
        "  search   -- find content by keyword across all knowledge folders\n"
        "  walk     -- run a step-by-step tutorial from a guide file\n"
        "  install  -- inspect a learning pack without auto-installing\n"
        "  index    -- show all installed packs and their metadata\n"
        "\n"
        "Learning packs are plain Markdown folders dropped into the vault.\n"
        "No binary files. No auto-install. Manual review before any apply.\n"
    )


def diagnostics() -> list:
    """
    Return a list of diagnostic items for this module.
    Each item: {key: str, value: str, status: 'ok' | 'warn' | 'error'}
    """
    from pathlib import Path
    results = []
    runtime = Path(__file__).resolve().parent.parent.parent
    vault   = _resolve_vault(runtime)
    for key, folder in [
        ("knowledge", "006_knowledge"),
        ("guides",    "007_guides"),
        ("agents",    "008_agents"),
        ("tutorials", "009_tutorials"),
    ]:
        path   = vault / folder if vault else None
        exists = path.exists() if path else False
        results.append({
            "key":    key,
            "value":  str(path) if path else "vault not found",
            "status": "ok" if exists else "warn",
        })
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
