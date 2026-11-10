# Optional: an Antigravity (`agy`) seat

A hub seat can run Google's Antigravity CLI instead of Claude Code or Codex. It takes tasks from the
board and is reached with `hubmsg`, like a Codex seat.

## Configure

| Name | What |
|---|---|
| `HUB_AGY_AGENTS` | space-separated names of agy seats, e.g. `Hephaestus` (empty by default) |
| `HUB_AGY_MODEL` | the model the launcher picks (default: Flash) |

Put them in `~/.config/hub/env` or your shell profile. Each name becomes a launcher command (its name
in lower case) once `shell.sh` is sourced again.

## Install

The launcher accepts only the agy version it was tested with, and checks it. Follow
`runbooks/antigravity-seat.md`: install the pinned tarball (never the auto-update manifest), sign in
once with the account whose plan you mean to use, and read its section on the consumer terms first.

What the harness gives the seat:

- `AGENTS-gemini.md`: its instructions (linked as `~/.gemini/GEMINI.md`).
- `agy/hooks.json`, `agy/settings.json`: heartbeat and inbox hooks, merged by the launcher.
- `agy-status.sh`: its statusLine, which records state and quota buckets (never the account) in
  `$HUB_DIR/state/<agent>.agy.json`, so the health watch can mark it rate limited.
- `hubaccounts` shows whether each agy seat is signed in.
