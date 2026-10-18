"""Inbox archive keeps every message until it has a receive receipt; hub sh logs last a week."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from inbox_gc import archive_inboxes, prune_logs


class InboxGCCase(unittest.TestCase):
    def test_archives_only_old_received_messages_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as root:
            inbox = Path(root) / "inbox"
            inbox.mkdir()
            messages = [
                {"at": "2026-10-01T10:00:00+00:00", "id": "old-acked", "text": "done"},
                {"at": "2026-10-01T11:00:00+00:00", "id": "old-unread", "text": "keep"},
                {"at": "2026-10-16T10:00:00+00:00", "id": "new-acked", "text": "keep"},
                {"at": "2026-10-01T12:00:00+00:00", "text": "no receipt possible"},
                {"at": "2026-10-01T13:00:00+00:00", "id": "../../outside", "text": "unsafe id"},
            ]
            source = inbox / "Zeus.jsonl"
            source.write_text("".join(json.dumps(m) + "\n" for m in messages) + "broken\n")
            receipts = inbox / ".received" / "Zeus"
            receipts.mkdir(parents=True)
            (receipts / "old-acked").touch()
            (receipts / "new-acked").touch()
            (inbox / "outside").touch()
            now = datetime(2026, 10, 17, 15, tzinfo=timezone.utc)

            self.assertEqual(archive_inboxes(inbox, now), 1)
            archived = inbox / "archive" / "Zeus-2026-10.jsonl"
            self.assertEqual(archived.read_text().splitlines(), [json.dumps(messages[0])])
            self.assertEqual(source.read_text().splitlines(),
                             [*(json.dumps(m) for m in messages[1:]), "broken"])
            self.assertEqual(archive_inboxes(inbox, now), 0)
            self.assertEqual(len(archived.read_text().splitlines()), 1)

    def test_prunes_sh_logs_older_than_seven_days(self):
        with tempfile.TemporaryDirectory() as root:
            logs = Path(root) / "logs" / "sh"
            (logs / "Zeus").mkdir(parents=True)
            old, new = logs / "Zeus" / "old.log", logs / "Zeus" / "new.log"
            now = datetime(2026, 10, 17, 15, tzinfo=timezone.utc)
            for f, days in ((old, 8), (new, 6)):
                f.touch()
                os.utime(f, (now.timestamp() - days * 86400,) * 2)
            self.assertEqual(prune_logs(logs, now), 1)
            self.assertEqual(list(logs.rglob("*.log")), [new])
            self.assertEqual(prune_logs(Path(root) / "missing", now), 0)


if __name__ == "__main__":
    unittest.main()
