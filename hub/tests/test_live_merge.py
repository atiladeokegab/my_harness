import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from live_merge import merge_tick


SHA = "a" * 40
MERGE = "b" * 40
REVERT = "c" * 40


def pr(number=7, author="worker", body="Closes #17", sha=SHA):
    return {"number": number, "author": {"login": author}, "body": body,
            "headRefOid": sha, "baseRefName": "integration", "isDraft": False,
            "mergeable": "MERGEABLE", "comments": []}


class FakeRun:
    def __init__(self, prs=None):
        self.prs = prs if prs is not None else [pr()]
        self.calls = []
        self.reviews = [{"state": "APPROVED", "commit_id": SHA}]
        self.checks = [{"name": "freeze-gate", "bucket": "pass", "state": "SUCCESS"}]
        self.issues = {17: "CLOSED"}
        self.issue_bodies = {17: ""}
        self.smoke_code = 0
        self.smoke_output = "ok\n"
        self.setup_fails = False
        self.conflicts = []
        self.head = SHA
        self.project = True  # the worktree has a pyproject.toml, so the smoke runs

    def __call__(self, args, cwd=None, timeout=60):
        self.calls.append((args, cwd, timeout))
        result = None
        if args[:3] == ["gh", "pr", "list"]:
            result = self.conflicts if any(c[0][:3] == ["gh", "pr", "merge"] for c in self.calls) else self.prs
        elif args[:2] == ["gh", "api"]:
            result = self.reviews
        elif args[:3] == ["gh", "pr", "checks"]:
            result = self.checks
        elif args[:3] == ["gh", "issue", "view"]:
            result = {"state": self.issues[int(args[3])],
                      "body": self.issue_bodies.get(int(args[3]), "")}
        elif args[:3] == ["gh", "pr", "view"]:
            result = {"mergeCommit": {"oid": MERGE}}
        if args[:2] == ["timeout", "300"]:
            return subprocess.CompletedProcess(args, self.smoke_code, self.smoke_output, "")
        if "worktree" in args and "add" in args and self.setup_fails:
            return subprocess.CompletedProcess(args, 1, "", "setup failed")
        if "worktree" in args and "add" in args and self.project:
            Path(args[args.index("--detach") + 1]).joinpath("pyproject.toml").write_text("")
        if args[-2:] == ["rev-parse", "origin/integration"]:
            return subprocess.CompletedProcess(args, 0, self.head, "")
        if args[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, REVERT if any("revert" in c[0] for c in self.calls) else self.head, "")
        return subprocess.CompletedProcess(args, 0, json.dumps(result) if result is not None else "", "")

    def commands(self, *prefix):
        return [args for args, _, _ in self.calls if args[:len(prefix)] == list(prefix)]


class MergeTickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clone = Path(self.tmp.name)
        self.run = FakeRun()
        self.sent = []
        self.state = {}

    def tick(self):
        merge_tick("o/r", self.clone, "make smoke", "lead", self.state,
                   self.run, lambda agent, msg: self.sent.append((agent, msg)))

    def test_no_project_yet_is_green_without_running_the_smoke(self):
        self.run.project = False
        self.run.smoke_code = 1
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertFalse(self.run.commands("timeout", "300"))
        self.assertFalse(any("revert" in args for args, _, _ in self.run.calls))
        self.assertTrue(any(args[-1] == f"{SHA}:refs/heads/main" for args, _, _ in self.run.calls))

    def test_lgtm_with_notes_below_still_merges_a_lead_pr(self):
        self.run.prs = [pr(7)]
        self.run.prs[0]["author"] = {"login": "lead"}
        self.run.prs[0]["comments"] = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}\nNotes: fine."}]
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_approved_head_merges_one_and_promotes_tested_sha(self):
        self.run.prs = [pr(7), pr(8)]
        self.tick()
        merges = self.run.commands("gh", "pr", "merge")
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0][3], "7")
        self.assertIn(SHA, merges[0])
        self.assertNotIn("--admin", merges[0])
        self.assertEqual(self.state["smoked"], SHA)
        self.assertTrue(any(c[-2:] == ["origin", f"{SHA}:refs/heads/main"] for c, _, _ in self.run.calls))

    def test_stale_approval_dependency_and_failed_gate_never_merge(self):
        self.run.issue_bodies[17] = "Depends on: #19, #20"
        self.run.issues[19] = "OPEN"
        self.run.issues[20] = "CLOSED"
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.issues[19] = "CLOSED"
        self.run.issues[20] = "OPEN"
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.issues[20] = "CLOSED"
        self.run.reviews[0]["commit_id"] = MERGE
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.reviews[0]["commit_id"] = SHA
        self.run.checks[0]["bucket"] = "fail"
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))

    def test_lead_requires_exact_lgtm_and_only_then_admin(self):
        self.run.prs = [pr(author="lead")]
        self.run.prs[0]["comments"] = [{"author": {"login": "lead"}, "body": f"LGTM {MERGE}"}]
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.prs[0]["comments"] = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
        self.tick()
        self.assertIn("--admin", self.run.commands("gh", "pr", "merge")[0])

    def test_red_reverts_reopens_issue_and_tells_zeus(self):
        self.run.smoke_code = 1
        self.run.smoke_output = "\n".join(str(i) for i in range(40))
        self.tick()
        self.assertTrue(any("revert" in c for c, _, _ in self.run.calls))
        self.assertTrue(any(c[-2:] == ["origin", "HEAD:refs/heads/integration"] for c, _, _ in self.run.calls))
        reopen = self.run.commands("gh", "issue", "reopen")[0]
        self.assertEqual(reopen[3], "17")
        self.assertIn("39", reopen[-1])
        self.assertNotIn("\n0\n", reopen[-1])
        self.assertTrue(self.sent and self.sent[0][0] == "Zeus")

    def test_setup_failure_does_not_promote_or_revert(self):
        self.run.setup_fails = True
        self.tick()
        self.assertFalse(any("push" in c or "revert" in c for c, _, _ in self.run.calls))
        self.assertNotIn("smoked", self.state)
        self.assertTrue(self.sent and self.sent[0][0] == "Zeus")

    def test_conflict_comment_once_and_idle_smoke(self):
        self.run.conflicts = [pr(9) | {"mergeable": "CONFLICTING"}]
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "comment")), 1)
        self.assertEqual(self.state["conflict_noted"], [9])
        self.run.prs = []
        self.run.head = MERGE
        self.tick()
        self.assertEqual(self.state["smoked"], MERGE)
        self.assertEqual(len(self.run.commands("gh", "pr", "comment")), 1)
        self.assertEqual(len(self.run.commands("timeout", "300")), 2)

    def test_retargets_before_checking_gate(self):
        self.run.prs = [pr() | {"baseRefName": "main"}]
        self.tick()
        edit = self.run.commands("gh", "pr", "edit")[0]
        checks = self.run.commands("gh", "pr", "checks")[0]
        self.assertLess(self.run.calls.index(next(c for c in self.run.calls if c[0] == edit)),
                        self.run.calls.index(next(c for c in self.run.calls if c[0] == checks)))

    def test_failed_gate_on_lead_pr_never_uses_admin(self):
        self.run.prs = [pr(author="lead") | {"comments": [{"author": {"login": "lead"},
                                                               "body": f"LGTM {SHA}"}]}]
        self.run.checks[0]["bucket"] = "fail"
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))


if __name__ == "__main__":
    unittest.main()
