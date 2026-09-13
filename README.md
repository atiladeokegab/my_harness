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
| [`hub/`](hub/) | The multi-agent hub: `board.py` (the `hub` CLI), `hubmsg`, `hubwaked`, `shell.sh`, and two test suites. [`HUB.md`](hub/HUB.md) is the operating manual. |
| [`claude/CLAUDE.md`](claude/CLAUDE.md) | Global instructions for every session: the hub protocol, how I like to work, and engineering defaults (uv, testing, deploys). |
| [`claude/settings.json`](claude/settings.json) | Settings template with agent teams on and an auto-mode skeleton. |
| [`claude/skills/design-system/`](claude/skills/design-system/) | A skill for authoring and enforcing a binding design system, then verifying it in a real browser. Includes a WCAG contrast and Display-P3 colour tool. |
| [`examples/refinery-design/`](examples/refinery-design/) | A real, filled-in design skill from a shipping product: the worked example. |
| [`runbooks/`](runbooks/) | Problems that already cost real time, each with the symptom, how to confirm it, and the fix. |
| [`templates/`](templates/) | Starting points for a project `CLAUDE.md` and `AGENTS.md`, project settings, runbooks and hub tasks. |
| [`docs/`](docs/) | The guides below. |

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

---

## Requirements

- Linux or WSL2 with **bash**, **tmux**, **git** and **python3**.
- **macOS:** also GNU coreutils and a modern bash, because macOS ships bash 3.2 and BSD
  tools: `brew install bash coreutils tmux python git`. The installer checks for both. The
  agent commands are installed as executables, so they work from the default zsh.
- [Claude Code](https://claude.com/claude-code) for the Claude agents.
- Optional: [Codex CLI](https://github.com/openai/codex) (`npm install -g @openai/codex`) for
  the Codex worker, [uv](https://docs.astral.sh/uv/) for Python work, and `gh`.
- One account per agent if you want independent rate limits. You can start with a single
  account and run only `zeus`.

## Tests

```bash
cd hub
python3 tests/test_board.py       # the board: state machine, locking, crash recovery
python3 tests/test_messaging.py   # the transport: wakes, relay, dedup, dialog guards
```

Both suites are dependency-free and run against throwaway boards and scratch tmux sessions.
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
