# ai_framework — Guide System

**Build step:** 10 / 10  
**Phase:** DOCS / GUIDES / USABILITY  
**Spec:** v5.0  
**Status:** Foundation complete. All 10 build steps verified.

---

## What is this?

ai_framework is a portable, terminal-native session management system for
structured AI conversations. It runs from a USB drive, requires no internet
connection, and uses only Python standard library (plus optional Tkinter for
the GUI).

The system has three scripts and a shared runtime:

| Script | Role |
|---|---|
| `prompter.py` | Build and copy SESSION blocks to the clipboard |
| `cleaner.py` | Parse, archive, and organise completed sessions |
| `prompt_manager.py` | Index, validate, and search prompt files |

---

## Guide levels

| Level | Folder | For |
|---|---|---|
| Beginner | `beginner/` | First-time setup and daily use |
| Intermediate | `intermediate/` | Flow modes, warnings, module status |
| Advanced | `advanced/` | Config tuning, vault structure, log management |
| Developer | `developer/` | Runtime architecture, build steps, module API |

---

## Quick navigation

### Beginner
- [Quick Start](beginner/quick_start.md) — first run in five steps
- [Daily Use](beginner/daily_use.md) — normal workflow

### Intermediate
- [Flow Guide](intermediate/flow_guide.md) — paste_flow and chat_flow modes
- [Warning Guide](intermediate/warning_guide.md) — reading and acting on warnings
- [Module Guide](intermediate/module_guide.md) — what modules do and how to check them

### Advanced
- [Config Reference](advanced/config_reference.md) — all config keys explained
- [Vault Structure](advanced/vault_structure.md) — folder layout and naming rules

### Developer
- [Build Steps](developer/build_steps.md) — all 10 steps with scope and status
- [Module API](developer/module_api.md) — commands / help / diagnostics contracts
- [GUI Guide](developer/gui_guide.md) — GUI layer design and launch contract

---

## Core rules (always active)

1. No absolute paths anywhere in runtime or vault
2. Snapshot required before any write operation
3. `startup_checks()` always runs first in every script
4. `check_snapshot()` always runs second
5. `core.py` must not import `module_loader`, `warn`, `flow`, or any module
6. Vault is never inside runtime_core/
7. All optional imports use `try/except` with fallback stubs

---

*Guides are plain Markdown. No special viewer required.*
