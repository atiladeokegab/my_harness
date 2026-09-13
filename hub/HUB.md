# The Hub

Named agent sessions on one machine that share a task board and can message each
other directly. Zeus leads and plans; the rest execute.

| Agent | CLI | Role |
|---|---|---|
| **Zeus** | Claude Code | Lead. Planning, decomposition, task authoring, review. Usually the one you talk to. |
| **Apollo** | Claude Code | Worker. |
| **Hermes** | Claude Code | Worker. |
| **Athena** | Claude Code | Worker. |
| **Prometheus** | Codex | Worker. Not a Claude session — see [Two vendors](#two-vendors-one-hub). |

The roster is configurable — see `docs/customizing.md` in the harness repo. These are the
defaults.

Roles beyond Zeus are deliberately not specialised — assign by task, not by title.

## Two vendors, one hub

Prometheus runs OpenAI's Codex CLI. That is useful — a second model family has different
blind spots, so it is worth pointing at review and at anything Claude has got stuck on —
but it means the hub cannot assume one vendor's tooling.

The split is clean, and it is worth knowing which side of it you are on:

| Layer | Mechanism | Works across vendors? |
|---|---|---|
| Task board, inbox, ledger | Plain files under `hub/` | **Yes.** `board.py` attributes work by `$HUB_AGENT`, and has no roster to add names to. |
| Waking a running agent | `hubmsg` → tmux keystroke | **Yes.** Every agent lives in a tmux session named `hub-<agent>`. |
| Waking a running agent | `SendMessage` / `ListAgents` | **No.** Claude-only socket protocol; Codex can neither send nor receive. |
| Skills, slash commands | Vendor-specific | **No.** Never write a task for Prometheus that assumes them. |

So: the board needed no changes to accept a Codex agent, and messaging needed `hubmsg`.

## Accounts

Each agent runs on its own subscription, so their rate limits and context budgets are
independent — five agents working hard don't compete for one account's capacity. The four
Claude agents bill to four Claude accounts; Prometheus bills to your ChatGPT account.

Claude Code keeps credentials, settings and history per *config directory*, so each agent
gets its own:

| Agent | Config dir |
|---|---|
| Zeus | `~/.claude` (the default — already signed in) |
| Apollo | `~/.claude-apollo` |
| Hermes | `~/.claude-hermes` |
| Athena | `~/.claude-athena` |
| Prometheus | `~/.codex` (Codex's own home, unrelated to the above) |

**First run per agent:** type its name, pick a theme, sign in to that agent's account, then
`Ctrl-b d` to detach. Once only. `hubaccounts` shows who still needs a login — including
Prometheus, which signs in with `/login` inside the session against your ChatGPT account.

None of the Claude config-dir machinery below applies to Prometheus: Codex keeps its own
credentials, history and settings in `$CODEX_HOME`, and reads `AGENTS.md` rather than
`CLAUDE.md`. `~/.codex/AGENTS.md` is symlinked to `hub/AGENTS-codex.md` so its protocol
stays versioned alongside everything else.

**The one thing that must stay shared.** Session discovery reads `<config>/sessions/`, so
four fully isolated config dirs would be invisible to each other and messaging would
silently stop working. Each agent's config dir therefore symlinks `sessions/` back to
`~/.claude/sessions`. Credentials, settings and history stay separate; only the registry
of who-is-running is shared. Don't remove that symlink — it's what makes this a hub rather
than four unrelated terminals.

`CLAUDE.md` is also symlinked so every agent reads the same protocol. `settings.json` is
copied rather than linked, because accounts differ in which models they can use — edit
each agent's copy independently.

Everything in `hub/` (board, ledger, inboxes) is plain files on disk and works across
accounts without any of this mattering.

## Starting and entering agents

Type the agent's name in any shell: `zeus`, `apollo`, `hermes`, `athena`, `prometheus`.

That attaches to the agent's tmux session, creating it on first use. The session keeps
running when you detach or close the terminal.

- Detach without stopping: `Ctrl-b d`
- See who's up (and which accounts are signed in): `hubs`
- Accounts only: `hubaccounts`
- Stop one: `hubkill apollo`

### Where an agent lands

You should not have to think about paths. Resolution order:

1. **An explicit project** — `apollo myproject`, `zeus hub`. Any git repo directly under
   `$HUB_CODE_DIR` (default `~/code`) works by name with no registration, as does `~/hub`. `apollo .` forces the
   current directory.
2. **The repo you are standing in** — `cd ~/code/myproject && apollo` keeps working.
3. **`$HUB_HOME_PROJECT`**, if you set one. With `HUB_HOME_PROJECT=myproject`, a bare
   `apollo` from your home directory, `/tmp`, or anywhere else that is not a repo lands in
   `$HUB_CODE_DIR/myproject` (default `~/code/myproject`).
4. **Otherwise, the current directory.**

So the everyday case is one word from a fresh shell (with `HUB_HOME_PROJECT=myproject`):

```bash
apollo            # → ~/code/myproject, scoped to project myproject
```

The launch line confirms it, and re-entering a running agent tells you where it already is:

```
started Apollo in ~/code/myproject  (account: ...)  project: myproject
attaching to running Apollo in ~/code/myproject
```

An unknown project name lists the ones it knows rather than guessing.

### What an agent knows on arrival

`_hub_enter` runs `hub brief` at launch and passes the result to Claude Code via
`--append-system-prompt`, so a session opens already knowing its inbox, the tasks
available to it, and **what every peer is currently holding** — instead of spending its
first turn working that out. Run `hub brief` any time for a fresh view; the injected copy
is a snapshot from launch and says so.

Prometheus gets no injection — Codex has no equivalent flag — so `AGENTS-codex.md` tells
it to run `hub brief` on arrival instead.

## The two task boards

**`hub` (this directory's `board.json`)** is the durable source of truth. It survives
restarts, is readable by any tool, and is what you should trust.

**Native `TaskCreate`/`TaskList`/`TaskUpdate`** tools also exist when agent teams are
enabled. They're convenient in-session but experimental — status can lag and in-process
teammates don't resume. Use them freely for scratch coordination, but anything that
matters gets written to `hub`.

## Projects

The board is one shared list for the whole machine — it is not per-repo. A task can carry a
`project` tag so agents working in one codebase are not handed another's work.

```bash
hub new "..." --project myproject      # tag at creation
hub list --project myproject           # only that project
hub next --project myproject           # only that project
```

`$HUB_PROJECT` is the default for all three, mirroring how `--as` defaults to `$HUB_AGENT`.

**You normally never set it.** `_hub_enter` derives it from the directory you launch the
agent in — the basename of that directory's git root — and passes it into the tmux session
alongside `HUB_AGENT`. Start `apollo` inside `~/code/myproject` and it is scoped to
`myproject` for the life of that session. The launch line tells you:

```
started Apollo in ~/code/myproject  (account: ...)  project: myproject
```

Two deliberate exceptions, both resolving to no scope (whole board): the hub directory
itself, because Zeus plans across every project; and any directory that is not a git repo.

Override per shell with `export HUB_PROJECT=...`, or per call with `--project`.

**Scoping is strict.** With a project in scope, `hub next` will not offer untagged tasks
either. That is deliberate: the leak worth closing is an agent that clears its own queue
and falls through to unrelated work. With no project in scope, everything is visible, so
Zeus keeps a whole-board view by default.

Tags are free-form — no registry, no setup. `hub list` shows each task's tag in `[brackets]`.

## Runbooks

`hub/runbooks/` holds fixes for problems that have already cost real time once. Check here
before debugging anything that smells familiar — each one records the symptom, how to
confirm it, and the fix.

The index, with the symptom each one solves, is `runbooks/README.md`.

Add one whenever a bug takes more than an hour to diagnose and could plausibly recur.

## Working agreement

The point of the hub is that a task can be picked up cold by an agent with no memory of
the conversation that produced it. That only works if planning happens up front.

1. **Plan before tasks exist.** Talk it through with Zeus. Explore the codebase, settle
   the approach, identify the risks. Do not create tasks during exploration.
2. **Write tasks that stand alone.** Every task carries its own context, files to touch,
   approach, and acceptance criteria in `--detail`. If an agent has to ask "what did you
   mean", the task was underwritten.
3. **Then execute.** Workers claim, do the work, and report back.

### One file, one owner

Two agents editing the same file at the same time lose work, and they lose it quietly --
the second writer simply wins. Nothing in the tooling prevents this, so it is a rule:

**For the duration of a cycle, every file has exactly one owner, and it is written into
the task.** If a task needs a file someone else owns, that is a message to its owner, not
an edit. This is what let Zeus rewrite `board.py` while Prometheus rewrote `hubmsg` and
`hubwaked` across a dozen tasks without a single conflict.

It has already failed once, in the way it always will: an agent picked up related work,
touched every file including two it did not own, and nobody noticed until someone ran
`git status` and found ten files dirty. Check `git status` before you start, and if the
tree is dirty with someone else's work, ask before you type.

Tests are the deliberate exception, and the reason is worth keeping: **each suite is
written by the agent that did *not* write the code under test.** Prometheus tests
`board.py`, Zeus tests the transport. That has caught real bugs in both directions that
neither author found in their own code.

## Commands

```bash
hub new "title" --detail "full plan"    # create a task
hub new "title" --dep T-001             # ...that waits on another
hub new "title" --owner Hermes          # ...assigned up front
hub list                                # active tasks (add --all for done)
hub next                                # next task available to you
hub show T-003                          # full detail and notes
hub claim T-003                         # claim it
hub claim T-003 --force                 # override assignment/deps (audited)
hub done T-003 --note "what happened"   # finish it
hub block T-003 "why it's stuck"        # flag a blocker
hub note T-003 "progress update"        # leave a note
hub release T-003                       # put it back
hub notify Hermes "text" --task T-003   # queue a durable message
hub brief                               # where you stand: inbox, your work, what peers hold
hub inbox [--clear]                     # read messages queued for you
hub receive <message-id>                # reveal one wake payload once
hub events [--tail 50] [--task T-003]   # the append-only ledger
```

Agents identify themselves automatically via `$HUB_AGENT`, falling back to
`$CLAUDE_CODE_SESSION_NAME`; `--as Name` overrides. `$HUB_AGENT` is set for every agent
including Prometheus, which is why the board needed no changes to take a Codex worker.
A task whose dependencies aren't done can't be claimed without `--force`.

Task state and ownership are enforced: claim before block/done, only the owner may
release/block/finish, and an assigned task cannot be taken by someone else without
`--force`. Overrides are recorded in `events.jsonl`. `hub note` remains deliberately
open to peers because notes are additive and attributed. Dependencies are normalized and
must exist; self-dependencies and cycles are rejected.

## Notifications

When a task completes, `hub done` works out which tasks it just unblocked and queues a
message to each new owner's inbox. Read yours with `hub inbox`.

**A queued message does not wake anybody up.** The inbox is durable but passive, so
finishing a task means queue *and* ping: the inbox survives restarts, the ping gets
attention now. `hub done` prints the exact call to make, and the agent finishing the work
is expected to make it.

Two ways to ping, because two vendors:

- `SendMessage` — Claude to Claude. Native, no tmux dependency. Only a Claude session can
  call it; a shell script cannot speak that socket protocol.
- `hubmsg <Agent> "text"` — anyone to anyone, including to and from Prometheus. A plain
  shell command, so scripts can use it too. It queues *and* wakes in one call.

Each message has a unique ID and its payload stays in the locked durable inbox. Tmux
carries only a short instruction such as `hub receive <id>`; that command atomically
reveals the payload once, so duplicate wake attempts cannot duplicate the work. Direct
delivery and the daemon atomically claim wake requests, and ambiguous submissions safely
return to the queue.

Delivery is deferred, not attempted, in two cases. If a human is attached to the target
pane, injected keystrokes would corrupt whatever they are typing, so the wake waits for
them to detach and a notice goes to the tmux status line instead. And if the pane is
showing a confirmation dialog, the wake waits too: a wake ends in Enter, and Enter
confirms whatever option is highlighted, so delivering one to an agent sitting on a
permission prompt would grant that permission on its behalf. Deferring is the safe
direction in both cases -- the message stays durable and is retried, whereas a
wrongly-granted permission cannot be taken back.

When you see a `[hub wake]` prompt, run its exact `hub receive` command before acting on
the message.

## Long-running work

Never block a session on a synchronous command that could run for minutes. A blocked
session cannot receive messages, cannot be interrupted cleanly, and looks identical to a
hung one from the outside.

- Run long jobs detached (`run_in_background`, or `tmux new-session -d`), then poll with
  explicit status checks.
- Put a `timeout` on anything that talks to the network, another session, or a lock.
- Prefer one long poll over many short ones — checking every few seconds wastes turns.
- If you're waiting on another agent, ask it to message you when it's done rather than
  polling the board in a loop.

## When something looks stuck

`hub events` is the audit trail — every transition, in order, with the agent that made it.
It's the first place to look when two agents disagree about state, because it records
history that `board.json` (a snapshot) has already overwritten.

Before journaling, each mutation writes a durable full-board WAL carrying the transaction
ID. The journal transaction and its commit marker are then appended and fsynced before
the snapshot replacement. On the next access, a WAL with that commit marker is replayed
automatically; an uncommitted or torn transaction is marked aborted and discarded. Event
display hides aborted records, so the journal and snapshot agree after recovery. Boards
carry a schema version and refuse versions newer than the code.

**The board lock** is held only for the moment of a read-modify-write. If an agent *dies*
holding it, the kernel releases it immediately — nothing to clean up. If an agent *hangs*
holding it, other agents fail after 10 seconds with a message telling you to `hubkill` it.
A leftover `.board.lock` file is normal and carries no state; don't delete it.

**Sockets** live in `$XDG_RUNTIME_DIR/cc-socks/` and are named by PID, not by agent. A
clean exit removes its own; a killed session leaks one. Entering any agent prunes sockets
whose process is gone. Never delete one by guessing which agent owns it — a live session's
socket is how it receives messages.

## Messaging

Agents talk over a local Unix socket — no server, no MCP, no network.

**Between Claude agents**, over a local Unix socket — no server, no MCP, no network.

- `ListAgents` shows reachable sessions; the name **is** the address.
- `SendMessage` with `to: "Apollo"` delivers directly.
- Messages queue if the agent is busy and drain on its next turn.
- Plain text output is *not* visible across sessions. To communicate, an agent must
  actually call `SendMessage`.

**To or from Prometheus**, `SendMessage` is not available in either direction, so use
`hubmsg` — a shell command, therefore usable by any agent:

```bash
hubmsg Prometheus "T-007 is yours — detail is on the board" --task T-007
```

It does both halves of the queue-and-ping rule in one call: `hub notify` for the durable
inbox, then a `tmux send-keys` into `hub-prometheus` so a running session notices now. It
prints `woke` only after confirmation, `relayed` when the sandbox relay owns delivery,
and `asleep` when the target is not running; the message remains in the durable inbox.
The full payload, including newlines, stays in the inbox; tmux carries only its short
message ID and an idempotent receive command. Run `hubs` or `hubwaked --status` for relay
pid, pending queue depth/age, retained failures and the last error. The relay is
single-instance, adopts queued requests on startup and bounds its log.
Its pidfile records a code fingerprint, so `hubs` reports `relay=stale` after an on-disk
upgrade and the launcher replaces the old process. `last_error` is shown only while a
retained failure is active, not merely because an old log entry exists.

`hubmsg` works for *any* agent, Claude ones included. Prefer `SendMessage` between Claude
agents — it is native and does not depend on tmux — and reach for `hubmsg` when the target
is Prometheus, or when a shell script needs to do the waking.

Permissions are per-session. Never ask a peer to do something your own session was denied
— route it back to the human instead.

## Running the tests

From `~/hub`:

```bash
python3 tests/test_board.py
python3 tests/test_messaging.py
```

Both suites are dependency-free and use temporary boards. The messaging suite creates
isolated scratch tmux sessions and never types into a real agent pane.
