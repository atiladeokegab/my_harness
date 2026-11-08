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
| [`hub/`](hub/) | The multi-agent hub: `board.py` (the `hub` CLI), `gh_sync.py` (`hub gh-sync`), `live.py` (`hub live`), `spec.py` (`hub spec`, the PRD tree), `workspace.py` (`hub ws`, a worktree per claim), `hubmsg`, `hubwaked`, `shell.sh`, optional agent hooks (`hooks/`), the optional factory (`dispatch.py`, `run.py`, `systemd/`, `factory.example.json`), and their test suites (`make check`). [`HUB.md`](hub/HUB.md) is the operating manual. |
| [`claude/CLAUDE.md`](claude/CLAUDE.md) | Global instructions for every session: the hub protocol, how I like to work, and engineering defaults (uv, testing, deploys). |
| [`claude/settings.json`](claude/settings.json) | Settings template with agent teams on and an auto-mode skeleton. |
| [`claude/skills/hub-planning/`](claude/skills/hub-planning/) | The lead's planning layer: where specs and plans go, grilling and C4 before approval, seeding the PRD, and turning an approved plan into board tasks with one owner per file. |
| [`claude/skills/development/`](claude/skills/development/) | Focused development: debug from evidence, test the behaviour that matters, review the connected change, and verify before claiming done. |
| [`claude/skills/grilling/`](claude/skills/grilling/) | Stress-test a plan or design as a tree of decisions, asked a round at a time with a recommended answer for each. |
| [`claude/skills/thinking-from-first-principles/`](claude/skills/thinking-from-first-principles/) | Five steps from the goal and the hard constraints, for acceptance tests, direction checks and any build judged on data it has not seen. |
| [`claude/skills/designing-products/`](claude/skills/designing-products/) | Plan a product's intent, UX, UI and brand on Impeccable: a blind direction tournament, generated tokens and brand page, four gates, the judge tour and a blind finish check. Run `npm ci` in its `kit/` before the kit's fixture build. |
| [`claude/skills/3d-model-workflow/`](claude/skills/3d-model-workflow/) | Build a real place or machine as an interactive 3D model in the browser: data contract, LiDAR ground, simulated mechanisms, eras, the look, GPU stills on Cloud Run and a tag, check, promote deploy. |
| [`claude/skills/intake/`](claude/skills/intake/) | Label pasted material (yours, an outside brief, or for later) before acting on it, so someone else's document never becomes your instructions. |
| [`claude/skills/clean-repo/`](claude/skills/clean-repo/) | Keep plans, reviews and agent config out of repos other people work in. |
| [`claude/skills/design-system/`](claude/skills/design-system/) | A skill for authoring and enforcing a binding design system, then verifying it in a real browser. Includes a WCAG contrast and Display-P3 colour tool. |
| [`examples/refinery-design/`](examples/refinery-design/) | A real, filled-in design skill from a shipping product: the worked example. |
| [`runbooks/`](runbooks/) | Problems that already cost real time, each with the symptom, how to confirm it, and the fix. |
| [`templates/`](templates/) | Starting points for a project `CLAUDE.md` and `AGENTS.md`, project settings, runbooks and hub tasks. |
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
7. [**Hackathon kit**](docs/hackathon-kit.md): run a human team the way the hub runs
   agents. The lead plans, every task becomes a GitHub Issue, and every teammate's AI agent
   follows one rulebook. Rehearsed on real GitHub with a second account.

---

## Requirements

- Linux or WSL2 with **bash**, **tmux**, **git** and **python3**.
- **macOS:** also GNU coreutils and a modern bash, because macOS ships bash 3.2 and BSD
  tools: `brew install bash coreutils tmux python git`. The installer checks for both. The
  agent commands are installed as executables, so they work from the default zsh.
- [Claude Code](https://claude.com/claude-code) for the Claude agents.
- Optional: [Codex CLI](https://github.com/openai/codex) (`npm install -g @openai/codex`) for
  the Codex worker, [uv](https://docs.astral.sh/uv/) for Python work, `gh`, `make`, and `node` for
  the optional agent hooks (turn-end message delivery, inbox surfacing).
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
python3 -m unittest tests.test_spec   # hub spec; also test_workspace, test_inbox_surface (needs node)
```

Run single suites with every `HUB_*` variable unset (`env -u HUB_DIR -u HUB_AGENT ...`), so nothing
touches your live hub. All suites are dependency-free and run against throwaway boards and scratch tmux sessions.
They never type into a real agent's pane.

## Status and honesty

The hub has run real multi-agent work daily since it was built in September 2026. [`hub/ARCHITECTURE.md`](hub/ARCHITECTURE.md)
lists what has been verified by running it and what is only inferred. The main open point:
the transport wakes agents by typing into their tmux pane. That is guarded (it never types
into a pane a human is attached to, or one showing a confirmation dialog), but it is still
keystrokes. See the known limitations in [`hub/OVERVIEW.md`](hub/OVERVIEW.md).

## Licence

MIT. See [LICENSE](LICENSE). The Refinery brand assets in `examples/` are included for
reference only.
