# Claaaude 🐑

A desktop mascot that shows the status of your running [Claude Code](https://claude.ai/claude-code) sessions. Each session gets its own animated sheep walking across the bottom of your screen.

![idle](https://img.shields.io/badge/idle-sleeping-yellow) ![working](https://img.shields.io/badge/working-running-green) ![ask](https://img.shields.io/badge/ask-question-red) ![done](https://img.shields.io/badge/done-finished-brightgreen)

## How it works

Claude Code hooks write the session state to `$XDG_RUNTIME_DIR/claude_mascot_states/<PID>` (falls back to `/tmp` if `XDG_RUNTIME_DIR` is unset). The mascot polls these files and spawns one sheep per active session, each showing:

- The current state (colored dot + label)
- The working directory name
- A speech bubble when Claude needs your attention

## Requirements

- Python 3
- PyQt5
- wmctrl
- A Linux desktop with X11 or XWayland

## Install

```bash
sudo apt install python3-pyqt5 wmctrl
python3 install.py        # sets up Claude Code hooks + autostart
```

The installer will:
1. Register hooks in `~/.claude/settings.json` so Claude Code reports its state
2. Create a `.desktop` entry in `~/.config/autostart/` so the mascot starts on login

To start the mascot right away (without logging out):

```bash
python3 claude_mascot.py &
```

## Controls

- **Left-click + drag** — move the strip vertically
- **Right-click** — quit

## Uninstall

```bash
python3 install.py --remove
```

This removes both the Claude Code hooks and the autostart entry.

## License & Attribution

The **Python code** (`claude_mascot.py`, `install.py`) is released under the [MIT License](LICENSE).

The **sprite assets** (BMP files, WAV sounds, icon, cursor) in `assets/` are **not** covered by the MIT license. They are the property of their respective owners (see below) and are included for educational and preservation purposes only.

### Original work

This project is a reimagining of **Esheep** (eSheep / Desktop Sheep), a classic Windows desktop pet from the late 1990s.

Original codebase owned by **Village Center, Inc.** (defunct).

All character sprites in bitmap images owned by **Fuji Television Network, Inc.** and **Robot Communications Inc.**

- Artwork: **NOMURA Tatsutoshi** (Robot)
- Producer: **SAITO Akimi** (Fuji TV)
- Poe's voice: **HARA Masumi**

The original C source code (`Scmpoo.c`) and Windows resource files are preserved in `assets/` for historical reference.
