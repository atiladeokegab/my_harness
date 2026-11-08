"""Factory dispatcher (T-501): dispatch.py tick and weekly against canned panes and stub tools.
Never touches the live board, panes or bucket.

    python3 tests/test_dispatch.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))
import dispatch  # noqa: E402  (pure functions only; the CLI runs in a subprocess on a temp hub)

# Canned panes, from real sessions where we have them.
CLAUDE_IDLE = "● Done, tests pass.\n\n" + "─" * 40 + "\n❯ \n" + "─" * 40 + "\n  ⏵⏵ auto mode on · ↓ to manage\n\n\n"
CLAUDE_BUSY = ("✽ Actualizing… (10s · ↓ 213 tokens)\n" + "─" * 40 + "\n❯ \n" + "─" * 40
               + "\n  ⏵⏵ auto mode on · 2 shells · esc to interrupt · ↓ to manage\n")
CLAUDE_PERMISSION = ("╭" + "─" * 40 + "\n│ Bash command\n│   rm -rf build\n│ Do you want to proceed?\n│ ❯ 1. Yes\n"
                     "│   2. Yes, and don't ask again for rm commands in ~/code/app\n"
                     "│   3. No, and tell Claude what to do differently (esc)\n╰" + "─" * 40 + "\n")
CLAUDE_LIMIT = ("  ⎿  Claude usage limit reached. Your limit will reset at 7pm (Europe/London).\n"
                "      /upgrade to increase your usage limit.\n" + "─" * 40 + "\n❯ \n")
CLAUDE_LOGGED_OUT = ('  ⎿  API Error: 401 {"type":"error","error":{"type":"authentication_error",'
                     '"message":"OAuth token has expired."}} · Please run /login\n❯ \n')
CODEX_LIMIT = ("■ You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit "
               "https://chatgpt.com/settings/usage to purchase more credits or try\nagain at 7:28 PM.\n"
               "› Ask Codex to do anything\n  GPT-6-Sol high · ~/code/webapp · Receive hub messages\n"
               "  ? for shortcuts                                         ⚠ 6 warnings · f2 to view\n")
CODEX_WARNING_IDLE = ("• Ran hub list --owner Prometheus --status open\n  └ no tasks match\n"
                      "                         ⚠ 5h limit: only 5% left · resets at 19:28 · /status\n"
                      "› Ask Codex to do anything\n  ? for shortcuts\n")
CODEX_BUSY = "• Working (26m 47s • esc to interrupt)\n› Ask Codex to do anything\n"
# hub-prometheus as captured live on 2026-10-17 at 15:31Z, blank rows dropped.
PROMETHEUS_LIMIT_LIVE = """  └ Read SKILL.md (superpowers:systematic-debugging skill)
    List runbooks
    Read run.py, test_run.py
    + Show details
■ You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try
again at 7:28 PM.
› [hub wake:1792250628561703592-699841-21123] Run exactly: hub receive 1792250628561703592-699841-21123
■ You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage to purchase more credits or try
again at 7:28 PM.
› Ask Codex to do anything
  GPT-6-Sol high · ~/code/webapp · Receive hub messages
  ? for shortcuts                                                                                                                 ⚠ 6 warnings · f2 to view
"""
CLAUDE_PERMISSION_UNBOXED = (" Bash command\n\n   rm -rf build\n\n Do you want to proceed?\n ❯ 1. Yes\n"
                             "   2. Yes, and don't ask again for rm commands\n   3. No (esc)\n")
CODEX_APPROVAL = ("  Would you like to run the following command?\n  $ rm -rf build\n› 1. Yes, proceed (y)\n"
                  "  2. No, and tell Codex what to do differently (esc)\n")
# Prose above a prompt (Hermes, T-501 review): words a dialog or error would use, but not chrome.
PROSE = ("● Done. Do you want to keep T-505 open for the review duty?",
         "● the watchdog marks an agent rate limited when the pane shows it",
         "  If the deployer is missing it says you are not logged in",
         "● I ran codex login checks yesterday",
         "  ⎿  dispatch.py:44: usage limit reached|limit reached|hit your (?:usage )?limit")

# agy 1.4.2 captures from the T-556 live check. Its limit and login screens were not captured: those
# lines are the strings the plan names, in agy's ⎿ transcript gutter.
AGY = {f.stem: f.read_text() for f in (HUB / "tests" / "fixtures" / "agy").glob("*.txt")}
AGY_LIMIT = "⎿  You have exhausted your quota on this model.\n" + AGY["idle"]
AGY_LOGGED_OUT = "⎿  Authentication expired. Please sign in again.\n" + AGY["idle"]

STUBS = {
    "tmux": r'''#!/usr/bin/env python3
import os, sys
from pathlib import Path
a = sys.argv[1:]
p = os.path.join(os.environ["FAKE_PANES"], a[a.index("-t") + 1])
if a[0] != "capture-pane" or not os.path.exists(p):
    sys.exit("can't find session")
if os.environ.get("FAKE_KICK_DURING_CAPTURE"):
    marker = Path(os.environ["FAKE_LOG"]) / "kicked"
    if not marker.exists():
        marker.touch()
        kick = Path(os.environ["HUB_DIR"]) / "state" / "dispatch.kick"
        kick.parent.mkdir(exist_ok=True)
        kick.touch()
print(open(p).read(), end="")
''',
    "hubmsg": r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["FAKE_LOG"], "hubmsg.jsonl"), "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "sender": os.environ.get("HUB_AGENT")}) + "\n")
print(f"queued  -> {sys.argv[1]} inbox")
''',
    "systemd-run": r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["FAKE_LOG"], "systemd-run.jsonl"), "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
''',
    "lead-alert": r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["FAKE_LOG"], "lead-alert.jsonl"), "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(1)  # a failing alert channel must be ignored
''',
}


def task(tid, owner="Hermes", status="open", **extra):
    return {"id": tid, "title": f"Task {tid}", "detail": "Do it.", "status": status, "owner": owner,
            "deps": [], "notes": [], "project": "hub", "created_by": "Zeus",
            "created": "2026-10-17T00:00:00+00:00", "updated": "2026-10-17T00:00:00+00:00", **extra}


class Factory(unittest.TestCase):
    """A throwaway hub with stub tmux, hubmsg, systemd-run and lead-alert on PATH. No tests here."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-dispatch-test-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name)
        self.bin, self.panes, self.logs = self.hub / "bin", self.hub / "panes", self.hub / "logs"
        for d in (self.bin, self.panes, self.logs):
            d.mkdir()
        for name, body in STUBS.items():
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        (self.hub / "factory.json").write_text(json.dumps({
            "agents": [{"name": "Prometheus", "kind": "codex", "session": "hub-prometheus"},
                       {"name": "Hermes", "kind": "claude", "session": "hub-hermes"},
                       {"name": "Zeus", "kind": "claude", "session": "hub-zeus", "dispatch": False}],
            "repos": [], "intervals": {"poll_seconds": 10 ** 12, "stuck_minutes": 30},
            "lead_alert": ["lead-alert", "send"]}))
        self.board([])
        env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        self.env = {**env, "HUB_DIR": str(self.hub), "HOME": str(self.hub), "HUB_LEAD": "Zeus",
                    "HUB_CLAUDE_AGENTS": "Hermes Zeus", "HUB_CODEX_AGENTS": "Prometheus", "FAKE_PANES": str(self.panes),
                    "FAKE_LOG": str(self.logs), "PATH": f"{self.bin}:{env['PATH']}"}

    def board(self, tasks):
        (self.hub / "board.json").write_text(json.dumps({"next_id": 900, "tasks": tasks}))

    def pane(self, session, text):
        (self.panes / session).write_text(text)

    def run_cmd(self, *args):
        r = subprocess.run([sys.executable, str(HUB / "dispatch.py"), *args], env=self.env,
                           text=True, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def calls(self, name):
        p = self.logs / f"{name}.jsonl"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def state(self, name):
        p = self.hub / "state" / name
        return json.loads(p.read_text()) if p.exists() else {}

    def write_state(self, name, data):
        (self.hub / "state").mkdir(exist_ok=True)
        (self.hub / "state" / name).write_text(json.dumps(data))


class ClassifyTest(unittest.TestCase):
    def test_canned_panes(self):
        cases = {
            "claude idle": (CLAUDE_IDLE, None, False),
            "claude busy": (CLAUDE_BUSY, None, True),
            "codex busy": (CODEX_BUSY, None, True),
            "claude permission": (CLAUDE_PERMISSION, "permission prompt", False),
            "claude limit": (CLAUDE_LIMIT, "rate limited", False),
            "codex limit": (CODEX_LIMIT, "rate limited", False),
            "codex low-usage warning is not a limit": (CODEX_WARNING_IDLE, None, False),
            "claude logged out": (CLAUDE_LOGGED_OUT, "logged out", False),
            "prometheus limit, live capture": (PROMETHEUS_LIMIT_LIVE, "rate limited", False),
            "claude permission, no box": (CLAUDE_PERMISSION_UNBOXED, "permission prompt", False),
            "codex approval": (CODEX_APPROVAL, "permission prompt", False),
        }
        for label, (pane, cause, busy) in cases.items():
            with self.subTest(label):
                self.assertEqual(dispatch.classify(pane)[0], cause)
                self.assertEqual(dispatch.busy(pane), busy)

    def test_prose_is_not_chrome(self):
        for line in PROSE:
            with self.subTest(line):
                self.assertEqual(dispatch.classify(line + "\n" + CLAUDE_IDLE), (None, ""))

    def test_old_scrollback_does_not_count(self):
        pane = CLAUDE_PERMISSION + "".join(f"● line {i}\n" for i in range(30)) + CLAUDE_IDLE
        self.assertIsNone(dispatch.classify(pane)[0])

    def test_reset_times(self):
        now = datetime(2026, 10, 17, 15, 30, tzinfo=timezone.utc).timestamp()
        at = lambda pane: dispatch.reset_at(dispatch.tail(pane), now)  # noqa: E731
        utc = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime("%m-%d %H:%M")  # noqa: E731
        with unittest.mock.patch.dict(os.environ, {"TZ": "UTC"}):
            time.tzset()
            self.assertEqual(utc(at(CODEX_LIMIT)), "10-17 19:28")  # wrapped across two lines
            self.assertEqual(utc(at("You've hit your limit · resets 3pm")), "10-18 15:00")  # passed: tomorrow
        time.tzset()
        self.assertEqual(utc(at(CLAUDE_LIMIT)), "10-17 18:00")  # 7pm BST
        self.assertEqual(at("hit your usage limit, try again in 2 hours 3 minutes."), now + 7380)
        self.assertIsNone(at("Claude usage limit reached."))

    def test_agy_panes(self):
        cases = {
            "idle": (AGY["idle"], None, False),
            "idle after a turn": (AGY["idle-after-turn"], None, False),
            "busy": (AGY["busy-generating"], None, True),
            "run command dialog": (AGY["dialog-run-command"], "permission prompt", True),
            "create file dialog": (AGY["dialog-create-file"], "permission prompt", True),  # esc to cancel
            "trust dialog": (AGY["dialog-trust-folder"], "permission prompt", False),
            "quota exhausted": (AGY_LIMIT, "rate limited", False),
            "individual quota": ("⎿  Individual quota reached, try again later\n" + AGY["idle"], "rate limited", False),
            "authentication expired": (AGY_LOGGED_OUT, "logged out", False),
            "not logged in": ("You are not logged into Antigravity.\n" + AGY["idle"], "logged out", False),
        }
        for label, (pane, cause, busy) in cases.items():
            with self.subTest(label):
                self.assertEqual(dispatch.classify(pane)[0], cause)
                self.assertEqual(dispatch.busy(pane), busy)

    def test_agy_busy_footer_is_not_a_dialogs_cancel_line(self):
        reply = AGY["busy-generating"].replace("⣽  Generating...", "  1. Yes, keep it\n  2. Close it")
        self.assertEqual(dispatch.classify(reply), (None, ""))


class TickTest(Factory):
    def test_recent_tick_is_debounced(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        last_tick = time.time() - 4
        self.write_state("dispatch.json", {"last_tick": last_tick})
        out = self.run_cmd("tick")
        self.assertIn("debounced ", out)
        self.assertIn("Hermes: idle, wake for T-002", out)
        self.assertGreaterEqual(self.state("dispatch.json")["last_tick"], last_tick + 5)
        self.assertEqual(len(self.calls("hubmsg")), 1)

    def test_kick_during_tick_runs_body_again(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.env["FAKE_KICK_DURING_CAPTURE"] = "1"
        out = self.run_cmd("tick")
        self.assertIn("Hermes: idle, wake for T-002", out)
        self.assertIn("Hermes: idle, offer of T-002 pending", out)
        self.assertEqual(len(self.calls("hubmsg")), 1)

    def test_idle_agent_is_woken_once_per_task(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        out = self.run_cmd("tick")
        self.assertIn("Hermes: idle, wake for T-002", out)
        [call] = self.calls("hubmsg")
        self.assertEqual(call["argv"][0], "Hermes")
        self.assertEqual(call["argv"][2:], ["--task", "T-002"])
        self.assertEqual(call["sender"], "Dispatch")
        state = self.state("dispatch.json")
        self.write_state("dispatch.json", {**state, "last_tick": time.time() - 6})
        self.run_cmd("tick")
        self.assertEqual(len(self.calls("hubmsg")), 1)
        self.assertEqual(self.state("dispatch.json")["woken"]["T-002"]["agent"], "Hermes")

    def test_a_wake_fetches_the_project_clone_first(self):
        """A sandboxed builder cannot fetch, so hub claim would build its worktree from stale refs."""
        (self.hub / "code" / "hub" / ".git").mkdir(parents=True)
        # Only here: tests.test_watchdog reuses Factory, and snapshot.sh needs the real git.
        (self.bin / "git").write_text(STUBS["systemd-run"].replace("systemd-run", "git"))
        (self.bin / "git").chmod(0o755)
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.assertIn("Hermes: idle, wake for T-002", self.run_cmd("tick"))
        self.assertEqual(self.calls("git"), [["-C", str(self.hub / "code" / "hub"), "fetch", "-q", "--prune", "origin"]])

    def test_only_factory_projects_are_offered(self):
        cfg = json.loads((self.hub / "factory.json").read_text())
        (self.hub / "factory.json").write_text(json.dumps({**cfg, "projects": ["hub"]}))
        self.board([task("T-001", project="plex"), task("T-002")])  # T-001 would come first
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.assertIn("Hermes: idle, wake for T-002", self.run_cmd("tick"))

    def test_agents_that_are_not_idle_are_never_woken(self):
        cases = {
            "holds a claimed task": lambda: self.board([task("T-002"), task("T-003", status="claimed")]),
            "permission prompt": lambda: self.pane("hub-hermes", CLAUDE_PERMISSION),
            "working": lambda: self.pane("hub-hermes", CLAUDE_BUSY),
            "logged out": lambda: self.pane("hub-hermes", CLAUDE_LOGGED_OUT),
            "no session": lambda: (self.panes / "hub-hermes").unlink(),
            "rate-limit breaker on": lambda: self.write_state(
                "watch.json", {"Hermes": {"limited": {"until": time.time() + 3600, "line": "x"}}}),
            "paused": lambda: (self.hub / "PAUSE").write_text("lead said stop"),
            "task tagged untrusted": lambda: self.board([task("T-002", tags=["untrusted"])]),
            "task already running headless": lambda: (self.hub / "run").mkdir() or
            (self.hub / "run" / "T-002.lock").write_text(f"{os.getpid()}\n"),
        }
        for label, arrange in cases.items():
            with self.subTest(label):
                self.setUp()
                self.board([task("T-002")])
                self.pane("hub-hermes", CLAUDE_IDLE)
                arrange()
                self.run_cmd("tick")
                self.assertEqual(self.calls("hubmsg"), [], label)
                self.assertEqual(self.calls("systemd-run"), [], label)

    def test_standing_duties_do_not_make_an_agent_busy(self):
        self.board([task("T-002"), task("T-003", status="claimed", tags=["standing"])])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.assertIn("Hermes: idle, wake for T-002", self.run_cmd("tick"))
        self.assertEqual([c["argv"][-1] for c in self.calls("hubmsg")], ["T-002"])

    def test_standing_duties_keep_every_other_idle_check(self):
        cases = {
            "also holds real work": lambda: self.board([task("T-002"), task("T-003", status="claimed", tags=["standing"]),
                                                        task("T-004", status="claimed")]),
            "working": lambda: self.pane("hub-hermes", CLAUDE_BUSY),
            "permission prompt": lambda: self.pane("hub-hermes", CLAUDE_PERMISSION),
            "rate-limit breaker on": lambda: self.write_state(
                "watch.json", {"Hermes": {"limited": {"until": time.time() + 3600, "line": "x"}}}),
            "offer pending": lambda: self.write_state(
                "dispatch.json", {"woken": {"T-009": {"agent": "Hermes", "at": datetime.now(timezone.utc).isoformat(),
                                                      "how": "wake"}}}),
        }
        for label, arrange in cases.items():
            with self.subTest(label):
                self.setUp()
                self.board([task("T-002"), task("T-003", status="claimed", tags=["standing"]), task("T-009")])
                self.pane("hub-hermes", CLAUDE_IDLE)
                arrange()
                self.run_cmd("tick")
                self.assertEqual(self.calls("hubmsg"), [], label)

    def idle(self, *sessions):
        for session in sessions:
            self.pane(session, CLAUDE_IDLE)

    def test_an_ignored_offer_does_not_stall_the_next_agent(self):
        self.board([task("T-001", owner=None), task("T-002", owner=None),
                    task("T-009", owner="Hermes", status="claimed")])
        self.idle("hub-prometheus", "hub-hermes")
        self.run_cmd("tick")
        self.assertEqual([c["argv"][0] for c in self.calls("hubmsg")], ["Prometheus"])  # T-001
        self.board([task("T-001", owner=None), task("T-002", owner=None)])  # Hermes is free now
        state = self.state("dispatch.json")
        self.write_state("dispatch.json", {**state, "last_tick": time.time() - 6})
        out = self.run_cmd("tick")
        self.assertIn("Prometheus: idle, offer of T-001 pending", out)
        self.assertEqual([(c["argv"][0], c["argv"][-1]) for c in self.calls("hubmsg")],
                         [("Prometheus", "T-001"), ("Hermes", "T-002")])

    def test_an_expired_offer_goes_to_another_agent_and_not_back(self):
        self.board([task("T-001", owner=None)])
        self.idle("hub-prometheus", "hub-hermes")
        old = datetime.fromtimestamp(time.time() - 31 * 60, timezone.utc).isoformat()
        self.write_state("dispatch.json", {"woken": {"T-001": {"agent": "Prometheus", "at": old, "how": "wake"}}})
        self.run_cmd("tick")
        self.assertEqual([c["argv"][0] for c in self.calls("hubmsg")], ["Hermes"])
        self.assertEqual(self.state("dispatch.json")["woken"]["T-001"]["ignored"], ["Prometheus"])

    def test_offers_for_tasks_no_longer_open_are_pruned(self):
        self.board([task("T-001", owner=None, status="claimed"), task("T-002", owner=None)])
        self.write_state("dispatch.json", {"woken": {"T-001": {"agent": "Hermes", "at": "2026-10-17T00:00:00+00:00"}}})
        self.idle("hub-hermes")
        self.run_cmd("tick")
        self.assertEqual(list(self.state("dispatch.json")["woken"]), ["T-002"])

    def test_skipped_tasks_fall_through_to_the_next_candidate(self):
        cases = {
            "untrusted": lambda: self.board([task("T-001", tags=["untrusted"]), task("T-002")]),
            "stale": lambda: self.board([task("T-001", tags=["stale"]), task("T-002")]),
            "run lock held": lambda: (self.board([task("T-001"), task("T-002")]), (self.hub / "run").mkdir(),
                                      (self.hub / "run" / "T-001.lock").write_text(f"{os.getpid()}\n")),
        }
        for label, arrange in cases.items():
            with self.subTest(label):
                self.setUp()
                self.idle("hub-hermes")
                arrange()
                self.run_cmd("tick")
                self.assertEqual([c["argv"][-1] for c in self.calls("hubmsg")], ["T-002"], label)

    def test_a_vertical_with_a_ready_child_offers_the_child(self):
        self.board([task("T-001", kind="vertical"), task("T-002", parent="T-001")])
        self.idle("hub-hermes")
        self.run_cmd("tick")
        self.assertEqual([c["argv"][-1] for c in self.calls("hubmsg")], ["T-002"])

    def test_a_task_delegated_to_another_agent_is_not_offered(self):
        self.board([task("T-001", owner=None, agent="Prometheus")])
        self.idle("hub-hermes")
        self.assertIn("Hermes: idle, nothing available", self.run_cmd("tick"))
        self.assertEqual(self.calls("hubmsg"), [])

    def test_dispatch_off_agent_is_skipped(self):
        self.board([task("T-002", owner="Zeus")])
        self.pane("hub-zeus", CLAUDE_IDLE)
        self.assertIn("Zeus: dispatch off", self.run_cmd("tick"))
        self.assertEqual(self.calls("hubmsg"), [])

    def test_expired_breaker_lets_the_wake_through(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.write_state("watch.json", {"Hermes": {"limited": {"until": time.time() - 60, "line": "x"}}})
        self.run_cmd("tick")
        self.assertEqual(len(self.calls("hubmsg")), 1)

    def test_a_passed_reset_time_on_a_stale_limit_message_lets_the_wake_through(self):
        """T-506 run 2: Codex's 'try again at 7:28 PM' stayed on screen after 7:28 PM."""
        self.board([task("T-002", owner=None)])
        self.pane("hub-prometheus", CODEX_LIMIT)
        line = dispatch.classify(CODEX_LIMIT)[1]
        self.write_state("watch.json", {"Prometheus": {"limited": {"until": time.time() - 120, "line": line, "told": True}}})
        self.run_cmd("watch")
        self.assertLess(self.state("watch.json")["Prometheus"]["limited"]["until"], time.time())  # not pushed a day on
        self.assertIn("Prometheus: idle, wake for T-002", self.run_cmd("tick"))

    def test_dead_pid_run_lock_is_not_held_and_left_for_run_py(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        dead = subprocess.Popen(["true"])
        dead.wait()
        (self.hub / "run").mkdir()
        (self.hub / "run" / "T-002.lock").write_text(f"{dead.pid}\n")
        out = self.run_cmd("tick")
        self.assertIn(f"run lock pid {dead.pid} is gone; stale, run.py reclaims it", out)
        self.assertTrue((self.hub / "run" / "T-002.lock").exists())  # one remover only: run.py's O_EXCL guard
        self.assertEqual(len(self.calls("hubmsg")), 1)

    def test_a_limit_hub_run_recorded_holds_the_agent(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.write_state("Hermes.limit.json", {"until": time.time() + 600})
        self.assertIn("Hermes: rate limited (hub run) until", self.run_cmd("tick"))
        self.assertEqual(self.calls("hubmsg"), [])

    def test_headless_task_starts_hub_run_not_a_wake(self):
        self.board([task("T-002", tags=["headless"])])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.run_cmd("tick")
        self.assertEqual(self.calls("hubmsg"), [])
        [argv] = self.calls("systemd-run")
        self.assertIn("--setenv=HUB_AGENT=Hermes", argv)
        self.assertEqual(argv[-2:], [str(HUB / "run.py"), "T-002"])
        self.assertEqual(self.state("dispatch.json")["woken"]["T-002"]["how"], "run")

    def test_dry_run_only_prints(self):
        self.board([task("T-002")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        dead = subprocess.Popen(["true"])
        dead.wait()
        (self.hub / "run").mkdir()
        (self.hub / "run" / "T-002.lock").write_text(f"{dead.pid}\n")
        out = self.run_cmd("tick", "--dry-run")
        self.assertIn("Hermes: idle, would wake for T-002", out)
        self.assertEqual(self.calls("hubmsg"), [])
        self.assertTrue((self.hub / "run" / "T-002.lock").exists())
        self.assertFalse((self.hub / "state" / "dispatch.json").exists())

    def test_github_poll_runs_when_due_and_is_recorded(self):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["intervals"]["poll_seconds"] = 0
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.env["HUB_AGENT"] = "Dispatch"
        out = self.run_cmd("tick")
        self.assertNotIn("factory poll failed", out)
        self.assertGreater(self.state("dispatch.json")["polled"], 0)


    def test_a_future_last_tick_debounces_at_most_five_seconds(self):
        """Hermes on T-528: a clock step or an edited state must not hold the oneshot."""
        self.write_state("dispatch.json", {"last_tick": time.time() + 3600})
        self.assertIn("debounced 5.0s", self.run_cmd("tick"))


class ReadRoutingTest(Factory):
    """A `read` task goes to the reader (factory.json "reads": true) and to others only after offer_minutes."""

    def setUp(self):
        super().setUp()
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["agents"].append({"name": "Iris", "kind": "agy", "reads": True})
        (self.hub / "factory.json").write_text(json.dumps(cfg))

    def test_the_reader_takes_a_read_task_before_a_build_task(self):
        self.board([task("T-001", owner=None), task("T-002", owner=None, tags=["read"])])
        self.pane("hub-iris", AGY["idle"])
        self.run_cmd("tick")
        self.assertEqual([(c["argv"][0], c["argv"][-1]) for c in self.calls("hubmsg")], [("Iris", "T-002")])

    def test_the_reader_is_never_offered_a_build_task(self):
        self.board([task("T-001", owner=None)])
        self.pane("hub-iris", AGY["idle"])
        self.run_cmd("tick")
        self.assertEqual(self.calls("hubmsg"), [])

    def test_others_get_a_read_task_only_after_the_offer_window(self):
        self.pane("hub-prometheus", CLAUDE_IDLE)  # the reader has no session: down
        self.board([task("T-002", owner=None, tags=["read"], created=hb_now(-29))])
        self.assertIn("Prometheus: idle, nothing available", self.run_cmd("tick"))
        self.assertEqual(self.calls("hubmsg"), [])
        self.board([task("T-002", owner=None, tags=["read"], created=hb_now(-31))])
        self.write_state("dispatch.json", {})
        self.run_cmd("tick")
        self.assertEqual([(c["argv"][0], c["argv"][-1]) for c in self.calls("hubmsg")], [("Prometheus", "T-002")])

    def test_a_reader_with_dispatch_off_holds_nothing_back(self):
        """Hermes on 69790f3: a reader the dispatcher never offers to must not withhold read tasks."""
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["agents"][-1]["dispatch"] = False
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.pane("hub-prometheus", CLAUDE_IDLE)
        self.board([task("T-002", owner=None, tags=["read"], created=hb_now(-1))])
        self.run_cmd("tick")
        self.assertEqual([(c["argv"][0], c["argv"][-1]) for c in self.calls("hubmsg")], [("Prometheus", "T-002")])


def hb_now(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


class ResetTest(Factory):
    """Agent OS §1: an idle agent with nothing held, just stopped, gets a fresh session per task."""

    def arrange(self, name="Hermes", reset="per-task", event="Stop", tasks=()):
        cfg = json.loads((self.hub / "factory.json").read_text())
        for a in cfg["agents"]:
            a.update(reset=reset, dispatch=True)
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.board([task("T-002", owner=name), *tasks])
        self.pane(f"hub-{name.lower()}", CLAUDE_IDLE)
        if event:
            self.write_state(f"{name}.json", {"at": datetime.now(timezone.utc).isoformat(), "event": event})

    def test_idle_after_stop_with_nothing_held_gets_a_reset_request(self):
        for name, kind in (("Hermes", "claude"), ("Prometheus", "codex")):
            with self.subTest(name):
                self.setUp()
                self.arrange(name)
                self.assertIn(f"{name}: idle, reset for T-002", self.run_cmd("tick"))
                self.assertEqual(self.calls("hubmsg"), [])
                [msg] = [json.loads(line) for line in (self.hub / "inbox" / f"{name}.jsonl").read_text().splitlines()]
                self.assertTrue(msg["text"].startswith(
                    "[dispatch] Fresh session. Your task: T-002 Task T-002. Run: hub claim T-002 && hub show T-002, "
                    "then work in the workspace path hub claim prints."), msg)
                lines = (self.hub / "wake" / f"{name}.wake").read_text().splitlines()
                self.assertEqual(lines[:5], ["version=2", f"agent={name}", f"ids={msg['id']}", "reset=1", f"kind={kind}"])
                self.assertRegex(lines[5], r"^created=\d+$")
                self.assertEqual(len(lines), 6)
                self.assertEqual(self.state("dispatch.json")["woken"]["T-002"]["how"], "reset")

    def test_plain_wake_when_reset_does_not_apply(self):
        cases = {
            "holds a blocked task": dict(tasks=[task("T-003", status="blocked")]),
            "holds a standing task": dict(tasks=[task("T-003", status="claimed", tags=["standing"])]),
            "opted out": dict(reset=False),
            "Zeus": dict(name="Zeus"),
            "last event not Stop": dict(event="PostToolUse"),
            "no heartbeat": dict(event=None),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                self.setUp()
                self.arrange(**kw)
                self.run_cmd("tick")
                self.assertEqual([c["argv"][-1] for c in self.calls("hubmsg")], ["T-002"], label)
                self.assertFalse((self.hub / "wake").exists(), label)
                self.assertEqual(self.state("dispatch.json")["woken"]["T-002"]["how"], "wake", label)

    def test_agy_is_resettable(self):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["agents"][1]["kind"] = "agy"
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.arrange()
        self.assertIn("Hermes: idle, reset for T-002", self.run_cmd("tick"))
        self.assertIn("kind=agy", (self.hub / "wake" / "Hermes.wake").read_text().splitlines())

    def test_dry_run_says_reset_and_writes_nothing(self):
        self.arrange()
        self.assertIn("Hermes: idle, would reset for T-002", self.run_cmd("tick", "--dry-run"))
        self.assertFalse((self.hub / "wake").exists())
        self.assertFalse((self.hub / "inbox").exists())

class ConfigTest(Factory):
    """Mistyped factory.json agent settings are loud (stderr, Zeus once, check-config) and fall back to off."""

    arrange = ResetTest.arrange

    def run_raw(self, *args):
        return subprocess.run([sys.executable, str(HUB / "dispatch.py"), *args], env=self.env,
                              text=True, capture_output=True, timeout=60)

    def edit(self, **hermes):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["agents"][1].update(hermes)
        (self.hub / "factory.json").write_text(json.dumps(cfg))

    def zeus_inbox(self):
        p = self.hub / "inbox" / "Zeus.jsonl"
        return [json.loads(line)["text"] for line in p.read_text().splitlines()] if p.exists() else []

    def test_reset_true_is_reported_once_and_treated_as_off(self):
        self.arrange(reset=True)
        line = 'factory.json: agent Hermes: reset=true is not allowed (allowed: false or "per-task"); treated as off'
        r = self.run_raw("tick")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(line, r.stderr.splitlines())
        self.assertIn("Hermes: idle, wake for T-002", r.stdout)
        self.assertFalse((self.hub / "wake").exists())
        [told] = self.zeus_inbox()
        self.assertIn(line, told.splitlines())
        self.run_raw("tick")
        self.run_raw("watch")
        self.assertEqual(len(self.zeus_inbox()), 1)
        r = self.run_raw("check-config")
        self.assertEqual(r.returncode, 1)
        self.assertIn(line, r.stderr.splitlines())

    def test_unknown_keys_kinds_and_values_are_reported(self):
        cases = {
            "unknown key": (dict(rest="per-task"), 'agent Hermes: unknown key "rest"; ignored'),
            "unknown kind": (dict(kind="gemini"), 'agent Hermes: kind="gemini" is not allowed '
                                                  '(allowed: "claude", "codex" or "agy"); no per-task reset'),
            "string dispatch": (dict(dispatch="yes"), 'agent Hermes: dispatch="yes" is not allowed '
                                                      '(allowed: true or false); treated as off'),
        }
        for label, (change, line) in cases.items():
            with self.subTest(label):
                self.setUp()
                self.edit(**change)
                r = self.run_raw("check-config")
                self.assertEqual(r.returncode, 1, label)
                [got] = r.stderr.splitlines()
                self.assertIn(line, got, label)

    def test_a_string_dispatch_is_off(self):
        self.board([task("T-002", owner="Hermes")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.edit(dispatch="yes")
        self.run_raw("tick")
        self.assertEqual(self.calls("hubmsg"), [])

    def test_an_unreadable_config_dispatches_nobody_but_watch_still_lists_the_roster(self):
        """The fallback roster ($HUB_CODEX_AGENTS, $HUB_CLAUDE_AGENTS) must not wake anyone, but watch still knows it."""
        self.board([task("T-002", owner="Hermes"), task("T-003", owner=None)])
        self.pane("hub-hermes", CLAUDE_IDLE)
        (self.hub / "factory.json").write_text("{not json")
        r = self.run_raw("tick")
        self.assertIn("factory.json: unreadable", r.stderr)
        self.assertEqual(self.calls("hubmsg"), [])
        self.assertEqual(self.run_cmd("agents").split(), ["Prometheus", "Hermes", "Zeus"])
        self.assertIn("Hermes:", self.run_cmd("watch", "--dry-run"))

    def test_valid_configs_are_silent(self):
        self.assertEqual(self.run_raw("tick").stderr, "")
        self.assertEqual(self.zeus_inbox(), [])
        for label, cfg in (("test fixture", None), ("factory.example.json", (HUB / "factory.example.json").read_text())):
            with self.subTest(label):
                if cfg:
                    (self.hub / "factory.json").write_text(cfg)
                r = self.run_raw("check-config")
                self.assertEqual((r.returncode, r.stderr), (0, ""))


class PhaseTest(Factory):
    """Living spec §4: a phase, not hand-set dispatch/reset, says whether an agent is woken and reset."""

    def test_configured_reviewer_is_not_offered_a_build(self):
        cfg = json.loads((HUB / "factory.example.json").read_text())
        cfg["projects"] = ["hub"]
        cfg["repos"] = []
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.board([task("T-002", owner="Prometheus")])
        self.pane("hub-prometheus", CODEX_WARNING_IDLE)
        self.write_state("Prometheus.json", {"at": datetime.now(timezone.utc).isoformat(), "event": "Stop"})
        self.assertIn("Prometheus: dispatch off in factory.json", self.tick().stdout)
        self.assertEqual(self.calls("hubmsg"), [])

    def arrange(self, **hermes):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["autonomy"] = json.loads((HUB / "factory.example.json").read_text())["autonomy"]
        cfg["agents"][1] = {"name": "Hermes", "session": "hub-hermes", **hermes}
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.board([task("T-002", owner="Hermes")])
        self.pane("hub-hermes", CLAUDE_IDLE)
        self.write_state("Hermes.json", {"at": datetime.now(timezone.utc).isoformat(), "event": "Stop"})

    def tick(self):
        r = subprocess.run([sys.executable, str(HUB / "dispatch.py"), "tick"], env=self.env, text=True,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_phase_trial_dispatches_without_reset(self):
        self.arrange(kind="claude", phase="trial")
        self.assertIn("Hermes: idle, wake for T-002", self.tick().stdout)
        self.assertFalse((self.hub / "wake").exists())

    def test_phase_trusted_resets_per_task(self):
        self.arrange(kind="claude", phase="trusted")
        self.assertIn("Hermes: idle, reset for T-002", self.tick().stdout)

    def test_unknown_kind_is_off(self):
        self.arrange(kind="gemini")
        r = self.tick()
        self.assertIn("Hermes: dispatch off in factory.json", r.stdout)
        self.assertIn("factory.json: agent Hermes: unknown kind gemini, phase off", r.stderr.splitlines())
        self.assertEqual(self.calls("hubmsg"), [])

    def test_no_phase_known_kind_gets_default(self):
        self.arrange(kind="claude")
        r = self.tick()
        self.assertIn("Hermes: idle, wake for T-002", r.stdout)  # trial: woken, never reset
        self.assertEqual(r.stderr, "")

    def test_phase_wins_over_dispatch_and_reset(self):
        self.arrange(kind="claude", phase="reviewer", dispatch=True, reset="per-task")
        self.assertIn("Hermes: dispatch off in factory.json", self.tick().stdout)
        self.assertEqual(self.calls("hubmsg"), [])

    def test_without_a_phase_hand_set_keys_still_work(self):
        self.arrange(kind="claude", dispatch=False)
        self.assertIn("Hermes: dispatch off in factory.json", self.tick().stdout)

    def test_a_bad_phase_or_phase_setting_is_reported_and_off(self):
        self.arrange(kind="claude", phase="boss")
        r = self.tick()
        self.assertIn('factory.json: agent Hermes: phase="boss" is not in autonomy.phases; phase off',
                      r.stderr.splitlines())
        self.assertIn("Hermes: dispatch off in factory.json", r.stdout)
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["autonomy"]["phases"]["trial"]["dispatch"] = "yes"
        cfg["agents"][1]["phase"] = "trial"
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        r = self.tick()
        self.assertIn('factory.json: autonomy phase trial: dispatch="yes" is not allowed (allowed: true or false); '
                      'treated as off', r.stderr.splitlines())
        self.assertEqual(self.calls("hubmsg"), [])


class WeeklyTest(Factory):
    def test_opens_two_tasks_for_zeus_once(self):
        self.run_cmd("weekly")
        board = json.loads((self.hub / "board.json").read_text())["tasks"]
        self.assertEqual(sorted((t["title"], t["owner"]) for t in board),
                         [("Promote rule candidates", "Zeus"), ("Weekly cleanup", "Zeus")])
        self.run_cmd("weekly")
        self.assertEqual(len(json.loads((self.hub / "board.json").read_text())["tasks"]), 2)


if __name__ == "__main__":
    unittest.main()
