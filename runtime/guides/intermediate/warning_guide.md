# Warning Guide

**Level:** Intermediate  
**File:** `runtime_core/lib/warn.py`

---

## What are runtime warnings?

Warnings are non-blocking status messages shown at startup (terminal mode only).
They tell you about things that need attention without stopping the script.

Warnings are optional. If `warn.py` is missing, scripts start silently.

---

## Severity levels

| Level | Colour | Meaning |
|---|---|---|
| `GREEN` | green `✓` | Safe — informational only |
| `YELLOW` | yellow `⚠` | Degraded — functional but needs attention |
| `RED` | red `✗` | Risk — possible data loss or portability violation |

---

## Warning triggers

| Trigger | Condition | Severity |
|---|---|---|
| `log_too_large` | `debug.log` exceeds line limit | YELLOW (1×) or RED (4×) |
| `missing_snapshot` | No snapshot folder beside runtime | YELLOW |
| `config_missing` | A config JSON file is absent | YELLOW |
| `vault_path_mismatch` | `vault_root` is absolute path | RED |
| `vault_path_mismatch` | Vault directory does not exist | YELLOW |
| `module_error` | A module `__init__.py` fails to import | RED |
| `module_error` | A module folder has no `__init__.py` | YELLOW |

---

## What to do for each warning

### `log_too_large` — YELLOW
Your `debug.log` file has grown past the rotation limit.
Run the cleaner to rotate it:
```bash
python3 runtime_core/scripts/cleaner.py
```
Then choose the log rotation option from the menu.

### `log_too_large` — RED
Log rotation may have failed. The file is more than 4× the limit.
Check `runtime_core/logs/` and manually move or clear `debug.log` if needed.
Archive it to `runtime_core/logs/archive/` with a date suffix.

### `missing_snapshot`
No snapshot folder was found beside `runtime_core/`.
Take a snapshot now before doing any write operations:
```bash
cp -r ai_framework/ ai_framework_snapshot_20260307/
```

### `config_missing`
A config file is absent. The script will use built-in defaults.
Defaults are safe — this is not an emergency.
To regenerate the file, delete the relevant config and restart the script.
It will be recreated from defaults automatically.

### `vault_path_mismatch` — RED
The `vault_root` value in `system_config.json` is an absolute path.
This breaks USB portability. Fix it to a relative path:
```json
{ "vault_root": "../ai-vault" }
```

### `vault_path_mismatch` — YELLOW
The vault directory does not exist at the resolved path.
Run bootstrap from the prompter menu (option `11`) to create it.

### `module_error`
A module could not be loaded. The module will be treated as unavailable.
Check the module's `__init__.py` for syntax errors.
The rest of the runtime is unaffected.

---

## Config — controlling warning behaviour

In `runtime_core/conf/system_config.json`:

```json
{
  "warnings": {
    "enabled":      true,
    "block_on_red": false,
    "log_warnings": true
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master switch. `false` disables all checks |
| `block_on_red` | `false` | If `true`, script exits on any RED warning |
| `log_warnings` | `true` | Write warnings to `debug.log` |

### Strict mode

Set `block_on_red: true` if you want the runtime to refuse to continue
when a RED-severity issue is present. Useful on systems where data integrity
is critical. Not recommended for casual use.

---

## Warnings in hotkey mode

Warnings are suppressed in hotkey mode (`--hotkey` flag).
The hotkey path is silent by design — it should not interrupt a keyboard shortcut.
Warnings are only shown in terminal (interactive) mode.

---

## Running checks manually

From Python (inside a function, never at top level):

```python
try:
    from warn import display_if_any
except ImportError:
    display_if_any = lambda *a, **kw: []

warnings = display_if_any(
    runtime_dir,
    sysconf,
    conf_dir=conf_dir,
    modules_dir=modules_dir,
    source="MY_SCRIPT",
)
```

To run only specific triggers:

```python
from warn import run_checks, display
ws = run_checks(runtime_dir, sysconf, triggers={"missing_snapshot", "log_too_large"})
display(ws, sysconf)
```

---

*See also: [Flow Guide](flow_guide.md), [Module Guide](module_guide.md)*
