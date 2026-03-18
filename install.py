#!/usr/bin/env python3
"""
Install Claude Code hooks for claude_mascot.py,
preserving any existing hooks.

Usage:
  python3 install.py             # install
  python3 install.py --remove    # uninstall
"""

import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "claude-mascot.desktop"
MASCOT_MARKER = "claude_mascot_state"  # used to detect our commands

# Hook commands per event.
# Each hook writes to $STATE_DIR/$PPID for multi-instance support.
# Uses XDG_RUNTIME_DIR if available, falls back to /tmp.
_STATE_DIR_SH = '${XDG_RUNTIME_DIR:-/tmp}/claude_mascot_states'
MASCOT_HOOKS: dict[str, str] = {
    "Stop":            f"mkdir -p {_STATE_DIR_SH} && echo done > {_STATE_DIR_SH}/$PPID",
    "Notification":    f"mkdir -p {_STATE_DIR_SH} && python3 -c \"import sys,json; d=json.load(sys.stdin); print('ask:'+d.get('message','?'))\" > {_STATE_DIR_SH}/$PPID",
    "UserPromptSubmit":f"mkdir -p {_STATE_DIR_SH} && echo working > {_STATE_DIR_SH}/$PPID",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"❌  {SETTINGS_PATH} contains invalid JSON: {e}")
    return {}


def backup(settings_path: Path) -> Path:
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = settings_path.with_suffix(f".json.bak_{ts}")
    shutil.copy2(settings_path, bak)
    return bak


def save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def is_mascot_cmd(cmd: str) -> bool:
    return MASCOT_MARKER in cmd


def make_hook_entry(cmd: str) -> dict:
    return {"type": "command", "command": cmd}


# ─── install ──────────────────────────────────────────────────────────────────

def install() -> None:
    settings = load_settings()

    if SETTINGS_PATH.exists():
        bak = backup(SETTINGS_PATH)
        print(f"📦  Backup created: {bak}")

    hooks_root: dict = settings.setdefault("hooks", {})
    changed = []

    for event, cmd in MASCOT_HOOKS.items():
        groups: list = hooks_root.setdefault(event, [])

        # Already present?
        already = any(
            is_mascot_cmd(h.get("command", ""))
            for g in groups
            for h in g.get("hooks", [])
        )
        if already:
            print(f"⏭   {event}: mascot hook already present, skipped")
            continue

        # Add a new minimal group (no matcher = always applies)
        groups.append({"hooks": [make_hook_entry(cmd)]})
        changed.append(event)

    if changed:
        save_settings(settings)
        print(f"✅  Hooks added for: {', '.join(changed)}")
        print(f"📝  Settings updated: {SETTINGS_PATH}")
    else:
        print("ℹ️   Nothing to do, all hooks already present.")

    install_autostart()


# ─── autostart ────────────────────────────────────────────────────────────────

def install_autostart() -> None:
    mascot_script = Path(__file__).resolve().parent / "claude_mascot.py"
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Claaaude\n"
        f"Exec=python3 {mascot_script}\n"
        "Hidden=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    print(f"✅  Autostart created: {AUTOSTART_FILE}")


def remove_autostart() -> None:
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        print(f"🗑   Autostart removed: {AUTOSTART_FILE}")
    else:
        print("ℹ️   No autostart file found.")


# ─── remove ───────────────────────────────────────────────────────────────────

def remove() -> None:
    if not SETTINGS_PATH.exists():
        print("ℹ️   No settings.json file found.")
        return

    settings = load_settings()
    hooks_root: dict = settings.get("hooks", {})
    changed = []

    for event in list(MASCOT_HOOKS.keys()):
        groups: list = hooks_root.get(event, [])
        if not groups:
            continue

        new_groups = []
        for g in groups:
            new_hooks = [
                h for h in g.get("hooks", [])
                if not is_mascot_cmd(h.get("command", ""))
            ]
            if new_hooks:
                new_groups.append({**g, "hooks": new_hooks})
            # empty group → removed

        if new_groups != groups:
            changed.append(event)
            if new_groups:
                hooks_root[event] = new_groups
            else:
                del hooks_root[event]

    # Clean up "hooks" key if empty
    if not hooks_root:
        settings.pop("hooks", None)

    if changed:
        bak = backup(SETTINGS_PATH)
        print(f"📦  Backup created: {bak}")
        save_settings(settings)
        print(f"🗑   Hooks removed for: {', '.join(changed)}")
        print(f"📝  Settings updated: {SETTINGS_PATH}")
    else:
        print("ℹ️   No mascot hooks found, nothing to remove.")

    remove_autostart()


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if "--remove" in sys.argv:
        remove()
        return

    install()

    print()
    print("━" * 50)
    print("Start the mascot now:")
    print("  python3 claude_mascot.py &")
    print()
    print("The mascot will start automatically on next login.")


if __name__ == "__main__":
    main()