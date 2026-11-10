# my_harness

My whole Claude Code setup, packaged so you can run it too: **a team of AI coding agents on
one machine** that share a task board, message each other and hand work back and forth,
plus the global instructions, engineering defaults, runbooks and design skill they all
work from.

Five named sessions by default. **Zeus** plans and decomposes. **Apollo**, **Hermes** and
**Athena** (Claude Code) and **Prometheus** (OpenAI Codex) execute. Each runs in its own
tmux session on its own account, so they don't share a context window or a rate limit.

Everything is plain files and Unix primitives. There's no server, no database and no
network, and the only hard dependencies are `python3`, `tmux` and `git`.

```bash
git clone https://github.com/atiladeokegab/my_harness.git
cd my_harness
./install.sh --dry-run     # see exactly what it would change
./install.sh
source ~/.bashrc
zeus                       # start the lead agent. Ctrl-b d to detach.
```

### Five minutes to a first task

With only `python3`, `tmux`, `git` and Claude Code installed:

1. `./install.sh --dry-run`, then `./install.sh` and `source ~/.bashrc` (about a minute). If it notes that
   `~/.local/bin` is not on `PATH`, add the line it prints.
2. `zeus`: sign in on first run, accept folder trust, `Ctrl-b d` to detach.
3. `hub new "Add a --version flag" --project myrepo` puts a task on the board; `hub list` shows it.
4. In a second shell, `apollo myrepo` starts a worker in `~/code/myrepo`. Ask it to take the next task: it runs `hub next`,
   `hub claim`, does the work in its own worktree, and `hub done` runs the repo's `make check` if it has one.
5. `hubs` shows who is running; `hub show <id>` shows the handoff note.

One account is enough to try it: run `zeus` alone and let it start sub-agents. The full
walkthrough, including plan → tasks → execute with the lead, is
[docs/getting-started.md](docs/getting-started.md).

---

## Why it's built this way

**One session means one context, one rate limit, one thing at a time.** The hub gives you
agents that hold separate contexts, run on separate accounts and pick up work written by
whoever planned it, without you copying context between terminals.

**The rule that drives everything: a task must be executable by an agent that never saw
the conversation which produced it.** So planning happens up front with the lead, and every
task on the board carries its own context, files, approach and acceptance criteria.

**Two vendors on purpose.** A second model family has different blind spots. That makes
Codex worth pointing at review, and at anything Claude has got stuck on. The board is plain
files, so Codex needed no changes to use it. Messaging did, and `hubmsg` handles it.

**Lessons get written down.** Every bug that took more than an hour becomes a runbook, and
every agent is told to check the runbooks before debugging. Every design decision becomes an
acceptance criterion in a skill.

---

## What's inside

| Path | What it is |
|---|---|
| [`install.sh`](install.sh) | Idempotent installer. Backs up anything it replaces and never touches board data. Re-run it after `git pull` to upgrade. |
| [`hub/`](hub/) | The multi-agent hub: `board.py` (the `hub` CLI), `gh_sync.py` (`hub gh-sync`), `live.py` (`hub live`), `spec.py` and `prd.py` (`hub spec`, `hub prd`: the PRD tree), `autonomy.py` (`hub agents`: per-agent phases), `workspace.py` (`hub ws`, a worktree per claim), `clean_repo.py` (`hub init-repo`, `hub ship-check`, `hub scrub`), `dashboard.py` (`hub dashboard`), `hub_trace.py` (`hub trace`), `map.py` (`hub map`), `hubmsg`, `hubwaked`, `shell.sh`, optional agent hooks (`hooks/`), the optional factory (`dispatch.py`, `run.py`, `systemd/`, `factory.example.json`), and their test suites (`make check`). [`HUB.md`](hub/HUB.md) is the index to the operating manual in [`hub/docs/hub/`](hub/docs/hub/). |
| [`claude/CLAUDE.md`](claude/CLAUDE.md) | Global instructions for every session: the hub protocol, how I like to work, and engineering defaults (uv, testing, deploys). |
| [`claude/settings.json`](claude/settings.json) | Settings template with agent teams on, the heartbeat hooks and an auto-mode skeleton. What the installer does to `~/.claude`, the plugin and the memory layout: [docs/claude-code.md](docs/claude-code.md). |
| [`plugin/`](plugin/) | Manifests for packaging the skills and hooks as a Claude Code and Codex plugin; `install.sh` assembles it in `$HUB_DIR/plugin/`. |
| [`claude/skills/`](claude/skills/) | Thirteen skills every agent shares: planning, development, grilling, first-principles checks, intake, clean-repo, product design, a design system, Penpot design, Studio, 3D models and the hackathon pair. The [skills index](claude/skills/README.md) says when each loads and what it needs. |
| [`examples/refinery-design/`](examples/refinery-design/) | A real, filled-in design skill from a shipping product: the worked example. |
| [`runbooks/`](runbooks/) | Problems that already cost real time, each with the symptom, how to confirm it, and the fix. |
| [`templates/`](templates/) | Starting points for a project `CLAUDE.md` and `AGENTS.md`, project settings, runbooks, hub tasks, a memory layout, and a self-hosted Penpot. |
| [`docs/`](docs/) | The guides below. |

## The factory (optional)

The hub can also run as a small AI code factory, so work moves without you relaying it:

1. An issue labelled `agent`, or a red CI run on `main`, in a repo listed in `factory.json` becomes
   a board task. Issues from people without write access arrive wrapped as untrusted data, and
   only the lead can clear them.
2. A board change (or, as a fallback, every 2 minutes) starts a dispatcher that offers the next task
   to an idle agent, optionally on a fresh session, or runs it headless. `hub claim` gives the task
   its own worktree.
3. `hub done` runs the task's check (default `make check`) and refuses on failure; two failures
   block the task and tell the lead.
4. `hub live` opens the PR, holds it without an Evidence block, flags files outside the task's
   scope, never counts a builder's own approval, merges one PR at a time, smokes, promotes or
   reverts, and turns red CI into a fix request.
5. A health watch spots dialogs, rate limits, logins and stuck agents; snapshots copy the board
   to a bucket; a weekly task turns repeated review findings into rules.
6. Optionally, a project's PRD drives the board (`hub spec`): a change of intent is an approved
   delta, and the task tree is regenerated from it, rewinding only the work it collides with.
7. Each agent has an autonomy phase in `factory.json` (`off`, `trial`, `trusted`, `reviewer`,
   `lead`) that sets whether it is dispatched, reset per task, its time budget and what it may
   do. `hub agents` shows the table; a weekly pass demotes a trusted agent whose work was
   reverted and opens a task for the lead to promote a clean trial one.
8. `hub dashboard` serves the board, agents and their token spend on `127.0.0.1:8765`; the agent
   launcher starts it for you (`HUB_DASHBOARD=0` turns it off).

`hub pause "reason"` stops all of it. It is off until you write `factory.json` and switch on the
systemd timers: [`runbooks/install-factory-timers.md`](runbooks/install-factory-timers.md). How it
works: the factory section of [`hub/OVERVIEW.md`](hub/OVERVIEW.md).

## Docs

1. [**Getting started**](docs/getting-started.md): install, sign the agents in, and run
   your first plan → tasks → execute cycle.
2. [**Working agreement**](docs/working-agreement.md): how the team works. Plan first, one
   file one owner, queue and ping, and tests written by whoever didn't write the code.
3. [**Engineering defaults**](docs/engineering.md): the stack and tooling (uv for Python,
   Next.js, FastAPI and more), and the testing doctrine: *a check proves nothing until it
   has failed*.
4. [**Customising**](docs/customizing.md): rename the agents, change the roster, run a
   second hub for a separate project, and write your own skills.
5. [**Claude Code facts**](docs/claude-code-facts.md): what was verified against the
   binary about multi-session features, including what the docs got wrong.
6. [**Hub architecture**](hub/ARCHITECTURE.md) and [**design review**](hub/OVERVIEW.md):
   how the hub works, what's verified and what's only assumed, and the decisions worth
   arguing about.
7. [**Learnings**](docs/learnings.md): the lessons that cost real time, each with why and how
   to apply it.
8. [**The Claude Code layer**](docs/claude-code.md): instructions, settings and hooks, skills and
   the plugin, and the memory layout.
9. **Optional modules**, each off until you configure it: [WhatsApp to the lead](docs/optional/whatsapp.md),
   [a cloud VM and the Cloud Run spend guard](docs/optional/cloud-run.md), [an agy seat](docs/optional/agy.md),
   [a self-hosted Penpot](docs/optional/penpot.md), [demo takes recorded in the Cap fork](docs/optional/cap.md). The watchdog that relaunches dead sessions is in
   [`hub/OVERVIEW.md`](hub/OVERVIEW.md).

---

## Configuration: the roster

`hub/shell.sh` reads these from your environment (set them in `~/.bashrc` before the line
that sources it). Names are case-insensitive; the tmux session is `hub-<name>`.

| Variable | Default | What it sets |
|---|---|---|
| `HUB_DIR` | `~/hub` | Where the board, inboxes, runbooks and project notes live |
| `HUB_CODE_DIR` | `~/code` | Where your git checkouts live; `apollo myrepo` starts in `$HUB_CODE_DIR/myrepo` |
| `HUB_LEAD` | `Zeus` | The planning agent. It runs on the default `~/.claude` account and gets lead-only messages |
| `HUB_CLAUDE_AGENTS` | `Zeus Apollo Hermes Athena` | Claude Code agents, space-separated. Each non-lead one uses `~/.claude-<name>` |
| `HUB_CODEX_AGENTS` | `Prometheus` | Codex agents. Set it to `""` for a Claude-only team |
| `HUB_AGY_AGENTS` | empty | Antigravity CLI agents ([setup](docs/optional/agy.md)) |
| `HUB_REVIEWER` | `Hermes` | The agent `hub live` sends event PRs to |
| `HUB_HOME_PROJECT` | unset | Where a bare agent command starts when you are not inside a repo |
| `HUB_DASHBOARD` | on | `0` stops the launcher starting `hub dashboard` |

`HUB_AGENT` and `HUB_PROJECT` are set per session by the launcher; you do not set them yourself.
The optional factory has its own per-agent settings in `hub/factory.example.json`. Renaming the
agents and running a second hub: [docs/customizing.md](docs/customizing.md).

## What is specific to Claude Code, Codex or agy

The board, `hub` CLI, worktrees and `hubmsg` are plain files and shell, so any agent that can run
a command can use them. The rest is per CLI:

| | Claude Code | Codex CLI | agy (Antigravity CLI) |
|---|---|---|---|
| Instructions | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` → `$HUB_DIR/AGENTS-codex.md` | `~/.gemini/GEMINI.md` → `$HUB_DIR/AGENTS-gemini.md` |
| Skills | `claude/skills/`, all installed | through the plugin (`$HUB_DIR/plugin`, [docs/claude-code.md](docs/claude-code.md)) | not loaded |
| Launcher | `shell.sh`, one config dir per agent | `shell.sh`, `--sandbox workspace-write --add-dir $HUB_DIR` | `shell.sh`, for each name in `HUB_AGY_AGENTS`, pinned version ([setup](docs/optional/agy.md)) |
| Wakes | typed into the tmux pane, guarded | through the `hubwaked` relay (its sandbox can't reach tmux) | the relay and dialog guards recognise agy panes |
| Turn-end delivery hook (optional, needs `node`; [setup](runbooks/install-factory-timers.md)) | `hub/hooks/stop-deliver.js` | the same hook, from `~/.codex/hooks.json` | the same hook, `--format agy` |
| Agent-to-agent | `hubmsg`, plus Claude's own SendMessage between Claude sessions | `hubmsg` only | `hubmsg` only |

The factory's watchdog reads all three CLIs' busy footers, dialogs and rate-limit screens.

## Requirements

- Linux or WSL2 with **bash**, **tmux**, **git** and **python3**.
- **macOS:** also GNU coreutils and a modern bash, because macOS ships bash 3.2 and BSD
  tools: `brew install bash coreutils tmux python git`. The installer checks for both. The
  agent commands are installed as executables, so they work from the default zsh.
- [Claude Code](https://claude.com/claude-code) for the Claude agents.
- Optional: [Codex CLI](https://github.com/openai/codex) (`npm install -g @openai/codex`) for
  the Codex worker, [uv](https://docs.astral.sh/uv/) for Python work, `gh`, `make`, `node` for
  the optional agent hooks (turn-end message delivery, inbox surfacing, ship-check), and
  `graphify` for `hub map`.
- For the optional factory: Linux with systemd user units, `gh`, and `gcloud` if you want
  bucket snapshots.
- One account per agent if you want independent rate limits. You can start with a single
  account and run only `zeus`.

## Tests

```bash
cd hub
make check                        # every suite, 4 at a time, with the hub environment unexported
python3 tests/test_board.py       # or one: the board: state machine, locking, crash recovery
python3 tests/test_messaging.py   # the transport: wakes, relay, dedup, dialog, busy and reset guards
python3 tests/test_gh_sync.py     # hub gh-sync against a stub gh: guards, sync, crash safety
python3 tests/test_live.py        # hub live; also test_live_merge, test_gh_board, test_review
python3 tests/test_dispatch.py    # the factory; also test_watchdog, test_run, test_gh_sync_factory, test_inbox_gc, test_snapshot
python3 -m unittest tests.test_spec   # hub spec; also test_prd, test_prd_grill, test_spec_lint, test_trace
python3 -m unittest tests.test_autonomy   # phases; also test_dashboard, test_clean_repo, test_map, test_workspace, test_inbox_surface (needs node)
```

Run single suites with every `HUB_*` variable unset (`env -u HUB_DIR -u HUB_AGENT ...`), so nothing
touches your live hub. All suites are dependency-free and run against throwaway boards and scratch tmux sessions.
They never type into a real agent's pane.

## Related repos

Three tools the author runs beside the hub live in their own repos, each optional:

- [Studio](https://github.com/atiladeokegab/studio): a self-hosted Penpot plus a CLI that imports live
  product pages as editable boards and turns design comments into hub tasks. The
  [studio-design skill](claude/skills/studio-design/SKILL.md) is how agents work with it.
- [film](https://github.com/atiladeokegab/film): the demo-film pipeline, from a recorded take to a gated,
  edited film. The hub side is the hackathon skill's [film reference](claude/skills/hackathon/reference/film.md).
- [Cap fork](https://github.com/atiladeokegab/Cap): the screen recorder the takes come from (AGPL-3.0;
  no Cap code is in this repo). Setup glue: [docs/optional/cap.md](docs/optional/cap.md).

## Status and honesty

The hub has run real multi-agent work daily since it was built in September 2026. [`hub/ARCHITECTURE.md`](hub/ARCHITECTURE.md)
lists what has been verified by running it and what is only inferred. The main open point:
the transport wakes agents by typing into their tmux pane. That is guarded (it never types
into a pane a human is attached to, or one showing a confirmation dialog), but it is still
keystrokes. See the known limitations in [`hub/OVERVIEW.md`](hub/OVERVIEW.md).

Some code paths serve tools from the [related repos](#related-repos) and stay inert without them.
The main one: `hub done` on a task tagged `ui` asks Studio whether the design was approved. With no
Studio configured it skips the check silently. The `penpot-comment` and `penpot-design` intake
sources are labels for tasks Studio files.

## Contributing

Issues and pull requests are welcome: [CONTRIBUTING.md](CONTRIBUTING.md) covers the checks a
change must pass and what must never be committed.

## Licence

MIT. See [LICENSE](LICENSE). The Refinery brand assets in `examples/` are included for
reference only.
