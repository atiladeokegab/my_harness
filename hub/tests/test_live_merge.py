import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from live_merge import is_lgtm, merge_tick, secret_files


SHA = "a" * 40
MERGE = "b" * 40
REVERT = "c" * 40


def pr(number=7, author="worker", body="Closes #17\n\nVerified: make check: 3 passed", sha=SHA):
    return {"number": number, "author": {"login": author}, "body": body,
            "headRefOid": sha, "headRefName": "17-parser", "baseRefName": "integration", "isDraft": False,
            "mergeable": "MERGEABLE", "comments": []}


class FakeRun:
    def __init__(self, prs=None):
        self.prs = prs if prs is not None else [pr()]
        self.calls = []
        self.reviews = [{"state": "APPROVED", "commit_id": SHA}]
        self.checks = [{"name": "freeze-gate", "bucket": "pass", "state": "SUCCESS"}]
        self.issues = {17: "CLOSED"}
        self.issue_bodies = {17: ""}
        self.issue_labels = {}
        self.smoke_code = 0
        self.smoke_output = "ok\n"
        self.setup_fails = False
        self.conflicts = []
        self.head = SHA
        self.project = True  # the worktree has a pyproject.toml, so the smoke runs
        self.diff = ""  # `gh pr diff`; None fails the call
        self.commits = []  # `gh pr view --json commits`; None fails the call
        self.restore_error = None

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
                      "body": self.issue_bodies.get(int(args[3]), ""),
                      "labels": [{"name": n} for n in self.issue_labels.get(int(args[3]), [])]}
        elif args[:3] == ["gh", "pr", "view"]:
            result = {"mergeCommit": {"oid": MERGE}}
        if args[:3] == ["gh", "pr", "view"] and args[-1] == "commits":
            return subprocess.CompletedProcess(args, 1 if self.commits is None else 0,
                                               json.dumps({"commits": self.commits}), "")
        if args[:3] == ["gh", "api", "repos/o/r/git/refs"] and self.restore_error:
            return subprocess.CompletedProcess(args, 1, "", self.restore_error)
        if args[:3] == ["gh", "pr", "diff"]:
            return subprocess.CompletedProcess(args, 1 if self.diff is None else 0, self.diff or "", "")
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


class LgtmTests(unittest.TestCase):
    def test_the_twelve_character_head_from_the_review_request_counts(self):
        """T-506 run 2: hub live asks with a 12-character head and the reviewer answered with it."""
        head = "e9525cd42dc2" + "a" * 28
        self.assertTrue(is_lgtm(f"LGTM {head}", head))
        self.assertTrue(is_lgtm("LGTM e9525cd42dc2\nscope fine", head))
        self.assertFalse(is_lgtm("LGTM e9525cd", head))  # too short to be unambiguous
        self.assertFalse(is_lgtm("LGTM 0123456789ab", head))  # another commit
        self.assertFalse(is_lgtm("LGTM e9525cd42dc2 but fix X", head))
        self.assertFalse(is_lgtm("lgtm e9525cd42dc2", head))


class MergeTickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clone = Path(self.tmp.name)
        self.run = FakeRun()
        self.sent = []
        self.state = {}

    def tick(self, **kw):
        merge_tick("o/r", self.clone, "make smoke", "lead", self.state,
                   self.run, lambda agent, msg: self.sent.append((agent, msg)), **kw)

    def fast(self, path="web/app.py", body="Closes #17\n\nDONE: notes\nVerified: make check: 12 passed",
             files="Context: x\nFiles: docs/, web/", count=None):
        """A lead-account PR (as hub live opens them) with no LGTM."""
        changed = [{"path": path}] if path else []
        self.run.prs = [pr(author="lead", body=body) | {"files": changed,
                                                         "changedFiles": len(changed) if count is None else count}]
        self.run.issue_bodies[17] = files

    def test_fast_lane_merges_without_lgtm_and_records_it(self):
        self.fast()
        self.tick(review_before=["verify/*"])
        merges = self.run.commands("gh", "pr", "merge")
        self.assertEqual(len(merges), 1)
        self.assertIn("--admin", merges[0])
        self.assertEqual(self.state["unreviewed"], [7])
        self.assertEqual(self.state["gated"], [])

    def test_anything_gated_or_unknown_waits_for_lgtm(self):
        cases = {"review_before path": dict(path="verify/rules.py", files="Files: verify/"),
                 "no review_before in hackathon.json": dict(review_before=None),
                 "outside Files:": dict(path="api/routes.py"),
                 "Evidence block, no Verified:": dict(body="Closes #17\n\n## Evidence\nmake check: 12 passed"),
                 "no Files: on the issue": dict(files="Context: x"),
                 "no changed files listed": dict(path=None),
                 "file list cut short": dict(count=101)}
        for name, kw in cases.items():
            with self.subTest(name):
                self.run, self.state = FakeRun(), {}
                review_before = kw.pop("review_before", ["verify/*"])
                self.fast(**kw)
                self.tick(review_before=review_before)
                self.assertFalse(self.run.commands("gh", "pr", "merge"))
                self.assertEqual(self.state["gated"], [7])
                self.run.prs[0]["comments"] = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
                self.tick(review_before=review_before)
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
                self.assertNotIn("unreviewed", self.state)

    def test_changes_after_the_last_push_gates_the_fast_lane_until_a_later_lgtm(self):
        """Dry run 2026-10-12: PR #44 fast-laned 32 s after a `CHANGES:` at its head."""
        ask = {"createdAt": "2026-10-12T12:05:00Z", "body": "CHANGES: handle 413", "author": {"login": "lead"}}
        lgtm = lambda at: {"createdAt": at, "body": f"LGTM {SHA}", "author": {"login": "lead"}}
        self.fast()
        self.tick(review_before=["verify/*"])  # no CHANGES: anywhere, so no per-PR commits fetch
        self.assertFalse(self.run.commands("gh", "pr", "view"))
        self.run, self.state = FakeRun(), {}
        self.fast()
        self.run.prs[0]["comments"] = [ask]
        self.run.commits = [{"committedDate": "2026-10-12T12:00:00Z"}]
        self.tick(review_before=["verify/*"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state["gated"], [7])
        # commits on the list call break GitHub's 500,000-node GraphQL limit: fetched per PR instead
        self.assertNotIn("commits", self.run.commands("gh", "pr", "list")[0][-1].split(","))
        self.assertEqual(self.run.commands("gh", "pr", "view")[0], ["gh", "pr", "view", "7", "-R", "o/r", "--json", "commits"])
        self.run.prs[0]["comments"] = [lgtm("2026-10-12T12:04:00Z"), ask]  # an LGTM before it does not count
        self.tick(review_before=["verify/*"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.prs[0]["comments"] = [ask, lgtm("2026-10-12T12:06:00Z")]
        self.tick(review_before=["verify/*"])
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertNotIn("unreviewed", self.state)
        self.run, self.state = FakeRun(), {}
        self.fast()
        self.run.prs[0]["comments"] = [ask]
        self.run.commits = None  # the commits cannot be read: it stays gated
        self.tick(review_before=["verify/*"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state["gated"], [7])
        self.run.commits = [{"committedDate": "2026-10-12T12:10:00Z"}]  # a push after the ask answers it
        self.tick(review_before=["verify/*"])
        self.assertEqual(self.state["unreviewed"], [7])

    def test_a_pr_without_evidence_never_merges_even_with_lgtm(self):
        lgtm = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
        self.run.prs = [pr(author="lead", body="Closes #17\n\nDONE: notes") | {"comments": lgtm}]
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.prs[0]["body"] += "\n\n## Evidence\nmake check: 12 passed"
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_docs_readme_and_media_only_merge_on_evidence_alone(self):
        """Factory rule F2, even with no review_before in hackathon.json (everything else waits)."""
        for paths, merged in ((["docs/guide.md", "README.md", "web/README", "shots/home.png"], True),
                              (["docs/guide.md", "web/app.py"], False), (["AGENTS.md"], False)):
            with self.subTest(paths):
                self.run, self.state = FakeRun(), {}
                self.run.prs = [pr(author="lead") | {"files": [{"path": p} for p in paths], "changedFiles": len(paths)}]
                self.tick(review_before=None)
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), int(merged))
                self.assertEqual(self.state.get("unreviewed", []), [7] if merged else [])

    def test_with_a_hackathon_config_docs_still_obey_review_before_and_files(self):
        """Hermes review of 4ac34c0: docs_only must not bypass review_before or the issue's Files:."""
        for path in ("docs/CONTRACT.md", "README.md"):  # gated by review_before; outside Files: docs/
            with self.subTest(path):
                self.run, self.state = FakeRun(), {}
                self.fast(path=path, files="Files: docs/")
                self.tick(review_before=["docs/CONTRACT.md"])
                self.assertFalse(self.run.commands("gh", "pr", "merge"))
                self.assertEqual(self.state["gated"], [7])
        self.run, self.state = FakeRun(), {}
        self.fast(path="docs/guide.md", files="Files: docs/")
        self.tick(review_before=["docs/CONTRACT.md"])  # ungated and in its area: the fast lane merges it
        self.assertEqual(self.state["unreviewed"], [7])

    def test_an_lgtm_from_the_builder_never_counts(self):
        """Hermes's LGTMs come from the lead account: on a PR Hermes built, that is the builder's."""
        for agent, merged in (("hermes", 0), ("prometheus", 1)):
            with self.subTest(agent):
                self.run, self.state = FakeRun(), {}
                self.run.issue_labels[17] = ["task", f"agent:{agent}"]
                self.run.prs = [pr(author="lead") | {"comments": [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]}]
                self.tick()
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), merged)
                self.assertEqual(self.state["gated"], [] if merged else [7])
        self.run, self.state = FakeRun(), {}
        self.run.reviews = [{"state": "APPROVED", "commit_id": SHA, "user": {"login": "worker"}}]
        self.tick()  # a teammate's PR approved by its own author
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.reviews[0]["user"]["login"] = "lead"
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_a_failed_image_check_holds_but_absent_or_pending_does_not(self):
        gate = {"name": "freeze-gate", "bucket": "pass", "state": "SUCCESS"}
        for image, merged in (("fail", 0), ("pending", 1), (None, 1), ("pass", 1)):
            with self.subTest(image):
                self.run, self.state = FakeRun(), {}
                self.run.checks = [gate] + ([{"name": "image", "bucket": image, "state": image}] if image else [])
                self.tick()
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), merged)

    def test_red_smoke_reverts_a_fast_lane_merge(self):
        self.fast()
        self.run.smoke_code = 1
        self.run.smoke_output = "collected 41 items\nFAILED tests/test_web.py\n1 failed, 40 passed\n\n"
        self.tick(review_before=["verify/*"])
        self.assertEqual(self.state["merge_events"][-1]["why"], "1 failed, 40 passed")  # hub live notes it on the task
        self.assertEqual(self.run.commands("gh", "issue", "reopen")[0][3], "17")
        self.assertEqual(self.state["unreviewed"], [])  # a reverted PR is not in Hermes' digest (#54, dry run 2026-10-12)
        self.assertEqual([(e["pr"], e["event"]) for e in self.state["merge_events"]],
                         [(7, "merged"), (7, "reverted")])  # the dashboard's merged-not-reverted source

    def test_secret_in_added_lines_gates_the_fast_lane_and_tells_zeus_once(self):
        self.fast()
        self.run.diff = ("diff --git a/docs/notes.md b/docs/notes.md\n--- a/docs/notes.md\n+++ b/docs/notes.md\n"
                         "@@ -0,0 +1,2 @@\n+aws_key = AKIAIOSFODNN7EXAMPLE\n+db: postgres://app:hunter2@db:5432/x\n")
        self.tick(review_before=["verify/*"])
        self.tick(review_before=["verify/*"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state["gated"], [7])
        self.assertEqual(self.sent, [("Zeus", "SECRET? PR #7 docs/notes.md: gated until a reviewer reads it; "
                                              "if it is real, revoke it at its provider")])
        self.run.prs[0]["comments"] = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
        self.tick(review_before=["verify/*"])  # a reviewer's LGTM still merges it
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_clean_diff_still_fast_lanes_and_an_unread_diff_is_gated(self):
        self.fast()
        self.run.diff = "+++ b/docs/notes.md\n+just notes, see https://github.com/actions/checkout@v4\n-old AKIAIOSFODNN7EXAMPLE\n"
        self.tick(review_before=["verify/*"])
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.run, self.state, self.sent = FakeRun(), {}, []
        self.fast()
        self.run.diff = None
        self.tick(review_before=["verify/*"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.sent, [])

    def test_secret_patterns(self):
        hits = ["sk-ant-api03-x", "sk_live_x", "AKIAIOSFODNN7EXAMPLE", "ghp_x", "github_pat_x", "AIzaSyx",
                "xoxb-1", "xoxp-1", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----",
                "https://user:pass@host/x"]
        misses = ["AKIA-not-a-key", "https://github.com/actions/checkout@v4", "http://localhost:8080/x@y",
                  "ghp is a word", "the sk-live docs"]
        for text in hits:
            with self.subTest(hit=text):
                self.assertEqual(secret_files(f"+++ b/a.py\n+{text}\n"), ["a.py"])
        for text in misses:
            with self.subTest(miss=text):
                self.assertEqual(secret_files(f"+++ b/a.py\n+{text}\n"), [])

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
        self.assertEqual(self.state["promoted"], SHA)
        self.assertEqual(self.state["first_merge"], SHA)
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
        self.assertIn(["gh", "api", "repos/o/r/git/refs", "-f", "ref=refs/heads/17-parser",
                       "-f", f"sha={SHA}"], [c for c, _, _ in self.run.calls])
        reopen = self.run.commands("gh", "issue", "reopen")[0]
        self.assertEqual(reopen[3], "17")
        self.assertIn("39", reopen[-1])
        self.assertNotIn("\n0\n", reopen[-1])
        self.assertTrue(self.sent and self.sent[0][0] == "Zeus")
        self.assertNotIn("promoted", self.state)

    def test_red_revert_accepts_a_branch_that_already_exists(self):
        self.run.smoke_code = 1
        self.run.restore_error = "gh: Reference already exists (HTTP 422)"
        self.tick()
        reopen = self.run.commands("gh", "issue", "reopen")[0]
        self.assertIn("Fix it on the same branch", reopen[-1])
        self.assertFalse(any("restore failed" in text for _, text in self.sent))

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

    def test_github_smoke_check_must_pass_before_the_merge(self):
        for bucket in ("fail", "pending"):
            with self.subTest(bucket):
                self.run, self.state = FakeRun(), {"smoked": SHA}  # integration was smoked already
                self.run.checks.append({"name": "smoke", "bucket": bucket, "state": bucket.upper()})
                self.tick()
                self.assertFalse(self.run.commands("gh", "pr", "merge"))
                self.assertFalse(self.run.commands("timeout", "300"))
        self.run.checks[-1]["bucket"] = "pass"
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual(self.run.commands("timeout", "300")[0][-1], "make smoke")  # the local smoke still decides main

    def test_no_smoke_check_falls_back_to_the_local_smoke(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual([c[-1] for c in self.run.commands("timeout", "300")], ["make smoke"])
        self.assertIn("live merge: #7 has no smoke check (Actions not reporting); the local smoke alone decides",
                      out.getvalue())


if __name__ == "__main__":
    unittest.main()
