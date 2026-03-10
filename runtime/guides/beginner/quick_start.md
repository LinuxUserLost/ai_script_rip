# Quick Start Guide

**Level:** Beginner  
**Time:** 5 minutes

---

## Before you begin

You need:
- Python 3.10 or later (`python3 --version`)
- A terminal (any — GNOME Terminal, Konsole, xterm, etc.)
- The `ai_framework` folder on your USB or local drive
- Wayland clipboard tool: `wl-copy` (install with `sudo apt install wl-clipboard`)

---

## Step 1 — Take a snapshot

Before doing anything else, make a copy of the entire `ai_framework` folder.
Name it with today's date:

```
ai_framework_snapshot_20260307/
ai_framework/              ← working copy
```

Both folders should sit beside each other. The runtime checks for this on
every startup. If no snapshot is found, it will warn you.

---

## Step 2 — Check the structure

Your folder should look like this:

```
ai_framework/
├── runtime_core/
│   ├── conf/         system_config.json, prompter_config.json, cleaner_config.json
│   ├── exec/         shell launchers (.sh files)
│   ├── lib/          core.py, module_loader.py, flow.py, warn.py
│   ├── logs/         debug.log (created on first run)
│   ├── modules/      learning/, analyzer/, chat/, editor/, gui/, updater/
│   ├── scripts/      prompter.py, cleaner.py, manager.py
│   └── state.json    (created on first run)
└── ai-vault/
    ├── 000_indexes/
    ├── 001_topics/
    ├── 002_sessions/
    ├── 003_raw/
    ├── 004_prompts/
    ├── 005_tags/
    ├── 006_knowledge/
    ├── 007_guides/   ← you are here
    ├── 008_agents/
    ├── 009_tutorials/
    └── bundles/
```

---

## Step 3 — Run the prompter

```bash
python3 runtime_core/scripts/prompter.py
```

On the first run it will:
1. Create `state.json` with default values
2. Create any missing vault folders
3. Show the main menu

---

## Step 4 — Build your first SESSION block

From the main menu, press `1` to copy a SESSION block to the clipboard
using your saved defaults. Then paste it into your AI chat window.

To customise before copying, press `2` (live edit).

---

## Step 5 — Archive completed sessions

After your session, run the cleaner to archive and index it:

```bash
python3 runtime_core/scripts/cleaner.py
```

---

## What a SESSION block looks like

```
[SESSION]
log: 2026-03-07-LOG-0001
date: 2026-03-07
time: 14:32
model: claude-sonnet-4-6
pipeline_stage: research
input_type: clipboard

[PROMPTS]
* your_prompt_alias

[INSTRUCTIONS]
...your instructions here...

[TASK]
...your task here...
<---End--->
```

---

## Key shortcuts

| Key | Action |
|---|---|
| `1` | Copy SESSION block with saved defaults |
| `2` | Live edit fields before copying |
| `q` | Exit |
| `??` | Show help |

---

*Next: [Daily Use](daily_use.md)*
