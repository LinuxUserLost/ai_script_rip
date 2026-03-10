#!/usr/bin/env bash
# verify.sh | ai_framework structure verifier
#
# Checks a runtime_WORK/ (or any target dir) for completeness.
# Prints PASS / FAIL per section. Returns exit code 1 if any FAIL.
#
# Usage:
#   bash verify.sh                        # checks ./runtime_WORK
#   bash verify.sh --target /path/to/dir  # checks specific dir
#   bash verify.sh --target ./runtime     # can also check source dir

set -euo pipefail

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
C_OK="\033[92m"; C_FAIL="\033[91m"; C_WARN="\033[93m"
C_HEAD="\033[96m"; C_DIM="\033[2m"; RESET="\033[0m"

# ── Args ──────────────────────────────────────────────────────────────────────
TARGET=""
i=1
while [[ $i -le $# ]]; do
    arg="${!i}"
    if [[ "$arg" == "--target" ]]; then
        i=$((i+1)); TARGET="${!i}"
    fi
    i=$((i+1))
done
[[ -z "$TARGET" ]] && TARGET="$SELF_DIR/runtime_WORK"

# ── Counters ──────────────────────────────────────────────────────────────────
PASS=0; FAIL=0; WARN_COUNT=0
SECTION_PASS=0; SECTION_FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────
_pass() { echo -e "  ${C_OK}PASS${RESET}  $*"; PASS=$((PASS+1)); }
_fail() { echo -e "  ${C_FAIL}FAIL${RESET}  $*"; FAIL=$((FAIL+1)); SECTION_FAIL=$((SECTION_FAIL+1)); }
_warn() { echo -e "  ${C_WARN}WARN${RESET}  $*"; WARN_COUNT=$((WARN_COUNT+1)); }
_info() { echo -e "  ${C_DIM}....${RESET}  $*"; }
_head() {
    SECTION_FAIL=0
    echo -e "\n${C_HEAD}── $1 ${RESET}"
}
_section_result() {
    local label="$1"
    if [[ $SECTION_FAIL -eq 0 ]]; then
        echo -e "  ${C_OK}PASS${RESET}  [$label]"
        SECTION_PASS=$((SECTION_PASS+1))
    else
        echo -e "  ${C_FAIL}FAIL${RESET}  [$label] — $SECTION_FAIL check(s) failed"
        SECTION_FAIL=0
    fi
}

check_file() {
    local f="$1" label="${2:-$1}"
    if [[ -f "$TARGET/$f" ]]; then
        _pass "$label"
    else
        _fail "$label  (not found: $TARGET/$f)"
    fi
}

check_dir() {
    local d="$1" label="${2:-$1}"
    if [[ -d "$TARGET/$d" ]]; then
        _pass "$label/"
    else
        _fail "$label/  (not found)"
    fi
}

check_exec() {
    local f="$1"
    if [[ ! -f "$TARGET/$f" ]]; then
        _fail "$f  (not found)"
    elif [[ -x "$TARGET/$f" ]]; then
        _pass "$f  (+x)"
    else
        _fail "$f  (not executable — run: chmod +x $TARGET/$f)"
    fi
}

check_json() {
    local f="$1"
    if [[ ! -f "$TARGET/$f" ]]; then
        _fail "$f  (not found)"; return
    fi
    if python3 -c "import json,sys; json.load(open('$TARGET/$f'))" 2>/dev/null; then
        _pass "$f  (valid JSON)"
    else
        _fail "$f  (invalid JSON)"
    fi
}

check_python_syntax() {
    local f="$1"
    if [[ ! -f "$TARGET/$f" ]]; then
        _fail "$f  (not found)"; return
    fi
    if python3 -m py_compile "$TARGET/$f" 2>/dev/null; then
        _pass "$f  (syntax OK)"
    else
        _fail "$f  (syntax error)"
    fi
}

check_contains() {
    local f="$1" pattern="$2" label="$3"
    if [[ ! -f "$TARGET/$f" ]]; then
        _fail "$label  (file not found: $f)"; return
    fi
    if grep -q "$pattern" "$TARGET/$f" 2>/dev/null; then
        _pass "$label"
    else
        _fail "$label  (pattern not found in $f)"
    fi
}

check_not_contains() {
    local f="$1" pattern="$2" label="$3"
    if [[ ! -f "$TARGET/$f" ]]; then
        _fail "$label  (file not found)"; return
    fi
    if grep -q "$pattern" "$TARGET/$f" 2>/dev/null; then
        _fail "$label  (forbidden pattern found: $pattern in $f)"
    else
        _pass "$label"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
echo -e "\n${C_HEAD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${C_HEAD}║   ai_framework  verify.sh                    ║${RESET}"
echo -e "${C_HEAD}╚══════════════════════════════════════════════╝${RESET}"
echo -e "  Target: ${C_DIM}$TARGET${RESET}"

if [[ ! -d "$TARGET" ]]; then
    echo -e "\n  ${C_FAIL}FAIL${RESET}  Target directory not found: $TARGET"
    echo -e "  Run install.sh first, or pass --target <dir>\n"
    exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
# 1. Runtime Structure
# ══════════════════════════════════════════════════════════════════════════════
_head "1. Runtime structure"

check_file "core.py"
check_file "flow.py"
check_file "warn.py"
check_file "module_loader.py"
check_file "app.py"
check_dir  "configs"
check_dir  "modules"
check_dir  "scripts"
check_dir  "logs"

_section_result "Runtime structure"

# ══════════════════════════════════════════════════════════════════════════════
# 2. Config files
# ══════════════════════════════════════════════════════════════════════════════
_head "2. Config files"

check_json "configs/system_config.json"
check_json "configs/prompter_config.json"
check_json "configs/cleaner_config.json"

# Spot-check key fields
check_contains "configs/system_config.json" "vault_root"      "system_config: vault_root key"
check_contains "configs/system_config.json" "vault_folders"   "system_config: vault_folders key"
check_contains "configs/system_config.json" "warnings"        "system_config: warnings block"
check_contains "configs/prompter_config.json" "flow_mode"     "prompter_config: flow_mode key"
check_contains "configs/cleaner_config.json" "max_log_lines"  "cleaner_config: max_log_lines"

# Vault root must not be absolute
vault_root=$(python3 -c "
import json
d = json.load(open('$TARGET/configs/system_config.json'))
print(d.get('vault_root',''))
" 2>/dev/null || echo "")
if [[ -z "$vault_root" ]]; then
    _fail "vault_root is empty"
elif [[ "$vault_root" = /* ]]; then
    _fail "vault_root is absolute path (portability violation): $vault_root"
else
    _pass "vault_root is relative: $vault_root"
fi

_section_result "Config files"

# ══════════════════════════════════════════════════════════════════════════════
# 3. Module loader
# ══════════════════════════════════════════════════════════════════════════════
_head "3. Module loader"

check_python_syntax "module_loader.py"
check_contains "module_loader.py" "_MODULES_DIR" "module_loader: _MODULES_DIR defined"
check_contains "module_loader.py" 'parent / "modules"' "module_loader: modules path relative"
check_contains "module_loader.py" "def list_available"    "module_loader: list_available()"
check_contains "module_loader.py" "def is_module_available" "module_loader: is_module_available()"
check_contains "module_loader.py" "def get_commands"      "module_loader: get_commands()"
check_contains "module_loader.py" "def get_help"          "module_loader: get_help()"
check_contains "module_loader.py" "def get_diagnostics"   "module_loader: get_diagnostics()"
check_contains "module_loader.py" "def all_commands"      "module_loader: all_commands()"
check_contains "module_loader.py" "def all_diagnostics"   "module_loader: all_diagnostics()"
check_contains "module_loader.py" "sys.modules.pop"       "module_loader: sys.modules cleanup"

# Live probe
if python3 -c "
import sys
sys.path.insert(0, '$TARGET')
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('ml', '$TARGET/module_loader.py')
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)
avail = ml.list_available()
assert len(ml.KNOWN_MODULES) == 6, f'expected 6 modules, got {len(ml.KNOWN_MODULES)}'
non_gui = [k for k,v in avail.items() if k != 'gui' and not v]
assert not non_gui, f'non-gui modules unavailable: {non_gui}'
" 2>/dev/null; then
    _pass "module_loader: live probe — 6 modules discovered, 5 available"
else
    _fail "module_loader: live probe failed"
fi

_section_result "Module loader"

# ══════════════════════════════════════════════════════════════════════════════
# 4. Modules folder
# ══════════════════════════════════════════════════════════════════════════════
_head "4. Modules folder"

check_file "modules/prompter.py"
check_file "modules/cleaner.py"
check_file "modules/prompt_manager.py"

for mod in learning analyzer chat editor gui updater; do
    check_file "modules/$mod/__init__.py"
    if [[ -f "$TARGET/modules/$mod/__init__.py" ]]; then
        for fn in is_available commands help_text diagnostics; do
            check_contains "modules/$mod/__init__.py" "def $fn" "$mod: $fn()"
        done
    fi
done

check_python_syntax "modules/prompter.py"
check_python_syntax "modules/cleaner.py"
check_python_syntax "modules/prompt_manager.py"

_section_result "Modules folder"

# ══════════════════════════════════════════════════════════════════════════════
# 5. core.py / flow.py / warn.py
# ══════════════════════════════════════════════════════════════════════════════
_head "5. core / flow / warn"

check_python_syntax "core.py"
check_contains     "core.py" 'RUNTIME_DIR = Path(__file__).resolve().parent' "core: RUNTIME_DIR from __file__"
check_contains     "core.py" '"configs"'        "core: CONF_DIR uses configs/"
check_contains     "core.py" "def startup_checks" "core: startup_checks() defined"
check_contains     "core.py" "def check_snapshot" "core: check_snapshot() defined"
check_not_contains "core.py" "LIB_DIR"            "core: no LIB_DIR reference"
check_not_contains "core.py" "import module_loader" "core: does not import module_loader"
check_not_contains "core.py" "from flow"          "core: does not import flow"
check_not_contains "core.py" "from warn"          "core: does not import warn"

check_python_syntax "flow.py"
check_contains "flow.py" "FLOW_NORMAL"       "flow: FLOW_NORMAL defined"
check_contains "flow.py" "FLOW_PASTE"        "flow: FLOW_PASTE defined"
check_contains "flow.py" "FLOW_CHAT"         "flow: FLOW_CHAT defined"
check_contains "flow.py" "def run_post_copy" "flow: run_post_copy()"
check_contains "flow.py" "def get_flow_mode" "flow: get_flow_mode()"
check_contains "flow.py" "def is_flow_active" "flow: is_flow_active()"

check_python_syntax "warn.py"
check_contains "warn.py" 'parent / "logs"'    "warn: log path .parent/logs"
check_contains "warn.py" "GREEN"              "warn: GREEN severity"
check_contains "warn.py" "YELLOW"             "warn: YELLOW severity"
check_contains "warn.py" "RED"                "warn: RED severity"
check_contains "warn.py" "def run_checks"     "warn: run_checks()"
check_contains "warn.py" "def display"        "warn: display()"
check_contains "warn.py" "def display_if_any" "warn: display_if_any()"
check_contains "warn.py" "log_too_large"      "warn: log_too_large trigger"
check_contains "warn.py" "missing_snapshot"   "warn: missing_snapshot trigger"
check_contains "warn.py" "config_missing"     "warn: config_missing trigger"
check_contains "warn.py" "vault_path_mismatch" "warn: vault_path_mismatch trigger"
check_contains "warn.py" "module_error"       "warn: module_error trigger"

_section_result "core / flow / warn"

# ══════════════════════════════════════════════════════════════════════════════
# 6. GUI app.py
# ══════════════════════════════════════════════════════════════════════════════
_head "6. GUI app.py"

check_python_syntax "app.py"
check_contains "app.py" "def is_available"  "app.py: is_available()"
check_contains "app.py" "def launch"        "app.py: launch()"
check_contains "app.py" "def status"        "app.py: status()"
check_contains "app.py" "class AppWindow"   "app.py: AppWindow class"
check_contains "app.py" "def run"           "app.py: run()"
check_contains "app.py" "def _load_data"    "app.py: _load_data()"
check_contains "app.py" "_build_status_tab"   "app.py: status tab builder"
check_contains "app.py" "_build_warnings_tab" "app.py: warnings tab builder"
check_contains "app.py" "_build_commands_tab" "app.py: commands tab builder"
check_contains "app.py" "_build_help_tab"     "app.py: help tab builder"
check_contains "app.py" "module_loader"    "app.py: imports module_loader"
check_contains "app.py" "import warn"      "app.py: imports warn"
check_contains "app.py" "WAYLAND_DISPLAY"  "app.py: checks WAYLAND_DISPLAY gate"
check_not_contains "app.py" '"/home'       "app.py: no hardcoded /home"
check_not_contains "app.py" '"/mnt'        "app.py: no hardcoded /mnt"

check_contains "modules/gui/__init__.py" "_APP"     "gui/__init__: _APP reference"
check_contains "modules/gui/__init__.py" "app.py"   "gui/__init__: delegates to app.py"
check_not_contains "modules/gui/__init__.py" \
    "^import tkinter" "gui/__init__: no top-level tkinter import"

_section_result "GUI app.py"

# ══════════════════════════════════════════════════════════════════════════════
# 7. Guides folder
# ══════════════════════════════════════════════════════════════════════════════
_head "7. Guides folder"

guides=(
    "guides/README.md"
    "guides/beginner/quick_start.md"
    "guides/beginner/daily_use.md"
    "guides/intermediate/flow_guide.md"
    "guides/intermediate/warning_guide.md"
    "guides/intermediate/module_guide.md"
    "guides/advanced/config_reference.md"
    "guides/advanced/vault_structure.md"
    "guides/developer/build_steps.md"
    "guides/developer/module_api.md"
    "guides/developer/gui_guide.md"
)
for g in "${guides[@]}"; do
    if [[ -f "$TARGET/$g" ]]; then
        size=$(wc -c < "$TARGET/$g")
        if [[ $size -gt 300 ]]; then
            _pass "$g  (${size}b)"
        else
            _fail "$g  (too small: ${size}b)"
        fi
    else
        _fail "$g  (not found)"
    fi
done

_section_result "Guides folder"

# ══════════════════════════════════════════════════════════════════════════════
# 8. Vault path config
# ══════════════════════════════════════════════════════════════════════════════
_head "8. Vault / path config"

# vault_root relative (already checked in section 2, repeat as section gate)
if [[ -n "$vault_root" && "$vault_root" != /* ]]; then
    _pass "vault_root relative: $vault_root"
else
    _fail "vault_root missing or absolute"
fi

# vault_folders count
folder_count=$(python3 -c "
import json
d = json.load(open('$TARGET/configs/system_config.json'))
print(len(d.get('vault_folders', {})))
" 2>/dev/null || echo "0")
if [[ "$folder_count" -ge 11 ]]; then
    _pass "vault_folders: $folder_count entries (expected 11)"
else
    _fail "vault_folders: $folder_count entries (expected 11)"
fi

# guides key present
check_contains "configs/system_config.json" '"guides"' "system_config: guides key in vault_folders"

# No absolute paths in any Python file
abs_found=0
while IFS= read -r -d '' f; do
    if grep -qP '["'"'"'](/home|/mnt|/root|/var)' "$f" 2>/dev/null; then
        _fail "absolute path found in: ${f#$TARGET/}"
        abs_found=1
    fi
done < <(find "$TARGET" -name "*.py" -not -path "*/__pycache__/*" -print0)
[[ $abs_found -eq 0 ]] && _pass "No absolute paths in Python files"

_section_result "Vault / path config"

# ══════════════════════════════════════════════════════════════════════════════
# 9. Step stamps
# ══════════════════════════════════════════════════════════════════════════════
_head "9. Step stamps / build order"

check_contains "guides/developer/build_steps.md" "10 / 10" \
    "build_steps.md: 10/10 stamp"
check_contains "guides/developer/build_steps.md" "COMPLETE" \
    "build_steps.md: COMPLETE marker"
check_contains "guides/README.md" "10 / 10" \
    "README.md: 10/10 stamp"

# All 11 steps present
all_steps=1
for i in $(seq 0 10); do
    if ! grep -q "## Step $i" "$TARGET/guides/developer/build_steps.md" 2>/dev/null; then
        _fail "build_steps.md: missing ## Step $i"
        all_steps=0
    fi
done
[[ $all_steps -eq 1 ]] && _pass "build_steps.md: Steps 0–10 all present"

# No numbered filenames
numbered=$(find "$TARGET" -type f | grep -P '_step\d|_v\d|\bstep\d' || true)
if [[ -z "$numbered" ]]; then
    _pass "No numbered/step filenames"
else
    _fail "Numbered filenames found: $numbered"
fi

_section_result "Step stamps / build order"

# ══════════════════════════════════════════════════════════════════════════════
# 10. Shell scripts
# ══════════════════════════════════════════════════════════════════════════════
_head "10. Shell scripts"

check_exec "scripts/hotkey_prompter.sh"
check_exec "scripts/hotkey_cleaner.sh"
check_exec "scripts/terminal_prompter.sh"
check_exec "scripts/terminal_cleaner.sh"
check_exec "scripts/terminal_manager.sh"

# Each sh must reference modules/ not a hardcoded path
for sh in hotkey_prompter hotkey_cleaner terminal_prompter terminal_cleaner terminal_manager; do
    f="scripts/${sh}.sh"
    check_contains "$f" "../modules/" "$sh.sh: calls ../modules/"
    check_not_contains "$f" "/home" "$sh.sh: no /home path"
done

# Scripts must use SCRIPT_DIR pattern
check_contains "scripts/hotkey_prompter.sh" 'SCRIPT_DIR' "hotkey_prompter: uses SCRIPT_DIR"
check_contains "scripts/terminal_prompter.sh" 'SCRIPT_DIR' "terminal_prompter: uses SCRIPT_DIR"

_section_result "Shell scripts"

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
echo -e "\n${C_HEAD}══════════════════════════════════════════════${RESET}"
echo -e "${C_HEAD}  VERIFY SUMMARY${RESET}"
echo -e "${C_HEAD}══════════════════════════════════════════════${RESET}"
echo -e "  Checks passed : ${C_OK}$PASS${RESET}"
if [[ $FAIL -eq 0 ]]; then
    echo -e "  Checks failed : ${C_OK}$FAIL${RESET}"
else
    echo -e "  Checks failed : ${C_FAIL}$FAIL${RESET}"
fi
[[ $WARN_COUNT -gt 0 ]] && echo -e "  Warnings      : ${C_WARN}$WARN_COUNT${RESET}"
echo

if [[ $FAIL -eq 0 ]]; then
    echo -e "  ${C_OK}ALL CHECKS PASSED${RESET}"
    exit 0
else
    echo -e "  ${C_FAIL}$FAIL CHECK(S) FAILED — see above${RESET}"
    exit 1
fi
