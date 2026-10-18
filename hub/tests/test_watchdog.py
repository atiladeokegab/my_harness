"""Watchdog health (T-501): dispatch.py watch, plus heartbeat.sh and snapshot.sh, against canned
panes and stub tools. Never touches the live board, panes or bucket.

    python3 tests/test_watchdog.py
"""

import hashlib
import json
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_dispatch import (CLAUDE_IDLE, CLAUDE_PERMISSION, CODEX_LIMIT, HUB, PROMETHEUS_LIMIT_LIVE, Factory,
                                 dispatch, task)

GCLOUD = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
with open(os.path.join(os.environ["FAKE_LOG"], "gcloud.jsonl"), "a") as f:
    f.write(json.dumps(a) + "\n")
if a[:3] == ["storage", "buckets", "describe"]:
    sys.exit(0 if os.environ.get("FAKE_BUCKET") else "ERROR: bucket not found")
if a[:2] == ["storage", "ls"]:
    print("\n".join(f"gs://b/nightly/hub-202609{d:02d}T023000Z.tar.gz" for d in range(1, 33)))
'''


class WatchTest(Factory):
    def zeus_inbox(self):
        p = self.hub / "inbox" / "Zeus.jsonl"
        return p.read_text().splitlines() if p.exists() else []

    def log_lines(self):
        p = self.hub / "watchdog.log"
        return p.read_text().splitlines() if p.exists() else []

    def test_permission_prompt_is_logged_and_alerted_once(self):
        self.pane("hub-hermes", CLAUDE_PERMISSION)
        out = self.run_cmd("watch")
        self.assertIn("Hermes: permission prompt", out)
        [line] = self.log_lines()
        self.assertRegex(line, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ Hermes: healthy -> permission prompt")
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.assertIn("never relaunches a live session", self.zeus_inbox()[0])
        self.assertEqual(self.calls("lead-alert"), [])  # only limits and Zeus reach the lead
        self.run_cmd("watch")
        self.assertEqual(len(self.log_lines()), 1)
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.run_cmd("watch")
        self.assertIn("permission prompt -> healthy", self.log_lines()[-1])
        self.assertEqual(len(self.zeus_inbox()), 1)

    def test_rate_limit_trips_the_breaker_alerts_the_lead_and_stops_wakes(self):
        self.board([task("T-002", owner="Prometheus")])
        self.pane("hub-prometheus", CODEX_LIMIT)
        self.run_cmd("watch")
        lim = self.state("watch.json")["Prometheus"]["limited"]
        self.assertEqual(datetime.fromtimestamp(lim["until"]).strftime("%H:%M"), "19:28")
        self.assertEqual(self.calls("lead-alert")[0][0], "send")  # its failure is ignored
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.pane("hub-prometheus", CLAUDE_IDLE)  # message scrolled away, reset not reached
        self.run_cmd("watch")
        self.assertIn("limited", self.state("watch.json")["Prometheus"])
        self.assertIn("Prometheus: rate limited until", self.run_cmd("tick"))
        self.assertEqual(self.calls("hubmsg"), [])

    def test_the_lead_hears_about_a_limit_once_per_reset_window(self):
        self.pane("hub-prometheus", CODEX_LIMIT)
        self.run_cmd("watch")
        self.pane("hub-prometheus", CLAUDE_IDLE)  # scrolled away; the breaker stays on until 19:28
        self.run_cmd("watch")
        self.pane("hub-prometheus", CODEX_LIMIT)
        self.run_cmd("watch")
        self.assertEqual(len(self.calls("lead-alert")), 1)
        self.assertEqual(len(self.zeus_inbox()), 2)  # Zeus still hears each change

    def test_breaker_without_a_reset_time_clears_when_the_message_goes(self):
        self.pane("hub-prometheus", "■ You've hit your usage limit.\n› Ask Codex to do anything\n")
        self.run_cmd("watch")
        self.assertIsNone(self.state("watch.json")["Prometheus"]["limited"]["until"])
        self.pane("hub-prometheus", CLAUDE_IDLE)
        self.run_cmd("watch")
        self.assertNotIn("limited", self.state("watch.json")["Prometheus"])

    def beat(self, minutes_ago):
        at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        self.write_state("Hermes.json", {"at": at.isoformat(), "event": "Stop", "tool": None})

    def test_stale_heartbeat_while_holding_a_task_is_stuck(self):
        self.board([task("T-002", status="claimed")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.beat(40)
        self.assertIn("Hermes: stuck: no heartbeat for 40 min while holding T-002", self.run_cmd("watch"))
        self.assertEqual(len(self.zeus_inbox()), 1)

    def test_fresh_heartbeat_beats_a_still_pane(self):
        self.board([task("T-002", status="claimed")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.write_state("watch.json", {"Hermes": {"pane": hashlib.sha1(CLAUDE_IDLE.encode()).hexdigest(),
                                                   "pane_since": time.time() - 3600}})
        self.beat(2)
        self.assertIn("Hermes: healthy", self.run_cmd("watch"))

    def test_still_pane_without_heartbeat_is_stuck_only_when_holding_a_task(self):
        seed = {"Hermes": {"pane": hashlib.sha1(CLAUDE_IDLE.encode()).hexdigest(),
                           "pane_since": time.time() - 31 * 60}}
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.write_state("watch.json", seed)
        self.assertIn("Hermes: healthy", self.run_cmd("watch"))
        self.board([task("T-002", status="claimed")])
        self.write_state("watch.json", seed)
        self.assertIn("Hermes: stuck: pane unchanged for 31 min while holding T-002", self.run_cmd("watch"))

    def test_missing_session_is_left_to_the_relaunch_loop(self):
        out = self.run_cmd("watch")
        self.assertIn("Hermes: no session", out)
        self.assertEqual(self.log_lines(), [])
        self.assertEqual(self.zeus_inbox(), [])

    def test_dry_run_only_prints(self):
        self.pane("hub-hermes", CLAUDE_PERMISSION)
        out = self.run_cmd("watch", "--dry-run")
        self.assertIn("would log 'Hermes: healthy -> permission prompt", out)
        self.assertEqual(self.log_lines(), [])
        self.assertEqual(self.zeus_inbox(), [])
        self.assertFalse((self.hub / "state" / "watch.json").exists())

    def test_agent_list_comes_from_factory_json(self):
        self.assertEqual(self.run_cmd("agents").split(), ["Prometheus", "Hermes", "Zeus"])
        (self.hub / "factory.json").write_text(json.dumps({"agents": [{"name": "Hermes; rm -rf ~"}]}))
        self.assertEqual(self.run_cmd("agents").split(), ["Prometheus", "Hermes", "Zeus"])
        self.assertIn("dispatch.py watch", (HUB / "systemd" / "hub-watch.service").read_text())


class HeartbeatTest(Factory):
    def hook(self, stdin, **env):
        e = {k: v for k, v in self.env.items() if k != "CLAUDE_CODE_SESSION_NAME"}
        return subprocess.run([str(HUB / "heartbeat.sh")], input=stdin, env={**e, **env},
                              text=True, capture_output=True, timeout=20)

    def test_writes_the_agents_heartbeat(self):
        r = self.hook(json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash"}), HUB_AGENT="Hermes")
        self.assertEqual(r.returncode, 0)
        beat = self.state("Hermes.json")
        self.assertEqual((beat["event"], beat["tool"]), ("PostToolUse", "Bash"))
        self.assertLess(time.time() - datetime.fromisoformat(beat["at"]).timestamp(), 60)

    def test_never_fails_and_ignores_sessions_without_an_agent(self):
        self.assertEqual(self.hook("not json", HUB_AGENT="Hermes").returncode, 0)
        self.assertEqual(self.state("Hermes.json")["event"], None)
        self.assertEqual(self.hook("{}").returncode, 0)
        self.assertEqual(self.hook("{}", HUB_AGENT="../escape").returncode, 0)
        self.assertEqual(sorted(p.name for p in (self.hub / "state").iterdir()), ["Hermes.json"])
        self.assertFalse((self.hub / "escape.json").exists())


class SnapshotTest(Factory):
    def setUp(self):
        super().setUp()
        (self.bin / "gcloud").write_text(GCLOUD)
        (self.bin / "gcloud").chmod(0o755)
        cfg = json.loads((self.hub / "factory.json").read_text())
        (self.hub / "factory.json").write_text(json.dumps({**cfg, "snapshot_bucket": "gs://b"}))
        (self.hub / "events.jsonl").write_text("{}\n")
        (self.hub / "inbox").mkdir()
        (self.hub / "projects" / "p").mkdir(parents=True)

    def snap(self, mode, **env):
        return subprocess.run([str(HUB / "snapshot.sh"), mode], env={**self.env, **env},
                              text=True, capture_output=True, timeout=60)

    def test_missing_bucket_exits_cleanly_and_copies_nothing(self):
        r = self.snap("full")
        self.assertEqual(r.returncode, 0)
        self.assertIn("bucket gs://b is missing", r.stdout)
        self.assertEqual([c[:2] for c in self.calls("gcloud")], [["storage", "buckets"]])

    def test_full_uploads_a_tarball_and_keeps_30(self):
        r = self.snap("full", FAKE_BUCKET="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.calls("gcloud")
        [cp] = [c for c in calls if c[:2] == ["storage", "cp"]]
        self.assertRegex(cp[-1], r"^gs://b/nightly/hub-\d{8}T\d{6}Z\.tar\.gz$")
        [rm] = [c for c in calls if c[:2] == ["storage", "rm"]]
        self.assertEqual(rm[-2:], ["gs://b/nightly/hub-20260901T023000Z.tar.gz",
                                   "gs://b/nightly/hub-20260902T023000Z.tar.gz"])

    def test_quick_copies_board_and_ledger(self):
        self.assertEqual(self.snap("quick", FAKE_BUCKET="1").returncode, 0)
        [cp] = [c for c in self.calls("gcloud") if c[:2] == ["storage", "cp"]]
        self.assertEqual(cp[-3:], [str(self.hub / "board.json"), str(self.hub / "events.jsonl"), "gs://b/live/"])


class ChromeTest(unittest.TestCase):
    """T-508 (Hermes review of dfb1b24): numbered lists, quoted errors and table rows are not chrome."""

    def test_lists_quotes_and_table_rows_are_not_causes(self):
        for line in ("  1. No change needed on your side.",
                     "1. Yes, keep it open; 2. close it",
                     "> API Error: 429 is what the classifier keys on",
                     "│ API Error: 401 │ logged out │"):
            with self.subTest(line):
                self.assertEqual(dispatch.classify(line + "\n" + CLAUDE_IDLE), (None, ""))

    def test_real_dialogs_and_errors_still_count(self):
        esc_dialog = "│ Do you want to make this edit?\n│ ❯ 1. Yes\n│   2. Yes, allow all edits\n│ Esc to cancel\n"
        for label, pane, cause in (("prometheus limit, live capture", PROMETHEUS_LIMIT_LIVE, "rate limited"),
                                   ("dialog ending in Esc to cancel", esc_dialog, "permission prompt")):
            with self.subTest(label):
                self.assertEqual(dispatch.classify(pane)[0], cause)


if __name__ == "__main__":
    unittest.main()
