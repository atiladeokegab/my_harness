# The Hub

A small system for running several AI coding agents on one machine as a team: they share a
task board, message each other, and hand work back and forth without a human relaying it.

Five named sessions. Four run Claude Code, one runs OpenAI's Codex. **Zeus** plans and
decomposes; **Apollo**, **Hermes**, **Athena** and **Prometheus** execute.

Everything is plain files and Unix primitives — no server, no database, no network. The
roster is configurable (`factory.json`); these are the defaults. `HUB.md` has the commands.

---

## The problem it solves

One agent session means one context window, one rate limit, and one thing happening at a
time. Long work serialises behind whatever the agent is currently doing, and any parallelism
means a human copy-pasting context between terminals.

The hub gives you agents that hold separate contexts, run on separate accounts (so they
don't compete for capacity), and pick up work written by whoever planned it. The design
constraint that drives everything: **a task must be executable by an agent that never saw
the conversation which produced it.** That is why planning happens up front and why every
task carries its own context, files, approach and acceptance criteria.

---

## Architecture

### The board

`board.json` is a snapshot; `events.jsonl` is an append-only ledger. Mutations take an
`flock` with a bounded wait, so a crashed holder is released by the kernel and a hung one
fails loudly with an actionable message rather than blocking everyone forever.

Writes are journal-first: events are appended and `fsync`ed *before* the snapshot is
replaced, and the snapshot's temp file and its parent directory are both `fsync`ed around
the rename. The ledger can therefore be legitimately **ahead** of the snapshot after a
crash; it can never be behind. That ordering is what makes "trust the ledger" true rather
than aspirational.

Agents identify themselves from `$HUB_AGENT`. There is no roster to register with — which
is the reason adding a non-Claude agent needed no board changes at all. State and ownership
are enforced: only the owner may finish, block or release a task, and overrides with `--force`
are recorded.

### Messaging

Two mechanisms, because two vendors:

| Path | Mechanism | Works across vendors |
|---|---|---|
| Claude → Claude | `SendMessage`, a Claude-private Unix socket | No |
| Anyone → anyone | `hubmsg`, handed over by the target's Stop hook, else a keystroke into its idle tmux pane | Yes |

Every agent lives in a tmux session named `hub-<agent>`, so typing into that pane is a wake
mechanism that works regardless of which vendor's CLI is on the other end.

`hubmsg` queues the payload in `inbox/<Agent>.jsonl` and one wake request per agent,
`wake/<Agent>.wake`; more messages only extend its id list. The wake asks for `hub receive --pending`,
which reveals every unreceived message once, so a repeated wake cannot repeat the work. Delivery
prefers the hook: when an agent's turn ends, the optional `stop-deliver` hook hands it its pending
messages as a Stop block, on both CLIs, with no keystroke. `hubwaked` types the receive line only into
an idle pane: never while it is busy (`esc to interrupt`, or a mid-turn heartbeat), a person is
attached, or a dialog is up, where an Enter would grant a permission. The lead is exempt from the Stop
hook; the `inbox-surface` hook shows it unseen inbox lines on every prompt and tool call instead.

The rule throughout is **queue *and* ping**: a durable inbox message (survives restarts,
passive) plus a live wake (gets attention now, ephemeral). `hubmsg` does both in one call.
`inbox_gc.py` archives inbox lines older than seven days each night.

---

## The interesting part: two vendors, one hub

Codex was added last. The split turned out cleaner than expected, and the failures were
instructive.

**What worked for free.** The board needed zero changes. Identity is an environment
variable and there is no roster, so a Codex agent claims, notes and finishes tasks
identically to a Claude one.

**What did not.** `SendMessage` is Claude-only in both directions, and `ListAgents` will
never list a Codex session. Waking had to be rebuilt on something vendor-neutral.

**Two sandbox discoveries**, both found by running the thing rather than reading docs:

1. Codex's `workspace-write` sandbox confines writes to the launch directory. The hub lives
   outside it, so the agent could *read* the board but every `claim`/`done`/`note` died with
   a bare `Read-only file system` error. Fixed by granting exactly the hub via `--add-dir`.
2. Codex's seccomp filter blocks `connect()` on AF_UNIX sockets. It can `stat` the tmux
   socket but never connect, so it could not wake anyone — and worse, the failure was
   indistinguishable from "that agent is asleep". No configuration short of disabling the
   sandbox lifts this.

Rather than disable the sandbox, wakes from a sandboxed agent are written as request files
into the hub directory, and a small relay daemon outside the sandbox performs the keystroke.

---

## The factory (optional)

On top of the board, the hub can run as a small AI code factory: work arrives from GitHub on its
own, timers hand it to idle agents, `hub done` will not accept work whose check fails, and
`hub live` enforces review, evidence and scope before anything merges. All of it is off until you
write `factory.json` and switch on the timers (`runbooks/install-factory-timers.md`). The timers
are systemd user units, so this part is Linux only.

### The loop

1. Work arrives: you plan it with the lead, or a factory repo gets an issue labelled `agent` or a
   red CI run on `main`, which the factory poll turns into a board task.
2. Every 2 minutes the dispatcher offers the next open task to an idle agent with `hubmsg`; a task
   tagged `headless` runs unattended through `run.py` (`hubrun`) instead.
3. The agent claims it, which makes a fresh worktree for the task (`workspace.py`), and builds on a
   branch there.
4. `hub done` runs the task's `verify:` command (default `make check`) and refuses on failure; two
   failures block the task and tell the lead.
5. In a factory repo the agent posts `DONE:` with its evidence and `hub live` opens the PR; a PR
   without an `## Evidence` block is held, and files outside the task's scope are flagged.
6. The reviewer (`$HUB_REVIEWER`) reviews code; a builder never approves its own PR; docs-only PRs
   merge on their evidence.
7. `hub live` merges one PR at a time at the reviewed commit, smokes it, promotes `main` or
   reverts and reopens the task, then deploys.
8. A red CI run becomes a fix request, and every Monday a timer gives the lead a cleanup task and
   a rule-promotion task.

### The pieces

| Unit (in `systemd/`) | When | Runs |
|---|---|---|
| `hub-dispatch.path` | on a kick | `dispatch.py tick` when `state/dispatch.kick` changes: a task created, done, released, unblocked, assigned, delegated or reopened, or an agent other than the lead stopping a turn |
| `hub-dispatch.timer` | every 2 min | `dispatch.py tick`, the fallback for a missed kick, and the factory poll every `poll_seconds` |
| `hub-watch.timer` | every minute | `dispatch.py watch` |
| `hub-snapshot-quick.timer` | every 15 min | `snapshot.sh quick` |
| `hub-nightly.timer` | 02:30 UTC | `inbox_gc.py` (inbox lines and `logs/sh` over 7 days), `hub ws gc`, then `snapshot.sh full` |
| `hub-weekly.timer` | Monday 07:00 UTC | `dispatch.py weekly`, then `hub spec converge` |
| `hub-live@<p>.service` | always, one per project | `hub live --project <p>`, restarted 30 s after a crash; output to `projects/<p>/live.out` |

**The dispatcher** (`dispatch.py tick`). For each agent in `factory.json` whose autonomy phase
enables dispatch (`hub agents` shows it; the reviewer and lead phases do not), it checks the agent holds no claimed task (a task tagged `standing` does not count), is not rate
limited, and its pane shows no dialog, error or "esc to interrupt". An idle agent is offered one
task from the `projects` list, its own tasks first, then unowned ones, in `hub next`'s order. Tasks
tagged `untrusted` or `stale` are never offered. An offer with no claim in 30 minutes expires and goes
to another agent, never back. A task tagged `read` goes first to the reader (`"reads": true`), and
reaches anyone else only after `offer_minutes`, in case the reader is down. A tick within 5 s of the
last waits out the gap; a kick during a tick runs it again, at most twice. State: `state/dispatch.json`.

An agent whose phase has `"reset": "per-task"` that holds no claimed or blocked task and whose
last heartbeat is `Stop` gets a reset offer instead: `hubwaked` types `/clear` or `/new` first, so the
task starts in a fresh session, and downgrades to a plain wake if any guard fails
(`docs/hub/dispatch.md`, "Fresh context per task"). The lead is never reset, and `hub done` refuses a reset agent a handoff note under
20 characters, because only the board, inbox, git and memory survive the reset.

**The factory poll** (`gh_sync.poll_factory_repos`). For each repo in `factory.json`, open issues
labelled `agent` become board tasks (`kind: factory`, carrying the issue number and a fixed "How to
ship" block), and the latest failed run of each workflow on `main` becomes one fix task with its
log tail. An issue from an author without write access is wrapped in `<untrusted-data>` and tagged
`untrusted`, so only the lead can clear it. Poll-created tasks never carry a `verify:` command,
because `verify` runs in a shell and the text came from GitHub.

**The health watch** (`dispatch.py watch`). Reads the bottom of each live pane and classifies it:
permission prompt, rate limited, logged out, or stuck. It matches the CLIs' own chrome, never
prose, so an agent quoting an error is not flagged. Stuck means a claimed task and no heartbeat for
30 minutes; `heartbeat.sh`, a `UserPromptSubmit`, `PostToolUse` and `Stop` hook, writes
`state/<agent>.json`. Claude seats run it from `settings.json`, a Codex seat from `~/.codex/hooks.json`
with `--agent <Name>`. Without a Codex heartbeat, stuck for a Codex agent means the pane has not changed
for 30 minutes.
A rate limit trips a breaker until the reset time shown, and the dispatcher wakes nobody behind it.
Changes go to `watchdog.log` and to the lead agent; the human hears of a limit once per reset window
through the optional `lead_alert` command. It never kills or relaunches a session.

**Weekly** (`dispatch.py weekly`). Two tasks for the lead: a cleanup of stale tasks, branches and
worktrees, and a promotion of the week's `rule candidate:` lines from the reviewer into rules,
skills or runbooks. Then `hub spec converge` checks each spec project's live line against its PRD and
opens one task per drift.

**`hub live` in a factory repo.** `projects/<p>/hackathon.json` sets `factory: true`; the same loop
runs hackathons, and `hub gh-sync` skips factory projects. Before review it holds a PR with no
`## Evidence` block, and tells the reviewer about files outside the task's `Files:` line (re-read
from the issue, except for untrusted tasks) and diffs over 800 lines. The reviewer's LGTM never
counts on a PR the reviewer built; an LGTM may cite the head commit by the 12-character prefix
`hub live` shows. A diff of only docs, READMEs and media merges on its evidence alone. A red
required check on an open PR posts the log tail to the builder as a fix request and counts an
attempt. Builders are labelled `agent:<name>` on their issues. A PR someone merges by hand is
recorded like any other merge; a revert reopens the factory task. The roll call stays quiet while
nothing has changed. After a green promote, the project's deploy command (`deploy.command` in
`hackathon.json`) runs in a throwaway worktree of the promoted commit, one deploy at a time; a failed
deploy leaves the last good one serving. A finished gate or deploy, or a `hub done`, touches `projects/<p>/.tick-now`, and
the loop runs a merge-and-deploy pass within 10 s instead of waiting for the next 5-minute tick. On
Linux it runs as the systemd unit `hub-live@<p>` (or in tmux, as before).

**Spec Tree** (`spec.py`, `hub spec`). In a project with a PRD (`projects/<p>/spec/prd.json`, or legacy
`requirements.json`),
the PRD sits above the board: tasks are generated from its numbered acceptance lines, never written by
hand, and every PR cites the lines it builds as `Req: A-3.2@2`. A change of intent is a delta file you
approve through a `hub review` receipt. `hub spec apply` then writes PRD v+1, reverts the done work the
change collides with onto `change/C-NNN`, and regenerates the whole tree: untouched done work carries
over, everything unfinished is replaced. The radius is deterministic (trace links, entangled commits, a
check run on the rewound tree), with no LLM in it. `hub live` adds three rules for spec projects: hold a
PR whose `Req:` is missing or stale, send any PR touching `spec/` or `tests/acceptance/` to the lead,
and merge a change branch into `integration` only after a detached gate runs every acceptance check, the
smoke, `make check` and the private held-out checks on its head. Small wording fixes go through
`hub spec correct` and a reviewer's receipt; anything with a blast radius goes through `hub spec
propose` and yours. Commands and roles: `docs/hub/living-spec.md`.

**Headless runs** (`run.py`, `hubrun`). Runs one task unattended with `claude -p --output-format
json` or `codex exec --json`, capped by turns (30), a wall timeout and, for Claude, a dollar budget
($10 for the lead, $2 otherwise). It strips API key variables so it bills the subscription seat, holds `run/<task>.lock`, stops
cleanly on `PAUSE`, backs off when the CLI reports a rate limit, and records the session, turns
and cost as a note on the task. It never changes the task's state: someone decides on the result.

**The kill switch.** `hub pause "reason"` writes `$HUB_DIR/PAUSE`; `hub resume` removes it. While it
exists `hub next` and `hub claim` refuse, the dispatcher wakes no one, the poll and weekly tasks
stop, `run.py` will not start, and `hub live` skips its passes and merges. The health watch keeps
reporting.

**State off the disk.** `snapshot.sh quick` copies `board.json` and `events.jsonl` to the
`snapshot_bucket` in `factory.json` every 15 minutes; `snapshot.sh full` writes a nightly tarball of
the board, ledger, inboxes, `projects/`, `artifacts/` and `hub.bundle` (a `git bundle --all` of the
hub, the only off-disk copy of its history), keeping 30. Restore: `runbooks/restore-hub.md`.

**Seeing it.** `hub dashboard` serves http://127.0.0.1:8765 (who is doing what, what needs you) and
`/phases` (where each project's build is). It is also the local OpenTelemetry metrics sink: the Claude
launchers export metrics tagged per agent to `/v1/metrics`. Logs: `journalctl --user -u hub-dispatch`
(and `-u hub-watch`, `-u hub-nightly`, `-u hub-live@<p>`), `watchdog.log`, `projects/<p>/live.log` and
`live.out`, `wake/hubwaked.log`, `logs/sh/<agent>/` for `hub sh` and verify output, and `hub events`
for the ledger.

---

## Decisions worth arguing about

Listed because they are the places a reviewer should push.

**Keystrokes as a transport.** Waking an agent means typing into its terminal. It is
vendor-neutral and needs no cooperation from either CLI, but it is unmistakably a hack: if a
human is attached to that pane and mid-sentence, the injected text lands inside their
half-typed message and corrupts both. tmux cannot see a TUI's input buffer, so there is no
clean fix while the transport is keystrokes.

**Confirming delivery by reading the screen.** The relay confirms a submission by checking
the message id reached the active cursor line, then that Enter moved it. This is screen
scraping. An earlier version counted id occurrences anywhere in the pane and was fooled by a
duplicated paste into reporting success for a message that was never submitted.

**Failing closed.** When a wake is ambiguous, the relay records the id as delivered and does
*not* retry. Duplicating an agent's turn is considered worse than a missed ping, and the
durable inbox is the backstop. Reasonable people could pick the other trade.

**Notes are not ownership-gated.** Any agent may annotate any task, though only the owner
may finish or block one. Cross-agent commentary is the mechanism by which review findings
get recorded, so gating it would have broken the most valuable traffic on the board.

**Polling, not webhooks.** The hub assumes no public IP, so GitHub is polled every
`poll_seconds` rather than pushing events in. Events inside the hub use kick files instead: a
touched file and a systemd path unit, with the timers kept as the fallback.

**Fresh sessions, not long ones.** A dispatched agent can start each task on a cleared session.
It loses warm knowledge of related work; the 20-character handoff note pays for that, and it
kills the stale-context class of bug.

---

## Testing

Suites in `tests/` are dependency-free and run against throwaway boards and scratch tmux
sessions. `make check` (`make -C hub check` from the harness checkout) runs every
`tests/test_*.py` in parallel with the hub environment unexported, and is the hub's own verify.
Run one suite with `python3 tests/<suite>.py` and with `HUB_DIR` and `HUB_AGENT` unset, or it
touches the live hub.

The rule that mattered most: **each suite was written by the agent that did not write the
code under test.** Prometheus wrote the board tests, Zeus wrote the transport tests. That is
not ceremony — it caught real bugs in both directions that neither author found in their own
code.

Two lessons are worth repeating to anyone extending this:

- **A green test proves nothing until it has failed.** The first concurrency test passed
  against the *pre-fix* code too — process-spawn overhead dwarfed the race window, so it was
  measuring nothing. The board suite is now checked against a pre-cycle commit and produces
  8 failures and 2 errors there, which is what makes its green meaningful.
- **Test the configuration you actually run.** The transport suite was 19/19 green over a
  live bug because it never ran `hubmsg` while the relay daemon was up — the only
  configuration that exists in production.

The factory pieces have their own suites (`test_dispatch.py`, `test_watchdog.py`,
`test_gh_sync_factory.py`, `test_live.py`, `test_run.py`, `test_snapshot.py`, `test_workspace.py`,
`test_spec.py`, `test_inbox_surface.py` and more), all against stub `tmux`, `gh`, `gcloud`,
`systemd-run` and agent CLIs.

---

## Known limitations

Stated plainly, because a reviewer's time is wasted rediscovering them.

1. **Wakes are still keystrokes.** The transport is fundamentally "type into someone's
   terminal". It is guarded now — deferred when a human is attached and when the pane shows
   a confirmation dialog — but the guards recognise known dialog shapes, so an unfamiliar
   modal from a future CLI version could slip through. This is the residual risk worth
   watching.
2. **Confirmation still observes the terminal**, though only via cursor coordinates
   (`cursor_x`/`cursor_y`) rather than matching rendered text. That is vendor-agnostic and
   far more stable than scraping output, but it is still an inference from the screen
   rather than an end-to-end acknowledgement.
3. **Wakes fail closed** — an ambiguous wake is dedup-guarded and never redelivered, so the
   durable inbox is the backstop rather than automatic retry.
4. **Identity is self-declared.** Factory rules that depend on who acts (only the lead clears
   `untrusted`; a builder's LGTM never counts) stop mistakes and naive injected instructions, not
   a determined actor. See `docs/hub/operations.md`.
5. **One host.** Board, ledger and inboxes live on one disk. Snapshots make a restore possible,
   not a failover; two live copies of the hub would fork the board.
6. **Spec Tree: a superseded builder is only told.** `apply` messages the holder of a stale task;
   nothing stops its session or deletes its branch. A PR from it is still refused for its stale `Req:`.
7. **Spec Tree: gaps in v1.** Files reached only by the commit cascade appear in no task's `Files:`, and
   two requirements sharing files can put two builders on one file.
8. **Wakes need the Codex hooks file.** Codex runs hooks in a shared daemon whose environment is whoever
   started it, so a Codex agent's heartbeat and Stop-hook delivery depend on `~/.codex/hooks.json`
   naming it explicitly. Without that file its messages wait for the relay to find its pane idle.
9. **Seats, not metered API.** Each agent is a subscription with its own rate limits and an
   interactive login. Adding a worker means a new seat and a browser login.
10. **Your credentials.** Every deploy and GitHub call runs as whoever is logged in to `gh` and
   the deploy tooling on the machine; there is no separate service identity.
11. **The factory timers are Linux only.** They are systemd user units. On macOS the board, agents
   and messaging work, but you would schedule `dispatch.py tick` yourself, and headless runs
   started by the dispatcher need `systemd-run`.

Fixed since the first draft of this document, listed because an earlier reviewer flagged
them: crash recovery now replays a write-ahead log automatically rather than by hand; a
relay running stale code is detected by comparing a SHA-256 fingerprint of the script
against the one recorded in its pidfile, and refuses to report healthy; resolved errors no
longer appear in health output; the wake queue and inboxes are `chmod 700`; and a wake can
no longer confirm a dialog it happens to land on.

---

## Layout

| File | Role |
|---|---|
| `board.py` | The `hub` CLI: tasks, locking, ledger, inboxes, verify gate, pause, `hub sh` |
| `workspace.py`, `bin/ws-node-modules` | `hub ws`: a worktree per claim, its gc, per-workspace `node_modules` |
| `autonomy.py` | Autonomy phases from `factory.json`: `hub agents`, `hub agent phase`, `hub approve`, `hub changes` |
| `dispatch.py` | Timed loops: tick (with reset offers and `read` routing), watch, weekly |
| `gh_sync.py`, `gh_board.py` | Board and GitHub Issues (`hub gh-sync`); the factory poll |
| `live.py`, `live_merge.py` | `hub live`, the per-project merge loop; one merge, smoke, promote or revert |
| `spec.py`, `spec_lint.py`, `stack_check.py` | `hub spec`: the PRD tree, lint, rewind, apply, converge; the stack-table gate |
| `prd.py`, `prd_grill.py`, `templates/prd/` | `hub prd`: show, render, check and grill a PRD |
| `hub_trace.py` | `hub trace`: provenance from a PRD line to a commit |
| `review.py` | `hub review` approval windows and receipts |
| `clean_repo.py`, `CLEAN-REPO.md` | `hub new-project`, `init-repo`, `ship-check`, `scrub`: keep harness files out of shared repos |
| `map.py` | `hub map`: a code call graph through graphify |
| `dashboard.py`, `dashboard.html`, `phases.html` | Dashboard, phases page, metrics sink |
| `run.py` (`hubrun`) | Headless runner for one task |
| `hubmsg`, `hubwaked` | Queue one wake per agent; the relay, with busy, attached, dialog and reset handling |
| `hooks/` | Optional hooks (need `node`): `stop-deliver.js`, `inbox-surface.js`, `session-ship-check.js` |
| `heartbeat.sh`, `snapshot.sh`, `inbox_gc.py` | Heartbeat hook and dispatch kick, bucket snapshots, nightly inbox and log prune |
| `shell.sh`, `hubctl` | Launchers, account status, relay supervision; the executables zsh shells use |
| `Makefile`, `tests/` | `make check`: every hub suite |
| `factory.example.json`, `systemd/` | Factory config template and the timer units |
| `HUB.md`, `docs/hub/` | Operating manual: a short index and one page per topic |
| `ARCHITECTURE.md` | What it is and what is verified versus assumed |
| `AGENTS-codex.md` | Protocol for the Codex agent (it reads `AGENTS.md`, never `CLAUDE.md`) |
| `runbooks/` (harness repo root) | Problems that already cost real time once, with symptom and fix |

---

## Trying it

```bash
hubs                                   # who is up, relay health, which accounts are signed in
zeus                                   # attach to an agent; Ctrl-b d detaches
hub new "title" --detail "..." --owner Prometheus
hubmsg Prometheus "..." --task T-020   # queues and wakes in one call
hub events --tail 20                   # the audit trail
```

Start an agent from inside the repository you want it working on — each session inherits the
directory it was launched from.
