# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible-based Ubuntu desktop provisioning project. Automates installation and configuration of development tools, GNOME extensions, security tools, and a Claude Code mascot integration. Targets localhost only.

## Running

```bash
# First time: install Ansible galaxy dependencies
make install

# Run the playbook (prompts for sudo password)
make
```

Underlying command: `ansible-playbook playbook.yml --ask-become-pass`

## Architecture

Single Ansible role (`roles/customize/`) with task files included sequentially from `tasks/main.yml`:

- **bash.yml** — Shell prompt (bash-git-prompt), aliases (`d`, `dc`, `c`), custom git functions
- **git.yml** — Git identity, gitconfig/gitignore templates, `act` tool
- **claude.yml** — Claude Code permissions hook, `claudio` tool, mascot installation
- **tools.yml** — Snap/APT packages (PhpStorm, VS Code, terminator, etc.), KeePass cron backup, ulauncher, espanso, JAN AI
- **docker.yml** — Docker engine + compose v2 plugin
- **python.yml** — Virtual environment at `~/.venvs/myEnv`
- **security.yml** — ClamAV antivirus with daily scan cron
- **android.yml** — Waydroid (Android emulator)

Templates live in `roles/customize/templates/` (gitconfig, gitignore, MCP config).

## Claaaude Mascot (`templates/claude/`)

PyQt5 desktop widget showing live Claude Code session status as animated sheep sprites. State files written to `$XDG_RUNTIME_DIR/claude_mascot_states/<PID>` by Claude Code hooks. `install.py` registers the hooks.

## Backups

`backups/keepass.kdbx` is auto-committed every 5 minutes via cron. `backups/thunderbird/` contains a Thunderbird profile snapshot.

## GNOME Extensions

The 24+ extension IDs with version pins are defined as variables in `playbook.yml`, not in the role.
