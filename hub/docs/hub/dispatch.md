# The factory: dispatch, fresh context, workspaces and hub sh

Part of the hub manual. Index: `$HUB_DIR/HUB.md` (default `~/hub/HUB.md`).

## The factory

Optional, off until you switch it on (`runbooks/install-factory-timers.md`; how it works:
`OVERVIEW.md`). The timers are systemd user units, so this part is Linux only: on macOS the
board, agents and messaging work, but you would schedule `dispatch.py tick` yourself, and
headless runs started by the dispatcher need `systemd-run`. The commands you use by hand:

```bash
hub pause "reason"            # kill switch: no claims, wakes, polls, headless runs or merges
hub resume
hub edit T-012 --tag headless # the dispatcher runs it unattended with hubrun
hub edit T-012 --untag untrusted   # only the lead ($HUB_LEAD) clears untrusted (after reading the issue)
hubrun T-012                  # one headless run now; the result lands as a task note
python3 ~/hub/dispatch.py tick --dry-run    # who would be woken, for what
python3 ~/hub/dispatch.py watch --dry-run   # each live pane's health
```

`hub done` runs the task's `verify:` command (default `make check` in the task's checkout) and
refuses on failure; at two failed attempts the task blocks and the lead is told. A task tagged
`standing` (a watch duty, a review rota) never makes its owner look busy to the dispatcher.

## Dispatch: a kick, then the timer

`dispatch.py tick` offers open tasks to idle agents whose effective phase enables dispatch.
`factory.json` is the source of truth; `hub agents` shows the resolved phase policy.
Reviewer and lead phases disable dispatch. It runs on a kick and every 2 minutes as
the fallback (`hub-dispatch.timer`).

- **Kicks.** A board write recording `created`, `done`, `released`, `unblocked`, `assigned`, `delegated`
  or `reopened` touches `state/dispatch.kick`, and so does any agent's `Stop` heartbeat except the lead's.
  `hub-dispatch.path` sees the change and starts the tick. Notes and messages do not kick.
- **Debounce.** A tick within 5 s of the last one waits out the rest of the 5 s (`debounced` in the
  journal). A kick that lands during a tick makes it run once more, at most twice.
- **hub live** gets its own kick: `hub done` touches `projects/<p>/.tick-now`, and a finished gate or deploy
  runs a merge-and-deploy pass within 10 s.
- **`read` tasks.** A task tagged `read` (`hub new --tag read`) goes first to the reader, a dispatched
  agent with `"reads": true` in `factory.json`, if you have one. Everyone else is offered it only once it
  has been open longer than `offer_minutes` (30), in case the reader is down or out of quota.

Log: `journalctl --user -u hub-dispatch`. Install: `runbooks/install-factory-timers.md`.

## The health watch

`hub-watch.timer` runs `hub-watch.service`, which runs `dispatch.py watch` every minute. It reads the
bottom of each live pane and classifies it: permission prompt, rate limited, logged out, or stuck
(a claimed task and no heartbeat for 30 minutes). It matches the CLIs' own chrome, never prose, so an
agent quoting an error is not flagged. A rate limit trips a breaker until the reset time shown, and
the dispatcher wakes nobody behind it. Changes go to `watchdog.log` and to the lead agent's inbox; an agent
at a prompt for 3 minutes is reported there too, again every 15 minutes. It never kills or relaunches a session.
Log: `journalctl --user -u hub-watch`.

## Fresh context per task

A session that lives for days resends its whole conversation every turn. The dispatcher can start a
dispatched agent on a clean session for each task instead.

- **Who.** Agents whose effective phase has `"reset": "per-task"`. A phase's `"reset": false`
  opts its agents out. With an explicit phase, per-agent `dispatch` and `reset` keys are
  ignored; change the phase through `hub agent phase`, not those keys. The lead phase never resets.
- **When.** At a dispatch tick, only if the agent holds no claimed task (standing ones included) and no
  blocked task, its pane is idle, and its last heartbeat is `Stop`. The configured reviewer's wakes come
  from `hub live`, not the dispatcher, so they never reset.
- **How.** The dispatcher queues `[dispatch] Fresh session. Your task: T-n ...` in the inbox and a reset
  request. `hubwaked` re-checks every guard, clears the composer, types `/clear` (Claude) or `/new`
  (Codex), confirms the composer let go of it, waits 3 s, then types the receive line. If anything fails
  (attached, dialog, busy, a heartbeat newer than the offer, a task now held, the command still in the
  composer) it downgrades to a plain wake. A reset is never retried. `wake/hubwaked.log` says `reset
  delivered` or `reset downgraded: <why>`.
- **The handoff note.** Only the board, inbox, git and memory survive a reset. For every agent
  in the factory roster, `hub done` refuses a `--note` under 20 characters: write what changed, the
  branch and commit, and what is left. `--force` bypasses it and is recorded in the ledger.

## Workspaces: one worktree per claim (`hub ws`)

Builders sharing one long-lived clone work on whatever happens to be checked out there, and can read a
stale branch from it. So `hub claim` makes a fresh worktree for the task:

```
workspace: ~/work/<p>/T-NNN (detached at origin/integration 1a2b3c4, fetched 12:05Z)
create your branch there: git switch -c <issue>-<slug> | task/T-NNN
```

- **Base:** `origin/change/C-NNN` for a spec-generated task, else `origin/integration` if it exists, else
  `origin/HEAD`. The clone (`$HUB_CODE_DIR/<p>`) is fetched first; `.env` is copied in.
- **Work only in the printed path**, and create your branch there (`git switch -c <issue>-<slug>` or
  `task/T-NNN`). `hub done` runs its verify in that path. A re-claim reuses the path untouched.
- **No workspace** for project `hub` (it works in the live hub directory, and never as a linked worktree:
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
