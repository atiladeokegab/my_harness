# Restore the hub from the snapshot bucket

**Symptom.** The hub machine's disk is lost or the board is corrupt, or you are standing up the hub
on a new machine.

**What exists.** The bucket named in factory.json `snapshot_bucket` (private, versioned), written by
`snapshot.sh` (see `install-factory-timers.md`):

- `nightly/hub-<UTC time>.tar.gz`: board.json, events.jsonl, inbox/ and projects/ at 02:30 UTC,
  newest 30 kept.
- `live/board.json`, `live/events.jsonl`: copied every 15 minutes. Older copies are noncurrent
  versions, kept for 7 days.

Code is not in the bucket: reinstall it from the harness repo (`./install.sh`), or from your own
git remote if you keep `~/hub` in git. factory.json is not in the bucket either; keep a copy.

## Steps

1. Stop everything that writes the board: `hub pause "restoring"`, then
   `systemctl --user stop hub-dispatch.timer hub-watch.timer hub-snapshot-quick.timer`, and
   `hubkill` each agent. A quick copy taken mid-restore would overwrite the good one.
2. Keep what is there: `mv ~/hub/board.json ~/hub/board.json.broken` (same for events.jsonl).
3. Take the newest nightly for inboxes and projects:

   ```bash
   B=gs://your-hub-snapshots          # factory.json snapshot_bucket
   gcloud storage ls "$B/nightly/" | sort | tail -1                  # newest
   gcloud storage cp "$B/nightly/hub-YYYYMMDDTHHMMSSZ.tar.gz" /tmp/
   tar -xzf /tmp/hub-YYYYMMDDTHHMMSSZ.tar.gz -C ~/hub
   ```

4. Then the newer board and ledger from `live/` (at most 15 minutes old):

   ```bash
   gcloud storage cp "$B/live/board.json" "$B/live/events.jsonl" ~/hub/
   ```

   To go back further, list versions and copy one by its generation:
   `gcloud storage ls -a "$B/live/board.json"`, then
   `gcloud storage cp "$B/live/board.json#<generation>" ~/hub/board.json`.

5. Check: `hub list` reads cleanly and `tail -3 ~/hub/events.jsonl` matches the newest work you
   remember. A torn last ledger line (copied mid-append) can be deleted.
6. Start again: `hub resume`, start the timers, relaunch the agents. Tell them the board was
   restored to <time>; work after that time is gone from the board and must be re-noted from git
   history.
