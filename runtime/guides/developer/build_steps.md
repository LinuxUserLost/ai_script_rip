# Build Steps Reference

**Level:** Developer  
**Build stamp:** 10 / 10 — COMPLETE

---

## Overview

The runtime was built in 10 ordered steps. Each step depended on the previous.
Rules established in Step 1 (core.py) remain active through all later steps.

---

## Step 0 — Snapshot
**Scope:** Project snapshot before any changes  
**Output:** `ai_framework_snapshot_YYYYMMDD/`  
**Rule established:** Snapshot required before any write operation. Enforced by
`check_snapshot()` in `core.py`. No step can bypass this.

---

## Step 1 — core.py
**Scope:** Shared library foundation  
**File:** `runtime_core/lib/core.py`  
**Contents:**
- Path constants (`RUNTIME_DIR`, `CONF_DIR`, `LOGS_DIR`, `STATE_FILE`, `DEBUG_LOG`)
- ANSI colour helpers and UI primitives
- `startup_checks()` — log rotation + startup log entry. Always called first.
- `check_snapshot()` — scans for snapshot folder. Always called second.
- `load_state()` / `save_state()` — JSON state with migration
- `load_config()` / `save_config()` — deep merge with defaults + backup
- `DEFAULT_SYSTEM_CONFIG`, `DEFAULT_PROMPTER_CONFIG`, `DEFAULT_CLEANER_CONFIG`

**Rule established:** `core.py` must not import `module_loader`, `warn`, `flow`,
or any module. Import direction is always scripts → lib, never lib → scripts.

---

## Step 2 — Config system
**Scope:** JSON config load/save with deep merge and backup  
**Files:** `conf/system_config.json`, `conf/prompter_config.json`, `conf/cleaner_config.json`  
**Rule established:** All config values have defaults in `core.py`. Missing keys
are filled by deep merge. Never crash on missing config file.

---

## Step 3 — Log rotation
**Scope:** `debug.log` rotation into `logs/archive/`  
**Built into:** `core.py` `startup_checks()` → `_rotate_log()`  
**Threshold:** `max_log_lines` from cleaner config (default 400)

---

## Step 4 — Bootstrap integration
**Scope:** Vault directory creation, exec scripts, path resolution  
**Files:** `exec/*.sh`, path system in all three scripts  
**Rule established:** No hardcoded vault paths. All paths from `system_config.json`.
`_resolve_runtime_paths()` in each script reads the config.

---

## Step 5 — Module framework
**Scope:** Module discovery infrastructure  
**Files:** `lib/module_loader.py`, `modules/*/  __init__.py`  
**Rule established:** Modules never load automatically. `module_loader` never
imported at top level. Fallback stubs in every script.

---

## Step 6 — Flow system
**Scope:** Optional post-copy interaction modes  
**File:** `lib/flow.py`  
**Modes:** `normal`, `paste_flow`, `chat_flow`  
**Rule established:** Flow only activates when `flow_mode != "normal"` in config
AND `flow.py` is present. Default is always `normal`.

---

## Step 7 — Warning system
**Scope:** Non-blocking runtime status indicators  
**File:** `lib/warn.py`  
**Triggers:** `log_too_large`, `missing_snapshot`, `config_missing`,
`vault_path_mismatch`, `module_error`  
**Rule established:** Warnings never block unless `block_on_red: true`. Hotkey
mode always suppresses warning display.

---

## Step 8 — Module command API
**Scope:** `commands()`, `help_text()`, `diagnostics()` on all six modules  
**Files:** All six `modules/*/  __init__.py`  
**Additions to module_loader:** `get_commands()`, `get_help()`, `get_diagnostics()`,
`all_commands()`, `all_diagnostics()`  
**Rule established:** All four module exports must never raise. `sys.modules`
cleaned after every probe.

---

## Step 9 — GUI layer
**Scope:** Tkinter dashboard, optional, launch-on-demand only  
**Files:** `modules/gui/__init__.py`, `modules/gui/app.py`  
**Gates:** `is_available()` → display present → `app.py` present → `launch()`  
**Tabs:** Status, Warnings, Commands, Help  
**Rule established:** GUI never auto-launches. All data gathered before any
tkinter import. No GUI-only features — terminal remains full-capability.

---

## Step 10 — Docs / Guides
**Scope:** Guide system in `007_guides/`  
**Files:** This file and all siblings  
**Rule established:** Guides are plain Markdown. No absolute paths. No binary files.

---

## Invariants (never violated by any step)

| Invariant | Where enforced |
|---|---|
| No absolute paths | All scripts, lib, modules, guides |
| Snapshot check before write | `core.py check_snapshot()` |
| `startup_checks()` always first | All three `main()` functions |
| `check_snapshot()` always second | All three `main()` functions |
| `core.py` imports nothing from lib siblings | Verified in every step |
| Vault never inside runtime_core | `system_config.json vault_root` |
| Modules never auto-load | `module_loader._probe()` only on demand |

---

*See also: [Module API](module_api.md), [GUI Guide](gui_guide.md)*
