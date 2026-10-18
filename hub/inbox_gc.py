#!/usr/bin/env python3
"""Archive inbox messages received more than seven days ago."""

import fcntl
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent


def _lock(file, timeout=5):
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"inbox lock busy: {file.name}")
            time.sleep(0.1)


def _old_received(line, receipts, cutoff):
    try:
        message = json.loads(line)
        at = datetime.fromisoformat(message["at"])
        if at.tzinfo is None or at >= cutoff:
            return None
        mid = message.get("id")
        if isinstance(mid, str) and re.fullmatch(r"[A-Za-z0-9._-]+", mid) and (receipts / mid).is_file():
            return at.astimezone(timezone.utc).strftime("%Y-%m"), mid
    except (ValueError, KeyError, TypeError):
        pass
    return None


def _archive_one(inbox, source, cutoff):
    agent = source.stem
    with (inbox / f".{agent}.lock").open("a") as lock:
        _lock(lock)
        lines = source.read_text().splitlines(keepends=True)
        receipts = inbox / ".received" / agent
        keep, groups = [], {}
        for line in lines:
            match = _old_received(line, receipts, cutoff)
            if match:
                month, mid = match
                groups.setdefault(month, []).append((mid, line))
            else:
                keep.append(line)
        if not groups:
            return 0

        archive_dir = inbox / "archive"
        archive_dir.mkdir(mode=0o700, exist_ok=True)
        for month, entries in groups.items():
            target = archive_dir / f"{agent}-{month}.jsonl"
            known = set()
            if target.exists():
                for line in target.read_text().splitlines():
                    try:
                        known.add(json.loads(line).get("id"))
                    except ValueError:
                        pass
            with target.open("a") as output:
                for mid, line in entries:
                    if mid not in known:
                        output.write(line if line.endswith("\n") else line + "\n")
                        known.add(mid)
                output.flush()
                os.fsync(output.fileno())

        with tempfile.NamedTemporaryFile(mode="w", dir=inbox, prefix=f".{agent}.",
                                         delete=False) as output:
            temp = Path(output.name)
            output.writelines(keep)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.replace(temp, source)
        finally:
            temp.unlink(missing_ok=True)
        return sum(map(len, groups.values()))


def archive_inboxes(inbox, now=None):
    inbox = Path(inbox)
    if not inbox.is_dir():
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)
    return sum(_archive_one(inbox, source, cutoff) for source in inbox.glob("*.jsonl"))


if __name__ == "__main__":
    hub = Path(os.environ.get("HUB_DIR") or HERE)
    try:
        print(f"archived {archive_inboxes(hub / 'inbox')} received message(s)")
    except (OSError, TimeoutError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
