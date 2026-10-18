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
| Waking a running agent | `hubmsg` → the agent's Stop hook, or a tmux keystroke when idle | **Yes.** Every agent lives in a tmux session named `hub-<agent>`; the Stop hook runs on both CLIs. |
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
hub show T-003 [--full]                 # detail and the 5 newest notes (--full: every note)
hub claim T-003                         # claim it; prints the workspace path to work in
hub claim T-003 --force                 # override assignment/deps (audited)
hub done T-003 --note "what happened"   # finish it; runs verify (default make check) in the workspace
hub block T-003 "why it's stuck"        # flag a blocker
hub note T-003 "progress update"        # leave a note
hub release T-003                       # put it back
hub notify Hermes "text" --task T-003   # queue a durable message
hub assign T-003 <owner|pool>           # hand a task to a person (or the pool)
hub delegate T-003 <agent>              # ...and to one of that person's agents
hub review --name approval-1 --title "Idea + C4" c4_*.png IDEA.md   # approval window built from files
hub gh-sync --project <p> [--init|--freeze|--dry-run]   # hackathon: board ↔ GitHub Issues
hub live --project <p> [--once]         # the mechanical Live loop (runs as systemd hub-live@<p>)
hub live --project <p> --merge-now|--hold-merges|--resume-merges   # the reviewer sets the merge pace
hub brief                               # where you stand: inbox, your work, what peers hold
hub inbox [--clear|--unseen]            # read messages queued for you (--unseen: only new ones, for the hook)
hub receive --pending                   # reveal every unreceived message once (what a wake asks for)
hub receive <message-id>                # reveal one message once (v1 wakes)
hub sh [--tail N] [--name x] -- <cmd>   # run a long or noisy command: full log on disk, tail on screen
hub ws path T-003 | hub ws gc [--dry-run]   # a task's workspace; remove finished, merged ones
hub events [--tail 50] [--task T-003]   # the append-only ledger
hub spec check|impact|rewind|apply|converge   # a spec project's PRD tree (see "Spec Tree")
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

Each message has a unique ID and its payload stays in the locked durable inbox. A wake carries
no payload, only `[hub wake] Run exactly: hub receive --pending`, and that command reveals every
unreceived message once and writes a receipt for each. A repeated wake therefore prints `nothing
pending` and cannot repeat the work.

### Wake semantics

| Rule | What happens |
|---|---|
| **One wake per agent** | `hubmsg` writes one request, `wake/<Agent>.wake`. A message that arrives while it is pending only adds its id, so three messages in a minute make one turn. The relay drops the request once every listed id has a receipt. |
| **Stop-hook delivery first** | The `stop-deliver` hook (`hooks/stop-deliver.js`) runs when an agent's turn ends. With messages pending it runs `hub receive --pending` and hands them over as a Stop block, so the agent continues straight into them with no keystroke. The receipts stop it looping. Both CLIs honour the block. |
| **Busy: nothing typed** | A pane showing `esc to interrupt`, or a heartbeat whose last event is a fresh `UserPromptSubmit`/`PostToolUse`, is mid-turn. The relay requeues for 15 s; the Stop hook usually delivers first. `hubmsg` prints `busy`. |
| **Attached: deferred** | A person attached to the pane gets no keystrokes, and the Stop hook stays silent too, so you talking to an agent are not pushed into peer mail. A notice goes to the tmux status line. `hubmsg` prints `deferred`. |
| **Dialog: deferred** | A permission prompt, Codex's "Hooks need review" or any `esc skip` screen gets no Enter: it would confirm the highlighted option, and a wrongly granted permission cannot be taken back. |
| **Idle: one line** | Only an idle, unattached pane with no dialog gets the receive line typed, after clearing any half-typed input. |
| **The lead exempt** | `$HUB_LEAD` (Zeus) gets no Stop-hook delivery and no reset, because it holds your conversation. The `inbox-surface` hook still shows it new messages on every prompt and tool call (`hub inbox --unseen`, which shares receipts with `hub receive`). |
| **Old messages** | A wake older than `HUB_WAKE_MAX_AGE` (6 h) is dropped; the message stays in the inbox for `hub inbox`. |

The hooks are optional and need `node`; without them every wake is a keystroke into an idle pane,
as before. Install them with `runbooks/install-factory-timers.md` section 4. Codex hooks run in a
shared daemon whose environment belongs to whichever process started it, so the Codex hook commands
in `~/.codex/hooks.json` pass `--agent <Name>` and `HUB_DIR` explicitly; the hooks ignore a Codex
payload without them.

When you see a `[hub wake]` prompt, run its exact `hub receive` command before acting on the
messages. An old-style `[hub wake:<id>]` line works the same way.

## Long-running work

Never block a session on a synchronous command that could run for minutes. A blocked
session cannot receive messages, cannot be interrupted cleanly, and looks identical to a
hung one from the outside.

- Run long jobs detached (`run_in_background`, or `tmux new-session -d`), then poll with
  explicit status checks.
- Run anything noisy (tests, builds, installs) through `hub sh -- <cmd>`: the tail on screen, the
  full log on disk. Read the log instead of re-running.
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
inbox, then one coalesced wake for that agent (see [Wake semantics](#wake-semantics)). It
prints `woke` only after confirmation, `relayed` when the sandbox relay owns delivery,
`busy` when the target is mid-turn (its Stop hook or the relay delivers at turn end),
`deferred` when a person is attached or a dialog is up, and `asleep` when the target is not
running; the message remains in the durable inbox either way. Tmux carries only the receive
command, never the payload. Run `hubs` or `hubwaked --status` for relay
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
make check                          # every tests/test_*.py, 4 at a time, one summary line
python3 tests/test_board.py         # one suite, while you work on it
```

`make check` is the hub's own verify: `hub done` runs it for a project `hub` task that sets no
`verify:`. It unexports `HUB_DIR`, `HUB_AGENT`, `HUB_PROJECT`, the roster variables,
`CLAUDE_CODE_SESSION_NAME`, `GIT_DIR` and `GIT_WORK_TREE`, runs each suite in its own process, and
prints `make check: OK, <n> tests in <m> modules` or each failing module's output and a `FAILED`
line (exit non-zero). It takes a few minutes: run it through `hub sh -- make check`. Run a single
suite with `HUB_DIR` and `HUB_AGENT` unset, so nothing touches your live hub. The suites are
dependency-free (the hook tests need `node`) and use temporary boards. The messaging suite runs its
scratch sessions on a private tmux server and never types into a real agent pane.

## Spec Tree: the PRD drives the board (`hub spec`)

A project with `projects/<p>/spec/requirements.json` is a **spec project**. The PRD is its only source of
truth: every change of intent is an approved delta that makes a new PRD version, and `hub spec apply`
regenerates the task tree from it. Nobody writes or edits those tasks by hand. A worked example lives in
`tests/fixtures/spec_linkly/`.

| File in `projects/<p>/spec/` | Holds |
|---|---|
| `requirements.json` | The PRD: requirements with `needs`, each with numbered acceptance lines (`A-3.2`) at a version, each line naming its test under `tests/acceptance/` in the product repo |
| `changes/C-NNN.json` | One change: `base_version`, added, modified and removed lines, a reason |
| `spec.lock` | The version, the sha256 of `requirements.json`, and the commits each change rewound |
| `reviews/` | The `hub review` receipt that approved each change |

```bash
hub spec init <p> --from seed.json             # first PRD: v1 and the lock (the lead agent, at spec approval)
hub spec check --project <p>                   # schema, lock hash, every line has a test and every test a line
hub spec impact C-NNN --project <p>            # the blast radius, from the graph alone
hub spec rewind C-NNN --dry-run --project <p>  # rewind and every acceptance check, in a throwaway clone
hub spec apply C-NNN --project <p>             # PRD v+1, branch change/C-NNN, the regenerated tree
hub spec bootstrap-sha T-5=<sha> --project <p> # one-time: merge_sha for tasks merged before it was recorded
hub spec converge [--project <p>]              # weekly (hub-weekly.service): one task per drift from the live line
```

`--repo` defaults to `$HUB_CODE_DIR/<p>`.

**A change, step by step.**

1. You state new intent. The lead agent writes `changes/C-NNN.json` against the current version. No code or task moves.
2. `impact`, then `rewind --dry-run`: the done tasks citing a changed line, the later commits entangled with
   them, and any kept check that goes red once they are reverted (a hidden dependency, which joins the rebuild).
   Same inputs, same report: no LLM in it.
3. A check-writer (a sub-agent of the lead, never a builder) writes the tests for added and changed lines and
   runs `make check` on them.
4. You approve the change file in a `hub review` window. That is the only human step.
5. `apply` refuses without a matching receipt, with a stale lock, while an earlier change has not landed, or if
   `change/C-NNN` exists. A radius over half the done tasks needs `--force`. Then it pushes `change/C-NNN` (the
   rewind commit) to origin, writes PRD v+1 and the lock, and regenerates the tree: done tasks outside the radius
   carry over, re-pinned to the new version; done tasks inside are rewound and rebuilt; every unfinished task is
   tagged `stale` and replaced. A builder holding a stale task is told to stop and abandon its branch.
6. Rebuild tasks cite `reqs` (`A-3.1@2`), list the rewound files, and build on `change/C-NNN`. Their PRs target it.
7. `hub live` merges task PRs into the change branch. When its tasks are done and no PR into it is open, a
   detached gate runs every current acceptance check, the smoke and `make check` on its head (`change_timeout`
   in `factory.json`, default 1800 s). Green, the branch joins `integration` as one unit, then smoke, promote,
   deploy, like any merge.

**Generated tasks verify** with `make check && hub spec check --project <p> --repo .`, so `hub done` gates them
in the task's workspace on both the product's tests and the PRD's links.

**Weekly converge.** Every Monday `hub spec converge` clones each spec project's live line and runs `check` and
every acceptance check whose test exists. A check red 3 times out of 3 is drift, red some of the time is reported
as flaky, and every check red at once is one environment task, not one per line. It opens one task per drift for
the lead agent, deduplicated by title, and never edits the spec. Paused hub: it opens nothing.

**Trailers.** Every PR in a spec project carries `Req: A-3.2@2` (each line it implements, at its current
version) and `Task: T-n`, in the body or a commit message. `hub live` comments on and holds a PR with no `Req:`
or a stale version, and never reviews or merges it. `Req: ci-fix` passes only on a PR that `Closes #` its ci-fix
task's own issue. The squash keeps the trailers and `hub live` records `merge_sha` on the task.

**Approval is a receipt, nothing else.** A review page with `data-approves=<path>` makes `hub review` record the
file's path and the sha256 of the bytes you approved. `apply` accepts only a receipt whose hash equals the
change file now; an edit after approval voids it. A hash written into the change file itself proves nothing.

| Who | May | May not |
|---|---|---|
| You | Approve a change in a `hub review` window | |
| Lead agent (`$HUB_LEAD`) | Write the PRD and change files, `init`, `apply`, clear `stale`, merge PRs touching `spec/` or `tests/acceptance/` by hand | Approve a change |
| Check-writer (the lead's sub-agent) | Write `tests/acceptance/` on the change branch | Build the feature it tests |
| Builders | Build generated tasks on `change/C-NNN`, citing current `Req:` lines | Touch `spec/` or `tests/acceptance/` (held for the lead), `hub new` in a spec project, edit a generated task's brief or verify, claim a `stale` task (all refused) |
| Reviewer (`$HUB_REVIEWER`) | Review rebuild PRs like any other | See PRs on protected paths: they go to the lead |

## Dispatch: a kick, then the timer

`dispatch.py tick` offers open tasks to idle dispatchable agents. It runs on a kick, and every 2
minutes as the fallback (`hub-dispatch.timer`).

- **Kicks.** A board write recording `created`, `done`, `released`, `unblocked`, `assigned`, `delegated`
  or `reopened` touches `state/dispatch.kick`, and so does any agent's `Stop` heartbeat except the lead's.
  `hub-dispatch.path` sees the change and starts the tick. Notes and messages do not kick.
- **Debounce.** A tick within 5 s of the last one waits out the rest of the 5 s (`debounced` in the
  journal). A kick that lands during a tick makes it run once more, at most twice.
- **hub live** gets its own kick: `hub done` touches `projects/<p>/.tick-now`, and a finished gate or deploy
  runs a merge-and-deploy pass within 10 s.

Log: `journalctl --user -u hub-dispatch`. Install: `runbooks/install-factory-timers.md`.

## Fresh context per task

A session that lives for days resends its whole conversation every turn. The dispatcher can start a
dispatched agent on a clean session for each task instead.

- **Who.** Agents with `"reset": "per-task"` in `factory.json`. `"reset": false` (the default) opts out.
  The lead is never reset.
- **When.** At a dispatch tick, only if the agent holds no claimed task (standing ones included) and no
  blocked task, its pane is idle, and its last heartbeat is `Stop`. The reviewer's review wakes come from
  `hub live`, not the dispatcher, so they never reset.
- **How.** The dispatcher queues `[dispatch] Fresh session. Your task: T-n ...` in the inbox and a reset
  request. `hubwaked` re-checks every guard, clears the composer, types `/clear` (Claude) or `/new`
  (Codex), confirms the composer let go of it, waits 3 s, then types the receive line. If anything fails
  (attached, dialog, busy, a heartbeat newer than the offer, a task now held, the command still in the
  composer) it downgrades to a plain wake. A reset is never retried. `wake/hubwaked.log` says `reset
  delivered` or `reset downgraded: <why>`.
- **The handoff note.** Only the board, inbox, git and memory survive a reset. So for an agent with reset
  on, `hub done` refuses a `--note` under 20 characters: write what changed, the branch and commit, and
  what is left. `--force` bypasses it and is recorded in the ledger.

## Workspaces: one worktree per claim (`hub ws`)

Builders sharing one long-lived clone work on whatever happens to be checked out there. So `hub claim`
makes a fresh worktree for the task:

```
workspace: ~/work/<p>/T-NNN (detached at origin/integration 1a2b3c4, fetched 12:05Z)
create your branch there: git switch -c <issue>-<slug> | task/T-NNN
```

- **Base:** `origin/change/C-NNN` for a spec-generated task, else `origin/integration` if it exists, else
  `origin/HEAD`. The clone (`$HUB_CODE_DIR/<p>`) is fetched first; `.env` is copied in.
- **Work only in the printed path**, and create your branch there. `hub done` runs its verify in that path.
  A re-claim reuses the path untouched.
- **No workspace** for project `hub` (it works in the live `~/hub`, and never as a linked worktree:
  `runbooks/worktree-hooks-leak-git-dir.md`), for a task with no project, or a project with no
  `$HUB_CODE_DIR/<p>` clone. The claim stands either way.
- **Cleanup.** `hub ws gc` runs nightly and on `hub release`. It removes a workspace only when the task is
  done or released, the tree is clean, and its commits are safe (merged, unchanged from base, on an
  origin ref, or patch-equivalent upstream). Anything else is kept. `hub ws path T-NNN` prints a task's
  path.

Claude and Codex launch with `--add-dir ~/work`; Codex also gets `--add-dir $HUB_CODE_DIR`, because a
worktree's commits write to its clone's `.git`.

## `hub sh`: long or noisy commands

```bash
hub sh -- uv run pytest -q
# exit 1 · 412 lines · 38.2s · log ~/hub/logs/sh/Prometheus/20261018T120501.482113Z-uv.log
# ...then the last 20 lines
```

The full output goes to `logs/sh/<agent>/`, the screen gets one summary line and the tail, and the
exit code is the command's. Read the log with `grep` or `sed -n` rather than re-running. stdin is
`/dev/null`, so nothing interactive. `--tail N` changes the tail, `--name x` the log name. Logs are
pruned after 7 days and never leave the machine.

The same runner backs `hub done`'s verify: a pass stores one line with the log path in the task's
notes, a failure keeps the last 30 lines. `hub show` prints the 5 newest notes, long ones cut in the
middle; `--full` prints everything.

## The factory

Optional, off until you switch it on (`runbooks/install-factory-timers.md`; how it works:
`OVERVIEW.md`). The commands you use by hand:

```bash
hub pause "reason"            # kill switch: no claims, wakes, polls, headless runs or merges
hub resume
hub edit T-012 --tag headless # the dispatcher runs it unattended with hubrun
hub edit T-012 --untag untrusted   # only $HUB_LEAD clears untrusted (after reading the issue)
hubrun T-012                  # one headless run now; the result lands as a task note
python3 ~/hub/dispatch.py tick --dry-run    # who would be woken, for what
python3 ~/hub/dispatch.py watch --dry-run   # each live pane's health
```

`hub done` runs the task's `verify:` command (default `make check` in the task's checkout) and
refuses on failure; at two failed attempts the task blocks and the lead is told. A task tagged
`standing` (a watch duty, a review rota) never makes its owner look busy to the dispatcher.

## Known limit: identity is self-declared

Board commands take the acting agent from `--as` or `HUB_AGENT`. Rules that depend on who acts (only
`$HUB_LEAD` clears `untrusted`; a builder's LGTM never counts) stop a naive injected instruction or an honest
mistake, not a determined one. Closing that needs signed identities; it is logged with the signed-LGTM
shortcut in `live_merge.py`. Likewise any agent can `hub edit --tag headless`, which hands the task to an
unattended `run.py` (`hubrun`) on the next dispatch tick: the same power as calling `hubrun` directly.
