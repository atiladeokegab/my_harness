"""`hub live`: the mechanical loop hands each item to the right judge once, and never judges.

    python3 tests/test_live.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
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
        if "--slurp" in args and "--jq" in args:
            return done("", 1)  # gh 2.102.0 rejects this combination
        for key, value in self.answers.items():
            if " ".join(args).startswith(key):
                return value(args) if callable(value) else value
        if args[:2] == ["gh", "api"] and args[2].startswith("repos/me/ev/branches?"):
            return done("integration\n")
        return done("[]" if args[0] == "gh" else "")

    def send(self, agent, text):
        self.sent.append((agent, text))


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for k in [k for k in os.environ if k.startswith("HUB_")]:  # HUB_LEAD, HUB_REVIEWER: test the default roster
            del os.environ[k]
        os.environ["HUB_DIR"] = self.tmp
        import board, live
        board.HUB_DIR = self.tmp
        # board read its paths at first import, maybe from the live hub: point every one at the temp dir
        for name in ("BOARD", "EVENTS", "LOCK", "WAL", "PAUSE", "INBOX_DIR"):
            setattr(board, name, os.path.join(self.tmp, os.path.basename(getattr(board, name))))
        self.board = board
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
            [{"number": 7, "title": "web", "headRefOid": "a" * 40, "isDraft": False, "body": "Verified: x"},
             {"number": 8, "title": "wip", "headRefOid": "b" * 40, "isDraft": True}]))
        self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if "PR #" in t], ["Hermes"])
        self.fake.answers["gh pr list"] = done(json.dumps(
            [{"number": 7, "title": "web", "headRefOid": "c" * 40, "isDraft": False, "body": "Verified: x"}]))
        self.live.tick()  # a new push is a new review
        self.assertEqual(sum("PR #7" in t for _, t in self.fake.sent), 2)

    def test_fast_lane_prs_are_not_relayed_but_gated_ones_are(self):
        """Dry run 2026-10-12 measured 1.37 relays per PR: fast-lane PRs reach Hermes in the digest instead."""
        (Path(self.tmp) / "projects" / "ev" / "hackathon.json").write_text(json.dumps(CFG | {"review_before": ["verify/*"]}))
        self.live = self.make()
        def pr(n, path="docs/a.md", author="lead"):
            return {"number": n, "title": "t", "headRefOid": f"{n:040d}", "isDraft": False,
                    "author": {"login": author}, "body": "Closes #17\n\nDONE: x\nVerified: make check: 3 passed",
                    "files": [{"path": path}], "changedFiles": 1, "comments": [], "reviews": []}
        changes = pr(11) | {"comments": [{"createdAt": "2026-10-01T12:05:00Z", "body": "CHANGES: x", "author": {"login": "lead"}}]}
        self.fake.answers["gh pr list"] = done(json.dumps([pr(7), pr(8), pr(9, author="sam"), pr(10, "verify/r.py"), changes]))
        self.fake.answers["gh issue view 17"] = done('{"body": "Files: docs/, verify/"}')
        self.fake.answers["gh pr view 11"] = done('{"commits": []}')
        self.fake.answers["gh pr diff 8"] = done("+++ b/docs/a.md\n+key = AKIAIOSFODNN7EXAMPLE\n")
        self.live.prs(); self.live.prs()
        relayed = [t.split()[2] for a, t in self.fake.sent if a == "Hermes" and "ready for review" in t]
        self.assertEqual(relayed, ["#8", "#9", "#10", "#11"])
        self.assertEqual(sum(c[:4] == ["gh", "pr", "diff", "7"] for c in self.fake.calls), 1)

    def tasks(self, *tasks):
        """Hub tasks for project ev on the temp board."""
        rows = [{"id": f"T-{i:03d}", "project": "ev", "status": "claimed", "notes": [], **t}
                for i, t in enumerate(tasks, 1)]
        (Path(self.tmp) / "board.json").write_text(json.dumps({"next_id": len(rows) + 1, "tasks": rows}))

    def board_task(self, i=1):
        return json.loads((Path(self.tmp) / "board.json").read_text())["tasks"][i - 1]

    def test_factory_task_agent_becomes_its_issue_label_once(self):
        """live_merge's own-LGTM check and fixes() read the issue's agent:<name> label; a factory task
        has its builder only on the board, so each tick copies it there, one gh call per change."""
        self.tasks({"issue": 4, "agent": "Prometheus", "kind": "factory"},
                   {"issue": 5, "agent": "Hermes"},                      # a hackathon task: gh-sync labels it
                   {"issue": 6, "kind": "factory", "status": "open"})    # nobody has claimed it yet
        self.live.tick(); self.live.tick()
        edits = [c for c in self.fake.calls if c[:3] == ["gh", "issue", "edit"]]
        self.assertEqual(edits, [["gh", "issue", "edit", "4", "-R", "me/ev", "--add-label", "agent:prometheus"]])
        self.assertEqual([c for c in self.fake.calls if c[:3] == ["gh", "label", "create"]],
                         [["gh", "label", "create", "agent:prometheus", "-R", "me/ev", "--force"]])
        rows = json.loads((Path(self.tmp) / "board.json").read_text())
        rows["tasks"][0]["agent"] = "Hermes"  # released and claimed again by another agent
        (Path(self.tmp) / "board.json").write_text(json.dumps(rows))
        self.fake.answers["gh issue edit"] = done("", 1)  # a failed edit is retried next tick
        self.live.tick()
        del self.fake.answers["gh issue edit"]
        self.live.tick(); self.live.tick()
        edits = [c for c in self.fake.calls if c[:3] == ["gh", "issue", "edit"]][1:]
        self.assertEqual(edits, [["gh", "issue", "edit", "4", "-R", "me/ev", "--add-label", "agent:hermes",
                                  "--remove-label", "agent:prometheus"]] * 2)

    def test_reverted_merge_reopens_its_board_task_and_wakes_its_agent_once(self):
        self.tasks({"issue": 4, "agent": "Prometheus", "owner": "Prometheus", "kind": "factory", "status": "done"},
                   {"issue": 4, "project": "other", "status": "done"})
        self.live.state["merge_events"] = [
            {"at": "2026-10-01T12:01:00+00:00", "pr": 9, "issue": 4, "event": "merged"},
            {"at": "2026-10-01T12:02:00+00:00", "pr": 9, "issue": 4, "event": "reverted", "why": "1 failed, 40 passed"}]
        self.live.tick(); self.live.tick()
        t = self.board_task(1)
        self.assertEqual((t["status"], t["owner"], t["agent"]), ("open", "Prometheus", "Prometheus"))
        self.assertEqual([n["text"] for n in t["notes"]], ["reverted after smoke: 1 failed, 40 passed"])
        self.assertEqual(self.board_task(2)["status"], "done")
        woken = [(a, x) for a, x in self.fake.sent if "reverted" in x]
        self.assertEqual(len(woken), 1)
        self.assertEqual(woken[0][0], "Prometheus")
        self.assertIn("T-001", woken[0][1])
        events = [json.loads(l) for l in (Path(self.tmp) / "events.jsonl").read_text().splitlines()]
        self.assertEqual([(e["event"], e["task"]) for e in events if e["event"] == "reopened"], [("reopened", "T-001")])

    def test_factory_project_skips_gh_sync(self):
        self.config(factory=True)
        self.live.sync()
        self.assertFalse([c for c in self.fake.calls if c[:2] == ["hub", "gh-sync"]])

    def test_revert_leaves_an_event_task_on_the_same_issue_alone(self):
        self.tasks({"issue": 4, "agent": "Prometheus", "owner": "Prometheus", "status": "done"})  # no kind: event task
        self.live.state["merge_events"] = [
            {"at": "2026-10-01T12:02:00+00:00", "pr": 9, "issue": 4, "event": "reverted", "why": "red"}]
        self.live.tick()
        self.assertEqual(self.board_task(1)["status"], "done")
        self.assertEqual([x for _, x in self.fake.sent if "reverted" in x], [])

    def test_review_request_flags_paths_outside_owned_files_and_big_diffs(self):
        self.tasks({"issue": 4, "agent": "Prometheus", "detail": "Do it.\nOWNS: `web/`, tests/test_web.py. Starts after T-1."},
                   {"issue": 5, "agent": "Prometheus", "detail": "Files owned: api/*.py\nFiles: docs/"},
                   {"issue": 6, "agent": "Hermes", "detail": "Files: docs/"})
        def pr(n, issue, paths, lines=10):
            return {"number": n, "title": "t", "headRefOid": f"{n:040d}", "isDraft": False, "author": {"login": "sam"},
                    "body": f"Closes #{issue}\nVerified: make check", "files": [{"path": p} for p in paths],
                    "additions": lines, "deletions": 1}
        self.fake.answers["gh pr list"] = done(json.dumps([
            pr(7, 4, ["web/a.py", "tests/test_web.py", "api/x.py", "Makefile"], lines=800),
            pr(8, 5, ["api/x.py", "docs/a.md"]), pr(9, 4, ["web/b.py"]), pr(10, 6, ["docs/a.md"])]))
        self.live.prs()
        asks = {t.split()[2]: (a, t) for a, t in self.fake.sent if "ready for review" in t}
        self.assertIn("\nOutside T-001's owned files: api/x.py, Makefile\n801 changed lines (over 800)", asks["#7"][1])
        self.assertTrue(asks["#8"][1].endswith("\nOutside T-002's owned files: docs/a.md"))
        self.assertTrue(asks["#9"][1].endswith(": t"))  # in scope, small: nothing added
        self.assertEqual(asks["#10"][0], "Zeus")  # Hermes built it, so Hermes cannot approve it
        self.assertIn("Built by Hermes, so its LGTM does not count", asks["#10"][1])

    def test_factory_scope_follows_the_issues_current_files_line(self):
        """Run 1 (T-506): Zeus widened the issue's Files: after the task was made, and the stale copy
        in the task detail flagged .env.example. A factory task reads the issue; an event task does not."""
        self.tasks({"issue": 4, "agent": "Prometheus", "kind": "factory", "detail": "Files: app.py"},
                   {"issue": 5, "agent": "Prometheus", "detail": "Files: app.py"})
        self.fake.answers["gh issue view 4"] = done(json.dumps({"body": "Files: app.py, .env.example, scripts/"}))
        self.fake.answers["gh issue view 5"] = done(json.dumps({"body": "Files: app.py, .env.example"}))
        def pr(n, issue):
            return {"number": n, "title": "t", "headRefOid": f"{n:040d}", "isDraft": False, "author": {"login": "sam"},
                    "body": f"Closes #{issue}\nVerified: make check", "additions": 5, "deletions": 1,
                    "files": [{"path": p} for p in ("app.py", ".env.example", "scripts/deploy.sh")]}
        self.fake.answers["gh pr list"] = done(json.dumps([pr(7, 4), pr(8, 5)]))
        self.live.prs()
        asks = {t.split()[2]: t for a, t in self.fake.sent if "ready for review" in t}
        self.assertTrue(asks["#7"].endswith(": t"))
        self.assertTrue(asks["#8"].endswith("\nOutside T-002's owned files: .env.example, scripts/deploy.sh"))

    def test_hand_merges_do_not_seed_on_a_failed_first_call(self):
        self.fake.answers["gh pr list -R me/ev --state merged"] = done("", code=1)
        self.live.hand_merges()
        self.assertNotIn("hand_merges_seeded", self.live.state)
        self.fake.answers["gh pr list -R me/ev --state merged"] = done(json.dumps(
            [{"number": 2, "body": "Closes #1", "mergedAt": "2026-10-01T10:00:00Z"}]))
        self.live.hand_merges()
        self.assertEqual(self.live.state["hand_merges_seen"], [2])
        self.assertEqual(self.live.state.get("merge_events", []), [])

    def test_untrusted_factory_scope_keeps_the_board_detail(self):
        """An untrusted issue's author can edit its body: their widened Files: must still be flagged."""
        self.tasks({"issue": 4, "agent": "Prometheus", "kind": "factory", "tags": ["untrusted"], "detail": "Files: app.py"})
        self.fake.answers["gh issue view 4"] = done(json.dumps({"body": "Files: app.py, .github/"}))
        self.fake.answers["gh pr list"] = done(json.dumps([
            {"number": 7, "title": "t", "headRefOid": "7" * 40, "isDraft": False, "author": {"login": "sam"},
             "body": "Closes #4\nVerified: make check", "additions": 5, "deletions": 1,
             "files": [{"path": "app.py"}, {"path": ".github/workflows/x.yml"}]}]))
        self.live.prs()
        [ask] = [t for a, t in self.fake.sent if "ready for review" in t]
        self.assertIn("Outside T-001's owned files: .github/workflows/x.yml", ask)

    def test_hand_merge_into_integration_is_recorded_once(self):
        """Run 1 (T-506): Zeus merged a Hermes-built PR by hand and the dashboard never counted it."""
        self.live.state["merge_events"] = [{"at": "2026-10-01T11:00:00+00:00", "pr": 3, "issue": 2, "event": "merged"}]
        old = {"number": 2, "body": "Closes #1", "mergedAt": "2026-10-01T10:00:00Z"}  # before this step existed
        self.fake.answers["gh pr list -R me/ev --state merged"] = done(json.dumps([old]))
        self.live.tick()  # the first pass only seeds what is already merged
        self.assertEqual(len(self.live.state["merge_events"]), 1)
        self.fake.answers["gh pr list -R me/ev --state merged"] = done(json.dumps([old,
            {"number": 3, "body": "Closes #2", "mergedAt": "2026-10-01T11:00:00Z"},
            {"number": 5, "body": "Closes #4\nVerified: x", "mergedAt": "2026-10-01T11:30:00Z"}]))
        self.live.tick(); self.live.tick()
        self.assertEqual(self.live.state["merge_events"][1:], [
            {"at": "2026-10-01T11:30:00Z", "pr": 5, "issue": 4, "event": "merged", "by": "hand"}])
        listed = [c for c in self.fake.calls if c[:5] == ["gh", "pr", "list", "-R", "me/ev"] and "merged" in c]
        self.assertEqual(listed[0][5:], ["--state", "merged", "--base", "integration", "--limit", "20",
                                         "--json", "number,body,mergedAt"])

    def test_pr_without_evidence_is_held_with_one_comment_and_docs_only_skip_review(self):
        lead_pr = {"number": 7, "title": "t", "headRefOid": "7" * 40, "isDraft": False, "author": {"login": "lead"},
                   "body": "Closes #4\nDONE: x", "files": [{"path": "README.md"}], "changedFiles": 1,
                   "comments": [], "reviews": []}
        self.fake.answers["gh pr list"] = lambda _: done(json.dumps([lead_pr]))
        self.live.prs(); self.live.prs()
        held = [c for c in self.fake.calls if c[:4] == ["gh", "pr", "comment", "7"]]
        self.assertEqual(len(held), 1)
        self.assertIn("`## Evidence`", held[0][-1])
        self.assertFalse(self.fake.sent)
        lead_pr["body"] += "\nVerified: rendered it"
        self.live.prs()  # docs-only with evidence: no review, even with no review_before (factory rule F2)
        self.assertFalse(self.fake.sent)
        self.assertIn(f"pr:7:{'7' * 40}", self.live.state["sent"])
        lead_pr["files"], lead_pr["headRefOid"] = [{"path": "web/app.py"}], "8" * 40
        self.live.prs()
        self.assertEqual([a for a, t in self.fake.sent if "ready for review" in t], ["Hermes"])

    def test_with_a_hackathon_config_docs_outside_files_or_gated_go_to_hermes(self):
        """Hermes review of 4ac34c0: in an event repo docs_only adds nothing to the fast lane."""
        self.config(review_before=["docs/CONTRACT.md"])
        self.fake.answers["gh issue view 4"] = done('{"body": "Files: docs/"}')
        prs = [{"number": n, "title": "t", "headRefOid": f"{n:040d}", "isDraft": False, "author": {"login": "lead"},
                "body": "Closes #4\nVerified: x", "files": [{"path": p}], "changedFiles": 1, "comments": [], "reviews": []}
               for n, p in ((7, "docs/CONTRACT.md"), (8, "README.md"), (9, "docs/guide.md"))]
        self.fake.answers["gh pr list"] = done(json.dumps(prs))
        self.live.prs()
        self.assertEqual([t.split()[2] for a, t in self.fake.sent if a == "Hermes"], ["#7", "#8"])

    def test_ci_failure_sends_the_log_tail_to_the_builder_and_counts_until_zeus_decides(self):
        self.tasks({"issue": 4, "agent": "prometheus", "detail": "Files: web/"},
                   {"issue": 5, "owner": "Sam", "detail": "Files: api/"})
        heads = {7: "1" * 40, 8: "8" * 40, 9: "9" * 40}
        def prs(_):
            return done(json.dumps([{"number": n, "title": "t", "headRefOid": sha, "isDraft": False,
                                     "author": {"login": "lead"}, "body": f"Closes #{n - 3}\nVerified: x"}
                                    for n, sha in heads.items()]))
        self.fake.answers["gh pr list"] = prs
        red = [{"name": "smoke", "bucket": "fail", "link": "https://github.com/me/ev/actions/runs/99/job/5"},
               {"name": "freeze-gate", "bucket": "pass"}, {"name": "lint", "bucket": "fail"}]
        self.fake.answers["gh pr checks 7"] = done(json.dumps(red), 1)  # gh exits 1 when a check failed
        self.fake.answers["gh pr checks 8"] = done(json.dumps(red[:1]), 1)
        self.fake.answers["gh pr checks 9"] = done(json.dumps(red[1:]))  # lint is not a required check
        self.fake.answers["gh run view 99 -R me/ev --log-failed"] = done("".join(f"line {i}\n" for i in range(1, 101)))
        self.live.tick(); self.live.tick()
        [(agent, text)] = [(a, t) for a, t in self.fake.sent if "CI failed" in t]
        self.assertEqual(agent, "Prometheus")
        self.assertIn("PR #7 at 111111111111: smoke.", text)
        self.assertIn("attempt 1 of 2", text)
        self.assertTrue(text.endswith("\n" + "\n".join(f"line {i}" for i in range(41, 101))))
        self.assertEqual(self.board_task()["attempts"], 1)
        self.assertIn("line 100", self.board_task()["notes"][-1]["text"])
        teammate = [c for c in self.fake.calls if c[:4] == ["gh", "pr", "comment", "8"]]
        self.assertEqual(len(teammate), 1)  # Sam's PR: the fix request goes where Sam reads, on GitHub
        self.assertIn("CI failed on PR #8", teammate[0][-1])
        self.assertFalse(any("CI failed on PR #9" in t for _, t in self.fake.sent))
        heads[7] = "2" * 40  # the fix push fails too: the second attempt goes to Zeus, not the builder
        self.live.tick(); heads[7] = "3" * 40; self.live.tick()
        self.assertEqual(sum("CI failed" in t for a, t in self.fake.sent if a == "Prometheus"), 1)
        stop = [t for a, t in self.fake.sent if a == "Zeus" and "failed CI" in t]
        self.assertEqual(len(stop), 1)
        self.assertIn("PR #7 (T-001) has failed CI 2 times", stop[0])
        self.assertEqual(self.board_task()["attempts"], 3)

    def test_pause_stops_every_pass_until_resumed(self):
        calls = []
        sys.modules["live_merge"] = type(sys)("live_merge")
        sys.modules["live_merge"].merge_tick = lambda *a: calls.append(1)
        self.fake.answers["gh api repos/me/ev/branches"] = done('9-web\nintegration\n')
        self.fake.answers["gh api repos/me/ev/commits/9-web"] = done('{"sha": "s1", "at": "2026-10-01T10:50:00Z"}')
        self.fake.answers["gh api repos/me/ev/compare/integration...9-web"] = done('{"ahead_by": 1}')
        pause = Path(self.tmp) / "PAUSE"
        pause.write_text("deploy freeze (by Zeus)\n")
        self.at(61); self.live.tick(); self.live.quick(); self.live.merge_now()
        self.assertEqual((calls, self.fake.calls, self.fake.sent), ([], [], []))
        self.assertIn("paused: deploy freeze", (Path(self.tmp) / "projects" / "ev" / "live.log").read_text())
        pause.unlink()
        self.live.tick()
        self.assertEqual(calls, [1])
        self.assertEqual(sum(c[:4] == ["gh", "issue", "comment", "9"] for c in self.fake.calls), 1)

    def test_review_asks_on_lead_prs_reach_the_building_agent_once(self):
        head = {"committedDate": "2026-10-01T12:00:00Z"}
        def pr(comments, reviews=()):
            return [{"number": 9, "title": "t", "headRefOid": "d" * 40, "isDraft": False,
                     "author": {"login": "lead"}, "body": "Closes #4",
                     "comments": list(comments), "reviews": list(reviews)}]
        self.fake.answers["gh pr view 9"] = done(json.dumps({"commits": [head]}))
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "task"}, {"name": "agent:prometheus"}]}')
        old = {"createdAt": "2026-10-01T11:00:00Z", "body": "fix the old thing", "author": {"login": "lead"}}
        lgtm = {"createdAt": "2026-10-01T12:05:00Z", "body": "LGTM " + "d" * 40, "author": {"login": "lead"}}
        self.fake.answers["gh pr list"] = done(json.dumps(pr([old, lgtm])))
        self.live.tick()
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))
        ask = {"submittedAt": "2026-10-01T12:06:00Z", "body": "CHANGES: Handle 413\nthanks", "author": {"login": "lead"}}
        self.fake.answers["gh pr list"] = done(json.dumps(pr([old], [ask])))
        self.live.tick(); self.live.tick()
        fixes = [(a, t) for a, t in self.fake.sent if "changes requested" in t]
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0][0], "Prometheus")
        self.assertIn("Handle 413", fixes[0][1])

    def test_done_comment_opens_one_pr_from_the_lead_account(self):
        plan = {"createdAt": "2026-10-01T12:01:00Z", "body": "Plan:\n1. x", "author": {"login": "sam"},
                "url": "https://github.com/me/ev/issues/12#issuecomment-1"}
        said = {"createdAt": "2026-10-01T12:30:00Z", "author": {"login": "sam"},
                "body": "DONE: parser works\nVerified: uv run pytest -q: 41 passed, clean worktree at 1a2b3c4\n"
                        "Not verified: the live deploy\nImpact: none"}
        fake = {"createdAt": "2026-10-01T12:31:00Z", "body": "DONE: me too", "author": {"login": "stranger"}}
        issue = {"number": 12, "title": "Parse totals", "comments": [plan, said, fake]}
        self.fake.answers["gh issue list -R me/ev --state open --limit 200 --json number,title,comments"] = \
            lambda _: done(json.dumps([issue]))
        self.fake.answers["gh api repos/me/ev/git/matching-refs/heads/12-"] = done('["refs/heads/12-parse"]')
        heads = []
        self.fake.answers["gh pr list -R me/ev --state open --limit 200 --json headRefName"] = \
            lambda _: done(json.dumps([{"headRefName": h} for h in heads]))
        creates = lambda: [c for c in self.fake.calls if c[:3] == ["gh", "pr", "create"]]
        self.live.tick(); self.live.tick()
        self.assertEqual(len(creates()), 1)
        c = creates()[0]
        self.assertEqual(c[c.index("--base") + 1], "integration")
        self.assertEqual(c[c.index("--head") + 1], "12-parse")
        body = c[c.index("--body") + 1]
        self.assertTrue(body.startswith("Closes #12"))
        self.assertIn(plan["url"], body)
        self.assertIn("\nVerified: uv run pytest -q: 41 passed, clean worktree at 1a2b3c4\n", body)
        self.assertIn("\nNot verified: the live deploy\n", body)
        heads.append("12-parse")  # a second DONE: after review fixes, on the open PR's branch
        issue["comments"].append({"createdAt": "2026-10-01T12:50:00Z", "body": "DONE: fixed\nVerified: 42 passed",
                                  "author": {"login": "sam"}})
        self.live.tick()
        self.assertEqual(len(creates()), 1)

    def test_failed_pr_create_retries_the_same_done(self):
        issue = {"number": 12, "title": "Parse totals", "comments": [
            {"createdAt": "2026-10-01T12:30:00Z", "author": {"login": "sam"},
             "body": "DONE: parser works\nVerified: 41 passed"}]}
        self.fake.answers["gh issue list"] = done(json.dumps([issue]))
        self.fake.answers["gh api repos/me/ev/git/matching-refs/heads/12-"] = done('["refs/heads/12-parse"]')
        attempts = []
        def create(args):
            attempts.append(args)
            return done("", 1 if len(attempts) == 1 else 0)
        self.fake.answers["gh pr create"] = create
        self.live.done()
        self.live.done()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len([key for key in self.live.state["sent"] if key.startswith("done:12:")]), 1)

    def test_done_without_verified_is_refused_once_with_what_is_missing(self):
        said = {"createdAt": "2026-10-01T12:30:00Z", "body": "DONE: parser works\nImpact: none",
                "author": {"login": "sam"}}
        self.fake.answers["gh issue list -R me/ev --state open --limit 200 --json number,title,comments"] = \
            done(json.dumps([{"number": 12, "title": "Parse totals", "comments": [said]}]))
        self.fake.answers["gh api repos/me/ev/git/matching-refs/heads/12-"] = done('["refs/heads/12-parse"]')
        self.live.tick(); self.live.tick()
        self.assertFalse([c for c in self.fake.calls if c[:3] == ["gh", "pr", "create"]])
        refusals = [c for c in self.fake.calls if c[:4] == ["gh", "issue", "comment", "12"]]
        self.assertEqual(len(refusals), 1)
        self.assertIn("Verified:", refusals[0][-1])
        self.assertIn("Not verified:", refusals[0][-1])

    def test_review_asks_on_a_teammates_issue_are_left_to_their_inbox(self):
        self.fake.answers["gh issue view 4"] = done('{"labels": [], "assignees": [{"login": "sam"}]}')
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": "e" * 40,
            "isDraft": False, "author": {"login": "lead"}, "body": "Closes #4", "reviews": [],
            "comments": [{"createdAt": "2026-10-01T12:06:00Z", "body": "CHANGES: fix", "author": {"login": "lead"}}]}]))
        self.fake.answers["gh pr view 9"] = done('{"commits": []}')
        self.live.tick()
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))

    def test_teammate_pr_comments_are_not_routed(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": "e" * 40,
            "isDraft": False, "author": {"login": "sam"}, "body": "Closes #4", "commits": [],
            "comments": [{"createdAt": "2026-10-01T12:06:00Z", "body": "CHANGES: fix", "author": {"login": "lead"}}], "reviews": []}]))
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

    def test_unreviewed_merges_reach_hermes_once_and_a_gated_wait_reaches_zeus_once(self):
        got = []
        def merge_tick(repo, clone, smoke, lead, state, run, send, review_before):
            got.append(review_before)
            state.setdefault("unreviewed", [31])
            state["gated"] = [32]
        sys.modules["live_merge"] = type(sys)("live_merge")
        sys.modules["live_merge"].merge_tick = merge_tick
        self.live.tick(); self.at(5); self.live.tick()
        self.assertEqual(got[0], None)  # no review_before in hackathon.json: live_merge gates everything
        self.assertFalse(any("#31" in t for _, t in self.fake.sent))
        self.assertFalse(any("#32" in t for _, t in self.fake.sent))
        self.at(11); self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if "#32" in t], ["Zeus"])
        self.at(31); self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if a == "Hermes" and "#31" in t], ["Hermes"])

    def test_roll_call_shows_live_and_untied_branches_with_work_status(self):
        issue = {"number": 8, "state": "OPEN", "assignees": [{"login": "sam"}], "comments": [
            {"body": "DONE: built UI\nVerified: tests", "createdAt": "2026-10-01T12:20:00Z",
             "author": {"login": "sam"}}]}
        self.fake.answers["gh issue list -R me/ev --state all"] = done(json.dumps([issue]))
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 18, "title": "UI", "headRefOid": "a" * 40,
            "headRefName": "8-ui", "isDraft": False, "author": {"login": "lead"}, "body": "Closes #8"}]))
        self.fake.answers["gh api repos/me/ev/branches"] = done('8-ui\nfrontend\nintegration\n')
        self.fake.answers["gh api repos/me/ev/compare/integration...8-ui"] = done('{"ahead_by": 1}')
        self.fake.answers["gh api repos/me/ev/compare/integration...frontend"] = done('{"ahead_by": 1}')
        self.fake.answers["gh api repos/me/ev/commits/8-ui"] = done(
            '{"sha": "s8", "at": "2026-10-01T12:25:00Z", "author": {"login": "sam"}}')
        self.fake.answers["gh api repos/me/ev/commits/frontend"] = done(
            '{"sha": "sf", "at": "2026-10-01T12:24:00Z", "author": {"login": "sam"}}')
        self.fake.answers["gh api repos/me/ev/events"] = done(json.dumps([{"type": "PushEvent",
            "payload": {"ref": "refs/heads/frontend"}, "created_at": "2026-10-01T12:27:00Z"}]))
        self.live.state["unreviewed"] = [31]
        self.fake.answers["gh pr view 31"] = done('{"number": 31, "headRefName": "8-ui", "body": "Closes #8"}')
        self.live.tick()
        self.at(31)
        self.live.tick()
        [roll] = [text for agent, text in self.fake.sent if agent == "Zeus" and text.startswith("ev roll call")]
        self.assertIn("Sam", roll)
        for part in ("#8", "8-ui", "frontend", "no issue", "#18", "DONE", "#31", "12:27"):
            self.assertIn(part, roll)
        self.assertEqual(len([c for c in self.fake.calls if c[:3] == ["gh", "pr", "list"]
                              and "--state" in c and c[c.index("--state") + 1] == "open"]), 2)
        self.assertEqual(len([c for c in self.fake.calls if c[:2] == ["gh", "api"]
                              and c[2].startswith("repos/me/ev/branches")]), 2)

    def test_factory_roll_call_skips_empty_work(self):
        self.config(factory=True)
        self.live.roll_call(force=True)
        self.at(31)
        self.live.roll_call(force=True)
        self.assertFalse(any(agent == "Zeus" and text.startswith("ev roll call")
                             for agent, text in self.fake.sent))
        self.assertNotIn("rollcall_last", self.live.state)

    def test_factory_roll_call_sends_only_changed_work_across_restart(self):
        self.config(factory=True)
        issue = {"number": 8, "state": "OPEN", "assignees": [{"login": "sam"}], "comments": []}
        self.fake.answers["gh issue list -R me/ev --state all"] = done(json.dumps([issue]))
        self.live.roll_call(force=True)
        self.live.save()
        self.live = self.make()
        self.at(31)
        self.live.roll_call(force=True)
        rolls = lambda: [text for agent, text in self.fake.sent if agent == "Zeus" and text.startswith("ev roll call")]
        self.assertEqual(len(rolls()), 1)
        self.fake.answers["gh issue list -R me/ev --state all"] = done(json.dumps([issue | {"number": 9}]))
        self.at(62)
        self.live.roll_call(force=True)
        self.assertEqual(len(rolls()), 2)
        self.assertIn("#9", rolls()[-1])

    def test_failed_pr_list_alerts_lead(self):
        self.fake.answers["gh pr list"] = done("", 1)
        self.live.tick()
        self.assertTrue(any(agent == "Zeus" and "PR list failed" in text for agent, text in self.fake.sent))

    def test_failed_branch_list_alerts_and_marks_roll_call_incomplete(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done("", 1)
        self.live.tick()
        self.at(31); self.live.tick()
        self.assertEqual(sum(agent == "Zeus" and "branch list failed" in text
                             for agent, text in self.fake.sent), 1)
        [roll] = [text for agent, text in self.fake.sent if agent == "Zeus" and text.startswith("ev roll call")]
        self.assertIn("branch list unavailable", roll)

    def test_failed_branch_compare_marks_roll_call_incomplete(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done("frontend\n")
        self.fake.answers["gh api repos/me/ev/compare/"] = done("", 1)
        self.live.tick()
        self.at(31); self.live.tick()
        [roll] = [text for agent, text in self.fake.sent if agent == "Zeus" and text.startswith("ev roll call")]
        self.assertIn("branch work check unavailable", roll)
        self.assertEqual(sum(agent == "Zeus" and "branch work check failed" in text
                             for agent, text in self.fake.sent), 1)

    def test_messages_from_live_merge_are_logged(self):
        """Dry run 2026-10-12: the revert after #54 reached Zeus but not live.log."""
        text = "Smoke failed after #54; reverted integration and reopened issue #17"
        sys.modules["live_merge"] = type(sys)("live_merge")
        sys.modules["live_merge"].merge_tick = lambda repo, clone, smoke, lead, state, run, send, rb: send("Zeus", text)
        self.live.merge()
        self.assertIn(("Zeus", text), self.fake.sent)
        self.assertIn(f"sent Zeus: {text}", (Path(self.tmp) / "projects" / "ev" / "live.log").read_text())

    def test_open_prs_listed_100_at_a_time_with_commits_fetched_per_changes_pr(self):
        """gh's default 30 dropped the 31st open PR; commits on a 100-PR list exceed GitHub's 500,000-node
        GraphQL limit, so they come per PR, only where a CHANGES: note needs them."""
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "agent:prometheus"}]}')
        stale = {"createdAt": "2026-10-01T12:05:00Z", "body": "CHANGES: fixed since", "author": {"login": "lead"}}
        self.fake.answers["gh pr list"] = done(json.dumps(
            [{"number": n, "title": "t", "headRefOid": f"{n:040d}", "isDraft": False, "author": {"login": "lead"},
              "body": "Closes #4\nVerified: x", "reviews": [], "comments": [stale] if n == 9 else []} for n in (8, 9)]))
        self.fake.answers["gh pr view 9"] = done('{"commits": [{"committedDate": "2026-10-01T12:10:00Z"}]}')
        self.live.prs()
        listed = next(c for c in self.fake.calls if c[:3] == ["gh", "pr", "list"])
        self.assertEqual(listed[listed.index("--limit") + 1], "100")
        self.assertNotIn("commits", listed[-1].split(","))
        self.assertEqual([c for c in self.fake.calls if c[:3] == ["gh", "pr", "view"]],
                         [["gh", "pr", "view", "9", "-R", "me/ev", "--json", "commits"]])
        self.assertFalse(any("changes requested" in t for _, t in self.fake.sent))  # the note predates the push
        self.assertEqual(sum("ready for review" in t for _, t in self.fake.sent), 2)

    def test_merge_flags_write_the_trigger_files(self):
        import types
        d = Path(self.tmp) / "projects" / "ev"
        ns = lambda **kw: types.SimpleNamespace(**{**dict(project="ev", once=True, interval=10, merge_now=False,
                                                          hold_merges=False, resume_merges=False, roll_call=False), **kw})
        self.live_mod.cmd_live(ns(merge_now=True))
        self.assertTrue((d / ".merge-now").is_file())
        self.live_mod.cmd_live(ns(hold_merges=True))
        self.assertTrue((d / ".merge-hold").is_file())
        self.live_mod.cmd_live(ns(resume_merges=True))
        self.assertFalse((d / ".merge-hold").exists())
        self.live_mod.cmd_live(ns(roll_call=True))
        self.assertTrue((d / ".roll-call-now").is_file())

    def test_quick_poll_tells_hermes_about_a_new_pr(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 4, "title": "t", "headRefOid": "f" * 40,
                                                            "isDraft": False, "author": {"login": "sam"},
                                                            "body": "## Evidence\nmake check: ok"}]))
        self.live.quick()
        self.assertEqual([a for a, t in self.fake.sent if "PR #4" in t], ["Hermes"])
        self.assertFalse(any(c[:2] == ["hub", "gh-sync"] for c in self.fake.calls))

    def test_third_round_of_changes_goes_to_zeus_once(self):
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "agent:prometheus"}]}')
        for i, sha in enumerate(("1" * 40, "2" * 40, "3" * 40, "4" * 40)):
            self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": sha,
                "isDraft": False, "author": {"login": "lead"}, "body": "Closes #4", "reviews": [],
                "comments": [{"createdAt": f"2026-10-01T12:0{i}:30Z", "body": "CHANGES: still drifts", "author": {"login": "lead"}}]}]))
            self.fake.answers["gh pr view 9"] = done(json.dumps({"commits": [{"committedDate": f"2026-10-01T12:0{i}:00Z"}]}))
            self.live.tick()
            if i == 1:
                self.assertFalse(any("round" in t for _, t in self.fake.sent))
        self.assertEqual(sum("changes requested" in t for a, t in self.fake.sent if a == "Prometheus"), 4)
        self.assertEqual(sum("3rd round" in t for a, t in self.fake.sent if a == "Zeus"), 1)

    def test_only_changes_notes_are_relayed(self):
        """Shapes of real-world-agents' 17 relayed notes: 12 were the author's own echoes from the lead
        account, one was `FYI, not blocking:`, and 4 were real requests (now opening `CHANGES:`)."""
        notes = ["Review fix in 53149cd: timeouts reordered", "Review fix in 8a1f2c0", "Pushed 4d2e9a1 with the fix",
                 "Addressed: moved the guard into verify/", "Fixed in 77ab310, re-running smoke",
                 "Rebased on integration, conflicts fixed", "Review fix in c0ffee1: tests added", "Done, see 1b2c3d4",
                 "Updated the PR body with Verified:", "Applied the suggestion", "Review fix in 9e8d7c6",
                 "Smoke green locally: 41 passed",
                 "FYI, not blocking: the claim linter rejects 44 answers",
                 "CHANGES: the voice transcript reaches the model unescaped",
                 "CHANGES: the outer timeout fires before the fallback",
                 "CHANGES: the authority role is read from the wrong field",
                 "  CHANGES: the fallback drops good evidence"]
        self.fake.answers["gh issue view 4"] = done('{"labels": [{"name": "agent:prometheus"}]}')
        self.fake.answers["gh pr list"] = done(json.dumps([
            {"number": 100 + i, "title": "t", "headRefOid": f"{i:040d}", "isDraft": False, "author": {"login": "lead"},
             "body": "Closes #4", "reviews": [],
             "comments": [{"createdAt": "2026-10-01T12:05:00Z", "body": body, "author": {"login": "lead"}},
                          {"createdAt": "2026-10-01T12:06:00Z", "body": f"LGTM {i:040d}", "author": {"login": "lead"}}]}
            for i, body in enumerate(notes)]))
        self.fake.answers["gh pr view"] = done('{"commits": [{"committedDate": "2026-10-01T12:00:00Z"}]}')
        self.live.tick()
        relayed = [t for _, t in self.fake.sent if "changes requested" in t]
        self.assertEqual(len(relayed), 4)
        self.assertTrue(all("CHANGES:" in t for t in relayed))

    def test_fyi_comment_is_not_a_change_request(self):
        self.fake.answers["gh pr list"] = done(json.dumps([{"number": 9, "title": "t", "headRefOid": "9" * 40,
            "isDraft": False, "author": {"login": "lead"}, "body": "Closes #4", "reviews": [],
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

    def config(self, **extra):
        (Path(self.tmp) / "projects" / "ev" / "hackathon.json").write_text(json.dumps({**CFG, **extra}))
        self.live = self.make()

    def freeze_answers(self, runner_code):
        sha, clone = "f" * 40, str(self.live.clone)
        self.fake.answers["gh api repos/me/ev/git/ref/tags/freeze"] = done(json.dumps({"object": {"sha": sha}}))
        self.fake.answers[f"git -C {clone} cat-file -e {sha}:scripts/run_cases.py"] = done(code=runner_code)
        self.fake.answers[f"git -C {clone} grep -n -E {self.live_mod.LIMITS} {sha}"] = done(
            f"{sha}:starter/core/store.py:12:# ponytail: global lock, per-case locks if it contends\n"
            f"{sha}:app/agent.py:40:# shortcut: one retry, add backoff if the API throttles\n")
        return sha

    def test_limits_pattern_matches_comments_only(self):
        repo = Path(self.tmp) / "lim"
        repo.mkdir()
        (repo / "a.py").write_text("# shortcut: one retry\nkeys = {'shortcut: ': 1}\n")
        (repo / "b.ts").write_text("// ponytail: global lock\nconst m = { shortcut: '⌘K' }\n")
        (repo / "c.md").write_text("Press the keyboard shortcut: Ctrl-K\n")
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        git("init", "-q"); git("add", "."); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
        hits = git("grep", "-n", "-E", self.live_mod.LIMITS, "HEAD").stdout
        self.assertEqual(sorted(l.split(":")[1] for l in hits.splitlines()), ["a.py", "b.ts"])

    def test_freeze_records_the_sha_and_reports_once(self):
        for runner_code, warned in ((128, 1), (0, 0)):
            with self.subTest(runner_code=runner_code):
                self.setUp()
                self.config(runner="scripts/run_cases.py")
                sha = self.freeze_answers(runner_code)
                self.at(119); self.live.tick()
                self.assertFalse(any(sha[:12] in t for _, t in self.fake.sent))
                self.at(120); self.live.tick(); self.live.tick(); self.live.tick()
                state = json.loads((Path(self.tmp) / "projects" / "ev" / "live-state.json").read_text())
                self.assertEqual(state["freeze_sha"], sha)
                to_zeus = [t for a, t in self.fake.sent if a == "Zeus" and sha[:12] in t]
                self.assertEqual(sum(sha in t and "Tell the lead" in t for t in to_zeus), 1)
                self.assertEqual(sum("not in the frozen commit" in t for t in to_zeus), warned)
                self.assertEqual(sum("starter/core/store.py:12:# ponytail: global lock" in t for t in to_zeus), 1)
                self.assertEqual(sum("app/agent.py:40:# shortcut: one retry" in t for t in to_zeus), 1)
                self.assertEqual(len(to_zeus), 2 + warned)

    def test_release_review_reminder_at_freeze_minus_45_once(self):
        self.live.state["unreviewed"] = [21, 23]
        self.at(74); self.live.tick()
        self.at(76); self.live.tick(); self.live.tick()
        self.at(121); self.live.tick()
        reminders = [(a, t) for a, t in self.fake.sent if "release review" in t]
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0][0], "Hermes")
        self.assertIn("#21, #23", reminders[0][1])

    def test_spine_reminder_once_at_its_deadline(self):
        self.at(119); self.live.tick()
        self.at(121); self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if "spine" in t], ["Zeus"])  # default: build start + 2 h
        self.setUp()
        self.config(deadlines=CFG["deadlines"] + [{"name": "spine", "at": "2026-10-01T13:00:00Z"}])
        self.at(59); self.live.tick()
        self.at(61); self.live.tick(); self.live.tick()
        self.assertEqual([a for a, t in self.fake.sent if "spine" in t], ["Zeus"])

    def test_throttle_skips_the_pass_backs_off_and_tells_zeus_once_per_episode(self):
        limited = subprocess.CompletedProcess([], 1, "", "gh: API rate limit exceeded for user ID 1. (HTTP 403)")
        secondary = subprocess.CompletedProcess([], 1, "", "gh: You have exceeded a secondary rate limit. (HTTP 403)")
        branches = lambda: sum(c[:2] == ["gh", "api"] and c[2].startswith("repos/me/ev/branches")
                               for c in self.fake.calls)
        self.fake.answers["gh issue list -R me/ev --label change-request"] = limited
        self.live.tick()
        self.assertEqual(branches(), 0)  # the rest of the pass (merge ... nudges) was skipped
        self.assertEqual(self.live.state["backoff"], 600)  # 2 x the 300 s interval, capped at 10 min
        calls = len(self.fake.calls)
        self.live.quick(); self.live.merge_now()
        self.assertEqual(len(self.fake.calls), calls)  # the in-between polls wait it out too
        self.at(10); self.fake.answers["gh issue list -R me/ev --label change-request"] = secondary
        self.live.tick()
        self.assertEqual(self.fake.sent, [("Zeus", "ev: hub live throttled by GitHub until ~13:10")])
        self.assertIn("throttled by GitHub", (Path(self.tmp) / "projects" / "ev" / "live.log").read_text())
        del self.fake.answers["gh issue list -R me/ev --label change-request"]
        self.at(20); self.live.tick()
        self.assertNotIn("backoff", self.live.state)  # a clean pass ends the episode
        self.assertEqual(branches(), 1)
        self.fake.answers["gh issue list -R me/ev --label change-request"] = limited
        self.at(30); self.live.tick()
        self.assertEqual([t for _, t in self.fake.sent if "throttled" in t][-1], "ev: hub live throttled by GitHub until ~13:40")

    def test_a_throttle_between_passes_backs_off_too(self):
        self.fake.answers["gh pr list"] = subprocess.CompletedProcess([], 1, "", "HTTP 429: Too Many Requests (Retry-After: 60)")
        self.live.quick()
        self.assertEqual(self.live.state["backoff"], 600)
        self.assertEqual([a for a, t in self.fake.sent if "throttled" in t], ["Zeus"])

    def test_a_403_without_rate_limit_is_an_ordinary_failure(self):
        self.fake.answers["gh issue list -R me/ev --label change-request"] = subprocess.CompletedProcess(
            [], 1, "", "HTTP 403: Resource not accessible by integration")
        self.live.tick()
        self.assertNotIn("backoff", self.live.state)
        self.assertEqual(sum(c[:2] == ["gh", "api"] and c[2].startswith("repos/me/ev/branches")
                             for c in self.fake.calls), 1)

    def deploy_repo(self, command):
        """A real one-commit clone and a deploy key: the deploy runs detached, so the fake runner
        can't stand in for it. Returns the sha marked as promoted."""
        clone = Path(self.tmp) / "clone"
        clone.mkdir()
        git = lambda *a: subprocess.run(["git", "-C", str(clone), *a], check=True, capture_output=True, text=True)
        git("init", "-q")
        (clone / "README.md").write_text("x\n")
        git("add", "README.md")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
        self.config(deploy={"owner": "Prometheus", "command": command})
        self.live.clone = clone
        self.live.state["promoted"] = sha = git("rev-parse", "HEAD").stdout.strip()
        return sha

    def wait_deploy(self):
        for _ in range(200):
            if (Path(self.tmp) / "projects" / "ev" / "deploy.exit").is_file():
                return
            time.sleep(0.05)
        self.fail("the deploy never finished")

    def test_green_promote_deploys_in_the_background_and_reports_sha_revision_and_url(self):
        sha = self.deploy_repo("sleep 0.5; test -f README.md && echo 'docs: https://docs.example.com' && "
                               "echo 'Service [ev] revision [ev-00012-xyz] has been deployed and is serving 100 percent of traffic.' && "
                               "echo 'Service URL: https://ev-abc.a.run.app'")
        self.live.tick()
        self.assertEqual(self.live.state["deploy"]["sha"], sha)
        self.assertNotIn("exit", self.live.state["deploy"])  # the tick did not wait for it
        self.wait_deploy()
        self.live.tick(); self.live.tick()
        state = json.loads((Path(self.tmp) / "projects" / "ev" / "live-state.json").read_text())
        self.assertEqual(state["deploy"]["url"], "https://ev-abc.a.run.app")
        self.assertEqual(state["deploy"]["revision"], "ev-00012-xyz")
        self.assertEqual([(a, t) for a, t in self.fake.sent if "deployed" in t],  # one release record
                         [("Zeus", f"ev deployed {sha[:12]}: revision ev-00012-xyz, https://ev-abc.a.run.app")])
        worktrees = subprocess.run(["git", "-C", str(self.live.clone), "worktree", "list"], capture_output=True, text=True)
        self.assertEqual(len(worktrees.stdout.splitlines()), 1)  # the throwaway worktree is gone

    def test_failed_deploy_alerts_zeus_once_and_never_touches_main(self):
        sha = self.deploy_repo("echo 'build ok'; echo 'ERROR: permission denied on run.services.create' >&2; exit 3")
        self.live.tick(); self.wait_deploy(); self.live.tick(); self.live.tick()
        alerts = [(a, t) for a, t in self.fake.sent if "deploy failed" in t]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0][0], "Zeus")
        self.assertIn(f"deploy failed at {sha[:12]} (exit 3)", alerts[0][1])
        self.assertIn("permission denied on run.services.create", alerts[0][1])
        self.assertNotIn("url", self.live.state["deploy"])
        self.assertFalse([c for c in self.fake.calls if "push" in c])

    def test_no_deploy_key_means_no_deploy(self):
        self.live.state["promoted"] = "a" * 40
        self.live.tick(); self.live.tick()
        self.assertNotIn("deploy", self.live.state)
        self.assertFalse((Path(self.tmp) / "projects" / "ev" / "deploy.log").exists())

    def test_first_merge_missing_ci_check_tells_zeus_once(self):
        sha = "e" * 40
        self.config(checks=["freeze-gate", "tests"])
        self.fake.answers[f"gh api repos/me/ev/commits/{sha}/check-runs"] = done('["freeze-gate"]')
        self.live.tick()
        self.assertFalse([c for c in self.fake.calls if "check-runs" in " ".join(c)])  # nothing merged yet
        self.live.state["first_merge"] = sha
        self.live.tick(); self.live.tick()
        self.assertEqual([(a, t) for a, t in self.fake.sent if "never reported" in t],
                         [("Zeus", "ev: CI never reported tests on the first merged PR's head eeeeeeeeeeee: check the "
                                   "repo's .github/workflows, or drop the name from \"checks\" in hackathon.json.")])
        self.assertEqual(sum("check-runs" in " ".join(c) for c in self.fake.calls), 1)

    def test_ci_check_defaults_to_freeze_gate_and_retries_a_failed_lookup(self):
        sha = "e" * 40
        self.live.state["first_merge"] = sha
        answers = [done(code=1), done('["freeze-gate"]')]
        self.fake.answers[f"gh api repos/me/ev/commits/{sha}/check-runs"] = lambda _: answers.pop(0)
        self.live.tick(); self.live.tick(); self.live.tick()
        self.assertEqual(self.live.state["ci_checked"], sha)
        self.assertFalse(any("never reported" in t for _, t in self.fake.sent))

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

    def test_idle_branch_nudged_at_45_minutes_even_with_closed_issue_then_escalated(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done('9-web\nintegration\n')
        self.fake.answers["gh api repos/me/ev/commits/9-web"] = done('{"sha": "s1", "at": "2026-10-01T10:50:00Z"}')
        self.fake.answers["gh api repos/me/ev/compare/integration...9-web"] = done('{"ahead_by": 1}')
        self.fake.answers["gh issue view 9"] = done('{"state": "CLOSED"}')
        self.live.tick()
        comments = [c for c in self.fake.calls if c[:4] == ["gh", "issue", "comment", "9"]]
        self.assertEqual(len(comments), 1)
        self.at(46); self.live.tick(); self.live.tick()
        self.assertEqual(len([c for c in self.fake.calls if c[:4] == ["gh", "issue", "comment", "9"]]), 1)
        self.assertEqual(sum(a == "Zeus" and "9-web" in t and "still silent" in t
                             for a, t in self.fake.sent), 1)

    def test_review_ready_pr_branch_is_not_nudged_but_draft_is(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done('8-ui\n9-draft\n')
        self.fake.answers["gh api repos/me/ev/compare/"] = done('{"ahead_by": 1}')
        for branch in ("8-ui", "9-draft"):
            self.fake.answers[f"gh api repos/me/ev/commits/{branch}"] = done(
                '{"sha": "old", "at": "2026-10-01T10:50:00Z"}')
        self.fake.answers["gh pr list -R me/ev --state merged"] = done('[]')
        self.fake.answers["gh pr list"] = done(json.dumps([
            {"number": 18, "title": "ready", "headRefOid": "old", "headRefName": "8-ui",
             "isDraft": False, "author": {"login": "sam"}},
            {"number": 19, "title": "draft", "headRefOid": "old", "headRefName": "9-draft",
             "isDraft": True, "author": {"login": "sam"}}]))
        self.live.tick()
        self.at(46); self.live.tick()
        self.assertFalse(any(c[:4] == ["gh", "issue", "comment", "8"] for c in self.fake.calls))
        self.assertFalse(any(a == "Zeus" and "8-ui" in t and "still silent" in t
                             for a, t in self.fake.sent))
        self.assertEqual(sum(c[:4] == ["gh", "issue", "comment", "9"] for c in self.fake.calls), 1)
        self.assertEqual(sum(a == "Zeus" and "9-draft" in t and "still silent" in t
                             for a, t in self.fake.sent), 1)

    def test_untied_branch_gets_commit_nudge_and_merged_head_gets_none(self):
        self.fake.answers["gh api repos/me/ev/branches"] = done('frontend\n7-merged\n')
        self.fake.answers["gh api repos/me/ev/compare/"] = done('{"ahead_by": 1}')
        self.fake.answers["gh api repos/me/ev/commits/frontend"] = done(
            '{"sha": "front-sha", "at": "2026-10-01T10:50:00Z", "author": "sam"}')
        self.fake.answers["gh api repos/me/ev/commits/7-merged"] = done(
            '{"sha": "merged-sha", "at": "2026-10-01T10:50:00Z", "author": "sam"}')
        self.fake.answers["gh pr list -R me/ev --state merged"] = done(
            '[{"headRefName": "7-merged", "headRefOid": "merged-sha"}]')
        self.live.tick()
        self.assertTrue(any(c[:4] == ["gh", "api", "-X", "POST"] and "front-sha/comments" in c[4]
                            for c in self.fake.calls), self.fake.calls)
        self.assertFalse(any("7-merged" in " ".join(c) and "comments" in " ".join(c)
                             for c in self.fake.calls))

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
