import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _k in [k for k in os.environ if k.startswith("HUB_")]:  # HUB_LEAD, HUB_REVIEWER: test the default roster
    del os.environ[_k]
from live_merge import DETACHED_SH, docs_only, fast_lane, is_lgtm, merge_tick, secret_files
import gh_sync
import spec
from tests.test_spec import Fixture, git  # hub spec's Linkly fixture


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
        self.close_fail = set()
        self.issue_bodies = {17: ""}
        self.issue_labels = {}
        self.smoke_code = 0
        self.smoke_output = "ok\n"
        self.setup_fails = False
        self.push_fails = False
        self.conflicts = []
        self.head = SHA
        self.project = True  # the worktree has a pyproject.toml, so the smoke runs
        self.diff = ""  # `gh pr diff`; None fails the call
        self.commits = []  # `gh pr view --json commits`; None fails the call
        self.restore_error = None
        self.remote_heads = ""  # `git ls-remote --heads origin`
        self.in_integration = False  # `git merge-base --is-ancestor <change head> origin/integration`
        self.acceptance_red = ()  # acceptance test paths that fail on the change head
        self.gate_exit = "0"  # how the detached change gate ends at once; None leaves it running
        self.spawned = []  # argv of each detached gate: sh -c DETACHED_SH name clone sha command exit_file cap

        self.raw_files = {}

    def spawn(self, argv, out):
        self.spawned.append(argv)
        if self.gate_exit is not None:
            Path(argv[7]).write_text(f"{self.gate_exit}\n")

    def __call__(self, args, cwd=None, timeout=60):
        self.calls.append((args, cwd, timeout))
        result = None
        if args[:2] == ["gh", "api"] and any("/contents/" in a for a in args):
            url = next(a for a in args if "/contents/" in a)
            path_part, _, ref = url.partition("/contents/")[2].partition("?ref=")
            if (path_part, ref) in self.raw_files:
                return subprocess.CompletedProcess(args, 0, self.raw_files[(path_part, ref)], "")
            return subprocess.CompletedProcess(args, 1, "", "HTTP 404: Not Found")
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
        elif args[:3] == ["gh", "issue", "close"]:
            number = int(args[3])
            if number in self.close_fail:
                return subprocess.CompletedProcess(args, 1, "", "temporary close failure")
            self.issues[number] = "CLOSED"
        elif args[:3] == ["gh", "pr", "view"]:
            result = {"mergeCommit": {"oid": MERGE}}
        if args[:3] == ["gh", "pr", "view"] and args[-1] == "commits":
            return subprocess.CompletedProcess(args, 1 if self.commits is None else 0,
                                               json.dumps({"commits": self.commits}), "")
        if args[:3] == ["gh", "api", "repos/o/r/git/refs"] and self.restore_error:
            return subprocess.CompletedProcess(args, 1, "", self.restore_error)
        if args[:3] == ["gh", "pr", "diff"]:
            return subprocess.CompletedProcess(args, 1 if self.diff is None else 0, self.diff or "", "")
        if "ls-remote" in args:
            return subprocess.CompletedProcess(args, 0, self.remote_heads, "")
        if args[:1] == ["env"]:
            return subprocess.CompletedProcess(args, int(any(t in args for t in self.acceptance_red)), "", "")
        if "--is-ancestor" in args:
            return subprocess.CompletedProcess(args, 0 if self.in_integration else 1, "", "")
        if "push" in args and "--delete" in args:
            if self.push_fails:
                return subprocess.CompletedProcess(args, 1, "", "push failed")
            branch = args[-1]
            self.remote_heads = "\n".join(
                line for line in self.remote_heads.splitlines() if not line.endswith(f"\trefs/heads/{branch}")
            ) + ("\n" if self.remote_heads else "")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:1] == ["timeout"] and args[2:3] == ["sh"]:  # the smoke, or make check on a change head
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
        merge_tick("o/r", self.clone, "make smoke", "lead", self.state, self.run,
                   lambda agent, msg: self.sent.append((agent, msg)), gate_dir=self.clone, spawn=self.run.spawn, **kw)

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
        self.assertEqual(len([a for a in self.run.commands("gh", "pr", "view") if a[-1] == "commits"]), 1)  # the squash body's
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

    def test_a_pr_with_undeclared_dependency_never_merges_even_with_lgtm(self):
        lgtm = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
        self.run.prs = [pr(author="lead", body="Closes #17\n\n## Evidence\nmake check: 12 passed") | {
            "files": [{"path": "pyproject.toml"}], "changedFiles": 1, "comments": lgtm, "baseRefName": "main"}]
        self.run.raw_files[("docs/stack.md", SHA)] = "| Lib | requests | Decided | http |\n"
        self.run.raw_files[("docs/stack.md", "main")] = "| Lib | requests | Decided | http |\n"
        self.run.raw_files[("pyproject.toml", "main")] = '[project]\ndependencies = ["requests"]\n'
        self.run.raw_files[("pyproject.toml", SHA)] = '[project]\ndependencies = ["requests", "redis"]\n'
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run.raw_files[("docs/stack.md", SHA)] = "| Lib | requests | Decided | http |\n| Lib | redis | Decided | cache |\n"
        self.tick()
        # Even if head has the row, base does not, so it never merges
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        # When declared in docs/stack.md at base (main), it merges
        self.run.raw_files[("docs/stack.md", "main")] = "| Lib | requests | Decided | http |\n| Lib | redis | Decided | cache |\n"
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_stack_table_path_is_never_docs_only_or_fast_lane(self):
        """Hermes T-583 review: docs_only and fast_lane must never bypass LGTM for the stack table."""
        stack_pr = pr(author="lead", body="Closes #17\n\nVerified: manual") | {
            "files": [{"path": "docs/stack.md"}], "changedFiles": 1}
        self.assertFalse(docs_only(stack_pr))
        self.assertFalse(fast_lane(stack_pr, "Files: docs/", review_before=[]))
        # Custom stack path
        custom_pr = pr(author="lead", body="Closes #17\n\nVerified: manual") | {
            "files": [{"path": "arch/stack.md"}], "changedFiles": 1}
        self.assertFalse(docs_only(custom_pr, stack="arch/stack.md"))
        self.assertFalse(fast_lane(custom_pr, "Files: arch/", review_before=[], stack="arch/stack.md"))
        # Hermes follow-up nit: normpath handles leading ./
        self.assertFalse(docs_only(stack_pr, stack="./docs/stack.md"))
        self.assertFalse(fast_lane(stack_pr, "Files: docs/", review_before=[], stack="./docs/stack.md"))
        dot_pr = pr(author="lead", body="Closes #17\n\nVerified: manual") | {
            "files": [{"path": "./docs/stack.md"}], "changedFiles": 1}
        self.assertFalse(docs_only(dot_pr, stack="docs/stack.md"))
        self.assertFalse(fast_lane(dot_pr, "Files: docs/", review_before=[], stack="docs/stack.md"))
        # In merge_tick: a stack table edit without LGTM is never fast-merged
        self.run = FakeRun()
        self.run.prs = [stack_pr]
        self.tick(review_before=None)
        self.assertFalse(self.run.commands("gh", "pr", "merge"))


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

    def test_trial_builder_skips_fast_lane(self):
        """Living spec §4: a trial builder's PR never takes fast_lane or docs_only; always waits for LGTM."""
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "docs/guide.md"}], "changedFiles": 1}]
        self.tick(review_before=None, trial_builders=["iris"])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state["gated"], [7])

    def test_trusted_builder_keeps_fast_lane(self):
        """Living spec §4: a trusted builder's docs-only PR still merges on evidence alone."""
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:prometheus"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "docs/guide.md"}], "changedFiles": 1}]
        self.tick(review_before=None, trial_builders=["iris"])
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual(self.state.get("unreviewed", []), [7])

    def test_board_approval_allows_trial_builder_merge(self):
        """Addendum 2 M4: live_merge counts board approvals for trial/trusted builders."""
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "src/app.py"}], "changedFiles": 1}]
        approvals = {(7, SHA): "Hermes"}
        self.tick(review_before=None, trial_builders=["iris"], approvals=approvals)
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_board_approval_from_builder_or_trial_agent_ignored(self):
        """Living spec §4: approvals from the builder or an agent lacking review capability do not count."""
        # Self-approval
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "src/app.py"}], "changedFiles": 1}]
        self.tick(review_before=None, trial_builders=["iris"], approvals={(7, SHA): "iris"})
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        # Approval from another trial agent
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "src/app.py"}], "changedFiles": 1}]
        self.tick(review_before=None, trial_builders=["iris", "ghost"], approvals={(7, SHA): "ghost"})
        self.assertFalse(self.run.commands("gh", "pr", "merge"))

    def test_board_approval_held_by_lead_changes_note(self):
        """Hermes review T-577: board-approval mode still obeys lead CHANGES: holds."""
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        ask = {"createdAt": "2026-10-12T12:05:00Z", "body": "CHANGES: fix edge case", "author": {"login": "lead"}}
        self.run.prs = [pr(author="lead") | {
            "files": [{"path": "src/app.py"}],
            "changedFiles": 1,
            "comments": [ask],
        }]
        self.run.commits = [{"committedDate": "2026-10-12T12:00:00Z"}]
        approvals = {(7, SHA): "Hermes"}
        self.tick(review_before=None, trial_builders=["iris"], approvals=approvals)
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state.get("gated"), [7])

    def test_board_approval_unpinned_pr_number_fallback_dropped(self):
        """T-577: board approval requires exact (pr, sha); no fallback to unpinned pr number."""
        self.run = FakeRun()
        self.run.issue_labels[17] = ["task", "agent:iris"]
        self.run.prs = [pr(author="lead") | {"files": [{"path": "src/app.py"}], "changedFiles": 1}]
        approvals = {7: "Hermes"}  # Unpinned int key should not be honored
        self.tick(review_before=None, trial_builders=["iris"], approvals=approvals)
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.state.get("gated"), [7])

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
        self.assertFalse(self.run.commands("timeout", "1800"))
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
        self.assertEqual(len(self.run.commands("timeout", "1800")), 2)

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
                self.assertFalse(self.run.commands("timeout", "1800"))
        self.run.checks[-1]["bucket"] = "pass"
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual(self.run.commands("timeout", "1800")[0][-1], "make smoke")  # the local smoke still decides main

    def test_no_smoke_check_falls_back_to_the_local_smoke(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual([c[-1] for c in self.run.commands("timeout", "1800")], ["make smoke"])
        self.assertIn("live merge: #7 has no smoke check (Actions not reporting); the local smoke alone decides",
                      out.getvalue())


LINES = {"A-1.1": 2, "A-1.2": 1}  # the current PRD of a project with a spec (T-517)


class SpecMergeTests(unittest.TestCase):
    setUp, tick = MergeTickTests.setUp, MergeTickTests.tick

    def spec_pr(self, body="Closes #17\n\nVerified: make check: 3 passed", path="app/links.py", **kw):
        files = [{"path": p} for p in ([path] if isinstance(path, str) else path)]
        return pr(body=body, **kw) | {"files": files, "changedFiles": len(files)}

    def test_a_pr_needs_req_trailers_citing_current_lines_in_body_or_commits(self):
        cases = {"no Req:": ("", [], False),
                 "an old version": ("\nReq: A-1.1@1", [], False),
                 "a line not in the PRD": ("\nReq: A-9.1@1", [], False),
                 "one current, one old": ("\nReq: A-1.1@2, A-1.2@0", [], False),
                 "current, in the body": ("\nReq: A-1.1@2\nTask: T-12", [], True),
                 "current, in a commit": ("", [{"messageHeadline": "stats", "messageBody": "Req: A-1.1@2 A-1.2@1"}], True)}
        for name, (extra, commits, merges) in cases.items():
            with self.subTest(name):
                self.run, self.state = FakeRun([self.spec_pr("Closes #17\n\nVerified: make check: 3 passed" + extra)]), {}
                self.run.commits = commits
                self.tick(req_lines=LINES, change_tasks=[])
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), int(merges))
                self.assertEqual(self.state["gated"], [])  # hub live holds it with a comment, not a review wait
        self.run, self.state = FakeRun([self.spec_pr()]), {}
        self.run.commits = None  # the commits cannot be read: not merged
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))

    def test_req_ci_fix_passes_only_for_a_task_tagged_ci_fix(self):
        """T-520 (3): a CI fix implements no PRD line; `Req: ci-fix` is its trailer, and only its."""
        for closes, body, tasks, merges in ((17, "Req: ci-fix\nTask: T-031", {"T-031": 17}, True),
                                            (8, "Req: ci-fix\nTask: T-031", {"T-031": 17}, False),
                                            (17, "Req: ci-fix\nTask: T-031", {}, False),
                                            (17, "Req: ci-fix\nTask: T-032", {"T-031": 17}, False),
                                            (17, "Req: ci-fix\nTask: T-032\nTask: T-031", {"T-031": 17}, False),
                                            (17, "Req: ci-fix", {"T-031": 17}, False)):
            with self.subTest(closes=closes, body=body, tasks=tasks):
                self.run, self.state = FakeRun([self.spec_pr(f"Closes #{closes}\n\n{body}\nVerified: make check: 3 passed")]), {}
                self.run.issues[8] = "CLOSED"
                self.tick(req_lines=LINES, change_tasks=[], ci_fix_tasks=tasks)
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), int(merges))

    def test_without_a_spec_no_trailer_is_needed(self):
        self.run.prs = [self.spec_pr()]
        self.tick()
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)

    def test_a_pr_touching_spec_or_acceptance_tests_never_merges_here(self):
        """Held for Zeus: not the fast lane, not an LGTM, and an unknown file list counts as touching them."""
        lgtm = [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]
        body = "Closes #17\n\nReq: A-1.1@2\nVerified: make check: 3 passed"
        for paths in (["tests/acceptance/test_A_1_1.py"], ["app/x.py", "spec/requirements.json"], ["docs/spec.md"]):
            with self.subTest(paths):
                self.run, self.state = FakeRun([self.spec_pr(body, paths, author="lead") | {"comments": lgtm}]), {}
                self.tick(req_lines=LINES, change_tasks=[], review_before=None)
                self.assertEqual(len(self.run.commands("gh", "pr", "merge")), int(paths == ["docs/spec.md"]))
        self.run, self.state = FakeRun([self.spec_pr(body, author="lead") | {"comments": lgtm, "changedFiles": 101}]), {}
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))

    def test_the_squash_keeps_githubs_default_body_and_adds_the_req_and_task_trailers(self):
        """For spec.py's history() and the board task's merge_sha (T-521 addition; Hermes: keep GitHub's body)."""
        body = "Closes #17\n\nReq: A-1.1@2\nTask: T-12\nVerified: make check: 3 passed"
        self.run.prs = [self.spec_pr(body) | {"baseRefName": "change/C-001"}]
        self.run.checks = []
        self.run.commits = [{"messageHeadline": "stats", "messageBody": "count by day\n\nCo-Authored-By: C <c@x>"},
                            {"messageHeadline": "tests", "messageBody": "Req: A-1.2@1\nCo-Authored-By: C <c@x>"}]
        self.tick(req_lines=LINES, change_tasks=[])
        [merge] = self.run.commands("gh", "pr", "merge")
        self.assertEqual(merge[merge.index("--body") + 1],  # GitHub's list of the commits, then one trailer block
                         "* stats\n\ncount by day\n\n* tests\n\nReq: A-1.1@2\nTask: T-12\nReq: A-1.2@1\nCo-Authored-By: C <c@x>")
        self.assertEqual(self.state["merge_events"][0] | {"at": None},
                         {"at": None, "pr": 7, "issue": 17, "event": "merged", "sha": MERGE, "task": "T-12",
                          "base": "change/C-001"})
        self.run, self.state = FakeRun([self.spec_pr("Closes #17\n\nVerified: make check: 3 passed")]), {}
        self.run.commits = [{"messageHeadline": "stats", "messageBody": "count by day\n\nReq: A-1.1@2\nTask: T-12"}]
        self.tick(req_lines=LINES, change_tasks=[])  # one commit: GitHub's body is its body; trailers from it kept
        [merge] = self.run.commands("gh", "pr", "merge")
        self.assertEqual(merge[merge.index("--body") + 1], "count by day\n\nReq: A-1.1@2\nTask: T-12")
        self.run, self.state = FakeRun([self.spec_pr()]), {}
        self.run.commits = None  # the commits cannot be read: no merge this pass, rather than lose the trailers
        self.tick()
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.run, self.state = FakeRun(), {}
        self.tick()  # no trailers: GitHub's own squash message
        self.assertNotIn("--body", self.run.commands("gh", "pr", "merge")[0])
        self.assertIsNone(self.state["merge_events"][0]["task"])

    def test_a_task_pr_into_a_change_branch_merges_there_without_the_integration_smoke(self):
        self.run.prs = [self.spec_pr("Closes #17\n\nReq: A-1.1@2\nVerified: make check: 3 passed")
                        | {"baseRefName": "change/C-001"}]
        self.run.checks = []  # CI runs on PRs into integration only
        self.tick(req_lines=LINES, change_tasks=["T-12"])
        [merge] = self.run.commands("gh", "pr", "merge")
        self.assertEqual(merge[:3], ["gh", "pr", "merge"])
        self.assertFalse(self.run.commands("gh", "pr", "edit"))  # not retargeted to integration
        self.assertFalse(self.run.commands("timeout", "1800"))
        self.assertFalse([a for a in self.run.commands("git") if "push" in a])
        self.assertEqual(self.state["merge_events"][0]["event"], "merged")
        self.assertNotIn("first_merge", self.state)

    def gate(self, sha):
        return self.state["change_gates"]["change/C-001"] if sha is None else next(
            g for g in self.state["change_gates"].values() if g["sha"] == sha)

    def finish(self, sha, code):
        """The detached gate on sha ends with code, as DETACHED_SH writes it."""
        (self.clone / f"change-gate-{sha[:12]}.exit").write_text(f"{code}\n")

    def test_a_change_branch_goes_into_integration_once_its_tasks_are_done_and_its_suite_is_green(self):
        change = "d" * 40
        self.run.prs, self.run.remote_heads = [], f"{SHA}\trefs/heads/integration\n{change}\trefs/heads/change/C-001\n"
        self.tick(req_lines=LINES, change_tasks=["T-12"])  # a generated task is still unfinished
        self.run.prs = [pr(number=9) | {"baseRefName": "change/C-001", "isDraft": True}]
        self.tick(req_lines=LINES, change_tasks=[])  # a task PR into it is still open
        self.assertFalse(self.run.spawned)
        self.run.prs, self.run.gate_exit = [], None
        self.tick(req_lines=LINES, change_tasks=[])
        self.tick(req_lines=LINES, change_tasks=[])  # T-521: the pass never waits for the gate, nor starts it twice
        self.assertEqual(len(self.run.spawned), 1)
        self.assertEqual(self.run.spawned[0][:6], ["sh", "-c", DETACHED_SH, "change-gate", str(self.clone), change])
        self.assertEqual(set(self.gate(change)), {"sha", "started", "cap", "steps"})  # running: no exit yet
        self.assertFalse([a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a])
        self.assertFalse(self.sent)
        self.finish(change, 1)  # its first step, the smoke, was red
        self.tick(req_lines=LINES, change_tasks=[])
        self.tick(req_lines=LINES, change_tasks=[])  # the same red head is not re-run, nor told twice
        self.assertEqual(len(self.run.spawned), 1)
        self.assertEqual([m for _, m in self.sent], ["change/C-001 is red at dddddddddddd (smoke): not merged into integration"])
        self.assertEqual((self.gate(change)["exit"], bool(self.gate(change)["finished"])), ("1", True))
        self.assertFalse([a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a])
        self.run.calls, self.sent, self.run.gate_exit = [], [], "0"
        self.run.remote_heads = f"{SHA}\trefs/heads/integration\n{'e' * 40}\trefs/heads/change/C-001\n"
        self.run.head = "f" * 40  # integration as it reads after the merge push
        self.tick(req_lines=LINES, change_tasks=[])  # starts the gate on the new head
        self.assertFalse([a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a])
        self.run.calls, self.state["smoked"] = [], None
        self.tick(req_lines=LINES, change_tasks=[])  # a later pass reads it green and merges
        merges = [a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a]
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0][-1], "e" * 40)
        pushes = [a[-1] for a in self.run.commands("git") if "push" in a]
        self.assertEqual(pushes[:2], ["HEAD:refs/heads/integration", "change/C-001"])  # then deleted
        self.assertEqual(pushes[2], f"{'f' * 40}:refs/heads/main")  # the ordinary smoke promotes integration
        self.assertTrue(any("change/C-001" in m and "merged into integration" in m for _, m in self.sent))

    def test_landed_change_closes_generated_issues_once(self):
        change = "d" * 40
        self.run.prs, self.run.remote_heads = [], f"{change}\trefs/heads/change/C-001\n"
        self.run.issues.update({7: "OPEN", 8: "OPEN"})
        options = {"req_lines": LINES, "change_tasks": [], "change_issues": {"change/C-001": [7, 8]}}
        self.tick(**options)  # start the gate
        self.tick(**options)  # land the change and close its issues
        closes = self.run.commands("gh", "issue", "close")
        self.assertEqual([int(command[3]) for command in closes], [7, 8])
        self.assertEqual({command[-1] for command in closes}, {"Landed with change/C-001 at dddddddddddd"})
        self.assertEqual(self.state.get("change_issue_pending"), {})
        self.tick(**options)
        self.assertEqual(self.run.commands("gh", "issue", "close"), closes)

    def test_a_failed_issue_close_is_retried_next_pass(self):
        change = "d" * 40
        self.run.prs, self.run.remote_heads = [], f"{change}\trefs/heads/change/C-001\n"
        self.run.issues.update({7: "OPEN", 8: "OPEN"})
        self.run.close_fail.add(8)
        options = {"req_lines": LINES, "change_tasks": [], "change_issues": {"change/C-001": [7, 8]}}
        self.tick(**options)
        self.tick(**options)
        self.assertEqual([int(command[3]) for command in self.run.commands("gh", "issue", "close")], [7, 8])
        self.run.close_fail.clear()
        self.tick(**options)
        self.assertEqual([int(command[3]) for command in self.run.commands("gh", "issue", "close")], [7, 8, 8])
        self.tick(**options)
        self.assertEqual(len(self.run.commands("gh", "issue", "close")), 3)
        self.assertEqual(self.state["change_issue_pending"], {})

    def test_a_landed_change_without_its_issues_closes_nothing(self):
        for name, extra in (("no change_issues: hub live's default", {}),
                            ("only another change's issues", {"change_issues": {"change/C-002": [7]}})):
            with self.subTest(name):
                self.run, self.state = FakeRun([]), {}
                self.run.remote_heads = f"{'d' * 40}\trefs/heads/change/C-001\n"
                self.run.issues.update({7: "OPEN"})
                self.tick(req_lines=LINES, change_tasks=[], **extra)
                self.tick(req_lines=LINES, change_tasks=[], **extra)  # lands change/C-001
                self.assertTrue([a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a])
                self.assertFalse(self.run.commands("gh", "issue", "close"))
                self.assertFalse(self.state.get("change_issue_pending"))

    def test_a_change_branch_needs_every_current_acceptance_check_green_not_just_the_smoke(self):
        """Hermes on T-517: the smoke alone does not prove the rebuild matches PRD v+1."""
        checks = [["uv", "run", "pytest", "-q", "tests/acceptance/test_A_1_1.py"],
                  ["uv", "run", "pytest", "-q", "tests/acceptance/test_A_1_2.py"]]
        self.run.prs, self.run.remote_heads = [], f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.run.gate_exit = 2  # the second acceptance check is red
        for _ in range(3):
            self.tick(req_lines=LINES, change_tasks=[], acceptance=checks, acceptance_timeout=120)
        self.assertFalse([a for a in self.run.commands("git") if "--no-ff" in a])
        told = [m for _, m in self.sent if "change/C-001 is red" in m]
        self.assertEqual(len(told), 1, self.sent)
        self.assertIn("(uv run pytest -q tests/acceptance/test_A_1_2.py)", told[0])
        self.assertEqual(len(self.run.spawned), 1)  # once per head
        self.assertEqual(self.run.spawned[0][6].splitlines(), [
            "env -u HUB_DIR -u HUB_AGENT timeout 120 uv run pytest -q tests/acceptance/test_A_1_1.py || exit 1",
            "env -u HUB_DIR -u HUB_AGENT timeout 120 uv run pytest -q tests/acceptance/test_A_1_2.py || exit 2",
            "timeout 1800 sh -c 'make smoke' || exit 3",
            "timeout 1800 sh -c 'if make -n check >/dev/null 2>&1; then make check; fi' || exit 4"])
        self.run.calls, self.sent, self.run.gate_exit = [], [], 0
        self.run.remote_heads = f"{'e' * 40}\trefs/heads/change/C-001\n"
        self.tick(req_lines=LINES, change_tasks=[], acceptance=checks, acceptance_timeout=120)
        self.tick(req_lines=LINES, change_tasks=[], acceptance=checks, acceptance_timeout=120)
        self.assertEqual(len([a for a in self.run.commands("git") if "--no-ff" in a]), 1)

    def test_a_slow_but_green_change_suite_under_change_timeout_merges(self):
        """Hermes on 460b0db: the hub suite alone takes ~264 s, so 300 s would hold a green change forever."""
        self.run.prs, self.run.remote_heads = [], f"{'d' * 40}\trefs/heads/change/C-001\n"
        checks = [["uv", "run", "pytest", "-q", "tests/acceptance/test_A_1_1.py"]]
        for _ in range(2):
            self.tick(req_lines=LINES, change_tasks=[], acceptance=checks, acceptance_timeout=120, change_timeout=1200)
        command, _, cap = self.run.spawned[0][6:]
        self.assertIn("timeout 1200 sh -c 'make smoke'", command)
        self.assertIn("timeout 1200 sh -c 'if make -n check", command)
        self.assertEqual(cap, str(120 + 2 * 1200 + 60))  # the whole gate's cap: every step's, plus a minute
        self.assertEqual(len([a for a in self.run.commands("git") if "--no-ff" in a]), 1)
        self.assertEqual({tuple(a) for a in self.run.commands("timeout")}, {("timeout", "1200", "sh", "-c", "make smoke")})
        self.assertFalse(self.run.commands("env"))  # no gate step ran inline: only integration's own smoke

    def test_a_red_make_check_also_keeps_a_change_branch_out(self):
        self.run.prs, self.run.remote_heads, self.run.gate_exit = [], f"{'d' * 40}\trefs/heads/change/C-001\n", 2
        self.tick(req_lines=LINES, change_tasks=[])
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse([a for a in self.run.commands("git") if "--no-ff" in a])
        self.assertTrue(any("(make check)" in m for _, m in self.sent), self.sent)

    def test_one_gate_runs_at_a_time(self):
        self.run.prs, self.run.gate_exit = [], None
        self.run.remote_heads = f"{'d' * 40}\trefs/heads/change/C-001\n{'e' * 40}\trefs/heads/change/C-002\n"
        self.tick(req_lines=LINES, change_tasks=[])
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual([a[5] for a in self.run.spawned], ["d" * 40])
        self.finish("d" * 40, 1)
        self.tick(req_lines=LINES, change_tasks=[])  # C-001 is read red, then C-002 starts
        self.assertEqual([a[5] for a in self.run.spawned], ["d" * 40, "e" * 40])

    def test_a_gate_lost_to_a_crash_or_reboot_is_not_running_forever(self):
        """Like deploy's: past its cap with no exit file, the gate is lost and starts again."""
        self.run.prs, self.run.gate_exit = [], None
        self.run.remote_heads = f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.tick(req_lines=LINES, change_tasks=[])
        self.gate("d" * 40)["started"] = (datetime.now(timezone.utc) - timedelta(seconds=3660 + 299)).isoformat()
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(len(self.run.spawned), 1)  # within its cap and five minutes: still running
        self.gate("d" * 40)["started"] = (datetime.now(timezone.utc) - timedelta(seconds=3660 + 301)).isoformat()
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(len(self.run.spawned), 2)
        self.assertIn(["git", "-C", str(self.clone), "worktree", "prune"], self.run.commands("git"))  # its worktree
        self.assertNotIn("exit", self.gate("d" * 40))  # the new gate, running
        self.assertFalse(self.sent)  # lost is not red: nothing for Zeus

    def test_the_real_gate_runs_detached_in_a_worktree_and_a_later_pass_merges_it(self):
        """DETACHED_SH and the step command for real, on a real origin; only gh is faked."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        self.enterContext(mock.patch.dict(os.environ, env, clear=True))
        root = Path(self.tmp.name)
        origin, clone, gates = root / "origin.git", root / "clone", root / "gates"
        gates.mkdir()
        sh = lambda *a, cwd=root: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
        sh("git", "init", "-q", "--bare", "-b", "integration", str(origin))
        sh("git", "clone", "-q", str(origin), str(clone))
        sh("git", "config", "user.email", "t@t", cwd=clone)
        sh("git", "config", "user.name", "t", cwd=clone)
        sh("git", "commit", "-q", "--allow-empty", "-m", "base", cwd=clone)
        sh("git", "push", "-q", "origin", "HEAD:integration", cwd=clone)
        (clone / "app.txt").write_text("v2\n")
        sh("git", "add", "app.txt", cwd=clone)
        sh("git", "commit", "-q", "-m", "C-001", cwd=clone)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/change/C-001", cwd=clone)
        run = lambda args, cwd=None, timeout=60: (
            subprocess.CompletedProcess(args, 0, "[]", "") if args[0] == "gh"
            else subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout))
        def tick():
            merge_tick("o/r", clone, "true", "lead", self.state, run, lambda a, m: self.sent.append(m),
                       req_lines=LINES, change_tasks=[], acceptance=[["sh", "-c", "test -f ok.txt"]],
                       acceptance_timeout=30, change_timeout=30, gate_dir=gates)
        def wait():
            for _ in range(200):
                if not [g for g in self.state["change_gates"].values() if "exit" not in g]:
                    return
                time.sleep(0.1)
                tick()
            self.fail("the gate never finished")
        tick()
        self.assertNotIn("exit", self.state["change_gates"]["change/C-001"])  # the pass did not wait
        wait()
        self.assertTrue((gates / ".tick-now").is_file())
        self.assertEqual(self.sent, [f"change/C-001 is red at {sh('git', 'rev-parse', 'HEAD', cwd=clone)[:12]} "
                                     "(sh -c test -f ok.txt): not merged into integration"])
        (clone / "ok.txt").write_text("")
        sh("git", "add", "ok.txt", cwd=clone)
        sh("git", "commit", "-q", "-m", "C-001 fix", cwd=clone)
        sh("git", "push", "-q", "origin", "HEAD:refs/heads/change/C-001", cwd=clone)
        head = sh("git", "rev-parse", "HEAD", cwd=clone)
        tick()
        wait()
        tick()
        self.assertTrue(any("merged into integration" in m for m in self.sent), self.sent)
        parents = sh("git", "--git-dir", str(origin), "log", "-1", "--format=%P", "integration").split()
        self.assertEqual(len(parents), 2)  # --no-ff
        self.assertEqual(parents[1], head)
        self.assertNotIn("change/C-001", sh("git", "--git-dir", str(origin), "branch"))
        self.assertEqual(sh("git", "worktree", "list", "--porcelain", cwd=clone).count("worktree "), 1)

    def test_a_change_branch_already_in_integration_is_only_deleted(self):
        self.run.prs, self.run.in_integration = [], True
        self.run.remote_heads = f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse([a for a in self.run.commands("git") if "merge" in a and "--no-ff" in a])
        self.assertIn("--delete", [x for a in self.run.commands("git") if "push" in a for x in a])
        self.assertEqual(self.sent, [("Zeus", f"change/C-001 already in integration at {'d' * 12}: branch deleted")])
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(len(self.sent), 1)  # once per branch

    def test_a_failed_change_branch_delete_is_retried_next_pass(self):
        self.run.prs, self.run.in_integration = [], True
        self.run.remote_heads = f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.run.push_fails = True
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(self.sent, [])
        self.run.push_fails = False
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(self.sent, [("Zeus", f"change/C-001 already in integration at {'d' * 12}: branch deleted")])
        deletes = [x for a in self.run.commands("git") if "push" in a for x in a if x == "--delete"]
        self.assertEqual(len(deletes), 2)

    def test_without_a_spec_change_branches_are_left_alone(self):
        self.run.prs, self.run.remote_heads = [], f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.tick()
        self.assertFalse([a for a in self.run.commands("git") if "ls-remote" in a or "--no-ff" in a])


HELDOUT = [("held-out A-1.1", ["sh", "-c", "cp /hub/heldout/A-1.1/test_codes_unique.py tests/_heldout/ && run it"])]


class HeldoutGateTests(unittest.TestCase):
    """Living spec section 3: held-out checks gate a change branch, and a red one is named by its line alone."""
    setUp, tick, finish, spec_pr = MergeTickTests.setUp, MergeTickTests.tick, SpecMergeTests.finish, SpecMergeTests.spec_pr
    CHECKS = [["uv", "run", "pytest", "-q", "tests/acceptance/test_A_1_1.py"]]

    def gate_tick(self, heldout=HELDOUT):
        self.tick(req_lines=LINES, change_tasks=[], acceptance=self.CHECKS, acceptance_timeout=120, heldout=heldout)

    def merges(self):
        return [a for a in self.run.commands("git") if "--no-ff" in a]

    def test_heldout_red_names_line_only(self):
        self.run.prs, self.run.remote_heads = [], f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.run.gate_exit = 2  # the held-out step
        self.gate_tick(); self.gate_tick()
        self.assertEqual(self.run.spawned[0][6].splitlines()[1:3], [  # after the visible checks, before the smoke
            "env -u HUB_DIR -u HUB_AGENT timeout 120 sh -c 'cp /hub/heldout/A-1.1/test_codes_unique.py "
            "tests/_heldout/ && run it' || exit 2", "timeout 1800 sh -c 'make smoke' || exit 3"])
        self.assertEqual(self.run.spawned[0][8], str(2 * 120 + 2 * 1800 + 60))  # one more step under the cap
        self.assertEqual(self.sent, [("Zeus", "change/C-001 is red at dddddddddddd (held-out A-1.1): not merged into "
                                              f"integration; log {self.clone / 'heldout' / 'gate.log'}")])
        self.assertEqual([{k: e[k] for k in ("branch", "sha", "line")} for e in self.state["heldout_red"]],
                         [{"branch": "change/C-001", "sha": "d" * 40, "line": "A-1.1"}])
        self.assertNotIn("test_codes_unique", json.dumps(self.sent) + json.dumps(self.state["heldout_red"]))
        self.assertFalse(self.merges())

    def test_two_heldout_reds_hold_the_branch_until_heldout_json_changes(self):
        self.run.prs, self.run.gate_exit = [], 2
        for head in "de":
            self.run.remote_heads = f"{head * 40}\trefs/heads/change/C-001\n"
            self.gate_tick(); self.gate_tick()
        self.assertEqual(len(self.sent), 2)
        self.assertIn("red twice on this branch", self.sent[1][1])
        self.run.remote_heads, self.run.gate_exit = f"{'f' * 40}\trefs/heads/change/C-001\n", "0"
        self.gate_tick(); self.gate_tick()
        self.assertEqual(len(self.run.spawned), 2)  # the third head is not gated: Zeus decides
        rewritten = [(HELDOUT[0][0], ["sh", "-c", "echo '== held-out A-1.1 v2 2026-10-21'; run it"])]
        self.gate_tick(rewritten); self.gate_tick(rewritten)
        self.assertEqual(len(self.run.spawned), 3)
        self.assertEqual(len(self.merges()), 1)

    def test_visible_reds_never_hold_the_branch(self):
        self.run.prs, self.run.gate_exit = [], 1
        for head in "def":
            self.run.remote_heads = f"{head * 40}\trefs/heads/change/C-001\n"
            self.gate_tick(); self.gate_tick()
        self.assertEqual(len(self.run.spawned), 3)
        self.assertNotIn("heldout_red", self.state)

    def test_heldout_red_trimmed_like_canary_clean(self):
        self.state["heldout_red"] = [
            {"at": "2026-10-19T00:00:00Z", "branch": f"change/C-{i:03d}", "sha": "a" * 40, "line": "A-1.1"}
            for i in range(250)
        ]
        self.run.prs, self.run.remote_heads = [], f"{'d' * 40}\trefs/heads/change/C-001\n"
        self.run.gate_exit = 2  # the held-out step
        self.gate_tick(); self.gate_tick()
        self.assertEqual(len(self.state["heldout_red"]), 200)
        self.assertEqual(self.state["heldout_red"][-1]["branch"], "change/C-001")


    def lead_pr(self, diff):
        body = "Closes #17\n\nReq: A-1.1@2\nVerified: make check: 3 passed"
        self.run = FakeRun([self.spec_pr(body, author="lead") | {"comments": [{"author": {"login": "lead"}, "body": f"LGTM {SHA}"}]}])
        self.run.diff = diff

    def test_canary_in_diff_holds_pr(self):
        self.lead_pr("+++ b/tests/test_sum.py\n@@ -0,0 +1,2 @@\n+# HELDOUT_CANARY_7f3a do not copy\n+assert sum_(-2, 3) == 1\n")
        self.tick(req_lines=LINES, change_tasks=[]); self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.sent, [("Zeus", "PR #7 contains a held-out file (tests/test_sum.py): held, never merged here")])
        self.lead_pr(None)  # an unread diff holds too, silently, until a pass can read it
        self.sent = []
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertFalse(self.run.commands("gh", "pr", "merge"))
        self.assertEqual(self.sent, [])

    def test_no_canary_no_hold(self):
        self.lead_pr("+++ b/app/links.py\n+def sum_(a, b):\n-# HELDOUT-CANARY removed is not added\n")
        self.tick(req_lines=LINES, change_tasks=[])
        self.assertEqual(len(self.run.commands("gh", "pr", "merge")), 1)
        self.assertEqual(self.sent, [])
        self.run.calls = []
        self.tick(req_lines=LINES, change_tasks=[])  # a clean head is read once
        self.assertFalse(self.run.commands("gh", "pr", "diff"))

    def test_a_bent_build_goes_red_only_at_its_heldout_step_and_leaves_nothing_behind(self):
        """The acceptance of T-575, on a factory-sandbox-shaped repo: GET /api/sum's helper is bent to pass the
        visible check (2 + 3) only. The real gate (DETACHED_SH, gh_sync.heldout_checks) goes red at the held-out
        step alone, its output reaches heldout/gate.log only, and no held-out file reaches the worktree or a branch."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        self.enterContext(mock.patch.dict(os.environ, env, clear=True))
        root = Path(self.tmp.name)
        hub, origin, clone = root / "hub", root / "origin.git", root / "sandbox"
        gates = hub / "projects" / "sandbox"
        (gates / "spec").mkdir(parents=True)
        (gates / "spec" / "requirements.json").write_text(json.dumps({"version": 1, "requirements": [
            {"id": "R-8", "title": "Sum endpoint", "acceptance": [{"id": "A-8.1", "v": 1, "test": "tests/acceptance/test_A_8_1.py",
             "text": "GET /api/sum?a=<int>&b=<int> returns {sum: a+b}"}]}]}))
        (gates / "heldout" / "A-8.1").mkdir(parents=True)
        (gates / "heldout" / "heldout.json").write_text(json.dumps(
            {"A-8.1": {"v": 1, "tests": ["A-8.1/test_sum_negatives.py"], "by": "Zeus check-writer", "at": "2026-10-20T09:00:00Z"}}))
        (gates / "heldout" / "A-8.1" / "test_sum_negatives.py").write_text(
            "# HELDOUT_CANARY_e2e575 do not copy\nimport os, sys\nsys.path.insert(0, os.getcwd())\n"
            "from app import total\nassert total(-2, 3) == 1, 'negatives'\n")
        (hub / "factory.json").write_text(json.dumps({"repos": [{"repo": "o/sandbox", "acceptance_cmd": f"{sys.executable} {{test}}"}]}))
        self.enterContext(mock.patch.object(spec.hb, "HUB_DIR", str(hub)))
        sh = lambda *a, cwd=root: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
        sh("git", "init", "-q", "--bare", "-b", "integration", str(origin))
        sh("git", "clone", "-q", str(origin), str(clone))
        sh("git", "config", "user.email", "t@t", cwd=clone)
        sh("git", "config", "user.name", "t", cwd=clone)
        (clone / "tests" / "acceptance").mkdir(parents=True)
        (clone / "tests" / "acceptance" / "test_A_8_1.py").write_text(
            "import os, sys\nsys.path.insert(0, os.getcwd())\nfrom app import total\nassert total(2, 3) == 5\n")
        sh("git", "add", "tests", cwd=clone)
        sh("git", "commit", "-q", "-m", "base", cwd=clone)
        sh("git", "push", "-q", "origin", "HEAD:integration", cwd=clone)
        def build(body, message):
            (clone / "app.py").write_text(f"def total(a, b):\n    return {body}\n")
            sh("git", "add", "app.py", cwd=clone)
            sh("git", "commit", "-q", "-m", message, cwd=clone)
            sh("git", "push", "-q", "origin", "HEAD:refs/heads/change/C-001", cwd=clone)
        build("abs(a) + abs(b)", "A-8.1: bent to the visible check")
        run = lambda args, cwd=None, timeout=60: (
            subprocess.CompletedProcess(args, 0, "[]", "") if args[0] == "gh"
            else subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout))
        acceptance, _ = gh_sync.acceptance_checks("sandbox")
        def tick():
            merge_tick("o/sandbox", clone, "true", "lead", self.state, run, lambda a, m: self.sent.append(m),
                       req_lines={"A-8.1": 1}, change_tasks=[], acceptance=acceptance, acceptance_timeout=30,
                       change_timeout=30, gate_dir=gates, heldout=gh_sync.heldout_checks("sandbox"))
        def wait():
            for _ in range(300):
                tick()
                if not [g for g in self.state["change_gates"].values() if "exit" not in g]:
                    return tick()
                time.sleep(0.1)
            self.fail("the gate never finished")
        tick()
        wait()
        bent = sh("git", "rev-parse", "HEAD", cwd=clone)
        self.assertEqual(self.sent, [f"change/C-001 is red at {bent[:12]} (held-out A-8.1): not merged into "
                                     f"integration; log {gates / 'heldout' / 'gate.log'}"])
        self.assertEqual(self.state["heldout_red"][0]["line"], "A-8.1")
        self.assertIn("AssertionError: negatives", (gates / "heldout" / "gate.log").read_text())
        gate_log = (gates / "change-gate.log").read_text()
        self.assertFalse(any(word in gate_log for word in ("negatives", "CANARY", "test_sum_negatives")), gate_log)
        build("a + b", "A-8.1: the sum, negatives included")
        tick()
        wait()
        self.assertTrue(any("merged into integration" in m for m in self.sent), self.sent)
        self.assertEqual(sh("git", "worktree", "list", "--porcelain", cwd=clone).count("worktree "), 1)
        self.assertFalse((clone / "tests" / "_heldout").exists())
        everything = sh("git", "--git-dir", str(origin), "log", "--all", "-p", "--stat")
        self.assertNotIn("_heldout", everything)
        self.assertNotIn("CANARY", everything)


class ChangeBranchRewindTest(Fixture):
    """Hermes on T-521, end to end with hub spec: C-001's rebuild lands through change/C-001 (task PRs squashed
    onto the branch, the branch merged --no-ff), then C-002 modifies a line that rebuild built. history() splices
    the branch's own commits in place of the merge, so C-002 reverts exactly the rebuilt work: never the merge
    (whose -m 1 revert would resurrect what C-001 removed), and never C-001's rewind commit."""

    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        self.enterContext(mock.patch.dict(os.environ, env, clear=True))
        import board, live  # noqa: E401  every board path at this test's hub, never the live one
        for name in ("BOARD", "EVENTS", "LOCK", "WAL", "PAUSE", "INBOX_DIR"):
            self.enterContext(mock.patch.object(board, name, str(self.hub / os.path.basename(getattr(board, name)))))
        self.enterContext(mock.patch.object(board, "HUB_DIR", str(self.hub)))
        self.live_mod = live
        git(self.repo, "push", "-q", "origin", "main:integration")

    def rebuild(self, files, task, pr, trailers):
        """A task PR squashed onto change/C-001 on GitHub. Returns its merged event, as live_merge records it."""
        for path in files:
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text((p.read_text() if p.exists() else "") + f"# {task}\n")
            git(self.repo, "add", path)
        git(self.repo, "commit", "-q", "-m", f"{task} rebuild (#{pr})" + (f"\n\nReq: A-3.2@2\nTask: {task}" if trailers else ""))
        git(self.repo, "push", "-q", "origin", "change/C-001")
        return {"at": "2026-10-01T12:00:00+00:00", "pr": pr, "issue": None, "event": "merged", "base": "change/C-001",
                "sha": git(self.repo, "rev-parse", "HEAD").strip(), "task": task}

    def test_c002_reverts_the_rebuilt_commits_never_the_merge_nor_c001s_rewind(self):
        self.hub_spec("apply", "C-001")
        git(self.repo, "checkout", "-q", "change/C-001")
        rewind = git(self.repo, "rev-parse", "HEAD").strip()
        # T-012 carries its trailers; T-014's squash has none, so only its merge_sha claims it
        events = [self.rebuild(["app/routes/stats.py"], "T-012", 5, True),
                  self.rebuild(["web/dashboard.html", "app/routes/stats.py"], "T-014", 6, False)]
        git(self.repo, "checkout", "-q", "main")
        board = json.loads((self.hub / "board.json").read_text())
        for t in board["tasks"]:
            t["status"] = "done" if t["id"] in ("T-011", "T-012", "T-013", "T-014") else t["status"]
        (self.hub / "board.json").write_text(json.dumps(board))
        # hub live lands change/C-001: the real detached gate, then a later pass merges it --no-ff
        state, gates = {"merge_events": list(events), "sent": []}, Path(self.temp.name) / "gates"
        gates.mkdir()
        run = lambda args, cwd=None, timeout=60: (
            subprocess.CompletedProcess(args, 0, "[]", "") if args[0] == "gh"
            else subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout))
        for _ in range(200):
            merge_tick("o/linkly", self.repo, "true", "lead", state, run, lambda a, m: None,
                       req_lines={"A-3.2": 2}, change_tasks=[], gate_dir=gates)
            if any(e["event"] == "change-merged" for e in state["merge_events"]):
                break
            time.sleep(0.1)
        merge = git(self.origin, "rev-parse", "integration").strip()
        self.assertEqual(git(self.origin, "log", "-1", "--format=%P", "integration").split()[1], events[1]["sha"])
        (self.hub / "projects" / "linkly" / "hackathon.json").write_text(json.dumps(
            {"repo": "o/linkly", "smoke": "true", "deadlines": [{"name": "submit", "at": "2099-01-01T00:00:00Z"}],
             "roster": [{"github": "lead", "lead": True}]}))
        lv = self.live_mod.Live("linkly", run=run, send=lambda a, m: None)
        lv.state = state
        lv.merge_shas()
        self.assertEqual([self.board()[t].get("merge_sha") for t in ("T-012", "T-014")], [e["sha"] for e in events])
        sha = events[1]["sha"]  # a change-branch commit is on the line history() walks, so bootstrap-sha takes it
        self.assertIn(f"T-014 merge_sha {sha}", self.hub_spec("bootstrap-sha", f"T-14={sha}"))
        # C-002 changes A-3.2 again: the line T-012 built in C-001's rebuild
        self.write_change({"id": "C-002", "base_version": 5, "added": [], "removed": [],
                           "modified": [{"id": "A-3.2", "text": "stats returns {total, unique, by_week}"}],
                           "reason": "weekly"})
        out = self.hub_spec("apply", "C-002")
        self.assertEqual(self.radius(out), {"T-011": "cites A-3.2@2 (modified)", "T-012": "cites A-3.2@2 (modified)",
                                            "T-014": "entangled with T-012 via app/routes/stats.py"})
        self.assertIn(f"rewind, newest first: T-014 {events[1]['sha'][:12]}, T-012 {events[0]['sha'][:12]}\n", out)
        self.assertIn(f"base: origin/integration {merge[:12]}", out)  # the merge is the base, never a unit
        self.assertNotIn(rewind[:12], out)
        self.assertEqual(json.loads((self.spec / "spec.lock").read_text())["rewound"]["C-002"],  # what it reverted
                         [events[1]["sha"], events[0]["sha"]])
        self.assertNotIn(rewind, [c["sha"] for c in spec.history(self.repo, merge, [])])  # by subject, lock or not
        tree = git(self.origin, "ls-tree", "-r", "--name-only", "change/C-002").split()
        for gone in ("app/routes/stats.py", "web/dashboard.html",  # the rebuilt work
                     "web/dashboard.js", "app/routes/dashboard.py"):  # T-7/T-8's, which C-001 removed: not back
            self.assertNotIn(gone, tree)
        self.assertEqual(git(self.origin, "show", "change/C-002:app/routes/redirect.py"), "# T-3\n# T-4\n# T-6\n")

if __name__ == "__main__":
    unittest.main()
