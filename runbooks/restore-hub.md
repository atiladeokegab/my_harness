# Restore the hub from the snapshot bucket

**Symptom.** The hub machine's disk is lost or the board is corrupt, or you are standing up the hub
on a new machine.

**What exists.** The bucket named in factory.json `snapshot_bucket` (private, versioned), written by
`snapshot.sh` (see `install-factory-timers.md`):

- `nightly/hub-<UTC time>.tar.gz`: board.json, events.jsonl, inbox/, projects/ and artifacts/ at
  02:30 UTC as plain files, plus, when `~/hub` is a git repo, `hub.bundle`: `git bundle --all`, the
  whole history including projects/. Newest 30 kept. Never push the bundle anywhere public.
- `live/board.json`, `live/events.jsonl`: copied every 15 minutes. Older copies are noncurrent
  versions, kept for 7 days.

Code is not in the bucket: reinstall it from the harness repo (`./install.sh`), or from your own
git remote if you keep `~/hub` in git. factory.json is not in the bucket either; keep a copy.

**What a disk loss costs, even after a clean restore:** `projects/`, `artifacts/` and `inbox/` come
back as of 02:30. Edits since are gone, messages sent since are lost, and messages read since
reappear.

Pick the case first. **Case A**, board or ledger corrupt but the disk is fine: steps 1, 2, 4, 5, 6.
Do **not** extract a nightly over a live `~/hub`: it rolls `projects/` and `inbox/` back to 02:30.
**Case B**, disk lost or new machine: steps 1 (whatever still runs), 3, 4, 5, 6.

## Steps

1. Stop everything that writes the board or the bucket: `hub pause "restoring"`, then
   `systemctl --user stop hub-dispatch.path hub-dispatch.timer hub-watch.timer hub-snapshot-quick.timer hub-nightly.timer hub-weekly.timer`,
   and `hubkill` each agent. A quick copy taken mid-restore would overwrite the good `live/` copy,
   and a nightly would upload the half-restored state.
2. Case A only. Keep what is there, including the write-ahead log, which the next `hub` command
   would otherwise replay over the restored board, then go to step 4:

   ```bash
   cd ~/hub && for f in board.json events.jsonl .board.wal; do [ -e $f ] && mv $f $f.broken; done
   ```
3. Case B only. The newest nightly: its bundle (if it has one) becomes `~/hub` with its history,
   the installer puts the code back, and the tarball's files restore inboxes, projects and artifacts:

   ```bash
   B=gs://your-hub-snapshots          # factory.json snapshot_bucket
   N=$(gcloud storage ls "$B/nightly/hub-*.tar.gz" | sort | tail -1)    # names sort by time
   R=$(mktemp -d); gcloud storage cp "$N" $R/ && tar -xzf $R/$(basename "$N") -C $R
   [ -f $R/hub.bundle ] && git clone -q $R/hub.bundle ~/hub
   ./install.sh                                          # from your harness checkout
   tar -xzf $R/$(basename "$N") -C ~/hub --exclude=hub.bundle
   rm -rf $R
   ```

4. The newer board and ledger from `live/` (at most 15 minutes old):

   ```bash
   gcloud storage ls -l "$B/live/"                       # the time they were copied
   gcloud storage cp "$B/live/board.json" "$B/live/events.jsonl" ~/hub/
   ```

   To go back further, list versions and copy one by its generation:
   `gcloud storage ls -a "$B/live/board.json"`, then
   `gcloud storage cp "$B/live/board.json#<generation>" ~/hub/board.json`. Take `events.jsonl`
   from the same copy time, so the ledger matches the board.

5. Check:

   ```bash
   hub list | head                                       # loads; exit 0
   uv run --no-project python -c 'import json,os; [json.loads(l) for l in open(os.path.expanduser("~/hub/events.jsonl"))]'
   tail -3 ~/hub/events.jsonl                            # the newest work you remember
   ls ~/hub/inbox ~/hub/projects | head                  # Case B
   ```

   A parse error on the last ledger line means it was copied mid-append (a torn line): delete
   that line. Any other bad line, try an older generation.
6. Start again: `hub resume`, start the timers (`install-factory-timers.md` on a new machine),
   relaunch the agents. Tell them the board was
   restored to <time>; work after that time is gone from the board and must be re-noted from git
   history.

## Rehearse without touching the live hub

Restore into a scratch dir and point the CLI at it, with the agent variables unset so nothing is
attributed to a live session, and use read-only commands only (`list`, `show`, `brief`):

```bash
S=$(mktemp -d); mkdir $S/hub
gcloud storage cp "$N" $S/ && tar -xzf $S/$(basename "$N") -C $S/hub
gcloud storage cp "$B/live/board.json" "$B/live/events.jsonl" $S/hub/
env -u HUB_AGENT -u HUB_PROJECT -u CLAUDE_CODE_SESSION_NAME HUB_DIR=$S/hub hub list
cmp <(head -n $(wc -l < $S/hub/events.jsonl) ~/hub/events.jsonl) $S/hub/events.jsonl   # a prefix of live
rm -rf $S
```

To test a fresh nightly without touching `nightly/` (its pruning counts files there), write one to a
scratch path: `SNAPSHOT_BUCKET=$B/rehearsal ~/hub/snapshot.sh full`, rehearse from it, then
`gcloud storage rm -r $B/rehearsal`.
