# Install the factory timers, snapshot bucket and heartbeat hooks

The factory loops (see the factory section of `~/hub/OVERVIEW.md`) are systemd user timers. Nothing
here is done by the installer: you switch them on once, by hand. No sudo. Linux only: macOS has no
systemd, so there you would run the same commands from launchd or cron yourself.

What gets installed:

| Unit | When | Runs |
|---|---|---|
| `hub-dispatch.timer` | every 2 min | `dispatch.py tick`: wakes each idle agent once per task, starts `hubrun` for tasks tagged `headless`, polls factory repos every `poll_seconds` |
| `hub-watch.timer` | every minute | `dispatch.py watch`: classifies each live pane (dialog, rate limited, logged out, stuck), logs changes, alerts the lead agent |
| `hub-snapshot-quick.timer` | every 15 min | `snapshot.sh quick`: board.json and events.jsonl to `<bucket>/live/` |
| `hub-nightly.timer` | 02:30 UTC | `inbox_gc.py`, then `snapshot.sh full` (keeps 30 nightly tarballs) |
| `hub-weekly.timer` | Monday 07:00 UTC | `dispatch.py weekly`: "Weekly cleanup" and "Promote rule candidates" for the lead agent |

Kill switch: `hub pause "reason"` stops the dispatcher, the weekly tasks and `hubrun`. The health
watch keeps reporting while paused.

## 0. Your factory.json

```bash
cp ~/hub/factory.example.json ~/hub/factory.json
$EDITOR ~/hub/factory.json
```

- `agents`: who the dispatcher may wake. `kind` is `claude` or `codex`; `dispatch: false` keeps the
  lead out of the rotation. Without the file, the roster variables (`HUB_CODEX_AGENTS`,
  `HUB_CLAUDE_AGENTS`, `HUB_LEAD`) are used, with the lead never dispatched.
- `repos`: GitHub repos whose `agent`-labelled issues and red CI on main become tasks.
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

## 4. Heartbeat hooks for the Claude agents

`heartbeat.sh` writes `~/hub/state/<agent>.json` on every tool call and at the end of every turn.
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
      | .hooks.Stop += [{"hooks": [{"type": "command", "command": $h, "timeout": 10}]}]' \
      "$f" > "$f.new" && mv "$f.new" "$f"
done
```

Hooks load when a session starts: restart each agent at a quiet moment. Then:

```bash
cat ~/hub/state/*.json   # {"at": ..., "event": "PostToolUse", "tool": "Bash"}
```

Codex agents have no such hook; the watch falls back to "pane unchanged for 30 minutes".

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

## Undo

```bash
systemctl --user disable --now hub-dispatch.timer hub-watch.timer hub-snapshot-quick.timer hub-nightly.timer hub-weekly.timer
rm ~/.config/systemd/user/hub-{dispatch,watch,snapshot-quick,nightly,weekly}.{service,timer}
systemctl --user daemon-reload
```

The hooks come out by restoring the `settings.json.bak-*` copies.
