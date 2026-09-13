# Customising

## Rename the agents or change the roster

Set these **before** `shell.sh` is sourced, meaning above the hub line in `~/.bashrc`:

```bash
export HUB_LEAD=Ada                          # the planner; uses your default ~/.claude
export HUB_CLAUDE_AGENTS="Ada Grace Linus"   # Claude Code agents
export HUB_CODEX_AGENTS="Ken"                # Codex agents ("" for none)
[ -f "$HOME/hub/shell.sh" ] && . "$HOME/hub/shell.sh"
```

Each name becomes a lower-case shell command (`ada`, `grace`, `ken`) and a tmux session
(`hub-ada`). Non-lead Claude agents get their own config directory, `~/.claude-<name>`.
The board has no roster, so any name works.

Then update the names in `~/.claude/CLAUDE.md` and `~/hub/AGENTS-codex.md`. They tell each
agent who leads and who can't be reached with `SendMessage`.

## Where agents land

| Variable | Default | Effect |
|---|---|---|
| `HUB_CODE_DIR` | `~/code` | `apollo <name>` resolves `<name>` to `$HUB_CODE_DIR/<name>`. |
| `HUB_HOME_PROJECT` | *(none)* | A bare `apollo` from outside any repo lands here. |
| `HUB_DIR` | `~/hub` | Where the board, inboxes and runbooks live. |

## A second, separate hub

To keep one project's tasks and inboxes entirely apart (a hackathon, a client), run a
second hub with its own directory, relay and agent names. Both `hub` and `hubmsg` honour
`HUB_DIR`.

```bash
./install.sh --hub-dir ~/hub-side --no-claude --no-codex --no-shell --no-bin
```

`--no-bin` keeps `~/.local/bin/hub` pointing at your main hub. The same `hub` command
serves both, because it reads `$HUB_DIR` first.

Then, in a shell dedicated to it:

```bash
export HUB_DIR=~/hub-side HUB_RELAY_SESSION=hub-relay-side
export HUB_CLAUDE_AGENTS="Zeus" HUB_CODEX_AGENTS="Prometheus-side"
. ~/hub-side/shell.sh
prometheus-side
```

Give the second hub's agents **different names** from the first, because tmux sessions are
named after agents. Prefix every call aimed at it with the directory, including
`HUB_DIR=~/hub-side hub receive <id>` when a wake arrives. An empty board must be seeded
(`{"next_id": 1, "tasks": [], "schema_version": 1}`); the installer does that for you.

## Multiple accounts

Claude Code keeps credentials, settings and history per *config directory*. `shell.sh`
gives every non-lead agent `CLAUDE_CONFIG_DIR=~/.claude-<name>` and symlinks three things
back to `~/.claude`:

| Link | Why |
|---|---|
| `sessions/` | **Load-bearing.** Session discovery reads it. Without the link, agents can't see each other and messaging goes silent with no error. |
| `CLAUDE.md` | Every agent reads the same protocol. |
| `skills/` | Every agent gets the same skills. |

`settings.json` is **copied**, not linked, because accounts differ in which models they can
use. Edit each agent's copy on its own.

## Skills

Global skills live in `~/.claude/skills/<name>/SKILL.md` and project skills in
`<repo>/.claude/skills/<name>/SKILL.md`. A skill is a folder with a `SKILL.md` whose
frontmatter `description` says when to load it, including trigger words. Put reference
material (screenshots, SVGs, scripts) next to it.

Codex has its own skills mechanism and can't load Claude skills. If a Codex agent needs
the content, point it at the file path.

To add a skill to this harness so `install.sh` ships it, put it in `claude/skills/<name>/`.

## Settings and auto mode

`claude/settings.json` is a template, and the installer only uses it if you have no
settings. The `autoMode.environment` block tells the auto-mode classifier about your
setup: trusted repos, where secrets live, what counts as production. Fill in the `<...>`
placeholders; the more specific it is, the fewer wrong prompts you get.

## Codex specifics

- Codex reads `AGENTS.md`, never `CLAUDE.md`. `~/.codex/AGENTS.md` links to
  `~/hub/AGENTS-codex.md`.
- It launches with `--sandbox workspace-write --add-dir ~/hub`. Both flags are required.
  See `runbooks/codex-sandbox-blocks-hub.md`.
- Its sandbox can't reach the tmux socket, so its wakes go through the `hubwaked` relay,
  which starts automatically with the first Codex agent.
