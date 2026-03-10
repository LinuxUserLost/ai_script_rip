"""
modules/chat/__init__.py
Chat session helpers: output formatting, marker stripping, paste assistance.

Planned capabilities (not yet implemented):
  - Strip AI markers from output for clean paste
  - Format SESSION block for different chat platforms
  - Detect clipboard content type (has SESSION, has markers, plain text)
  - Quick-copy helpers for paste_flow and chat_flow modes
"""


def is_available() -> bool:
    """Returns True — no external dependencies required."""
    return True


def commands() -> dict:
    return {
        "strip":   "Strip AI markers from clipboard content",
        "format":  "Format SESSION block for a target platform",
        "detect":  "Detect type of current clipboard content",
        "wrap":    "Wrap plain text in a SESSION block",
    }


def help_text() -> str:
    return (
        "chat module\n"
        "\n"
        "Helpers for working with chat session content at the clipboard level.\n"
        "No GUI required. All operations are terminal-friendly.\n"
        "\n"
        "Commands:\n"
        "  strip   -- remove <---Marker----> tags from clipboard content\n"
        "  format  -- reformat SESSION block for a specific platform\n"
        "  detect  -- identify what type of content is in the clipboard\n"
        "  wrap    -- wrap raw text in a minimal SESSION block\n"
        "\n"
        "Designed to complement paste_flow and chat_flow modes.\n"
    )


def diagnostics() -> list:
    results = []
    # Check clipboard tools available
    import shutil
    for tool in ("wl-copy", "wl-paste", "xclip", "xsel"):
        found = shutil.which(tool) is not None
        results.append({
            "key":    tool,
            "value":  shutil.which(tool) or "not found",
            "status": "ok" if found else "warn",
        })
    return results
