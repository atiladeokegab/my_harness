#!/usr/bin/env bash
# Copies hub state off this disk to the private, versioned bucket named in factory.json (T-501).
#
#   snapshot.sh full    nightly: tarball of board.json, events.jsonl, inbox/, projects/; keeps the newest 30
#   snapshot.sh quick   every 15 min: board.json and events.jsonl to live/ (bucket versioning keeps history)
#
# Never blocks anything: a missing bucket, gcloud or login logs one line and exits 0.
# The bucket is created once by hand: runbooks/install-factory-timers.md. Restore: runbooks/restore-hub.md.
set -uo pipefail
HUB_DIR="${HUB_DIR:-$HOME/hub}"
mode="${1:-full}"
say() { echo "snapshot $mode: $*"; }

bucket=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_bucket"])' \
    "$HUB_DIR/factory.json" 2>/dev/null)
[[ "$bucket" == gs://* ]] || { say "no snapshot_bucket in $HUB_DIR/factory.json; nothing copied"; exit 0; }
command -v gcloud >/dev/null || { say "gcloud not on PATH; nothing copied"; exit 0; }
if ! timeout 60 gcloud storage buckets describe "$bucket" --format='value(name)' >/dev/null 2>&1; then
    say "bucket $bucket is missing or unreadable; nothing copied. Create it with runbooks/install-factory-timers.md"
    exit 0
fi

case "$mode" in
quick)
    timeout 300 gcloud storage cp --quiet "$HUB_DIR/board.json" "$HUB_DIR/events.jsonl" "$bucket/live/" \
        && say "copied board.json and events.jsonl to $bucket/live/" || say "copy failed"
    ;;
full)
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
    name="hub-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
    parts=(); for p in board.json events.jsonl inbox projects; do [ -e "$HUB_DIR/$p" ] && parts+=("$p"); done
    # --warning=no-file-changed: agents keep writing while we read; a moving file is not a failure.
    tar --warning=no-file-changed -czf "$tmp/$name" -C "$HUB_DIR" "${parts[@]}"
    [ $? -le 1 ] || { say "tar failed; nothing copied"; exit 0; }
    timeout 1800 gcloud storage cp --quiet "$tmp/$name" "$bucket/nightly/$name" \
        || { say "upload failed"; exit 0; }
    say "uploaded $bucket/nightly/$name ($(du -h "$tmp/$name" | cut -f1))"
    # Names sort by time; deleting makes a noncurrent version, which the bucket lifecycle expires.
    old=$(timeout 120 gcloud storage ls "$bucket/nightly/hub-*.tar.gz" | sort | head -n -30)
    [ -z "$old" ] || { echo "$old" | xargs timeout 300 gcloud storage rm --quiet && say "pruned $(echo "$old" | wc -l) old snapshot(s)"; }
    ;;
*) echo "usage: snapshot.sh full|quick" >&2; exit 2 ;;
esac
exit 0
