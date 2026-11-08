# State off the disk, long-running work, stuck agents, tests and limits

Part of the hub manual. Index: `$HUB_DIR/HUB.md` (default `~/hub/HUB.md`).

## State off the disk

Board, ledger and inboxes live on one disk. `snapshot.sh` copies them to the private, versioned
bucket named by `snapshot_bucket` in `factory.json` (it uses `gcloud storage`; a missing bucket,
`gcloud` or login logs one line and copies nothing):

- `snapshot.sh quick`, every 15 minutes (`hub-snapshot-quick.timer`): `board.json` and `events.jsonl`
  to `live/`; bucket versioning keeps their history.
- `snapshot.sh full`, nightly (`hub-nightly.timer`): a tarball of the board, ledger, inboxes,
  `projects/`, `artifacts/` and, when the hub directory is a git repo, `hub.bundle` (a `git bundle
  --all`, the only off-disk copy of `projects/` history). Newest 30 kept. Never push the bundle
  anywhere public.

Create the bucket once by hand: `runbooks/install-factory-timers.md` section 2. Restore:
`runbooks/restore-hub.md`.

## Long-running work

Never block a session on a synchronous command that could run for minutes. A blocked
session cannot receive messages, cannot be interrupted cleanly, and looks identical to a
hung one from the outside.

- Run long jobs detached (`run_in_background`, or `tmux new-session -d`), then poll with
  explicit status checks.
- Run anything noisy (tests, builds, installs) through `hub sh -- <cmd>`: the tail on screen, the
  full log on disk. Read the log instead of re-running.
- Put a `timeout` on anything that talks to the network, another session, or a lock.
- A sub-agent never ends its turn to wait for a background job: no hub wake reaches it
  (`runbooks/subagent-misses-background-notice.md`). It waits in the foreground in bounded slices.
- Prefer one long poll over many short ones: checking every few seconds wastes turns.
- If you're waiting on another agent, ask it to message you when it's done rather than
  polling the board in a loop.

## When something looks stuck

`hub events` is the audit trail: every transition, in order, with the agent that made it.
It's the first place to look when two agents disagree about state, because it records
history that `board.json` (a snapshot) has already overwritten.

Before journaling, each mutation writes a durable full-board WAL carrying the transaction
ID. The journal transaction and its commit marker are then appended and fsynced before
the snapshot replacement. On the next access, a WAL with that commit marker is replayed
automatically; an uncommitted or torn transaction is marked aborted and discarded. Event
display hides aborted records, so the journal and snapshot agree after recovery. Boards
carry a schema version and refuse versions newer than the code.

**The board lock** is held only for the moment of a read-modify-write. If an agent *dies*
holding it, the kernel releases it immediately: nothing to clean up. If an agent *hangs*
holding it, other agents fail after 10 seconds with a message telling you to `hubkill` it.
A leftover `.board.lock` file is normal and carries no state; don't delete it.

**Sockets** live in `$XDG_RUNTIME_DIR/cc-socks/` and are named by PID, not by agent. A
clean exit removes its own; a killed session leaks one. Entering any agent prunes sockets
whose process is gone. Never delete one by guessing which agent owns it: a live session's
socket is how it receives messages.

## Running the tests

The hub is stdlib-only on purpose, because a dependency that fails to resolve takes down the
thing every agent coordinates through. Its suites run with plain `python3`:

```bash
make -C hub check                   # from the harness checkout
make check                          # from the installed hub directory
python3 tests/test_board.py         # one suite, while you work on it (HUB_DIR and HUB_AGENT unset)
```

`make check` is the hub's own verify: `hub done` runs it for a project `hub` task that sets no
`verify:`. It unexports `HUB_DIR`, `HUB_AGENT`, `HUB_PROJECT`, `HUB_CODE_DIR`, the roster variables
(`HUB_LEAD`, `HUB_REVIEWER`, `HUB_CLAUDE_AGENTS`, `HUB_CODEX_AGENTS`), `CLAUDE_CODE_SESSION_NAME`,
`GIT_DIR` and `GIT_WORK_TREE`, runs each suite in its own process, a few at a time, and prints
`make check: OK, <n> tests in <m> modules` or each failing module's output and a `FAILED` line (exit
non-zero). It takes a few minutes: run it through `hub sh -- make check`. Run a single suite the same
way, with `HUB_DIR`/`HUB_AGENT` unset or pointed at a temp dir, never the live hub.

The suites are dependency-free (the hook tests need `node`) and use temporary boards. The messaging
suite runs its scratch sessions on a private tmux server and never types into a real agent pane.
Product repos are another matter: there, Python goes through `uv run`.

## Dashboard and build phases

`hub dashboard` serves http://127.0.0.1:8765/ (who is doing what) and http://127.0.0.1:8765/phases
(where a project's build is). The phases page reads `projects/<project>/phases.json` (each phase's
name, goal, task ids and a `waiting_on_you` line) and takes every status live from the board. The
planner owns that file: add new tasks to a phase and keep `waiting_on_you` current as things move.
The dashboard is also a local OpenTelemetry metrics sink: the Claude launchers export metrics tagged
per agent to `/v1/metrics` (`HUB_DASHBOARD=0` turns that off).

## Known limit: identity is self-declared

Board commands take the acting agent from `--as` or `HUB_AGENT`. Rules that depend on who acts (only
`$HUB_LEAD` clears `untrusted`; a builder's LGTM never counts) stop a naive injected instruction or an
honest mistake, not a determined one. Closing that needs signed identities; it is logged with the
signed-LGTM shortcut in `live_merge.py`. Likewise any agent can `hub edit --tag headless`, which hands
the task to an unattended `run.py` (`hubrun`) on the next dispatch tick: the same power as calling
`hubrun` directly.
