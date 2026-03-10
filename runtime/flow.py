"""
flow.py | ai_framework runtime_core/lib
Optional flow mode system for the prompter.

Modes:
  normal      — current behaviour, no change
  paste_flow  — after copy, pause and allow quick re-use without returning
                to the main menu. Suitable for single-window chat sessions.
  chat_flow   — minimal keypress interaction. Terminal-friendly.
                No hotkeys required. Stays in a tight prompt loop.

Rules:
  - Never imported at top level by any script.
  - Imported inside a function with try/except only.
  - Default mode is "normal" — no behaviour change unless opted in.
  - Mode value comes from pconf["behavior"]["flow_mode"].
  - Never raises on bad config — falls back to normal.
  - No GUI. No hotkeys. No external dependencies beyond stdlib.
  - Does not import from scripts/. Does not import module_loader.
  - lib/core.py must not import this file.

Valid modes:
  FLOW_NORMAL     = "normal"
  FLOW_PASTE      = "paste_flow"
  FLOW_CHAT       = "chat_flow"
"""

import sys
from pathlib import Path

# ── ANSI (inline — flow.py must be usable without importing core) ──────────────
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"
_C_OK    = "\033[92m"
_C_ERR   = "\033[91m"
_C_WARN  = "\033[93m"
_C_NUM   = "\033[33m"
_C_KEY   = "\033[94m"
_C_SEL   = "\033[96m"
_C_HINT  = "\033[2m"


# ── Constants ──────────────────────────────────────────────────────────────────

FLOW_NORMAL = "normal"
FLOW_PASTE  = "paste_flow"
FLOW_CHAT   = "chat_flow"
VALID_FLOWS = {FLOW_NORMAL, FLOW_PASTE, FLOW_CHAT}


# ── Public API ─────────────────────────────────────────────────────────────────

def get_flow_mode(pconf: dict) -> str:
    """
    Read flow_mode from pconf["behavior"]["flow_mode"].
    Returns FLOW_NORMAL for any unknown or missing value.
    Never raises.
    """
    try:
        mode = pconf.get("behavior", {}).get("flow_mode", FLOW_NORMAL)
        return mode if mode in VALID_FLOWS else FLOW_NORMAL
    except Exception:
        return FLOW_NORMAL


def is_flow_active(pconf: dict) -> bool:
    """Return True if any non-normal flow is configured."""
    return get_flow_mode(pconf) != FLOW_NORMAL


def run_post_copy(
    output: str,
    log_num: str,
    pconf: dict,
    copy_fn,
    save_fn,
    build_fn,
) -> None:
    """
    Called after a successful clipboard copy, when a non-normal flow is active.

    Arguments:
      output    — the SESSION block text that was copied
      log_num   — log number string for display
      pconf     — prompter config dict
      copy_fn   — callable(text) → bool: copies text to clipboard
      save_fn   — callable() → None: saves state
      build_fn  — callable() → (str, str): returns (new_output, new_log_num)

    Dispatches to the appropriate flow handler.
    Falls back silently to normal if mode unrecognised.
    """
    mode = get_flow_mode(pconf)
    if mode == FLOW_PASTE:
        _paste_flow(output, log_num, pconf, copy_fn, save_fn, build_fn)
    elif mode == FLOW_CHAT:
        _chat_flow(output, log_num, pconf, copy_fn, save_fn, build_fn)
    # FLOW_NORMAL: caller handles its own pause — nothing to do here


# ── paste_flow ─────────────────────────────────────────────────────────────────

def _paste_flow(output, log_num, pconf, copy_fn, save_fn, build_fn):
    """
    paste_flow:
      After copy, remain in a tight loop.
      User pastes the copied block into their chat window manually.
      After receiving a response, press Enter to build and copy the next block,
      or q to return to the main menu.

    Keys:
      Enter  — build and copy next SESSION block
      r      — re-copy the current block (in case clipboard was cleared)
      q      — exit flow, return to menu
    """
    current_output  = output
    current_log_num = log_num

    _flow_banner("paste_flow", "Enter=next block  r=re-copy  q=back")

    while True:
        print(
            f"\n  {_c(_C_HINT, 'Ready. Paste into chat, get response, then press Enter.')}"
        )
        print(
            f"  {_c(_C_NUM, 'Enter')} next   "
            f"{_c(_C_KEY, 'r')} re-copy   "
            f"{_c(_C_KEY, 'q')} back menu"
        )
        print(f"\n  : ", end="", flush=True)
        key = input().strip().lower()

        if key == "q":
            print(_c(_C_HINT, "\n  Leaving paste_flow.\n"))
            break

        if key == "r":
            if copy_fn(current_output):
                print(_c(_C_OK, f"\n  ✓  Re-copied {current_log_num}"))
            else:
                print(_c(_C_ERR, "\n  ✗  Copy failed."))
            continue

        # Enter or any other key — build next block
        try:
            new_output, new_log_num = build_fn()
            if copy_fn(new_output):
                save_fn()
                current_output  = new_output
                current_log_num = new_log_num
                print(_c(_C_OK, f"\n  ✓  Copied {new_log_num}"))
            else:
                print(_c(_C_ERR, "\n  ✗  Copy failed."))
        except Exception as e:
            print(_c(_C_ERR, f"\n  ✗  Build error: {e}"))


# ── chat_flow ──────────────────────────────────────────────────────────────────

def _chat_flow(output, log_num, pconf, copy_fn, save_fn, build_fn):
    """
    chat_flow:
      Minimal keypress loop designed for terminal-only use.
      No hotkeys. No mouse. Single character commands.
      Stays in the flow until the user explicitly exits.

    Keys:
      c      — copy current block to clipboard
      n      — build and copy next block
      s      — show current block (print to terminal)
      q      — exit flow, return to menu
    """
    current_output  = output
    current_log_num = log_num

    _flow_banner("chat_flow", "c=copy  n=next  s=show  q=back")

    while True:
        print(
            f"\n  {_c(_C_NUM, 'c')} copy  "
            f"{_c(_C_NUM, 'n')} next  "
            f"{_c(_C_NUM, 's')} show  "
            f"{_c(_C_KEY, 'q')} back"
        )
        print(f"\n  : ", end="", flush=True)
        key = input().strip().lower()

        if key == "q":
            print(_c(_C_HINT, "\n  Leaving chat_flow.\n"))
            break

        elif key == "c":
            if copy_fn(current_output):
                print(_c(_C_OK, f"\n  ✓  Copied {current_log_num}"))
            else:
                print(_c(_C_ERR, "\n  ✗  Copy failed."))

        elif key == "s":
            print()
            print(_c(_C_HINT, "─" * 52))
            print(current_output)
            print(_c(_C_HINT, "─" * 52))

        elif key == "n":
            try:
                new_output, new_log_num = build_fn()
                if copy_fn(new_output):
                    save_fn()
                    current_output  = new_output
                    current_log_num = new_log_num
                    print(_c(_C_OK, f"\n  ✓  Copied {new_log_num}"))
                else:
                    print(_c(_C_ERR, "\n  ✗  Copy failed."))
            except Exception as e:
                print(_c(_C_ERR, f"\n  ✗  Build error: {e}"))

        else:
            print(_c(_C_HINT, f"  Unknown key: {key!r}  (c/n/s/q)"))


# ── Internal helpers ───────────────────────────────────────────────────────────

def _c(col: str, text: str) -> str:
    return f"{col}{text}{_RESET}"


def _flow_banner(mode: str, keys: str) -> None:
    print()
    print(_c(_C_HINT, "─" * 52))
    print(_c(_C_SEL, f"  {mode}"))
    print(_c(_C_HINT, f"  {keys}"))
    print(_c(_C_HINT, "─" * 52))
