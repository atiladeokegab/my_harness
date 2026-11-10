# The Claude Code layer

What `install.sh` puts into `~/.claude`, and the pieces you add by hand.

## Instructions: `~/.claude/CLAUDE.md`

Installed from `claude/CLAUDE.md`. A different existing file is backed up next to it and replaced,
and so is your own edit when you re-run the installer: keep a copy, or skip it with `--no-claude`.
It holds the hub protocol every session follows (planning, ownership, the worker loop, token habits,
messaging across Claude, Codex and agy), how the agents should work with you, and engineering
defaults. Rename the agents and cut what you do not use. Project rules go in each repo's `CLAUDE.md` (`templates/project-CLAUDE.md`).

## Settings and hooks: `~/.claude/settings.json`

With no `settings.json`, the installer copies `claude/settings.json`: agent teams on, an auto-mode
skeleton to fill in, and the **heartbeat hooks** (`PostToolUse`, `Stop`, `UserPromptSubmit` run
`$HUB_DIR/heartbeat.sh`). The heartbeat is what lets the health watch tell a working agent from a
stuck one and lets `hubwaked` see a fresh turn; it writes nothing for a session that is not a hub
agent. With an existing `settings.json` the installer only adds the agent-teams flag; merge the
hooks yourself with the `jq` loop in `runbooks/install-factory-timers.md` section 4, which also
covers each agent's own `~/.claude-<name>/settings.json` and the optional delivery hooks
(`stop-deliver.js`, `inbox-surface.js`, `session-ship-check.js`).

## Skills, and the plugin

`install.sh` copies every skill in `claude/skills/` into `~/.claude/skills/`, which is all Claude
Code needs. It also assembles `$HUB_DIR/plugin/`: the same skills plus the hooks (`hub/hooks/*.js`,
including `paste-intake.js`, which labels pasted text before an agent acts on it), packaged for both
CLIs. Codex has no skills directory, so the plugin is how a Codex seat gets them:

```bash
codex  plugin marketplace add "$HUB_DIR/plugin" && codex plugin add hub@hub
claude plugin marketplace add "$HUB_DIR/plugin" && claude plugin install hub@hub   # optional
```

Installing the plugin in Claude Code as well gives each skill twice (`intake` and `hub:intake`) and
turns on its hooks; do it only if you want the hooks from the plugin rather than from
`settings.json`. After editing a skill, re-run `install.sh` and refresh the plugin
(`plugin/README.md`).

## Memory

Claude Code keeps a per-project memory under `~/.claude/projects/<project-slug>/memory/` and loads
its `MEMORY.md` into every session in that project. Left alone it grows into one long file. The
layout that has held up: `MEMORY.md` is only a router (a few topic indexes and the handful of lessons
every session needs), each topic index lists its lessons one line each, and each lesson is one
fact in its own file with frontmatter saying when it applies, why, and how to apply it.
`templates/memory/` is that layout with no memories in it; copy it in and tell your agents to keep
to it in your `CLAUDE.md`.
