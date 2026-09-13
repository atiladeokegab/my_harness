# Claude Code facts: verified, not recalled

These were established by testing against the installed binary while building the hub
(Claude Code v2.1.259). Documentation and secondhand summaries got several of them
**wrong**. This area moves fast, so re-verify after an upgrade (`claude --help`, and
experiment) before relying on any of it.

## True

- `CLAUDE_CODE_SESSION_NAME=Apollo claude` names an interactive session, and peers address
  it by that name.
- Cross-session messaging runs over a per-session **Unix domain socket**
  (`$XDG_RUNTIME_DIR/cc-socks/<pid>.sock`). It's genuinely local: no MCP, no network. The
  `SendMessage` and `ListAgents` tools address peers by bare name.
- Session discovery reads one JSON file per live session in `<config-dir>/sessions/`.
- `claude agents --json` is the scriptable session list. Subcommands include
  `agents | attach | logs | stop | rm | respawn`.
- `/rename` and `/color` help tell running sessions apart.
- `--append-system-prompt` injects text at launch. The hub uses it to hand each agent its
  `hub brief` on arrival.

## False: don't repeat these

- There is **no `--name` flag.** `claude --bg` names the session after the prompt text.
- There is **no `claude daemon` subcommand.**
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` does **not**, on its own, give independently
  launched sessions the `TaskCreate`/`TaskList`/`TaskUpdate` tools. Those appear in a real
  team context, with a lead spawning teammates. The file-based board does the actual work.

## Config-dir isolation vs discovery

`CLAUDE_CONFIG_DIR` isolates credentials, settings and history, which is what lets several
accounts run at once on one machine. But discovery is scoped to the config dir, so isolated
dirs can't see each other: `claude agents` returns `[]` and messaging silently stops.
Symlinking `<config>/sessions` → `~/.claude/sessions` restores discovery *and*
cross-session `SendMessage`. This was confirmed with a round trip between two different
config dirs. Each config dir still needs its own folder-trust acceptance and onboarding.

## Sharp edges

- **`CLAUDE_CODE_*` variables are stripped from Bash tool subprocesses**, so a script an
  agent runs can't read `$CLAUDE_CODE_SESSION_NAME` to learn who it is. `$TMUX`,
  `$TMUX_PANE`, custom variables and `CLAUDE_CONFIG_DIR` do survive. The hub sets
  `$HUB_AGENT` for this reason, and `board.py` falls back to walking up `/proc` to an
  ancestor that has the name.
- **The socket is not a public interface.** Its wire protocol is undocumented, so a shell
  script can't deliver a message into a session. Only a Claude session calling
  `SendMessage` can interrupt another one. Anything built outside Claude that notifies an
  agent is either a passive queue or, as `hubmsg` does, a keystroke into its terminal.
- Sockets are named by **PID**, not agent. A clean exit removes its own; a killed session
  leaks one. Only ever prune sockets whose PID is gone.
