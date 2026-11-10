# hub plugin

The skills and hooks this machine's agents share, packaged so Claude Code and Codex load the
same files from the same place.

```bash
claude plugin marketplace add ~/hub/plugin && claude plugin install hub@hub
codex   plugin marketplace add ~/hub/plugin && codex   plugin add hub@hub
```

**Why this is a subdirectory and not `~/hub` itself.** Both CLIs *copy* the marketplace
root into their own cache. Pointing them at `~/hub` copied 15 MB, including a frozen
snapshot of `board.json`, `events.jsonl` and `inbox/` — live state, stale the moment it
was written, sitting where something might later read it. The plugin gets its own
directory so the copy contains only the plugin.

## What is in it

| Component | What it does |
|---|---|
| `skills/clean-repo` | Never ship harness output into a repo other people work in |
| `skills/hub-planning` | Self-contained team planning: spec and plan to `~/hub/projects/`, plan → board |
| `skills/development` | Focused debugging, behavior tests, review and verification; small tasks skip ceremony |
| `skills/intake` | Whose words is a paste? Asks, files outside material, traces the user's points |
| `skills/3d-model-workflow` | A real place or machine as a browser 3D model: contract, LiDAR ground, eras, look, GPU stills, tagged deploy |
| `hooks/session-ship-check.js` | `SessionStart`: warns if harness files would reach someone else's tree |
| `hooks/paste-intake.js` | `UserPromptSubmit`: labels pastes as Wispr dictation or unknown; always exits 0 |

The hook runs `hub ship-check --quiet`, which prints nothing unless there is something to
say — a clean repo costs a silent 50 ms and adds nothing to context. It always exits 0: a
hook that breaks session startup is a hook somebody deletes.

## Refreshing after an edit

```bash
claude plugin marketplace update hub          # local marketplaces update in place
codex plugin remove hub@hub && codex plugin add hub@hub
```

`codex plugin marketplace upgrade` only works for **Git** marketplaces — against a local
one it fails with "marketplace `hub` is not configured as a Git marketplace". Remove and
re-add instead.

A new or changed Codex hook needs trusting once via `/hooks` inside a Codex session.
A hook that seems not to fire usually needs that, not a reinstall.

Skills live here and nowhere else. There is no copy in `~/.claude/skills/`; that was the
duplication that made `ponytail-AGENTS.md` drift, and it is not repeated.
