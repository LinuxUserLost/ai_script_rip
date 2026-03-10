# Daily Use

**Level:** Beginner

---

## Normal session workflow

```
1. Run prompter  →  2. Copy SESSION block  →  3. Paste into chat
4. Do your work  →  5. Copy response       →  6. Run cleaner
```

---

## Starting the prompter

From your `ai_framework/` folder:

```bash
python3 runtime_core/scripts/prompter.py
```

Or use the hotkey launcher (binds to a keyboard shortcut, copies silently):

```bash
bash runtime_core/exec/hotkey_prompter.sh
```

---

## Starting the cleaner

```bash
python3 runtime_core/scripts/cleaner.py
```

---

## Managing prompts

```bash
python3 runtime_core/scripts/manager.py
```

Use the manager to:
- Add new prompts to `004_prompts/`
- Set aliases for quick activation
- Search by keyword
- Check prompt health (missing fields, broken aliases)

---

## Setting defaults

From the prompter menu, press `10` (Session defaults) to set:

| Field | What it controls |
|---|---|
| model | Which AI model name appears in the SESSION block |
| pipeline_stage | research / draft / review / final |
| input_type | clipboard / file / manual / api |

Defaults are saved to `state.json` and reused next time.

---

## Active prompts

Active prompts are injected into every SESSION block you copy.
From the prompter menu, press `5` to manage the active list.

You can activate prompts by alias (e.g. `* research_mode`) or by bundle.

---

## Log numbers

Each SESSION block gets a log number: `2026-03-LOG-0001`.
Numbers increment automatically and are stored in `state.json`.
The cleaner uses them to match sessions to their raw files.

---

## If something goes wrong

1. Check `runtime_core/logs/debug.log` for error messages
2. Check that `state.json` is valid JSON (open in any text editor)
3. If `state.json` is corrupted, delete it — it will be rebuilt from defaults
4. Never delete `conf/` files — restore from your snapshot if needed

---

*Back: [Quick Start](quick_start.md)*
