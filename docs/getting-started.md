# Getting started

## 1. Install

```bash
git clone https://github.com/atiladeokegab/my_harness.git ~/code/my_harness
cd ~/code/my_harness
./install.sh --dry-run    # read this first
./install.sh
source ~/.bashrc
```

What the installer does, in order:

| Step | Result |
|---|---|
| hub | Copies the hub code, docs, tests and runbooks to `~/hub` and seeds an empty `board.json`. |
| commands | Links `hub`, `hubmsg` and `hubwaked` into `~/.local/bin`. |
| claude | Installs `~/.claude/CLAUDE.md` and the `design-system` skill. Adds one env key to an existing `settings.json`, or installs the template if you have none. |
| codex | Links `~/.codex/AGENTS.md` → `~/hub/AGENTS-codex.md`, if Codex is present. |
| shell | Adds one line to `~/.bashrc` that sources `~/hub/shell.sh`. |

Anything it replaces is saved next to the original as `<file>.bak.<timestamp>`. It never
touches `board.json`, `events.jsonl`, `inbox/` or `wake/`. Flags: `--no-claude`,
`--no-codex`, `--no-shell`, `--hub-dir DIR`.

**Already have a `~/.claude/CLAUDE.md`?** The installer backs yours up and installs this
one. Merge your own rules back into the "How I work" section, then delete the backup.

## 2. Start the agents

Type an agent's name in any shell:

```bash
zeus          # the lead, on your default ~/.claude account
apollo        # a worker, on ~/.claude-apollo
hermes
athena
prometheus    # the Codex worker
```

Each one runs in a tmux session called `hub-<name>`, so it survives detaching and closing
the terminal. `Ctrl-b d` detaches. Typing the name again re-attaches.

**First run per agent:** pick a theme, sign in to *that agent's* account, accept folder
trust, then detach. You only do this once. `hubaccounts` shows who still needs a login. For
Prometheus, run `/login` inside the session.

**Only one account?** Run `zeus` alone and let it spawn subagents, or run workers on the
same account and accept a shared rate limit. Everything else still works.

Where an agent lands: `apollo myproject` starts it in `~/code/myproject`. A bare `apollo`
starts in the repo you're standing in, or in `$HUB_HOME_PROJECT` if you set one, or
otherwise in the current directory. An agent started inside a repo is automatically
scoped to that repo's tasks.

```bash
hubs          # who's running, relay health, which accounts are signed in
hubkill apollo
hubkill all
```

## 3. Your first cycle

**Plan with Zeus.** Describe the work, let it explore the code, and settle the approach and
the risks. Don't create tasks yet.

**Write the tasks.** Ask Zeus to decompose the plan. Each task carries its context, the
files it owns, the approach, and checkable acceptance criteria. See
[`templates/task-detail.md`](../templates/task-detail.md).

```bash
hub list                  # what's on the board
hub show T-001            # one task in full
```

**Workers execute.** In each worker session, say "check the board". The worker runs
`hub brief`, `hub next`, `hub claim`, does the work, then `hub done --note` and reports
back. Finishing a task queues a message to anyone it unblocked and prints the `hubmsg`
command that wakes them.

**Watch it happen.**

```bash
hub events --tail 30      # the audit trail: every transition, by whom
```

## 4. Set up a project

For each repo agents will work in:

1. Copy [`templates/project-CLAUDE.md`](../templates/project-CLAUDE.md) to
   `<repo>/CLAUDE.md` and fill it in. It is the brief an agent reads cold. Keep it short, and
   put anything that has cost you an hour under "Traps".
2. `ln -s CLAUDE.md AGENTS.md` so Codex gets the same brief, or use
   [`templates/project-AGENTS.md`](../templates/project-AGENTS.md).
3. Optionally copy [`templates/project-settings.json`](../templates/project-settings.json)
   to `<repo>/.claude/settings.json` to pre-approve routine commands.
4. If the project has a visual identity, ask Claude to "load the design-system skill and
   write `<project>-design`".

## 5. Check it works

```bash
cd ~/hub && python3 tests/test_board.py && python3 tests/test_messaging.py
HUB_AGENT=Zeus hub new "hello" --detail "smoke test"
hub list
```

In a Claude session, `ListAgents` should list the other running Claude agents. If it shows
no peers, see "The one load-bearing constraint" in
[`hub/ARCHITECTURE.md`](../hub/ARCHITECTURE.md): the `sessions/` symlink.

## Gotchas

- **WSL:** enter with `wsl ~`, not plain `wsl`. Plain `wsl` keeps your Windows directory,
  so agents launch in `/mnt/c/...`, which is the wrong place and slow.
- `~/.local/bin` must be on `PATH`. The installer tells you if it isn't.
- `shell.sh` is bash. If your login shell is zsh, run agents from a bash shell.
- Don't delete `~/hub/.board.lock`. It's a zero-byte anchor for `flock`.
