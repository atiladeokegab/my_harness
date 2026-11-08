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
from tests.test_dispatch import (AGY, AGY_LIMIT, CLAUDE_IDLE, CLAUDE_PERMISSION, CODEX_LIMIT, HUB,
                                 PROMETHEUS_LIMIT_LIVE, Factory, dispatch, task)

FIXTURES = HUB / "tests" / "fixtures" / "agy"

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
        self.assertEqual(self.zeus_inbox(), [])  # recovered: the stale alert is withdrawn

    def test_alerts_collapse_to_one_per_agent_and_a_relaunch_clears_them(self):
        """2026-11-01: Zeus's inbox held 1004 messages, mostly stuck alerts about sessions since relaunched."""
        self.board([task("T-002", status="claimed")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.beat(40)
        self.run_cmd("watch")
        self.pane("hub-hermes", CLAUDE_PERMISSION)
        self.run_cmd("watch")
        [alert] = self.zeus_inbox()
        self.assertIn("Hermes: stuck -> permission prompt", alert)
        (self.panes / "hub-hermes").unlink()  # the session dies; the relaunch loop brings it back
        self.run_cmd("watch")
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.beat(1)
        self.run_cmd("watch")
        self.assertEqual(self.zeus_inbox(), [])

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
        [alert] = self.zeus_inbox()  # Zeus still hears each change; only the current one stays
        self.assertIn("healthy -> rate limited", alert)

    def test_breaker_without_a_reset_time_clears_when_the_message_goes(self):
        self.pane("hub-prometheus", "■ You've hit your usage limit.\n› Ask Codex to do anything\n")
        self.run_cmd("watch")
        self.assertIsNone(self.state("watch.json")["Prometheus"]["limited"]["until"])
        self.pane("hub-prometheus", CLAUDE_IDLE)
        self.run_cmd("watch")
        self.assertNotIn("limited", self.state("watch.json")["Prometheus"])

    def agy_quota(self, remaining, reset_in, bucket="gemini-5h", **model):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["agents"].append({"name": "Iris", "kind": "agy"})
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        reset = datetime.now(timezone.utc) + timedelta(seconds=reset_in)
        quota = {b: {"remaining_fraction": 0.5, "reset_time": "2026-10-26T12:38:42Z"}
                 for b in ("gemini-5h", "gemini-weekly", "3p-5h", "3p-weekly")}
        quota[bucket] = {"remaining_fraction": remaining, "reset_time": reset.strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.write_state("Iris.agy.json", {"agent_state": "idle", "quota": quota, **model})
        return int(reset.timestamp())

    def test_agy_reads_the_quota_family_of_the_running_model(self):
        """T-579: Claude models in agy draw on 3p-* buckets, Gemini models on gemini-*; unknown model: either."""
        cases = [("claude-opus-5-5-high", "3p-5h", "Iris: rate limited: 3p-5h quota used up"),
                 ("claude-opus-5-5-high", "gemini-5h", "Iris: healthy"),
                 ("Gemini 3.8 Flash (High)", "3p-weekly", "Iris: healthy"),
                 ("gemini-4-argon-high", "gemini-weekly", "Iris: rate limited: gemini-weekly quota used up"),
                 (None, "3p-5h", "Iris: rate limited: 3p-5h quota used up")]
        for model, bucket, line in cases:
            with self.subTest(model=model, bucket=bucket):
                self.setUp()  # fresh hub: a breaker left on by one case would hide the next
                self.pane("hub-iris", AGY["idle"])
                self.agy_quota(0, 7200, bucket, **({"model": model} if model else {}))
                self.assertIn(line, self.run_cmd("watch"))

    def test_argons_own_bucket_never_blocks_flash(self):
        """Gemini docs review 2026-10-20: gemini-argon-wtu-weekly empty until 26 Oct marked a Flash seat limited."""
        for model, bucket, line in (("Gemini 3.8 Flash (Medium)", "gemini-argon-wtu-weekly", "Iris: healthy"),
                                    ("Gemini 3.8 Flash (Medium)", "gemini-5h", "Iris: rate limited: gemini-5h"),
                                    ("Gemini 4 Argon (Medium)", "gemini-argon-wtu-weekly",
                                     "Iris: rate limited: gemini-argon-wtu-weekly quota used up")):
            with self.subTest(model=model, bucket=bucket):
                self.setUp()
                self.pane("hub-iris", AGY["idle"])
                self.agy_quota(0, 7200, bucket, model=model)
                self.assertIn(line, self.run_cmd("watch"))

    def test_flash_fallback_only_when_the_running_bucket_is_empty_and_flash_has_room(self):
        def fallback(since=0):
            return subprocess.run([sys.executable, str(HUB / "dispatch.py"), "flash-fallback", "Iris",
                                   "--since", str(since)], env=self.env, timeout=60).returncode == 0
        at = datetime.now(timezone.utc).isoformat()
        cases = [("Gemini 4 Argon (Medium)", "gemini-argon-wtu-weekly", 0, True),
                 ("claude-opus-5-5-high", "3p-weekly", 0, True),
                 ("Gemini 4 Argon (Medium)", "gemini-argon-wtu-weekly", time.time() + 60, False),  # stale statusLine
                 ("Gemini 4 Argon (Medium)", "gemini-weekly", 0, False),  # Flash has no room either
                 ("Gemini 3.8 Flash (Medium)", "gemini-argon-wtu-weekly", 0, False),  # already on Flash
                 ("Gemini 4 Argon (Medium)", "gemini-5h", 0, False)]
        for model, bucket, since, want in cases:
            with self.subTest(model=model, bucket=bucket, since=since):
                self.setUp()
                self.agy_quota(0, 7200, bucket, model=model, at=at)
                self.assertEqual(fallback(since), want)

    def test_agy_at_its_quota_is_limited_until_the_reset_and_zeus_hears_once(self):
        self.board([task("T-002", owner=None)])
        self.pane("hub-iris", AGY["idle"])  # agy stops by itself: nothing on screen to read
        reset = self.agy_quota(0, 7200)
        self.assertIn("Iris: rate limited: gemini-5h quota used up", self.run_cmd("watch"))
        self.assertEqual(self.state("watch.json")["Iris"]["limited"]["until"], reset)
        self.pane("hub-iris", AGY_LIMIT)  # the message appears and scrolls; still one window
        self.run_cmd("watch")
        self.pane("hub-iris", AGY["idle"])
        self.run_cmd("watch")
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.assertEqual(len(self.calls("lead-alert")), 1)
        self.assertIn("Iris: rate limited until", self.run_cmd("tick"))
        self.assertNotIn("Iris", [c["argv"][0] for c in self.calls("hubmsg")])

    def test_agy_quota_left_or_reset_passed_is_healthy(self):
        self.board([task("T-002", owner=None)])
        self.pane("hub-iris", AGY["idle"])
        self.agy_quota(0, -60)  # reset passed; statusLine only rewrites on the next state change
        self.assertIn("Iris: healthy", self.run_cmd("watch"))
        self.agy_quota(0.4, 7200)
        self.assertIn("Iris: healthy", self.run_cmd("watch"))

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

    def over_budget(self, minutes, **extra):
        """Hermes (claude, no phase: trial, 90 min) holds T-002, claimed `minutes` ago, heartbeat fresh."""
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["autonomy"] = json.loads((HUB / "factory.example.json").read_text())["autonomy"]
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        at = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        self.board([task("T-002", status="claimed", claimed_at=at, **extra)])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.beat(2)

    def budget_events(self):
        p = self.hub / "events.jsonl"
        return [e for e in map(json.loads, p.read_text().splitlines())
                if e["event"] == "over_budget"] if p.exists() else []

    def test_over_budget_tells_zeus_once(self):
        self.over_budget(95)
        self.assertIn("T-002 over budget: claimed 95 min ago, budget 90 min", self.run_cmd("watch"))
        [msg] = self.zeus_inbox()
        self.assertIn("T-002 over budget: claimed 95 min ago, budget 90 min", msg)
        note = json.loads((self.hub / "board.json").read_text())["tasks"][0]["notes"][-1]
        self.assertEqual(note["by"], "Watchdog")
        self.assertIn("over budget", note["text"])
        self.assertEqual([(e["task"], e["level"], e["agent"]) for e in self.budget_events()], [("T-002", 1, "Hermes")])
        self.run_cmd("watch")
        self.assertEqual(len(self.zeus_inbox()), 1)
        self.assertEqual(self.calls("lead-alert"), [])
        self.assertEqual(json.loads((self.hub / "board.json").read_text())["tasks"][0]["status"], "claimed")

    def test_two_x_budget_tells_lead(self):
        self.over_budget(181)
        self.assertIn("T-002 over 2x budget", self.run_cmd("watch"))
        self.assertEqual(len(self.calls("lead-alert")), 1)
        self.run_cmd("watch")
        self.assertEqual(len(self.calls("lead-alert")), 1)
        self.assertEqual([e["level"] for e in self.budget_events()], [2])

    def test_two_x_budget_replaces_the_first_alert_and_release_withdraws_it(self):
        self.over_budget(95)
        self.run_cmd("watch")
        board = json.loads((self.hub / "board.json").read_text())
        board["tasks"][0]["claimed_at"] = (datetime.now(timezone.utc) - timedelta(minutes=181)).isoformat()
        (self.hub / "board.json").write_text(json.dumps(board))
        self.run_cmd("watch")
        [msg] = self.zeus_inbox()
        self.assertIn("over 2x budget", msg)
        board["tasks"][0]["status"] = "done"
        (self.hub / "board.json").write_text(json.dumps(board))
        self.run_cmd("watch")
        self.assertEqual(self.zeus_inbox(), [])

    def test_standing_task_never_over_budget(self):
        self.over_budget(500, tags=["standing"])
        self.run_cmd("watch")
        self.assertEqual(self.zeus_inbox(), [])
        self.assertEqual(self.budget_events(), [])

    def test_task_budget_beats_the_phase_and_the_breaker_exempts(self):
        self.over_budget(20, budget_minutes=15)
        self.assertIn("budget 15 min", self.run_cmd("watch"))
        self.over_budget(500)
        self.write_state("watch.json", {"Hermes": {"limited": {"until": time.time() + 3600, "line": "x", "told": True},
                                                   "cause": "rate limited"}})
        self.pane("hub-hermes", CODEX_LIMIT)
        self.run_cmd("watch")
        self.assertEqual(len(self.budget_events()), 1)  # only the first task's

    def test_a_task_without_claimed_at_falls_back_to_the_claim_in_the_ledger(self):
        self.over_budget(0)
        board = json.loads((self.hub / "board.json").read_text())
        del board["tasks"][0]["claimed_at"]
        (self.hub / "board.json").write_text(json.dumps(board))
        at = (datetime.now(timezone.utc) - timedelta(minutes=100)).isoformat(timespec="seconds")
        (self.hub / "events.jsonl").write_text(json.dumps({"at": at, "by": "Hermes", "event": "claimed",
                                                           "task": "T-002"}) + "\n")
        self.assertIn("T-002 over budget: claimed 100 min ago", self.run_cmd("watch"))

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
    def hook(self, stdin, *args, script="heartbeat.sh", **env):
        e = {k: v for k, v in self.env.items() if k != "CLAUDE_CODE_SESSION_NAME"}
        return subprocess.run([str(HUB / script), *args], input=stdin, env={**e, **env},
                              text=True, capture_output=True, timeout=20)

    def test_event_flag_names_agys_events(self):
        stop = (FIXTURES / "hook-Stop.json").read_text()
        for event in ("UserPromptSubmit", "PostToolUse"):
            with self.subTest(event):
                r = self.hook(stop, "--agent", "Iris", "--event", event)
                self.assertEqual((r.returncode, r.stdout), (0, "{}\n" if event == "PostToolUse" else ""))
                self.assertEqual(self.state("Iris.json")["event"], event)
                self.assertFalse((self.hub / "state" / "dispatch.kick").exists())
        self.hook(stop, "--event", "Stop", "--agent", "Iris")
        self.assertEqual(self.state("Iris.json")["event"], "Stop")
        self.assertTrue((self.hub / "state" / "dispatch.kick").exists())

    def test_a_probe_marked_hub_no_hooks_beats_for_nobody(self):
        """Hermes on 7146895: a launcher's `agy -p` probe fires the seat's global hooks; it must not beat as the seat."""
        stop = (FIXTURES / "hook-Stop.json").read_text()
        r = self.hook(stop, "--agent", "Iris", "--event", "Stop", HUB_NO_HOOKS="1")
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.hub / "state" / "Iris.json").exists())
        self.assertFalse((self.hub / "state" / "dispatch.kick").exists())
        r = self.hook(stop, "--agent", "Iris", "--event", "PostToolUse", HUB_NO_HOOKS="1")
        self.assertEqual(r.stdout, "{}\n")  # agy still gets its JSON

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
