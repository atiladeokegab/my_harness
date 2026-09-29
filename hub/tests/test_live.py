"""`hub live`: the mechanical loop hands each item to the right judge once, and never judges.

    python3 tests/test_live.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
CFG = {"repo": "me/ev", "timezone": "Europe/London", "smoke": "true",
       "deadlines": [{"name": "build start", "at": "2026-10-01T12:00:00Z"},
                     {"name": "code freeze", "at": "2026-10-01T14:00:00Z"},
                     {"name": "submit", "at": "2026-10-01T15:00:00Z"}],
       "roster": [{"name": "Lead", "github": "lead", "lead": True}, {"name": "Sam", "github": "sam"}]}


def done(out="", code=0):
    return subprocess.CompletedProcess([], code, out, "")


class Fake:
    """Answers gh/hub calls from a table keyed by the command's first words."""

    def __init__(self):
        self.calls, self.sent, self.answers = [], [], {}

    def run(self, args, cwd=None, timeout=60):
        args = [str(a) for a in args]
        self.calls.append(args)
        for key, value in self.answers.items():
            if " ".join(args).startswith(key):
                return value(args) if callable(value) else value
        return done("[]" if args[0] == "gh" else "")

    def send(self, agent, text):
        self.sent.append((agent, text))


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["HUB_DIR"] = self.tmp
        import board, live
        board.HUB_DIR = self.tmp
        self.live_mod = live
        (Path(self.tmp) / "projects" / "ev").mkdir(parents=True)
        (Path(self.tmp) / "projects" / "ev" / "hackathon.json").write_text(json.dumps(CFG))
        self.fake, self.clock = Fake(), [T0]
        sys.modules.pop("live_merge", None)
        sys.modules["live_merge"] = None  # merges are live_merge's tests; ImportError here
        self.live = self.make()

    def make(self):
        return self.live_mod.Live("ev", run=self.fake.run, send=self.fake.send, now=lambda: self.clock[0])

    def at(self, minutes):
        self.clock[0] = T0 + timedelta(minutes=minutes)

    def test_each_pr_head_goes_to_hermes_once(self):
        self.fake.answers["gh pr list"] = done(json.dumps(
            [{"number": 7, "title": "web", "headRefOid": "a" * 40, "isDraft": False},
             {"number": 8, "title": "wip", "headRefOid": "b" * 40, "isDraft": True}]))
        self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if "PR #" in t], ["Hermes"])
        self.fake.answers["gh pr list"] = done(json.dumps(
            [{"number": 7, "title": "web", "headRefOid": "c" * 40, "isDraft": False}]))
        self.live.tick()  # a new push is a new review
        self.assertEqual(sum("PR #7" in t for _, t in self.fake.sent), 2)

    def test_review_asks_on_lead_prs_reach_the_building_agent_once(self):
        head = {"committedDate": "2026-10-01T12:00:00Z"}
        def pr(comments, reviews=()):
            return [{"number": 9, "title": "t", "headRefOid": "d" * 40, "isDraft": False,
                     "author": {"login": "lead"}, "body": "Closes #4", "commits": [head],
                     "comments": list(comments), "reviews": list(reviews)}]
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "task"}, {"name": "agent:prometheus"}]}')
        old = {"createdAt": "2026-10-01T11:00:00Z", "body": "fix the old thing", "author": {"login": "lead"}}
        lgtm = {"createdAt": "2026-10-01T12:05:00Z", "body": "LGTM " + "d" * 40, "author": {"login": "lead"}}
        self.fake.answers["gh pr list"] = done(json.dumps(pr([old, lgtm])))
        self.live.tick()
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))
        ask = {"submittedAt": "2026-10-01T12:06:00Z", "body": "Handle 413\nthanks", "author": {"login": "lead"}}
        self.fake.answers["gh pr list"] = done(json.dumps(pr([old], [ask])))
        self.live.tick(); self.live.tick()
        fixes = [(a, t) for a, t in self.fake.sent if "changes requested" in t]
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0][0], "Prometheus")
        self.assertIn("Handle 413", fixes[0][1])

    def test_teammate_pr_comments_are_not_routed(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": "e" * 40,
            "isDraft": False, "author": {"login": "sam"}, "body": "Closes #4", "commits": [],
            "comments": [{"createdAt": "2026-10-01T12:06:00Z", "body": "fix", "author": {"login": "lead"}}], "reviews": []}]))
        self.live.tick()
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))

    def test_hold_stops_merges_and_zeus_hears_after_15_min(self):
        calls = []
        sys.modules["live_merge"] = type(sys)("live_merge")
        sys.modules["live_merge"].merge_tick = lambda *a: calls.append(1)
        hold = Path(self.tmp) / "projects" / "ev" / ".merge-hold"
        hold.write_text("2026-10-01T12:00:00+00:00\n")
        self.at(10); self.live.tick()
        self.assertEqual(calls, [])
        self.assertFalse(any("held" in t for _, t in self.fake.sent))
        self.at(16); self.live.tick(); self.live.tick()
        self.assertEqual(sum("held by Hermes" in t for _, t in self.fake.sent), 1)
        hold.unlink(); self.live.merge_now()
        self.assertEqual(calls, [1])

    def test_merge_flags_write_the_trigger_files(self):
        import types
        d = Path(self.tmp) / "projects" / "ev"
        ns = lambda **kw: types.SimpleNamespace(**{**dict(project="ev", once=True, interval=10, merge_now=False,
                                                          hold_merges=False, resume_merges=False), **kw})
        self.live_mod.cmd_live(ns(merge_now=True))
        self.assertTrue((d / ".merge-now").is_file())
        self.live_mod.cmd_live(ns(hold_merges=True))
        self.assertTrue((d / ".merge-hold").is_file())
        self.live_mod.cmd_live(ns(resume_merges=True))
        self.assertFalse((d / ".merge-hold").exists())

    def test_quick_poll_tells_hermes_about_a_new_pr(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 4, "title": "t", "headRefOid": "f" * 40,
                                                            "isDraft": False, "author": {"login": "sam"}}]))
        self.live.quick()
        self.assertEqual([a for a, t in self.fake.sent if "PR #4" in t], ["Hermes"])
        self.assertFalse(any(c[:2] == ["hub", "gh-sync"] for c in self.fake.calls))

    def test_third_round_of_changes_goes_to_zeus_once(self):
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "agent:prometheus"}]}')
        for i, sha in enumerate(("1" * 40, "2" * 40, "3" * 40, "4" * 40)):
            self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": sha,
                "isDraft": False, "author": {"login": "lead"}, "body": "Closes #4",
                "commits": [{"committedDate": f"2026-10-01T12:0{i}:00Z"}], "reviews": [],
                "comments": [{"createdAt": f"2026-10-01T12:0{i}:30Z", "body": "still drifts", "author": {"login": "lead"}}]}]))
            self.live.tick()
            if i == 1:
                self.assertFalse(any("round" in t for _, t in self.fake.sent))
        self.assertEqual(sum("changes requested" in t for a, t in self.fake.sent if a == "Prometheus"), 4)
        self.assertEqual(sum("3rd round" in t for a, t in self.fake.sent if a == "Zeus"), 1)

    def test_fyi_comment_is_not_a_change_request(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": "9" * 40,
            "isDraft": False, "author": {"login": "lead"}, "body": "Closes #4",
            "commits": [{"committedDate": "2026-10-01T12:00:00Z"}], "reviews": [],
            "comments": [{"createdAt": "2026-10-01T12:05:00Z", "body": "FYI: findings only", "author": {"login": "lead"}}]}]))
        self.live.tick()
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))

    def test_full_sync_runs_every_other_pass(self):
        for _ in range(4):
            self.live.tick()
        syncs = [c for c in self.fake.calls if c[:4] == ["hub", "gh-sync", "--project", "ev"] and "--freeze" not in c]
        self.assertEqual(len(syncs), 2)

    def test_state_survives_a_restart(self):
        self.fake.answers["gh issue list -R me/ev --label change-request"] = done(json.dumps([{"number": 3, "title": "cr"}]))
        self.live.tick()
        self.make().tick()
        self.assertEqual(sum("change-request #3" in t for _, t in self.fake.sent), 1)

    def test_inbox_lines_split_between_hermes_and_zeus(self):
        clone = Path(self.tmp) / "clone"
        (clone / "scripts").mkdir(parents=True)
        (clone / "scripts" / "team-inbox.sh").write_text("")
        self.live.clone = clone
        self.fake.answers[str(clone / "scripts" / "team-inbox.sh")] = done(
            'NEW     #11 in #3 by sam: "a"\nCHANGED #12 in #3 by sam: "b"\nDRAFT   #13 in #3 by sam: "c"\n')
        self.live.tick()
        self.assertEqual([a for a, _ in self.fake.sent], ["Hermes", "Hermes", "Zeus"])

    def test_sync_errors_go_to_zeus_once(self):
        self.fake.answers["hub gh-sync --project ev"] = done("error: boom\n")
        self.live.tick(); self.live.tick()
        self.assertEqual(self.fake.sent, [("Zeus", "ev gh-sync: error: boom")])

    def test_freeze_is_retried_until_it_succeeds(self):
        codes = [1, 0]
        self.fake.answers["hub gh-sync --project ev --freeze"] = lambda _: done(code=codes.pop(0))
        self.at(119); self.live.tick()
        freezes = lambda: sum("--freeze" in c for c in self.fake.calls)
        self.assertEqual(freezes(), 0)
        self.at(120); self.live.tick(); self.live.tick(); self.live.tick()
        self.assertEqual(freezes(), 2)

    def test_unseen_reminders_at_30_and_60(self):
        self.at(29); self.live.tick()
        self.at(31); self.live.tick(); self.live.tick()
        self.at(61); self.live.tick()
        self.assertEqual([t for _, t in self.fake.sent if "unseen" in t],
                         ["ev: build start +30 min: drop unseen sample set 1.",
                          "ev: build start +60 min: drop unseen sample set 2."])

    def test_question_nudged_then_escalated_once(self):
        q = {"number": 5, "title": "q", "body": "@sam which?", "assignees": [],
             "createdAt": "2026-10-01T12:00:00Z", "comments": []}
        self.fake.answers["gh issue list -R me/ev --label question"] = lambda _: done(json.dumps([q]))
        self.at(10); self.live.tick()
        self.assertFalse(any("comment" in c for c in self.fake.calls))
        self.at(21); self.live.tick()
        self.assertTrue(any(c[:3] == ["gh", "issue", "comment"] and "@sam this is waiting on you" in c for c in self.fake.calls))
        q["comments"] = [{"author": {"login": "lead"}, "body": "@sam this is waiting on you",
                          "createdAt": "2026-10-01T12:21:00Z"}]
        self.at(42); self.live.tick(); self.live.tick()
        self.assertEqual(sum("unanswered" in t for _, t in self.fake.sent), 1)

    def test_answered_question_is_left_alone_and_lead_questions_go_to_zeus(self):
        answered = {"number": 5, "title": "q", "body": "", "assignees": [{"login": "sam"}],
                    "createdAt": "2026-10-01T11:00:00Z",
                    "comments": [{"author": {"login": "sam"}, "body": "blue", "createdAt": "2026-10-01T11:05:00Z"}]}
        mine = {"number": 6, "title": "for lead", "body": "@lead ?", "assignees": [],
                "createdAt": "2026-10-01T11:00:00Z", "comments": []}
        self.fake.answers["gh issue list -R me/ev --label question"] = done(json.dumps([answered, mine]))
        self.live.tick()
        self.assertFalse(any(c[:3] == ["gh", "issue", "comment"] for c in self.fake.calls))
        self.assertEqual(self.fake.sent, [("Zeus", "ev question #6 for the lead: for lead")])

    def test_idle_branch_commented_once_per_head(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done('["9-web", "integration"]')
        self.fake.answers["gh api repos/me/ev/commits/9-web"] = done('{"sha": "s1", "at": "2026-10-01T10:50:00Z"}')
        self.fake.answers["gh issue view 9"] = done('{"state": "OPEN"}')
        self.live.tick(); self.live.tick()
        comments = [c for c in self.fake.calls if c[:4] == ["gh", "issue", "comment", "9"]]
        self.assertEqual(len(comments), 1)

    def test_stops_after_submit_and_tells_zeus(self):
        self.at(180)
        self.assertFalse(self.live.tick())
        self.assertEqual(self.fake.sent, [("Zeus", "ev: submit has passed; hub live stopped.")])
        self.assertFalse(any(c[:2] == ["hub", "gh-sync"] for c in self.fake.calls))

    def test_second_instance_exits(self):
        r1 = subprocess.Popen([sys.executable, "-c", (
            "import fcntl,sys,time;f=open(sys.argv[1],'w');fcntl.flock(f,fcntl.LOCK_EX);print('locked',flush=True);time.sleep(5)"),
            str(Path(self.tmp) / "projects" / "ev" / ".live.lock")], stdout=subprocess.PIPE, text=True)
        r1.stdout.readline()
        env = {**os.environ, "HUB_DIR": self.tmp}
        r2 = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import live, types;"
                             "live.cmd_live(types.SimpleNamespace(project='ev', once=True, interval=1, merge_now=False, hold_merges=False, resume_merges=False))", str(HUB)],
                            capture_output=True, text=True, env=env, timeout=30)
        r1.kill(); r1.wait(); r1.stdout.close()
        self.assertEqual(r2.returncode, 1)
        self.assertIn("already running", r2.stderr)


if __name__ == "__main__":
    unittest.main()
