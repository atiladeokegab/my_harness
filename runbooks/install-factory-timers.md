# Install the factory timers, snapshot bucket and agent hooks

The factory loops (see the factory section of `~/hub/OVERVIEW.md`) are systemd user timers. Nothing
here is done by the installer: you switch them on once, by hand. No sudo. Linux only: macOS has no
systemd, so there you would run the same commands from launchd or cron yourself.

What gets installed:

| Unit | When | Runs |
|---|---|---|
| `hub-dispatch.timer` | every 2 min | `dispatch.py tick`: wakes each idle agent once per task, starts `hubrun` for tasks tagged `headless`, polls factory repos every `poll_seconds` |
| `hub-dispatch.path` | on a kick | the same tick, started when `state/dispatch.kick` changes; the timer stays as the fallback |
| `hub-watch.timer` | every minute | `dispatch.py watch`: classifies each live pane (dialog, rate limited, logged out, stuck), logs changes, alerts the lead agent |
| `hub-snapshot-quick.timer` | every 15 min | `snapshot.sh quick`: board.json and events.jsonl to `<bucket>/live/` |
| `hub-nightly.timer` | 02:30 UTC | `inbox_gc.py`, `hub ws gc`, then `snapshot.sh full` (keeps 30 nightly tarballs, with `artifacts/` and, if the hub is a git repo, `hub.bundle`) |
| `hub-weekly.timer` | Monday 07:00 UTC | `dispatch.py weekly`: "Weekly cleanup" and "Promote rule candidates" for the lead agent; then `hub spec converge` |
| `hub-live@<p>.service` | always, per project | `hub live --project <p>`, restarted on failure; see section 6 |

Kill switch: `hub pause "reason"` stops the dispatcher, the weekly tasks and `hubrun`. The health
watch keeps reporting while paused.

## 0. Your factory.json

```bash
cp ~/hub/factory.example.json ~/hub/factory.json
$EDITOR ~/hub/factory.json
```

- `agents`: who the dispatcher may wake. `kind` is `claude` or `codex`; `dispatch: false` keeps the
  lead out of the rotation. `"reset": "per-task"` starts that agent on a fresh session for each
  dispatched task (`docs/hub/dispatch.md`, "Fresh context per task"); `false` or missing keeps one session. Without the file, the roster variables (`HUB_CODEX_AGENTS`,
  `HUB_CLAUDE_AGENTS`, `HUB_LEAD`) are used, with the lead never dispatched.
- `repos`: GitHub repos whose `agent`-labelled issues and red CI on main become tasks. A spec
  project's repo may set `acceptance_cmd` (default `uv run pytest -q {test}`).
- `projects`: the only hub projects the dispatcher offers work from. Missing means every project.
- `snapshot_bucket`: a `gs://` bucket you own (step 2). Leave the placeholder to skip snapshots.
- `lead_alert`: optional argv of a command that reaches you, the human (a chat bot, a pager,
  `["notify-send", "hub"]`). The message is appended as the last argument. Empty means only the lead
  agent's inbox hears of trouble.

factory.json is gitignored: it names your repos.

## 1. Look before you switch on

```bash
cd ~/hub
env -u HUB_AGENT python3 dispatch.py tick --dry-run     # who would be woken, for what
env -u HUB_AGENT python3 dispatch.py watch --dry-run    # each live pane's health
env -u HUB_AGENT python3 dispatch.py weekly --dry-run
```

Only tasks in factory.json `projects` are offered: an agent's own open tasks first, then unowned
ones, in `hub next`'s order. Unowned open tasks in those projects go to any idle agent, so give
them an owner or close them first if they should not be picked up.

## 2. The snapshot bucket (optional; private, versioned, uniform access)

Use your own project and region. The name goes in factory.json `snapshot_bucket`.

```bash
B=gs://your-hub-snapshots          # as in factory.json
P=your-gcp-project
gcloud storage buckets create "$B" --project="$P" --location=<region> \
    --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "$B" --versioning
cat > /tmp/hub-snapshots-lifecycle.json <<'JSON'
{"rule": [{"action": {"type": "Delete"}, "condition": {"isLive": false, "daysSinceNoncurrentTime": 7}}]}
JSON
gcloud storage buckets update "$B" --lifecycle-file=/tmp/hub-snapshots-lifecycle.json
gcloud storage buckets describe "$B" \
    --format='yaml(location,versioning,iamConfiguration.uniformBucketLevelAccess,iamConfiguration.publicAccessPrevention,lifecycle)'
```

Expect versioning enabled, uniform access enabled and `publicAccessPrevention: enforced`. The
lifecycle rule expires overwritten quick copies and pruned nightly tarballs a week after they stop
being current, so the bucket stays at roughly 30 nightly tarballs plus a week of history.

First copies by hand, so a failure shows now and not at 02:30:

```bash
~/hub/snapshot.sh quick
~/hub/snapshot.sh full
gcloud storage ls -l "$B/live/" "$B/nightly/"
```

Until the bucket exists, both modes print `bucket ... is missing or unreadable; nothing copied`
and exit 0.

## 3. Timers

The units read `HUB_DIR` (default `~/hub`) and your roster from `~/.config/hub/env`. Write it from a
shell that has sourced `shell.sh`, so the timers see the same names you do:

```bash
mkdir -p ~/.config/hub
env | grep -E '^HUB_(DIR|CODE_DIR|LEAD|REVIEWER|CLAUDE_AGENTS|CODEX_AGENTS)=' > ~/.config/hub/env
cd ~/.config/systemd/user 2>/dev/null || { mkdir -p ~/.config/systemd/user && cd ~/.config/systemd/user; }
for u in hub-dispatch hub-watch hub-snapshot-quick hub-nightly hub-weekly; do
    ln -sf "$HUB_DIR/systemd/$u.service" "$HUB_DIR/systemd/$u.timer" .
done
systemctl --user daemon-reload
systemctl --user enable --now hub-dispatch.timer hub-watch.timer hub-snapshot-quick.timer hub-nightly.timer hub-weekly.timer
systemctl --user list-timers
loginctl enable-linger "$USER"   # keep user timers running while you are logged out
```

Check a real tick:

```bash
systemctl --user start hub-dispatch.service
journalctl --user -u hub-dispatch -n 20 --no-pager
cat ~/hub/state/dispatch.json
```

### Dispatch on a kick

`board.py` touches `~/hub/state/dispatch.kick` whenever a board write records `created`, `done`,
`released`, `unblocked`, `assigned`, `delegated` or `reopened`, and `heartbeat.sh` touches it
when any agent but the lead stops a turn. `hub note` and `notify` events do not kick. `hub done`
also touches `~/hub/projects/<p>/.tick-now` when that directory exists, for hub live.

The path unit watches `%h/hub/state/dispatch.kick`; systemd cannot read `HUB_DIR` there, so if
your hub is elsewhere, edit `PathModified=` in `hub-dispatch.path` first.

```bash
ln -sf "$HUB_DIR/systemd/hub-dispatch.path" ~/.config/systemd/user/
systemctl --user daemon-reload
systemd-analyze --user verify "$HUB_DIR/systemd/hub-dispatch.path"   # no output
systemctl --user enable --now hub-dispatch.path
systemctl --user status hub-dispatch.path --no-pager              # active (waiting)
touch "$HUB_DIR/state/dispatch.kick"
sleep 5; journalctl --user -u hub-dispatch --since -1min --no-pager   # a tick within seconds
```

A kick while a tick is still running starts nothing new, because the oneshot is already active;
the dispatcher's own re-run covers that. A missed kick waits for the 2-minute timer.

## 4. Heartbeat and delivery hooks

`heartbeat.sh` writes `~/hub/state/<agent>.json` when a prompt is submitted, on every tool call and
at the end of every turn. `hubwaked` reads a fresh `UserPromptSubmit`/`PostToolUse` heartbeat as
busy and types nothing into that pane.
The health watch reads it before the pane: a heartbeat older than `stuck_minutes` (30) while the
agent holds a claimed task is "stuck". The agent name comes from `HUB_AGENT`, which the launchers
set, so one command serves every config and ad-hoc sessions write nothing.

Merge this into each Claude agent's `settings.json` (`~/.claude/` for the lead,
`~/.claude-<name>/` for the others), with your real `HUB_DIR` in place of `~/hub`:

```bash
H="$HUB_DIR/heartbeat.sh"
for f in ~/.claude/settings.json ~/.claude-*/settings.json; do
    [ -f "$f" ] || continue
    cp "$f" "$f.bak-$(date +%Y%m%d)"
    jq --arg h "$H" '.hooks.PostToolUse += [{"matcher": "*", "hooks": [{"type": "command", "command": $h, "timeout": 10}]}]
      | .hooks.Stop += [{"hooks": [{"type": "command", "command": $h, "timeout": 10}]}]
      | .hooks.UserPromptSubmit += [{"hooks": [{"type": "command", "command": $h, "timeout": 10}]}]' \
      "$f" > "$f.new" && mv "$f.new" "$f"
done
```

The two delivery hooks are optional and need `node` and `hub` on `PATH`. `stop-deliver.js` hands
an agent its pending messages when its turn ends, as a Stop block, so it continues into them with
no keystroke; `inbox-surface.js` shows new inbox lines on each prompt and tool call (`hub inbox
--unseen`). Both stay silent for an ad-hoc session, and `stop-deliver` for the lead and for a pane
a person is attached to. Add them the same way:

```bash
D="node $HUB_DIR/hooks/stop-deliver.js" S="node $HUB_DIR/hooks/inbox-surface.js"
for f in ~/.claude/settings.json ~/.claude-*/settings.json; do
    [ -f "$f" ] || continue
    jq --arg d "$D" --arg s "$S" '.hooks.Stop += [{"hooks": [{"type": "command", "command": $d, "timeout": 15}]}]
      | .hooks.UserPromptSubmit += [{"hooks": [{"type": "command", "command": $s, "timeout": 8}]}]
      | .hooks.PostToolUse += [{"hooks": [{"type": "command", "command": $s, "timeout": 8}]}]' \
      "$f" > "$f.new" && mv "$f.new" "$f"
done
```

A third, `session-ship-check.js`, runs `hub ship-check --quiet` at `SessionStart` and warns when
harness files (plans, reviews, agent notes) would reach a shared repo; a clean repo prints nothing.
Add it the same way: `.hooks.SessionStart += [{"hooks": [{"type": "command", "command":
"node $HUB_DIR/hooks/session-ship-check.js", "timeout": 10}]}]`.

Hooks load when a session starts: restart each agent at a quiet moment. Then:

```bash
cat ~/hub/state/*.json   # {"at": ..., "event": "PostToolUse", "tool": "Bash"}
```

### Codex agents: `~/.codex/hooks.json`

Codex runs hooks in its shared app-server daemon, whose environment belongs to whichever process
started it, so a Codex hook must never read `HUB_AGENT` or `HUB_DIR` from the env. The hooks ignore
a Codex payload with no `--agent`, so a Codex agent gets heartbeats, Stop-hook delivery and inbox
surfacing only from this file. Write it (back up any existing copy first), with your agent's name
and your real `HUB_DIR` in place of `/path/to/hub`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [
      {"type": "command", "command": "HUB_DIR=/path/to/hub /path/to/hub/heartbeat.sh --agent Prometheus", "timeout": 10},
      {"type": "command", "command": "HUB_DIR=/path/to/hub node /path/to/hub/hooks/inbox-surface.js --agent Prometheus", "timeout": 8}]}],
    "PostToolUse": [{"hooks": [
      {"type": "command", "command": "HUB_DIR=/path/to/hub /path/to/hub/heartbeat.sh --agent Prometheus", "timeout": 10},
      {"type": "command", "command": "HUB_DIR=/path/to/hub node /path/to/hub/hooks/inbox-surface.js --agent Prometheus", "timeout": 8}]}],
    "Stop": [{"hooks": [
      {"type": "command", "command": "HUB_DIR=/path/to/hub /path/to/hub/heartbeat.sh --agent Prometheus", "timeout": 10},
      {"type": "command", "command": "HUB_DIR=/path/to/hub node /path/to/hub/hooks/stop-deliver.js --agent Prometheus", "timeout": 15}]}]
  }
}
```

`hub` must be on the daemon's `PATH` (`~/.local/bin`) for the node hooks. Relaunch the agent
attended. Codex opens on "Hooks need review": trust them. If it offers "Update available", press
Esc, never Enter: the default option runs an npm global install.

Without this file the watch falls back to "pane unchanged for 30 minutes" for a Codex agent, and its
messages wait for the relay to find its pane idle.

## 5. Where to look

| Question | Look at |
|---|---|
| Why was an agent woken, or not? | `journalctl --user -u hub-dispatch`, `~/hub/state/dispatch.json` |
| What went wrong with an agent, and when? | `~/hub/watchdog.log` (one line per change of cause, UTC) |
| Is an agent's rate-limit breaker on? | `~/hub/state/watch.json`, key `limited` |
| Did last night's snapshot run? | `journalctl --user -u hub-nightly`, `gcloud storage ls <bucket>/nightly/` |

An offer that gets no claim within `intervals.offer_minutes` (30) expires and the task goes to
another idle agent, never back to the one that ignored it; an agent with an offer pending gets no
new one. Offers for tasks that are no longer open are dropped. To re-offer a task by hand, delete
its id from `woken` in `~/hub/state/dispatch.json`. Restore from the bucket: `restore-hub.md`.

## 6. hub live under systemd

`hub-live@<p>.service` runs `hub live --project <p>` for one project, in place of a hand-started
`tmux hub-live-<p>` session. Output is appended to `~/hub/projects/<p>/live.out`. A crash restarts it
after 30 s; 5 starts in 10 minutes stop it (`failed`, the journal says "Start request repeated too
quickly"). A clean exit, after submit has passed, stays stopped. With linger on (section 3), enabled
instances start at boot. Like the path unit it names `%h/hub`: edit it if your hub is elsewhere.

If another `hub live` holds `projects/<p>/.live.lock` (an old tmux one), the unit writes
`hub-live@<p>: .live.lock held or unreadable (flock exit 75), not starting` to live.out, exits 75
and is not restarted. So stop the tmux session first. A missing `projects/<p>/` (a typo in the
instance name) fails at once with `status=209/STDOUT` and is not restarted either. `systemctl --user
stop` signals only hub live itself (`KillMode=process`): a change gate or deploy it started keeps
running, writes its exit file, and the next hub live reads it.

```bash
ln -sf "$HUB_DIR/systemd/hub-live@.service" ~/.config/systemd/user/
systemctl --user daemon-reload
p=your-project
tmux kill-session -t hub-live-$p 2>/dev/null
systemctl --user enable --now hub-live@$p
systemctl --user status hub-live@$p --no-pager       # active (running)
tail ~/hub/projects/$p/live.out ~/hub/projects/$p/live.log
```

`hub live --merge-now`, `--hold-merges` and `--resume-merges` work as before: they touch files the
running loop reads. After a crash loop, fix the cause, then
`systemctl --user reset-failed hub-live@$p && systemctl --user start hub-live@$p`.
Roll back with `systemctl --user disable --now hub-live@$p` and start it in tmux again.

## Undo

```bash
systemctl --user disable --now hub-dispatch.path hub-dispatch.timer hub-watch.timer hub-snapshot-quick.timer hub-nightly.timer hub-weekly.timer
rm ~/.config/systemd/user/hub-{dispatch,watch,snapshot-quick,nightly,weekly}.{service,timer} ~/.config/systemd/user/hub-dispatch.path
systemctl --user daemon-reload
```

The hooks come out by restoring the `settings.json.bak-*` copies.
