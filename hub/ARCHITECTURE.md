# The Hub

Five named agent sessions running on separate accounts, on one machine, sharing a task
board and able to message each other directly. Four run Claude Code; one (Prometheus)
runs Codex.

`HUB.md` is the day-to-day operating manual — commands, workflow, troubleshooting. This
document explains what the system *is*, how it's put together, and what has actually been
verified versus assumed.

Built 2026-09-03 on WSL2 (Ubuntu 26.04), Claude Code v2.1.259.

---

## What problem it solves

Working with one Claude session means one context, one rate limit, and one thing happening
at a time. The hub gives you five agents that can hold separate contexts, work in parallel
on separate accounts, hand work to each other, and pick up tasks written by whoever planned
them — without you re-explaining the plan to each one. One of them is a different model
family entirely, which is worth pointing at review: it has different blind spots.

The workflow it's built around:

> Plan extensively first. Turn the plan into richly-described tasks. Then let agents pick
> them up and execute.

The board enforces the part that makes this work: a task must carry enough context to be
executed by an agent that never saw the conversation that produced it.

---

## The roster

| Agent | Role | Account (config dir) |
|---|---|---|
| **Zeus** | Lead — planning, decomposition, task authoring, review | `~/.claude` |
| **Apollo** | Worker | `~/.claude-apollo` |
| **Hermes** | Worker | `~/.claude-hermes` |
| **Athena** | Worker | `~/.claude-athena` |
| **Prometheus** | Worker (Codex) | `~/.codex` |

Worker roles are deliberately not specialised. Assign by task, not by title.

Type an agent's name in any WSL shell to enter it. The session runs in tmux, so it survives
detaching and closing the terminal.

---

## Architecture

Three independent layers. Each keeps working if the others break, which matters — they have
different failure modes.

### 1. Sessions — tmux + per-account config dirs

Each agent runs inside a detached tmux session named `hub-<agent>`. Claude agents receive
`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_SESSION_NAME`, and `HUB_AGENT`; Prometheus runs Codex
with `HUB_AGENT` and write access to the hub via `--add-dir`.

Claude Code stores credentials, settings and history **per config directory**. That's what
lets four subscriptions run concurrently without overwriting each other's tokens.

### 2. Messaging — Unix domain sockets

Agents talk over a per-session socket in `$XDG_RUNTIME_DIR/cc-socks/<pid>.sock`. No server,
no MCP, no network — this is why it's fast. Agents call the `SendMessage` tool with a peer's
bare name; `ListAgents` lists who's reachable.

Discovery works through a registry of one JSON file per live session in
`<config-dir>/sessions/<pid>.json`, holding the agent's name, socket path and status.

### 3. Coordination — files in `hub/`

| File | Purpose |
|---|---|
| `board.json` | Current state of every task |
| `events.jsonl` | Append-only ledger of every transition |
| `inbox/<Agent>.jsonl` | Durable queued messages |
| `board.py` | The `hub` CLI (on `PATH` as `hub`) |
| `shell.sh` | Shell entry points, sourced from `~/.bashrc` |

Plain files, so this layer is account-agnostic and tool-agnostic. It works even if
messaging is broken, and it's the intended integration point for non-Claude tools.

---

## The one load-bearing constraint

**Session discovery is scoped to the config directory.**

This is the single most important fact about the setup. Four fully isolated config dirs
would each have their own `sessions/` registry, so agents would be invisible to each other:
`ListAgents` shows no peers, `SendMessage` can't resolve names, and messaging silently stops
working. Nothing errors — it just goes quiet.

The fix is that every agent's config dir symlinks `sessions/` back to `~/.claude/sessions`:

```
~/.claude-apollo/sessions   ->  ~/.claude/sessions     # shared: who is running
~/.claude-apollo/CLAUDE.md  ->  ~/.claude/CLAUDE.md    # shared: the protocol
~/.claude-apollo/settings.json                          # copied: accounts differ in model access
~/.claude-apollo/.credentials.json                      # private: this agent's account
```

Credentials, history, memory and rate limits stay separate. Only the registry of who's
running is shared.

**If messaging ever goes quiet, check that symlink first.**

---

## How work flows

1. **Plan with Zeus.** Explore, settle the approach, identify risks. Don't create tasks yet.
2. **Write the tasks.** `hub new "title" --detail "..."` with enough context, files,
   approach and acceptance criteria that a cold agent can execute it. Chain with `--dep`,
   pre-assign with `--owner`.
3. **Workers execute.** `hub next` → `hub claim` → work → `hub done --note "..."`.
4. **Completion cascades.** `hub done` works out which tasks it unblocked, queues a message
   to each new owner's inbox, and prints a universal `hubmsg` command to ping them live.

### Notifications are two-part, on purpose

The inbox is **durable but passive** — it survives restarts and nothing wakes anyone up.
`SendMessage` is **live but ephemeral** — it interrupts the recipient now.

A shell script cannot speak Claude's undocumented socket protocol, so `hubmsg` supplies
the cross-vendor path: it queues the durable copy and wakes the target through tmux,
directly or through the sandbox relay.

---

## Status

### Verified by running it

- Named sessions register and are addressable by name
- Cross-session messaging round-trip, including **between two different config directories**
- Board: create, dependency-gated claim, done, auto-unblock, inbox delivery
- State/ownership enforcement, dependency validation and cycle rejection
- Safe canonical inbox names and concurrent atomic inbox consumption
- Concurrent board writers, bounded lock waits and torn-line tolerance
- Journal-first crash injection, durable snapshot replacement and schema migration
- Wake content integrity, IDs, confirmation, deduplication and slow targets
- Relay validation, lifecycle, health reporting and restart recovery
- Agent identity auto-detected with no `--as` flag
- Event ledger captured a full multi-agent sequence in order
- Lock timeout fails at 10s against a hung holder; frees instantly when a holder dies
- Socket pruning removes orphans and leaves live sockets alone
- No environment leakage into the parent shell
- All entry points load in a fresh login shell

### Not yet proven

- **Multiple accounts have never run simultaneously.** The cross-config-dir test symlinked
  one account's credentials to both sides. It proved the plumbing survives isolation; it did
  not prove rate-limit independence. That follows from credentials being per-directory, and
  a fresh config dir does get its own onboarding rather than inheriting Zeus's auth — but
  it's inference, not observation.
- Five concurrent agents under sustained production load

### Built since

- **Codex integration** (2026-09-04). Prometheus runs Codex CLI v0.153.2. The board needed
  no changes at all — `board.py` resolves identity from `$HUB_AGENT` and has no roster —
  so only messaging had to be solved. `SendMessage` is Claude-only in both directions, so
  `hubmsg` wakes any agent by typing into its `hub-<agent>` tmux session.

  Two sandbox limits were found by testing, not by reading docs, and both are fixed:
  Codex's `workspace-write` blocks writes to `~/hub` (fixed with `--add-dir`), and its
  seccomp filter blocks `connect()` on AF_UNIX so it cannot reach tmux at all (fixed with
  the `hubwaked` relay, which performs the keystroke outside the sandbox). See
  `runbooks/codex-sandbox-blocks-hub.md`.

  Verified end to end: Prometheus claims and finishes board tasks, and wakes a Claude pane
  through the relay.

### Remaining operational prerequisites

- Apollo, Hermes and Athena require their one-time interactive account login before all
  five agents are usable; agents cannot perform those human authentication steps.
- Tmux wakes to an attached pane are deliberately deferred until detach. The durable
  inbox remains readable immediately, and Claude peers can use `SendMessage` instead.

The previous technical limits are now closed: relay processes fingerprint their code,
resolved errors disappear from health output, crash recovery replays a transaction WAL,
wake retries carry only an idempotent `hub receive <id>` instruction, and attached panes
never receive injected keystrokes.

---

## Gotchas

**Enter WSL with `wsl ~`, not plain `wsl`.** Plain `wsl` keeps your Windows working
directory, so agents launch pointed at `/mnt/c/...` — wrong location, and slow over the
filesystem bridge.

**Launch each agent from the repo you want it in.** Sessions start in `$PWD`.

**First run per agent** brings a theme picker, a login, and a folder-trust prompt. Each
config directory needs its own trust acceptance. `hubaccounts` shows who still needs
signing in.

**Native `Task*` tools don't apply here.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is
enabled, but it does not give independently-launched sessions the `TaskCreate`/`TaskList`
tools — verified with the flag confirmed live in the session's environment. Those appear
only in a real team context. The file-based board does all the actual work.

**`CLAUDE_CODE_*` variables are stripped from Bash subprocesses**, so a script can't read
`$CLAUDE_CODE_SESSION_NAME` to learn its own identity. `board.py` walks up `/proc` to find
an ancestor that has it. `CLAUDE_CONFIG_DIR` is *not* stripped.

**Don't delete `.board.lock`.** It's a zero-byte anchor holding no state, and removing it
while an agent holds the lock breaks mutual exclusion. A crashed agent never leaves a stuck
lock — the kernel releases `flock` on process death.

**Never delete a socket by guessing its owner.** They're named by PID, not agent. A live
session's socket is how it receives messages. Pruning only ever removes sockets whose
process is gone.

---

## Command reference

Day-to-day commands are in `HUB.md`. In short:

```bash
zeus | apollo | hermes | athena     # enter a Claude agent
prometheus                           # enter the Codex agent
hubs                                # who's running, and which accounts are signed in
hubaccounts                         # accounts only
hubkill <agent|all>                 # stop a session (conversation is kept)

hub new "title" --detail "plan"     # create a task
hub next | claim | done | block     # the work cycle
hub inbox [--clear]                 # your queued messages
hub receive <message-id>            # idempotently receive one wake payload
hub events [--tail N] [--task ID]   # the audit trail
```

`Ctrl-b d` detaches from an agent without stopping it.

## Tests

```bash
python3 tests/test_board.py
python3 tests/test_messaging.py
```

The suites are dependency-free and use temporary boards and scratch tmux sessions rather
than live agent state.
