"""`hub gh-sync` against a stub `gh` on PATH. Never touches the live board.

    python3 tests/test_gh_sync.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent

# Records argv to calls.jsonl, answers from files in $GH_STUB.
STUB = r'''#!/usr/bin/env python3
import fcntl, json, os, sys
d = os.environ["GH_STUB"]
a = sys.argv[1:]
with open(os.path.join(os.environ["HUB_DIR"], ".board.lock"), "a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
log = os.path.join(d, "calls.jsonl")
with open(log, "a") as f:
    f.write(json.dumps(a) + "\n")
if os.environ.get("GH_FAIL_ARG") in a:
    sys.stderr.write("simulated API failure")
    sys.exit(1)
if "--body-file" in a:
    with open(a[a.index("--body-file") + 1]) as body:
        with open(os.path.join(d, "bodies.jsonl"), "a") as log_body:
            log_body.write(json.dumps(body.read()) + "\n")
if os.environ.get("GH_REPO_404") and (a[:2] == ["issue", "list"] or (a[:1] == ["api"] and "-X" not in a)):
    sys.stderr.write("gh: Not Found (HTTP 404)")
    sys.exit(1)
if "--input" in a and a[a.index("--input") + 1] == "-":
    with open(os.path.join(d, "stdin.json"), "w") as f:
        f.write(sys.stdin.read())
if a[:2] == ["auth", "status"]:
    sys.exit(int(os.environ.get("GH_AUTH_FAIL", "0")))
if a[:2] == ["issue", "create"]:
    n = sum(1 for l in open(log) if json.loads(l)[:2] == ["issue", "create"])
    if str(n) == os.environ.get("GH_KILL_ON_CREATE"):
        import signal
        os.kill(os.getppid(), signal.SIGKILL)  # gh-sync dies mid-run: laptop lid, Ctrl-C, OOM
        sys.exit(1)
    print(f"https://github.com/o/hk/issues/{n}")
elif a[:2] == ["issue", "list"]:
    p = os.path.join(d, "issues.json")
    print(open(p).read() if os.path.exists(p) else "[]")
elif a[:2] == ["issue", "view"]:
    print(json.dumps({"body": open(os.path.join(d, f"body-{a[2]}.txt")).read()}))
elif a[:1] == ["api"] and "milestones" in a[-1] and "-X" not in a:
    p = os.path.join(d, "milestones.json")
    print(open(p).read() if os.path.exists(p) else "[]")
elif a[:1] == ["api"] and "collaborators" in a[-1] and "-X" not in a:
    people = os.environ.get("GH_COLLABORATORS", "lead-gh,sam-gh").split(",")
    print(json.dumps([{"login": p} for p in people if p]))
elif a[:2] == ["api", "user"]:
    print(json.dumps({"id": 42, "login": "lead-gh"}))
elif a[:1] == ["api"] and a[-1] == "repos/o/hk/branches" and "-X" not in a:
    names = [n for n in os.environ.get("GH_BRANCHES", "main").split(",") if n]
    print(json.dumps([{"name": n} for n in names[:30]]))      # GitHub's first page
elif a[:1] == ["api"] and a[-1].startswith("repos/o/hk/git/matching-refs/heads/"):
    prefix = a[-1].rsplit("/heads/", 1)[1]
    names = [n for n in os.environ.get("GH_BRANCHES", "main").split(",") if n]
    print(json.dumps([{"ref": f"refs/heads/{n}"} for n in names if n.startswith(prefix)]))
elif a[:1] == ["api"] and a[-1] == "repos/o/hk/git/ref/heads/main":
    print(json.dumps({"object": {"sha": "abc123"}}))
elif a[:1] == ["api"] and a[-1] == "repos/o/hk" and "-X" not in a:
    print(json.dumps({"default_branch": os.environ.get("GH_DEFAULT", "main")}))
elif a[:2] == ["repo", "view"]:
    if os.environ.get("GH_REPO_MISSING") == "1":
        sys.stderr.write("GraphQL: Could not resolve to a Repository with the name 'o/hk'. (repository)")
        sys.exit(1)
    if os.environ.get("GH_REPO_ERROR"):
        sys.stderr.write(os.environ["GH_REPO_ERROR"])
        sys.exit(1)
    tpl = os.environ.get("GH_TEMPLATE", "tpl/hackathon_teamwork")
    owner, _, name = tpl.partition("/")
    print(json.dumps({"templateRepository": {"name": name, "owner": {"login": owner}} if tpl else None}))
'''

CFG = {
    "repo": "o/hk",
    "template": "tpl/hackathon_teamwork",
    "timezone": "Europe/London",
    "deadlines": [{"name": "code freeze", "at": "2026-10-04T14:00:00+01:00"},
                  {"name": "submit", "at": "2026-10-04T15:00:00+01:00"}],
    "roster": [{"name": "Atilade", "github": "lead-gh", "lead": True},
               {"name": "Sam", "github": "sam-gh"}],
}


class GhSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-ghsync-test-")
        self.hub = Path(self.temp.name)
        (self.hub / "board.json").write_text(json.dumps({"next_id": 1, "tasks": []}))
        (self.hub / "inbox").mkdir()
        proj = self.hub / "projects" / "hk"
        proj.mkdir(parents=True)
        (proj / "hackathon.json").write_text(json.dumps(CFG))
        self.stub = self.hub / "stub"
        (self.stub / "bin").mkdir(parents=True)
        gh = self.stub / "bin" / "gh"
        gh.write_text(STUB)
        gh.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT",
                                 "HUB_LEAD", "HUB_CLAUDE_AGENTS", "HUB_CODEX_AGENTS", "HUB_CODE_DIR")}
        self.env.update(HUB_DIR=str(self.hub), HUB_AGENT="Zeus", GH_STUB=str(self.stub),
                        PATH=f"{self.stub / 'bin'}:{os.environ['PATH']}")

    def tearDown(self):
        self.temp.cleanup()

    def add_task(self, tid, owner="Sam", detail="Context: x\nDeadline: submit", **kw):
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"].append({"id": tid, "title": f"title {tid}", "detail": detail,
                              "status": "open", "owner": owner, "deps": [],
                              "project": "hk", "notes": [], **kw})
        (self.hub / "board.json").write_text(json.dumps(data))

    def tasks(self):
        return {t["id"]: t for t in json.loads((self.hub / "board.json").read_text())["tasks"]}

    def sync(self, *args):
        return subprocess.run([sys.executable, str(HUB / "board.py"), "gh-sync",
                               "--project", "hk", *args],
                              env=self.env, capture_output=True, text=True, timeout=60)

    def calls(self, verb=None):
        p = self.stub / "calls.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
        rows = [r for r in rows if r[:2] != ["auth", "status"]]
        return [r for r in rows if verb is None or r[:2] == verb]

    def writes(self):
        return [c for c in self.calls() if c[:2] not in (["issue", "list"], ["issue", "view"], ["repo", "view"])
                and not (c[:1] == ["api"] and "-X" not in c)]       # api without -X is a GET

    def test_push_creates_issue_and_records_it(self):
        self.add_task("T-001")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("sam-gh", create)
        self.assertIn("submit", create)            # milestone from the Deadline: line
        t = self.tasks()["T-001"]
        self.assertEqual(t["issue"], 1)
        self.assertEqual(t["issue_assignee"], "sam-gh")
        self.assertEqual(len(t["issue_hash"]), 64)

    def test_rerun_is_noop(self):
        self.add_task("T-001")
        self.sync()
        before = len(self.writes())
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(len(self.writes()), before)

    def test_changed_brief_edits_and_comments(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "body-1.txt").write_text("Context: x\nDeadline: submit")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: y\nDeadline: submit"
        (self.hub / "board.json").write_text(json.dumps(data))
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(len(self.calls(["issue", "edit"])), 1)
        self.assertEqual(len(self.calls(["issue", "comment"])), 1)

    def test_github_edit_is_not_overwritten(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "body-1.txt").write_text("teammate rewrote this")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: y"
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertEqual(self.calls(["issue", "edit"]), [])
        self.assertIn("#1", r.stdout)
        self.assertIn("not overwriting", r.stdout)

    def test_agent_owner_goes_to_lead_with_label(self):
        self.add_task("T-001", owner="Prometheus")
        self.sync()
        [create] = self.calls(["issue", "create"])
        self.assertIn("lead-gh", create)
        self.assertIn("task,agent:prometheus", create)

    def test_pool_gets_label_and_no_assignee(self):
        self.add_task("T-001", owner="")
        self.sync()
        [create] = self.calls(["issue", "create"])
        self.assertIn("task,pool", create)
        self.assertNotIn("--assignee", create)

    def test_unknown_owner_fails_one_task(self):
        self.add_task("T-001", owner="Smа")          # typo
        self.add_task("T-002")
        r = self.sync()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("T-001", r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue"], 1)

    def test_pull_marks_closed_issue_done(self):
        self.add_task("T-001", issue=4, issue_hash="h", issue_assignee="sam-gh")
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 4, "title": "t", "state": "CLOSED", "stateReason": "COMPLETED",
             "assignees": [{"login": "sam-gh"}], "labels": [], "url": "u"}]))
        self.sync("--pull-only")
        self.assertEqual(self.tasks()["T-001"]["status"], "done")

    def test_pull_pool_assignee_sets_owner(self):
        self.add_task("T-001", owner="", issue=4, issue_hash="h", issue_assignee=None)
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 4, "title": "t", "state": "OPEN", "stateReason": "",
             "assignees": [{"login": "sam-gh"}], "labels": [{"name": "pool"}], "url": "u"}]))
        self.sync("--pull-only")
        self.assertEqual(self.tasks()["T-001"]["owner"], "Sam")

    def test_change_request_delivered_once(self):
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 9, "title": "swap db", "state": "OPEN", "stateReason": "",
             "assignees": [], "labels": [{"name": "change-request"}], "url": "u9"}]))
        self.sync()
        self.sync()
        inbox = (self.hub / "inbox" / "Zeus.jsonl").read_text().splitlines()
        self.assertEqual(len(inbox), 1)
        self.assertIn("#9", inbox[0])

    def test_dry_run_changes_nothing(self):
        self.add_task("T-001")
        before = (self.hub / "board.json").read_text()
        r = self.sync("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn("would run", r.stdout)
        self.assertEqual((self.hub / "board.json").read_text(), before)

    def test_gh_logged_out(self):
        self.env["GH_AUTH_FAIL"] = "1"
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertIn("gh auth login", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_gh_has_one_line_error(self):
        self.env["PATH"] = str(self.hub / "empty-bin")
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not installed", r.stderr)
        self.assertEqual(len(r.stderr.splitlines()), 1)

    def test_timeout_has_one_line_error(self):
        script = '''
import argparse, subprocess
from unittest.mock import patch
import gh_sync
with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 60)) as run:
    try:
        gh_sync.cmd_gh_sync(argparse.Namespace(project="hk", dry_run=False, init=False, pull_only=False))
    finally:
        assert run.call_args.kwargs["timeout"] == 60
'''
        r = subprocess.run([sys.executable, "-c", script], cwd=HUB, env=self.env,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 1)
        self.assertIn("timed out", r.stderr)
        self.assertEqual(len(r.stderr.splitlines()), 1)

    def test_failed_issue_does_not_block_other_tasks(self):
        self.env["GH_FAIL_ARG"] = "title T-001"
        self.add_task("T-001")
        self.add_task("T-002")
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("issue", self.tasks()["T-001"])
        self.assertEqual(self.tasks()["T-002"]["issue"], 2)

    def test_changed_owner_removes_old_assignee(self):
        self.add_task("T-001")
        self.assertEqual(self.sync().returncode, 0)
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["owner"] = ""
        (self.hub / "board.json").write_text(json.dumps(data))
        self.assertEqual(self.sync().returncode, 0)
        [edit] = self.calls(["issue", "edit"])
        self.assertIn("--remove-assignee", edit)
        self.assertIn("sam-gh", edit)
        self.assertNotIn("--add-assignee", edit)
        self.assertIsNone(self.tasks()["T-001"]["issue_assignee"])

    def test_multiline_body_is_passed_verbatim_as_file(self):
        body = "Context: `literal` $(literal)\n\nDeadline: submit\n"
        self.add_task("T-001", detail=body)
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("--body-file", create)
        bodies = (self.stub / "bodies.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(bodies[0]), body)

    def test_init_creates_everything(self):
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertIn(["repo", "create", "o/hk", "--template", "tpl/hackathon_teamwork",
                       "--public", "--clone"], calls)
        self.assertTrue(any(c[:3] == ["api", "-X", "PUT"] and c[3] == "repos/o/hk/collaborators/sam-gh" for c in calls))
        self.assertFalse(any("collaborators/lead-gh" in " ".join(c) for c in calls))
        labels = {c[2] for c in self.calls(["label", "create"])}
        self.assertTrue({"task", "pool", "change-request", "submission", "question", "agent:prometheus"} <= labels)
        ms = [c for c in calls if c[:4] == ["api", "-X", "POST", "repos/o/hk/milestones"]]
        self.assertEqual(len(ms), 2)
        self.assertIn("due_on=2026-10-04T13:00:00Z", ms[0])      # 14:00 +01:00 in UTC
        prot = [c for c in calls if "repos/o/hk/branches/main/protection" in c]
        self.assertEqual(len(prot), 1)

    def test_init_is_idempotent(self):
        self.env["GH_REPO_MISSING"] = "0"                       # repo already exists
        self.env.update(GH_BRANCHES="main,integration", GH_DEFAULT="integration")
        (self.stub / "milestones.json").write_text(json.dumps([
            {"number": 1, "title": "code freeze", "due_on": "2026-10-04T00:00:00Z"},
            {"number": 2, "title": "submit", "due_on": "2026-10-04T00:00:00Z"}]))
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(["repo", "create"]), [])
        self.assertFalse(any(c[:4] == ["api", "-X", "POST", "repos/o/hk/milestones"] for c in self.calls()))
        self.assertFalse(any(c[:3] == ["api", "-X", "PATCH"] for c in self.calls()))
        self.assertIn("question", {c[2] for c in self.calls(["label", "create"])})   # rerun keeps labels

    def test_init_creates_integration_and_makes_it_default(self):
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertIn(["api", "-X", "POST", "repos/o/hk/git/refs",
                       "-f", "ref=refs/heads/integration", "-f", "sha=abc123"], calls)
        self.assertIn(["api", "-X", "PATCH", "repos/o/hk", "-f", "default_branch=integration"], calls)
        for branch in ("main", "integration"):
            self.assertEqual(len([c for c in calls if f"repos/o/hk/branches/{branch}/protection" in c]), 1)

    def test_init_rerun_leaves_integration_alone(self):
        self.env.update(GH_BRANCHES="main,integration", GH_DEFAULT="integration")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any("repos/o/hk/git/refs" in c for c in self.calls()))
        self.assertFalse(any(c[:4] == ["api", "-X", "PATCH", "repos/o/hk"] for c in self.calls()))

    def test_init_fills_only_the_missing_default(self):
        self.env.update(GH_BRANCHES="main,integration", GH_DEFAULT="main")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any("repos/o/hk/git/refs" in c for c in self.calls()))
        self.assertIn(["api", "-X", "PATCH", "repos/o/hk", "-f", "default_branch=integration"], self.calls())

    def test_init_rerun_finds_integration_past_the_first_page_of_branches(self):
        issue_branches = [f"{n}-task" for n in range(10, 45)]   # sort before "integration"
        self.env.update(GH_BRANCHES=",".join(["main", *issue_branches, "integration"]),
                        GH_DEFAULT="integration")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any("repos/o/hk/git/refs" in c for c in self.calls()))

    def test_init_does_not_mistake_a_prefix_branch_for_integration(self):
        self.env.update(GH_BRANCHES="main,integration-old", GH_DEFAULT="integration-old")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(["api", "-X", "POST", "repos/o/hk/git/refs",
                       "-f", "ref=refs/heads/integration", "-f", "sha=abc123"], self.calls())

    def test_dry_run_init_shows_integration_steps(self):
        self.env.update(GH_REPO_404="1", GH_REPO_MISSING="1")
        r = self.sync("--init", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ref=refs/heads/integration", r.stdout)
        self.assertIn("default_branch=integration", r.stdout)

    def test_integration_error_is_one_line_and_protection_still_runs(self):
        self.env["GH_FAIL_ARG"] = "repos/o/hk/git/refs"
        r = self.sync("--init")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error: integration branch:", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(any("repos/o/hk/branches/main/protection" in c for c in self.calls()))
        self.assertEqual(r.stderr.count("error:"), 1, r.stderr)            # one line, not two
        self.assertFalse(any("repos/o/hk/branches/integration/protection" in c for c in self.calls()))

    def test_failed_branch_lookup_is_not_read_as_missing(self):
        self.env["GH_FAIL_ARG"] = "repos/o/hk/git/matching-refs/heads/integration"
        r = self.sync("--init")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error: integration branch:", r.stderr)
        self.assertFalse(any("repos/o/hk/git/refs" in c for c in self.calls()))   # no blind create
        self.assertTrue(any("repos/o/hk/branches/main/protection" in c for c in self.calls()))

    def test_dry_run_init_on_missing_repo(self):
        self.env["GH_REPO_404"] = "1"             # repo does not exist yet: every read 404s
        self.env["GH_REPO_MISSING"] = "1"
        self.add_task("T-001")
        r = self.sync("--init", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would run: gh repo create", r.stdout)
        self.assertEqual(self.writes(), [c for c in self.writes() if c[:2] == ["repo", "view"]])

    def test_init_sets_commit_identity_on_the_clone(self):
        home = self.hub / "home"
        clone = home / "code" / "hk"               # what `gh repo create --clone` leaves behind
        clone.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        self.env["HOME"] = str(home)
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        email = subprocess.run(["git", "-C", str(clone), "config", "user.email"],
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(email, "42+lead-gh@users.noreply.github.com")  # from `gh api user`

    def test_init_protection_dismisses_stale_approvals(self):
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        body = json.loads((self.stub / "stdin.json").read_text())
        reviews = body["required_pull_request_reviews"]
        self.assertIs(reviews["dismiss_stale_reviews"], True)   # a push after approval voids it
        self.assertIs(reviews["require_code_owner_reviews"], True)
        self.assertNotIn("require_last_push_approval", reviews)

    def write_cfg(self, **changes):
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps({**CFG, **changes}))

    def test_pool_owner_as_the_hub_stores_it(self):
        self.add_task("T-001", owner="Pool")            # `hub assign T-1 pool` stores "Pool"
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("task,pool", create)
        self.assertNotIn("--assignee", create)

    def test_owner_name_matches_the_hub_spelling(self):
        self.write_cfg(roster=[{"name": "Atilade", "github": "lead-gh", "lead": True},
                               {"name": "DeShawn", "github": "ds-gh"}])
        self.env["GH_COLLABORATORS"] = "lead-gh,ds-gh"
        self.add_task("T-001", owner="Deshawn")         # the hub's canon() of DeShawn
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("ds-gh", create)

    def test_uninvited_teammate_gets_the_issue_unassigned_then_assigned(self):
        self.env["GH_COLLABORATORS"] = "lead-gh"          # Sam has not accepted the invite
        self.add_task("T-001")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertNotIn("--assignee", create)
        self.assertIn("Sam", r.stdout)
        self.assertIn("invite", r.stdout)
        self.assertIsNone(self.tasks()["T-001"]["issue_assignee"])
        self.env["GH_COLLABORATORS"] = "lead-gh,sam-gh"   # Sam accepts
        self.assertEqual(self.sync().returncode, 0)
        [edit] = self.calls(["issue", "edit"])
        self.assertIn("--add-assignee", edit)
        self.assertIn("sam-gh", edit)
        self.assertEqual(self.tasks()["T-001"]["issue_assignee"], "sam-gh")

    def test_lead_moving_a_task_back_to_pool_sticks(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "t", "state": "OPEN", "stateReason": "",
             "assignees": [{"login": "sam-gh"}], "labels": [], "url": "u"}]))
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["owner"] = ""
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-001"]["owner"], "")
        [edit] = self.calls(["issue", "edit"])
        self.assertIn("--remove-assignee", edit)

    def test_crash_mid_sync_keeps_the_issues_already_created(self):
        self.add_task("T-001")
        self.add_task("T-002")
        self.env["GH_KILL_ON_CREATE"] = "2"
        self.sync()
        self.assertEqual(self.tasks()["T-001"]["issue"], 1)
        del self.env["GH_KILL_ON_CREATE"]
        self.assertEqual(self.sync().returncode, 0)
        creates = [c for c in self.calls(["issue", "create"]) if "title T-001" in c]
        self.assertEqual(len(creates), 1)                # no duplicate for T-001

    def test_second_sync_while_one_runs_exits(self):
        import fcntl
        with open(self.hub / "projects" / "hk" / ".gh-sync.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.add_task("T-001")
            r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertIn("already running", r.stderr)
        self.assertEqual(self.calls(["issue", "create"]), [])

    def test_bad_config_is_one_line_not_a_traceback(self):
        cfg = self.hub / "projects" / "hk" / "hackathon.json"
        cases = {
            "no lead": json.dumps({**CFG, "roster": [{"name": "Sam", "github": "sam-gh"}]}),
            "not json": "{repo: o/hk",
            "no timezone": json.dumps({**CFG, "deadlines": [{"name": "code freeze", "at": "2026-10-04T14:00"},
                                                            {"name": "submit", "at": "2026-10-04T15:00+01:00"}]}),
            "name with a space": json.dumps({**CFG, "roster": [*CFG["roster"], {"name": "Sam Lee", "github": "sl"}]}),
            "no submit deadline": json.dumps({**CFG, "deadlines": CFG["deadlines"][:1]}),
            "wrong shape": json.dumps(["o/hk"]),
            "no template": json.dumps({k: v for k, v in CFG.items() if k != "template"}),
            "handle not text": json.dumps({**CFG, "roster": [*CFG["roster"], {"name": "Bo", "github": 123}]}),
            "handle not a handle": json.dumps({**CFG, "roster": [*CFG["roster"], {"name": "Bo", "github": "bo gh!"}]}),
            "deadline without a name": json.dumps({**CFG, "deadlines": [*CFG["deadlines"], {"at": "2026-10-04T16:00+01:00"}]}),
            "duplicate deadline": json.dumps({**CFG, "deadlines": [*CFG["deadlines"], CFG["deadlines"][1]]}),
        }
        for why, text in cases.items():
            with self.subTest(why):
                cfg.write_text(text)
                r = self.sync()
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertIn("hackathon.json", r.stderr)

    def test_unknown_deadline_names_the_choices(self):
        self.add_task("T-001", detail="Context: x\nDeadline: freeze")
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertIn("'freeze'", r.stderr)
        self.assertIn("code freeze", r.stderr)
        self.assertEqual(self.calls(["issue", "create"]), [])

    def test_done_tasks_are_left_alone(self):
        self.add_task("T-001", status="done", issue=1, issue_hash="stale", issue_assignee="old-gh")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.calls(["issue", "view"]), [])
        self.assertNotIn("warning", r.stdout)

    def test_refuses_a_repo_not_made_from_the_template(self):
        self.env["GH_TEMPLATE"] = ""                  # e.g. hackathon.json typo'd to a real repo
        self.add_task("T-001")
        for args in ((), ("--init",)):
            with self.subTest(args=args):
                r = self.sync(*args)
                self.assertEqual(r.returncode, 1)
                self.assertIn("refusing", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(self.writes(), [])           # no issue, no invite, no protection

    def test_repo_name_must_match_the_project(self):
        self.write_cfg(repo="o/refinery")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 1)
        self.assertIn("project", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_repo_without_init_says_run_init(self):
        self.env["GH_REPO_MISSING"] = "1"
        self.add_task("T-001")
        r = self.sync()
        self.assertEqual(r.returncode, 1)
        self.assertIn("--init", r.stderr)
        self.assertEqual(self.writes(), [])

    def test_retitle_and_new_deadline_reach_the_issue(self):
        self.add_task("T-001")                        # Deadline: submit
        self.sync()
        (self.stub / "body-1.txt").write_text("Context: x\nDeadline: submit")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["title"] = "renamed"
        data["tasks"][0]["detail"] = "Context: x\nDeadline: code freeze"
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        edits = self.calls(["issue", "edit"])
        self.assertTrue(any("--title" in e and "renamed" in e for e in edits), edits)
        self.assertTrue(any("--milestone" in e and "code freeze" in e for e in edits), edits)
        before = len(self.writes())
        self.assertEqual(self.sync().returncode, 0)   # and then it is settled
        self.assertEqual(len(self.writes()), before)

    def test_pull_reports_not_planned_and_missing_issues(self):
        self.add_task("T-001", issue=1, issue_hash="h", issue_assignee="sam-gh")
        self.add_task("T-002", issue=7, issue_hash="h", issue_assignee="sam-gh")
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "t", "state": "CLOSED", "stateReason": "NOT_PLANNED",
             "assignees": [], "labels": [], "url": "u1"}]))
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("#1", r.stdout)
        self.assertIn("not planned", r.stdout)
        self.assertIn("#7", r.stdout)
        self.assertIn("not found", r.stdout)
        self.assertEqual(self.tasks()["T-001"]["status"], "open")

    def test_reopened_issue_reopens_only_a_task_the_sync_closed(self):
        self.add_task("T-001", issue=1, issue_hash="h", issue_assignee="sam-gh")
        self.add_task("T-002", status="done", issue=2, issue_hash="h", issue_assignee="sam-gh")
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": n, "title": "t", "state": state, "stateReason": reason,
             "assignees": [{"login": "sam-gh"}], "labels": [], "url": "u"}
            for n, state, reason in ((1, "CLOSED", "COMPLETED"), (2, "OPEN", "REOPENED"))]))
        self.sync("--pull-only")
        self.assertEqual(self.tasks()["T-001"]["status"], "done")
        self.assertEqual(self.tasks()["T-002"]["status"], "done")    # closed by hand: left alone
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "t", "state": "OPEN", "stateReason": "REOPENED",
             "assignees": [{"login": "sam-gh"}], "labels": [], "url": "u"}]))
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-001"]["status"], "open")

    def test_init_only_provisions_and_publishes_no_issues(self):
        self.add_task("T-001")                        # IDEA.md isn't published yet: the gate
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(["issue", "create"]), [])
        self.assertIn("hub gh-sync", r.stdout)        # says what to run once the kit is pushed

    def test_init_clones_an_existing_repo_that_is_missing_here(self):
        home = self.hub / "home"
        (home / "code").mkdir(parents=True)
        self.env["HOME"] = str(home)
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(["repo", "clone", "o/hk", str(home / "code" / "hk")], self.calls())

    def test_contested_pool_issue_goes_to_the_alphabetically_first_login(self):
        self.write_cfg(roster=[*CFG["roster"], {"name": "Zed", "github": "zed-gh"}])
        self.add_task("T-001", owner="", issue=1, issue_hash="h", issue_assignee=None)
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "t", "state": "OPEN", "stateReason": "",
             "assignees": [{"login": "zed-gh"}, {"login": "sam-gh"}], "labels": [], "url": "u"}]))
        self.sync("--pull-only")
        self.assertEqual(self.tasks()["T-001"]["owner"], "Sam")   # same rule as AGENTS.md §3

    def test_moved_deadline_updates_the_milestone(self):
        (self.stub / "milestones.json").write_text(json.dumps([
            {"number": 1, "title": "code freeze", "due_on": "2026-10-01T00:00:00Z"},
            {"number": 2, "title": "submit", "due_on": "2026-10-04T00:00:00Z"}]))
        self.env.update(GH_BRANCHES="main,integration", GH_DEFAULT="integration")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        patches = [c for c in self.calls() if c[:3] == ["api", "-X", "PATCH"]]
        self.assertEqual(len(patches), 1)
        self.assertIn("repos/o/hk/milestones/1", patches[0])
        self.assertIn("due_on=2026-10-04T13:00:00Z", patches[0])

    def test_labels_follow_the_owner(self):
        # a task moved to the pool must carry `pool`, or `label:pool no:assignee` never finds it
        self.add_task("T-001", owner="Zeus", issue=1, issue_hash="h", issue_assignee="lead-gh",
                      detail="Context: x\nDeadline: submit")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["issue_hash"] = __import__("hashlib").sha256(b"Context: x\nDeadline: submit").hexdigest()
        data["tasks"][0]["owner"] = "Pool"
        (self.hub / "board.json").write_text(json.dumps(data))
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "t", "state": "OPEN", "stateReason": "",
             "assignees": [{"login": "lead-gh"}], "labels": [{"name": "task"}, {"name": "agent:zeus"}],
             "url": "u"}]))
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [edit] = self.calls(["issue", "edit"])
        self.assertEqual(edit[edit.index("--add-label") + 1], "pool")
        self.assertEqual(edit[edit.index("--remove-label") + 1], "agent:zeus")
        self.assertIn("--remove-assignee", edit)

    def test_repo_lookup_error_is_not_mistaken_for_a_missing_repo(self):
        self.env["GH_REPO_ERROR"] = "HTTP 502: Bad Gateway"
        self.add_task("T-001")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 1)
        self.assertIn("502", r.stderr)
        self.assertEqual(self.calls(["repo", "create"]), [])   # never "create" over a hiccup
        self.assertEqual(self.writes(), [])

    def test_failed_brief_notice_is_retried(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "body-1.txt").write_text("Context: x\nDeadline: submit")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: y\nDeadline: submit"
        (self.hub / "board.json").write_text(json.dumps(data))
        self.env["GH_FAIL_ARG"] = "comment"             # the edit lands, the notice fails
        self.assertNotEqual(self.sync().returncode, 0)
        del self.env["GH_FAIL_ARG"]
        self.assertEqual(self.sync().returncode, 0)     # the notice goes out now
        self.assertEqual(self.sync().returncode, 0)     # and only once
        comments = self.calls(["issue", "comment"])
        self.assertEqual(len(comments), 2)              # one failed, one delivered
        self.assertEqual(len(self.calls(["issue", "edit"])), 1)

    def test_roster_comes_from_the_environment(self):
        self.env.update(HUB_LEAD="Lead", HUB_CLAUDE_AGENTS="Lead Builder", HUB_CODEX_AGENTS="")
        self.add_task("T-001", owner="Builder")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("task,agent:builder", create)
        self.assertIn("lead-gh", create)                 # hub agents work as the lead's hands
        self.add_task("T-002", owner="Prometheus")       # not on this roster
        r = self.sync()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("T-002", r.stderr)

    def test_init_creates_the_code_dir_on_a_fresh_machine(self):
        home = self.hub / "fresh-home"                  # no ~/code yet
        home.mkdir()
        self.env["HOME"] = str(home)
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((home / "code").is_dir())


if __name__ == "__main__":
    unittest.main()
