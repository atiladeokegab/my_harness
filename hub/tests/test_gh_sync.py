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
    data = sys.stdin.read()
    with open(os.path.join(d, "stdin.json"), "w") as f:
        f.write(data)
    if "/protection" in a[-3]:
        with open(os.path.join(d, "protection-" + a[-3].split("/branches/")[1].split("/")[0] + ".json"), "w") as f:
            f.write(data)
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
    if os.path.exists(p):
        print(open(p).read())
    elif os.environ.get("GH_LIST_CREATED"):   # GitHub lists what was created earlier in the run
        n = sum(1 for l in open(log) if json.loads(l)[:2] == ["issue", "create"])
        print(json.dumps([{"number": k, "title": f"t{k}", "state": "OPEN", "stateReason": "",
                           "assignees": [], "labels": [], "body": "",
                           "url": f"https://github.com/o/hk/issues/{k}"} for k in range(1, n + 1)]))
    else:
        print("[]")
elif a[:2] == ["issue", "view"]:
    print(json.dumps({"body": open(os.path.join(d, f"body-{a[2]}.txt")).read()}))
elif a[:1] == ["api"] and "/sub_issues" in a[-1]:
    n = a[-1].split("/issues/", 1)[1].split("/", 1)[0]
    p = os.path.join(d, f"subissues-{n}.json")
    print(open(p).read() if os.path.exists(p) else "[]")
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
elif a[:2] == ["api", "graphql"]:
    p = os.path.join(d, "graphql.json")
    if not os.path.exists(p):
        sys.stderr.write("graphql unavailable")
        sys.exit(1)
    print(open(p).read())
elif a[:2] == ["variable", "set"]:
    pass
elif a[:2] == ["run", "list"]:
    per_branch = os.path.join(d, f"runs-{a[a.index('--branch') + 1]}.json") if "--branch" in a else ""
    p = per_branch if per_branch and os.path.exists(per_branch) else os.path.join(d, "runs.json")
    print(open(p).read() if os.path.exists(p) else "[]")
elif a[:2] == ["run", "rerun"]:
    pass
elif a[:2] == ["run", "view"]:
    p = os.path.join(d, "run-views.json")
    seq = json.load(open(p)) if os.path.exists(p) else ["in_progress"]
    status = seq.pop(0) if len(seq) > 1 else seq[0]
    json.dump(seq, open(p, "w"))
    print(json.dumps({"status": status}))
elif a[:2] == ["pr", "list"]:
    p = os.path.join(d, "prs.json")
    print(open(p).read() if os.path.exists(p) else "[]")
elif a[:1] == ["api"] and a[-1] == "repos/o/hk/git/ref/tags/freeze" and "-X" not in a:
    if os.environ.get("GH_TAG_ERROR"):
        sys.stderr.write(os.environ["GH_TAG_ERROR"])
        sys.exit(1)
    if not os.path.exists(os.path.join(d, "tag-exists")):
        sys.stderr.write("gh: Not Found (HTTP 404)")
        sys.exit(1)
    print(json.dumps({"object": {"sha": "old999"}}))
elif a[:2] == ["project", "list"]:
    p = os.path.join(d, "projects.json")
    print(open(p).read() if os.path.exists(p) else '{"projects": []}')
elif a[:2] == ["project", "copy"]:
    print(json.dumps({"number": 9, "url": "https://github.com/users/lead-gh/projects/9", "id": "P9"}))
elif a[:2] == ["project", "field-list"]:
    if not os.path.exists(os.path.join(d, "fields.json")):
        sys.stderr.write("no fields in the stub")
        sys.exit(1)
    print(open(os.path.join(d, "fields.json")).read())
elif a[:2] == ["project", "item-list"]:
    print(json.dumps({"items": []}))
elif a[:2] == ["project", "item-add"]:
    print(json.dumps({"id": "ITEM-" + a[a.index("--url") + 1].rsplit("/", 1)[1]}))
elif a[:2] == ["project", "item-edit"]:
    pass
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
    "event": "Hack Day",
    "title": "Sample App",
    "summary": "A sample app for the accessibility track.",
    "smoke": "python3 -m unittest",
    "deadlines": [{"name": "code freeze", "at": "2026-10-04T14:00:00+01:00"},
                  {"name": "submit", "at": "2026-10-04T15:00:00+01:00"}],
    "roster": [{"name": "Alex", "github": "lead-gh", "lead": True},
               {"name": "Sam", "github": "sam-gh"}],
}

AGENT_CFG = {**CFG, "roster": [
    {"name": "Alex", "github": "lead-gh", "lead": True,
     "agents": [{"name": "Zeus"}, {"name": "Prometheus", "github": "bot-gh"}]},
    {"name": "Sam", "github": "sam-gh"}]}


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

    def vertical_fixture(self, children, detail="Context: area\nFiles: expenses/parse/, tests/parse/\nDeadline: submit"):
        self.add_task("T-001", kind="vertical", issue=1, issue_hash="h", issue_assignee="sam-gh",
                      issue_title="title T-001", issue_milestone="submit", detail=detail)
        data = json.loads((self.hub / "board.json").read_text())
        data["next_id"] = 2
        (self.hub / "board.json").write_text(json.dumps(data))
        issues = [{
            "number": 1, "title": "title T-001", "state": "OPEN", "stateReason": "",
            "assignees": [{"login": "sam-gh"}], "labels": [{"name": "task"}, {"name": "vertical"}],
            "url": "u1", "body": detail}]
        issues += [{**child, "state": child["state"].upper(), "stateReason": "", "url": f"u{child['number']}"}
                   for child in children]
        (self.stub / "issues.json").write_text(json.dumps(issues))
        (self.stub / "subissues-1.json").write_text(json.dumps(children))

    def subissue(self, number=2, body="Context: parser\nFiles: expenses/parse/, tests/parse/\nDeadline: submit",
                 labels=("task",), **extra):
        return {"number": number, "title": f"parser {number}", "body": body, "state": "open",
                "labels": [{"name": x} for x in labels], "assignees": [{"login": "sam-gh"}],
                "milestone": {"title": "submit"}, **extra}

    def test_approved_subissue_imports_once_without_rewriting_its_body(self):
        child = self.subissue()
        self.vertical_fixture([child])
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        imported = [t for t in self.tasks().values() if t.get("issue") == 2]
        self.assertEqual(len(imported), 1)
        t = imported[0]
        self.assertEqual((t["kind"], t["parent"], t["owner"], t["detail"]),
                         ("gh-imported", "T-001", "Sam", child["body"]))
        self.assertEqual((t["issue_assignee"], t["issue_title"], t["issue_milestone"]),
                         ("sam-gh", "parser 2", "submit"))
        self.assertEqual(len(t["issue_hash"]), 64)
        self.assertFalse(any(c[:3] == ["issue", "edit", "2"] for c in self.calls()))
        self.assertIn("owners (for IDEA.md):", r.stdout)
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(sum(t.get("issue") == 2 for t in self.tasks().values()), 1)

    def test_import_alone_reprints_owners_on_pull_only(self):
        self.vertical_fixture([self.subissue()])
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("owners (for IDEA.md):", r.stdout)
        self.assertIn("#2 parser 2", r.stdout)

    def test_import_is_not_duplicated_after_later_sync_failure(self):
        self.vertical_fixture([self.subissue()])
        self.env["GH_FAIL_ARG"] = "repos/o/hk/collaborators?per_page=100"
        failed = self.sync()
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(sum(t.get("issue") == 2 for t in self.tasks().values()), 1)
        del self.env["GH_FAIL_ARG"]
        recovered = self.sync()
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(sum(t.get("issue") == 2 for t in self.tasks().values()), 1)

    def test_dry_run_shows_import_without_changing_board(self):
        self.vertical_fixture([self.subissue()])
        r = self.sync("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would import #2 under #1", r.stdout)
        self.assertEqual(len(self.tasks()), 1)

    def test_draft_imports_after_draft_label_is_removed(self):
        child = self.subissue(labels=("task", "draft"))
        self.vertical_fixture([child])
        self.assertEqual(self.sync("--pull-only").returncode, 0)
        self.assertEqual(len(self.tasks()), 1)
        child["labels"] = [{"name": "task"}]
        (self.stub / "subissues-1.json").write_text(json.dumps([child]))
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue"], 2)

    def test_subissue_of_non_vertical_is_not_imported(self):
        self.vertical_fixture([self.subissue()])
        data = json.loads((self.hub / "board.json").read_text())
        del data["tasks"][0]["kind"]
        (self.hub / "board.json").write_text(json.dumps(data))
        self.assertEqual(self.sync("--pull-only").returncode, 0)
        self.assertEqual(len(self.tasks()), 1)
        self.assertFalse(any("/sub_issues" in " ".join(c) for c in self.calls()))

    def test_subissue_files_outside_vertical_warn_and_do_not_import(self):
        child = self.subissue(body="Context: totals\nFiles: expenses/totals/x.py\nDeadline: submit")
        self.vertical_fixture([child])
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("#2 Files: expenses/totals/x.py is outside #1 Files: expenses/parse/, tests/parse/", r.stdout)
        self.assertEqual(len(self.tasks()), 1)

    def test_empty_files_heading_does_not_use_next_heading_as_an_area(self):
        child = self.subissue(body="Context: parser\nFiles:\nApproach: expenses/parse/\nDeadline: submit")
        self.vertical_fixture([child], detail="Context: area\nFiles:\nApproach: expenses/parse/\nDeadline: submit")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.tasks()), 1)
        self.assertIn("is outside", r.stdout)

    def test_github_form_files_and_deadline_import(self):
        area = "### Context\n\narea\n\n### Files\n\nreceipts/parse\n\n### Deadline\n\nsubmit"
        body = "### Context\n\nparser\n\n### Files\n\nreceipts/parse/x.py\n\n### Deadline\n\nsubmit"
        self.vertical_fixture([self.subissue(body=body, milestone=None)], detail=area)
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue_milestone"], "submit")

    def test_multiline_form_files_rejects_outside_path(self):
        body = "### Files\n\nreceipts/parse/\nreceipts/model.py\n\n### Deadline\n\nsubmit"
        self.vertical_fixture([self.subissue(body=body)], detail="### Files\n\nreceipts/parse/")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.tasks()), 1)
        self.assertIn("is outside", r.stdout)

    def test_empty_optional_form_deadline_uses_code_freeze(self):
        body = "### Files\n\nreceipts/parse/x.py\n\n### Deadline\n\n_No response_"
        self.vertical_fixture([self.subissue(body=body, milestone=None)],
                              detail="### Files\n\nreceipts/parse/")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue_milestone"], "code freeze")

    def test_markdown_file_paths_import(self):
        children = [self.subissue(number=2, body="Files: `receipts/parse/csv.py`"),
                    self.subissue(number=3, body="### Files\n\n- receipts/parse/x.py"),
                    self.subissue(number=4, body="### Files\n\n* `receipts/parse/y.py`")]
        self.vertical_fixture(children, detail="### Files\n\n- `receipts/parse/`")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({t.get("issue") for t in self.tasks().values()}, {1, 2, 3, 4})

    def test_area_without_trailing_slash_admits_descendant(self):
        self.vertical_fixture([self.subissue(body="Files: receipts/parse/x.py")],
                              detail="Files: receipts/parse")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue"], 2)

    def test_subissue_files_inside_normalized_comma_areas_import(self):
        child = self.subissue(body="Context: parser\nFiles: expenses/parse/lexer.py, tests/parse/ \nDeadline: submit")
        self.vertical_fixture([child], detail="Context: area\nFiles: expenses/parse/ , tests/parse/  \nDeadline: submit")
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["issue"], 2)

    def test_subissue_maps_known_dep_and_warns_once_for_unknown_dep(self):
        child = self.subissue(body="Context: parser\nFiles: expenses/parse/\nDeadline: submit\nDepends on: #3, #99, #99")
        self.vertical_fixture([child])
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"].append({"id": "T-003", "title": "precondition", "detail": "Context: pre\nDeadline: submit",
                              "status": "done", "owner": "Sam", "deps": [], "project": "hk", "notes": [], "issue": 3})
        data["next_id"] = 4
        (self.hub / "board.json").write_text(json.dumps(data))
        issues = json.loads((self.stub / "issues.json").read_text())
        issues.append({"number": 3, "title": "precondition", "state": "CLOSED", "stateReason": "COMPLETED",
                       "assignees": [], "labels": [{"name": "task"}], "body": "Context: pre", "url": "u3"})
        (self.stub / "issues.json").write_text(json.dumps(issues))
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-004"]["deps"], ["T-003"])
        self.assertEqual(r.stdout.count("Depends on: #99 is not on the hub"), 1)

    def test_imported_subissue_keeps_agent_and_owner_edit_flow(self):
        child = self.subissue(labels=("task", "agent:hermes"))
        self.vertical_fixture([child])
        self.assertEqual(self.sync().returncode, 0)
        t = self.tasks()["T-002"]
        self.assertEqual((t["owner"], t["agent"], t["issue_agent"]), ("Sam", "Hermes", "hermes"))
        issues = json.loads((self.stub / "issues.json").read_text())
        issues[1]["body"] = "Context: better parser\nFiles: expenses/parse/, tests/parse/\nDeadline: submit"
        (self.stub / "issues.json").write_text(json.dumps(issues))
        self.editor("sam-gh")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tasks()["T-002"]["detail"], issues[1]["body"])
        self.assertFalse(any(c[:3] == ["issue", "edit", "2"] for c in self.calls()))

    def test_replanned_imported_subissue_updates_body_without_hub_marker(self):
        self.vertical_fixture([self.subissue()])
        self.assertEqual(self.sync().returncode, 0)
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][1]["detail"] = "Context: revised\nFiles: expenses/parse/\nDeadline: submit"
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(c[:3] == ["issue", "edit", "2"] for c in self.calls()))
        bodies = [json.loads(line) for line in (self.stub / "bodies.jsonl").read_text().splitlines()]
        revised = [body for body in bodies if body.startswith("Context: revised")]
        self.assertEqual(len(revised), 1)
        self.assertNotIn("<!-- hub-task:", revised[0])

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

    def test_vertical_issue_has_vertical_label(self):
        self.add_task("T-001", kind="vertical")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("vertical", create[create.index("--label") + 1].split(","))

    def test_init_creates_vertical_and_draft_labels(self):
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        labels = {c[2] for c in self.calls(["label", "create"])}
        self.assertTrue({"vertical", "draft"} <= labels)

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

    def test_human_owner_with_agent_goes_to_human_with_label(self):
        self.add_task("T-001", owner="Alex", agent="Prometheus")
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
        self.assertEqual(json.loads(bodies[0]), body.rstrip() + "\n\n<!-- hub-task: T-001 -->")

    def test_init_creates_everything(self):
        self.use_agents()
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
        clone, _ = self.event_clone()
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

    def event_clone(self, idea=None):
        home = self.hub / "home"
        home.mkdir(exist_ok=True)
        remote = self.hub / "remote.git"
        clone = home / "code" / "hk"
        subprocess.run(["git", "init", "--bare", "-q", "--initial-branch=main", str(remote)], check=True)
        clone.parent.mkdir()
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True,
                       stderr=subprocess.DEVNULL)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com")):
            subprocess.run(["git", "-C", str(clone), "config", key, value], check=True)
        (clone / "README.md").write_text(
            "# <Project name>\n\n<One paragraph: what we're building and who it's for.>\n"
            "1. `gh repo clone <this repo>`\n\n## Architecture\n\n"
            "<!-- the lead adds the C4 diagrams here -->\n")
        (clone / "HACKATHON.md").write_text("# <Event name>\n")
        table = ("# The idea\n\n## Areas and owners\n\n"
                 "| Area | Directories | Owner | Issues |\n|---|---|---|---|\n"
                 "| web | `web/` | — | — |\n| pool | `samples/` | — | — |\n")
        (clone / "IDEA.md").write_text(idea or table)
        (self.hub / "projects" / "hk" / "IDEA.md").write_text(idea or table)
        subprocess.run(["git", "-C", str(clone), "add", "README.md", "HACKATHON.md", "IDEA.md"], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "-qm", "template"], check=True)
        subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main", "main:integration"], check=True)
        self.env["HOME"] = str(home)
        self.write_cfg(board={"number": 9, "url": "https://github.com/users/lead-gh/projects/9", "id": "P9"})
        return clone, remote

    def test_init_fills_and_pushes_event_docs(self):
        clone, remote = self.event_clone()
        self.write_cfg(board={"number": 9, "url": "https://github.com/users/lead-gh/projects/9", "id": "P9"},
                       roster=[{**CFG["roster"][0], "strengths": "architecture", "agents": [{"name": "Zeus"}]},
                               {**CFG["roster"][1], "strengths": "web design", "designer": True, "tool": "Codex"}])
        (self.hub / "projects" / "hk" / "c4_context.png").write_bytes(b"PNG")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        def show(branch, path):
            return subprocess.run(["git", "--git-dir", str(remote), "show", f"{branch}:{path}"],
                                  check=True, capture_output=True, text=True).stdout
        hackathon = show("integration", "HACKATHON.md")
        self.assertIn("# Hack Day", hackathon)
        self.assertIn("| code freeze | 2026-10-04T14:00+01:00 | 2026-10-04T13:00Z |", hackathon)
        self.assertIn("| Alex | @lead-gh | lead, architecture |", hackathon)
        self.assertIn("| Sam | @sam-gh | designer, web design |", hackathon)
        self.assertIn("The lead's agents: Zeus.", hackathon)
        self.assertIn("Board: https://github.com/users/lead-gh/projects/9", hackathon)
        readme = show("integration", "README.md")
        self.assertIn("# Sample App", readme)
        self.assertIn("gh repo clone o/hk", readme)
        self.assertIn("docs/architecture/c4_context.png", readme)
        self.assertEqual(show("integration", "IDEA.md"), (self.hub / "projects" / "hk" / "IDEA.md").read_text())
        self.assertEqual(show("main", "README.md"), readme)
        self.assertEqual(subprocess.run(["git", "--git-dir", str(remote), "show", "integration:docs/architecture/c4_context.png"],
                                        check=True, capture_output=True).stdout, b"PNG")

    def test_init_retry_finishes_main_push_after_docs_commit(self):
        clone, remote = self.event_clone()
        self.assertEqual(self.sync("--init").returncode, 0)
        subprocess.run(["git", "-C", str(clone), "push", "-q", "--force", "origin", "main:main"], check=True)
        before = subprocess.run(["git", "--git-dir", str(remote), "show", "main:HACKATHON.md"],
                                check=True, capture_output=True, text=True).stdout
        self.assertIn("<Event name>", before)
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = subprocess.run(["git", "--git-dir", str(remote), "show", "main:HACKATHON.md"],
                               check=True, capture_output=True, text=True).stdout
        self.assertIn("# Hack Day", after)

    def test_init_placeholder_stops_before_push(self):
        idea = "# The idea\n\n<feature>\n"
        _, remote = self.event_clone(idea)
        before = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"],
                                check=True, capture_output=True, text=True).stdout
        r = self.sync("--init")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("IDEA.md", r.stderr)
        self.assertIn("<feature>", r.stderr)
        after = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"],
                               check=True, capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_init_broken_c4_link_stops_before_push(self):
        clone, remote = self.event_clone()
        readme = clone / "README.md"
        readme.write_text(readme.read_text() + "\n![Missing](docs/architecture/c4_missing.png)\n")
        subprocess.run(["git", "-C", str(clone), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "-qm", "broken link"], check=True)
        subprocess.run(["git", "-C", str(clone), "push", "-q", "origin", "main:integration"], check=True)
        before = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "integration"],
                                check=True, capture_output=True, text=True).stdout
        r = self.sync("--init")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("c4_missing.png", r.stderr)
        after = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "integration"],
                               check=True, capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_dry_run_init_describes_docs_without_writing(self):
        clone, remote = self.event_clone()
        before = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "integration"],
                                check=True, capture_output=True, text=True).stdout
        r = self.sync("--init", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would fill IDEA.md, HACKATHON.md, README.md", r.stdout)
        self.assertIn("would commit docs: fill in the event and push integration and main", r.stdout)
        self.assertIn("<Project name>", (clone / "README.md").read_text())
        after = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "integration"],
                               check=True, capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_sync_updates_idea_owners_table_only_when_changed(self):
        _, remote = self.event_clone()
        self.add_task("T-001", owner="Alex", agent="Zeus", detail="Files: web/\nDeadline: submit")
        self.add_task("T-002", owner="Sam", detail="Files: web/page.html\nDeadline: submit")
        self.add_task("T-003", owner="Pool", detail="Files: samples/\nDeadline: submit")
        self.add_task("T-004", owner="Sam", detail="Files: misc/\nDeadline: submit")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("IDEA.md owners table updated", r.stdout)
        self.assertIn("warning: #4", r.stdout)
        idea = subprocess.run(["git", "--git-dir", str(remote), "show", "integration:IDEA.md"],
                              check=True, capture_output=True, text=True).stdout
        self.assertIn("| web | `web/` | @lead-gh [Zeus], @sam-gh | #1, #2 |", idea)
        self.assertIn("| pool | `samples/` | pool | #3 |", idea)
        main_idea = subprocess.run(["git", "--git-dir", str(remote), "show", "main:IDEA.md"],
                                   check=True, capture_output=True, text=True).stdout
        self.assertIn("| web | `web/` | — | — |", main_idea)
        commits = subprocess.run(["git", "--git-dir", str(remote), "rev-list", "--count", "integration"],
                                 check=True, capture_output=True, text=True).stdout
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("IDEA.md owners table updated", r.stdout)
        again = subprocess.run(["git", "--git-dir", str(remote), "rev-list", "--count", "integration"],
                               check=True, capture_output=True, text=True).stdout
        self.assertEqual(commits, again)
        self.assertEqual(self.sync("--init").returncode, 0)
        main_after = subprocess.run(["git", "--git-dir", str(remote), "show", "main:IDEA.md"],
                                    check=True, capture_output=True, text=True).stdout
        self.assertEqual(main_idea, main_after)

    def test_pool_owner_as_the_hub_stores_it(self):
        self.add_task("T-001", owner="Pool")            # `hub assign T-1 pool` stores "Pool"
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("task,pool", create)
        self.assertNotIn("--assignee", create)

    def test_owner_name_matches_the_hub_spelling(self):
        self.write_cfg(roster=[{"name": "Alex", "github": "lead-gh", "lead": True},
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

    def test_create_accepted_but_unrecorded_is_not_duplicated(self):
        # GitHub creates #1, then gh-sync dies before recording it (lost response, crash).
        self.add_task("T-001")
        self.env["GH_KILL_ON_CREATE"] = "1"
        self.sync()
        self.assertNotIn("issue", self.tasks()["T-001"])
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 1, "title": "title T-001", "state": "OPEN", "stateReason": None,
             "assignees": [], "labels": [{"name": "task"}], "url": "u"}]))
        (self.stub / "body-1.txt").write_text(body)
        del self.env["GH_KILL_ON_CREATE"]
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.calls(["issue", "create"])), 1)     # the lost one only
        self.assertEqual(self.tasks()["T-001"]["issue"], 1)

    def test_body_edit_folded_into_the_hub_clears_the_conflict(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "body-1.txt").write_text("Context: agreed\nDeadline: submit")
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: agreed\nDeadline: submit"   # lead folds the edit in
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertNotIn("not overwriting", r.stdout)
        r = self.sync()                                                   # and it stays settled
        self.assertNotIn("not overwriting", r.stdout)
        self.assertEqual(self.calls(["issue", "edit"]), [])               # GitHub already has it

    def test_dependencies_reach_the_issue(self):
        self.add_task("T-001")
        self.add_task("T-002", deps=["T-001"])
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        bodies = [json.loads(b) for b in (self.stub / "bodies.jsonl").read_text().splitlines()]
        self.assertIn("Depends on: #1", bodies[1])
        self.assertNotIn("Depends on", bodies[0])

    def test_dry_run_init_leaves_an_existing_clone_alone(self):
        home = self.hub / "home"
        clone = home / "code" / "hk"
        clone.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        self.env["HOME"] = str(home)
        r = self.sync("--init", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        email = subprocess.run(["git", "-C", str(clone), "config", "--local", "user.email"],
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(email, "")

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

    def test_two_designers_are_refused_and_named(self):
        self.write_cfg(roster=[{**CFG["roster"][0], "designer": True},
                               {**CFG["roster"][1], "designer": True}])
        r = self.sync("--pull-only")
        self.assertEqual(r.returncode, 1)
        self.assertIn("designer", r.stderr)
        self.assertIn("Alex", r.stderr)
        self.assertIn("Sam", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_init_requires_event_fields_before_github(self):
        for field in ("event", "title", "summary", "smoke"):
            with self.subTest(field=field):
                cfg = {**CFG}
                del cfg[field]
                (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
                (self.stub / "calls.jsonl").unlink(missing_ok=True)
                r = self.sync("--init")
                self.assertEqual(r.returncode, 1)
                self.assertIn(field, r.stderr)
                self.assertEqual(self.calls(), [])
                self.assertEqual(self.sync("--pull-only").returncode, 0)
        self.write_cfg(event="", title="", summary="", smoke="")
        r = self.sync("--init")
        self.assertEqual(r.returncode, 1)
        for field in ("event", "title", "summary", "smoke"):
            self.assertEqual(sum(line.startswith(field + " ") for line in r.stderr.splitlines()), 1)

    def test_designer_without_tool_is_refused_and_named(self):
        for tool in (None, "", "  "):
            with self.subTest(tool=tool):
                designer = {**CFG["roster"][1], "designer": True}
                if tool is not None:
                    designer["tool"] = tool
                self.write_cfg(roster=[CFG["roster"][0], designer])
                r = self.sync("--pull-only")
                self.assertEqual(r.returncode, 1)
                self.assertIn("designer 'Sam' has no AI tool", r.stderr)
                self.assertEqual(self.calls(), [])

    def test_non_boolean_designer_is_refused_and_named(self):
        for value in ("true", 1, None):
            with self.subTest(value=value):
                self.write_cfg(roster=[CFG["roster"][0], {**CFG["roster"][1], "designer": value}])
                r = self.sync("--pull-only")
                self.assertEqual(r.returncode, 1)
                self.assertIn("designer", r.stderr)
                self.assertIn("Sam", r.stderr)
                self.assertEqual(self.calls(), [])

    def test_zero_or_one_designer_is_valid(self):
        for roster in (CFG["roster"], [CFG["roster"][0], {**CFG["roster"][1], "designer": True, "tool": "Codex"}],
                       [CFG["roster"][0], {**CFG["roster"][1], "designer": False}]):
            with self.subTest(roster=roster):
                self.write_cfg(roster=roster)
                r = self.sync("--pull-only")
                self.assertEqual(r.returncode, 0, r.stderr)

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
        # The one write is the project-level FREEZE_AT a first sync pushes; no task is touched.
        self.assertEqual([w for w in self.writes() if w[:2] != ["variable", "set"]], [])
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
        self.write_cfg(repo="o/webapp")
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
        self.add_task("T-001", owner="Alex", issue=1, issue_hash="h", issue_assignee="lead-gh",
                      issue_agent="Zeus",
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
        self.add_task("T-001", owner="Alex", agent="Builder")    # owners are humans; agents are delegates
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        [create] = self.calls(["issue", "create"])
        self.assertIn("task,agent:builder", create)
        self.assertIn("lead-gh", create)                 # hub agents work as the lead's hands
        # an unknown delegate is refused earlier, by `hub delegate` (board.py agents_of)

    def test_init_creates_the_code_dir_on_a_fresh_machine(self):
        home = self.hub / "fresh-home"                  # no ~/code yet
        home.mkdir()
        self.env["HOME"] = str(home)
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((home / "code").is_dir())

    def issue(self, n, body, title=None, assignee="sam-gh"):
        return {"number": n, "title": title or f"title T-00{n}", "state": "OPEN",
                "stateReason": "", "assignees": [{"login": assignee}] if assignee else [],
                "labels": [{"name": "task"}], "url": "u", "body": body}

    def test_github_edit_warns_every_sync_without_a_hub_change(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, "teammate rewrote this\n\n<!-- hub-task: T-001 -->")]))
        for _ in range(2):
            r = self.sync()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("#1 was edited on GitHub; not overwriting", r.stdout)
            self.assertIn("hub edit 1 --take-github", r.stdout)
        self.assertEqual(self.calls(["issue", "edit"]), [])

    def test_warning_counts_a_removed_markdown_rule(self):
        self.add_task("T-001", detail="Context: x\n---\nDeadline: submit")
        self.sync()
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, "Context: x\nDeadline: submit\n\n<!-- hub-task: T-001 -->")]))
        r = self.sync()
        self.assertIn("+0/-1 lines", r.stdout)
        self.assertIn("    ----", r.stdout)

    def test_taking_the_github_brief_adopts_it_with_one_notice(self):
        self.add_task("T-001")
        self.sync()
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, "Context: teammate rewrote this\nDeadline: submit\n\n<!-- hub-task: T-001 -->")]))
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: teammate rewrote this\nDeadline: submit"
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertNotIn("was edited on GitHub", r.stdout)
        self.assertEqual(len(self.calls(["issue", "comment"])), 1)
        self.assertEqual(self.calls(["issue", "edit"]), [])

    def test_keeping_the_hub_brief_overwrites_github_with_one_notice(self):
        import hashlib
        self.add_task("T-001")
        self.sync()
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, "teammate rewrote this\n\n<!-- hub-task: T-001 -->")]))
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["issue_hash"] = hashlib.sha256(b"teammate rewrote this").hexdigest()
        (self.hub / "board.json").write_text(json.dumps(data))
        r = self.sync()
        self.assertNotIn("was edited on GitHub", r.stdout)
        self.assertEqual(len(self.calls(["issue", "edit"])), 1)
        self.assertEqual(len(self.calls(["issue", "comment"])), 1)

    def test_crlf_or_trailing_spaces_are_not_an_edit(self):
        self.add_task("T-001")
        self.sync()
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, body.replace("\n", "  \r\n"))]))
        self.assertNotIn("was edited on GitHub", self.sync().stdout)

    def test_deleting_only_the_marker_is_not_an_edit(self):
        self.add_task("T-001")
        self.sync()
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        (self.stub / "issues.json").write_text(json.dumps(
            [self.issue(1, body.replace("<!-- hub-task: T-001 -->", ""))]))
        self.assertNotIn("was edited on GitHub", self.sync().stdout)

    def test_pull_asks_for_bodies(self):
        self.sync()
        fields = [c[c.index("--json") + 1].split(",") for c in self.calls(["issue", "list"])
                  if "--json" in c]
        self.assertTrue(any("body" in f for f in fields), fields)

    def test_owner_list_after_creating_issues(self):
        self.add_task("T-001", owner="Sam")
        self.add_task("T-002", owner="Alex", agent="Zeus")
        self.add_task("T-003", owner="")
        r = self.sync()
        self.assertIn("owners (for IDEA.md):", r.stdout)
        self.assertIn("Sam (@sam-gh): #1 title T-001", r.stdout)
        self.assertIn("Alex (@lead-gh): #2 title T-002 [Zeus]", r.stdout)
        self.assertIn("pool: #3 title T-003", r.stdout)

    def test_no_owner_list_on_a_quiet_sync(self):
        self.add_task("T-001")
        self.sync()
        self.assertNotIn("owners (for IDEA.md):", self.sync().stdout)

    def test_owner_list_after_a_pool_pickup(self):
        self.add_task("T-001", owner="", issue=4, issue_hash="h", issue_assignee=None)
        (self.stub / "issues.json").write_text(json.dumps([
            {"number": 4, "title": "t", "state": "OPEN", "stateReason": "",
             "assignees": [{"login": "sam-gh"}], "labels": [{"name": "pool"}], "url": "u"}]))
        r = self.sync("--pull-only")
        self.assertIn("Sam (@sam-gh): #4", r.stdout)

    def use_agents(self, cfg=AGENT_CFG):
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
        self.env["GH_COLLABORATORS"] = "lead-gh,sam-gh,bot-gh"

    def editor(self, login, older="lead-gh", oldest_first=False):
        # GitHub doesn't document userContentEdits' order, so the code picks the latest editedAt.
        nodes = [{"editedAt": "2026-09-29T11:40:41Z", "editor": {"login": login}},
                 {"editedAt": "2026-09-29T11:27:41Z", "editor": {"login": older}}]
        if oldest_first:
            nodes.reverse()
        (self.stub / "graphql.json").write_text(json.dumps({"data": {"repository": {"issue": {
            "userContentEdits": {"nodes": nodes}}}}}))

    def edited(self, body, labels=("task",), assignee="lead-gh"):
        (self.stub / "issues.json").write_text(json.dumps([{
            "number": 1, "title": "title T-001", "state": "OPEN", "stateReason": "",
            "assignees": [{"login": assignee}], "labels": [{"name": l} for l in labels],
            "url": "u", "body": body}]))

    def test_config_rejects_bad_agents(self):
        for roster, needle in [
            ([{"name": "Alex", "github": "lead-gh", "lead": True, "agents": [{"name": "robin"}]},
              {"name": "Robin", "github": "mx-gh"}], "Robin"),
            ([{"name": "Alex", "github": "lead-gh", "lead": True,
               "agents": [{"name": "Prometheus", "github": "mx-gh"}]},
              {"name": "Robin", "github": "mx-gh"}], "mx-gh"),
            ([{"name": "Alex", "github": "lead-gh", "lead": True, "agents": [{"name": "Zeus"}]},
              {"name": "Robin", "github": "mx-gh", "agents": [{"name": "zeus"}]}], "Zeus")]:
            self.use_agents({**CFG, "roster": roster})
            r = self.sync()
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(needle, r.stderr + r.stdout)

    def test_owner_is_assignee_agent_is_label(self):
        self.use_agents()
        self.add_task("T-001", owner="Alex", agent="Prometheus")
        self.sync()
        create = self.calls(["issue", "create"])[0]
        self.assertEqual(create[create.index("--assignee") + 1], "lead-gh")
        self.assertIn("agent:prometheus", create[create.index("--label") + 1])

    def test_agent_label_added_on_github_is_pulled(self):
        self.use_agents()
        self.add_task("T-001", owner="Alex")
        self.sync()
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        self.edited(body, labels=("task", "agent:zeus"))
        self.sync()
        self.assertEqual(self.tasks()["T-001"]["agent"], "Zeus")

    def test_hub_delegate_adds_agent_label(self):
        self.use_agents()
        self.add_task("T-001", owner="Alex")
        self.sync()
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        self.edited(body)
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["agent"] = "Zeus"
        (self.hub / "board.json").write_text(json.dumps(data))
        self.sync()
        edits = self.calls(["issue", "edit"])
        self.assertTrue(any("agent:zeus" in c for c in edits), edits)
        self.assertEqual(self.tasks()["T-001"]["issue_agent"], "Zeus")

    def test_new_agent_label_is_created_once_before_use(self):
        cfg = {**AGENT_CFG, "roster": [{**AGENT_CFG["roster"][0],
                                        "agents": [*AGENT_CFG["roster"][0]["agents"],
                                                   {"name": "Cursor"}]}, AGENT_CFG["roster"][1]]}
        self.use_agents(cfg)
        self.add_task("T-001", owner="Alex", agent="Cursor")
        self.add_task("T-002", owner="Alex", agent="Cursor")
        self.sync()
        calls = self.calls()
        creates = [i for i, c in enumerate(calls) if c[:3] == ["label", "create", "agent:cursor"]]
        issues = [i for i, c in enumerate(calls) if c[:2] == ["issue", "create"]]
        self.assertEqual(len(creates), 1)
        self.assertEqual(len(issues), 2)
        self.assertLess(creates[0], issues[0])

    def test_pool_claim_by_agent_account_goes_to_its_human(self):
        self.use_agents()
        self.add_task("T-001", owner="", issue=4, issue_hash="h", issue_assignee=None)
        (self.stub / "issues.json").write_text(json.dumps([{
            "number": 4, "title": "t", "state": "OPEN", "stateReason": "",
            "assignees": [{"login": "bot-gh"}, {"login": "lead-gh"}],
            "labels": [{"name": "pool"}], "url": "u"}]))
        self.sync("--pull-only")
        t = self.tasks()["T-001"]
        self.assertEqual((t["owner"], t["agent"]), ("Alex", "Prometheus"))
        self.sync("--pull-only")
        self.assertEqual(self.tasks()["T-001"]["agent"], "Prometheus")

    def test_pool_pickup_removes_agent_account_assignee(self):
        self.use_agents()
        self.add_task("T-001", owner="")
        self.sync()
        body = json.loads((self.stub / "bodies.jsonl").read_text().splitlines()[0])
        (self.stub / "issues.json").write_text(json.dumps([{
            "number": 1, "title": "title T-001", "state": "OPEN", "stateReason": "",
            "assignees": [{"login": "lead-gh"}, {"login": "bot-gh"}],
            "labels": [{"name": "task"}, {"name": "pool"}], "url": "u", "body": body}]))
        self.sync()
        edits = self.calls(["issue", "edit"])
        self.assertTrue(any(c[c.index("--remove-assignee") + 1] == "bot-gh"
                            for c in edits if "--remove-assignee" in c), edits)

    def test_owner_edit_is_adopted_and_lead_told(self):
        self.use_agents()
        self.add_task("T-001", owner="Sam", detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        self.edited("Context: better\nFiles: a/\nDeadline: submit\n\n<!-- hub-task: T-001 -->",
                    assignee="sam-gh")
        self.editor("sam-gh")
        r = self.sync()
        self.assertNotIn("was edited on GitHub", r.stdout)
        self.assertEqual(self.tasks()["T-001"]["detail"], "Context: better\nFiles: a/\nDeadline: submit")
        self.assertEqual(self.calls(["issue", "comment"]), [])
        self.assertIn("Sam edited #1", (self.hub / "inbox" / "Zeus.jsonl").read_text())

    def test_owner_edit_is_adopted_whatever_order_github_lists_edits(self):
        self.use_agents()
        self.add_task("T-001", owner="Sam", detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        self.edited("Context: better\nFiles: a/\nDeadline: submit", assignee="sam-gh")
        self.editor("sam-gh", oldest_first=True)
        self.assertNotIn("was edited on GitHub", self.sync().stdout)

    def test_agent_account_edit_is_adopted(self):
        self.use_agents()
        self.add_task("T-001", owner="Alex", agent="Prometheus",
                      detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        self.edited("Context: y\nFiles: a/\nDeadline: submit", labels=("task", "agent:prometheus"))
        self.editor("bot-gh")
        self.sync()
        self.assertEqual(self.tasks()["T-001"]["detail"], "Context: y\nFiles: a/\nDeadline: submit")

    def test_files_change_by_owner_warns(self):
        self.use_agents()
        self.add_task("T-001", owner="Sam", detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        self.edited("Context: x\nFiles: a/, b/\nDeadline: submit", assignee="sam-gh")
        self.editor("sam-gh")
        r = self.sync()
        self.assertIn("the Files: line changed", r.stdout)
        self.assertEqual(self.tasks()["T-001"]["detail"], "Context: x\nFiles: a/\nDeadline: submit")

    def test_stranger_edit_or_graphql_failure_warns(self):
        self.use_agents()
        self.add_task("T-001", owner="Sam", detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        self.edited("Context: z\nFiles: a/\nDeadline: submit", assignee="sam-gh")
        self.editor("lead-gh")
        self.assertIn("was edited on GitHub", self.sync().stdout)
        (self.stub / "graphql.json").unlink()
        self.assertIn("was edited on GitHub", self.sync().stdout)

    def test_owner_edit_while_hub_also_changed_warns(self):
        self.use_agents()
        self.add_task("T-001", owner="Sam", detail="Context: x\nFiles: a/\nDeadline: submit")
        self.sync()
        data = json.loads((self.hub / "board.json").read_text())
        data["tasks"][0]["detail"] = "Context: lead replanned\nFiles: a/\nDeadline: submit"
        (self.hub / "board.json").write_text(json.dumps(data))
        self.edited("Context: sam\nFiles: a/\nDeadline: submit", assignee="sam-gh")
        self.editor("sam-gh")
        self.assertIn("was edited on GitHub", self.sync().stdout)

    def test_init_invites_agent_accounts(self):
        self.use_agents()
        self.env["GH_REPO_MISSING"] = "1"
        self.sync("--init")
        invited = [c for c in self.calls() if c[:1] == ["api"] and "collaborators/bot-gh" in c[-1]]
        self.assertTrue(invited)
    def test_dry_run_writes_no_lock_and_says_so(self):
        self.add_task("T-001")
        r = self.sync("--dry-run")
        self.assertFalse((self.hub / "projects" / "hk" / ".gh-sync.lock").exists())
        self.assertIn("dry run: nothing changed", r.stdout)

    def test_dry_run_init_says_nothing_changed(self):
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init", "--dry-run")
        self.assertIn("dry run: nothing changed", r.stdout)
        self.assertNotIn("provisioned", r.stdout)
        self.assertFalse((self.hub / "projects" / "hk" / ".gh-sync.lock").exists())

    def test_dry_run_prints_freeze_writes_it_would_make(self):
        self.env["GH_REPO_MISSING"] = "1"
        r = self.sync("--init", "--dry-run")
        self.assertIn("would run: gh variable set FREEZE_AT", r.stdout)
        self.assertIn("would run: gh label create fix", r.stdout)
        self.assertEqual([c for c in self.calls() if c[:2] == ["variable", "set"]], [])

    def test_init_sets_freeze_variable_label_and_required_check(self):
        self.env["GH_REPO_MISSING"] = "1"
        self.sync("--init")
        var = [c for c in self.calls() if c[:2] == ["variable", "set"]]
        self.assertEqual(var[0][2], "FREEZE_AT")
        self.assertIn("2026-10-04T13:00:00Z", var[0])            # CFG's 14:00+01:00 in UTC
        self.assertTrue(any(c[:3] == ["label", "create", "fix"] for c in self.calls()))
        integration = json.loads((self.stub / "protection-integration.json").read_text())
        main = json.loads((self.stub / "protection-main.json").read_text())
        self.assertEqual(integration["required_status_checks"],
                         {"strict": False, "contexts": ["freeze-gate"]})
        self.assertIsNone(main["required_status_checks"])
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        self.assertEqual(cfg["freeze_at_pushed"], "2026-10-04T13:00:00Z")

    def test_moved_freeze_is_pushed_once(self):
        self.add_task("T-001")
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        cfg["freeze_at_pushed"] = "2026-10-04T13:00:00Z"
        cfg["deadlines"][0]["at"] = "2026-10-04T15:00:00+01:00"
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
        self.sync()
        self.sync()
        var = [c for c in self.calls() if c[:2] == ["variable", "set"]]
        self.assertEqual(len(var), 1)
        self.assertIn("2026-10-04T14:00:00Z", var[0])

    def test_freeze_tags_once_and_reruns_stale_gates(self):
        (self.stub / "prs.json").write_text(json.dumps([{"number": 7, "headRefName": "3-x"}]))
        (self.stub / "runs.json").write_text(json.dumps([{"databaseId": 55, "status": "completed"}]))
        r = self.sync("--freeze")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tagged freeze at abc123", r.stdout)
        def posts():
            return [c for c in self.calls() if c[:1] == ["api"] and "POST" in c
                    and "repos/o/hk/git/refs" in c]
        self.assertEqual(len(posts()), 1)
        self.assertTrue(any(x == "ref=refs/tags/freeze" for x in posts()[0]))
        self.assertIn(["run", "rerun", "55", "-R", "o/hk"], self.calls())
        (self.stub / "tag-exists").write_text("")
        r = self.sync("--freeze")
        self.assertIn("freeze tag already set; keeping it", r.stdout)
        self.assertEqual(len(posts()), 1)                        # the first tag is kept

    def test_freeze_does_not_retag_when_the_tag_lookup_fails(self):
        self.env["GH_TAG_ERROR"] = "gh: Bad Gateway (HTTP 502)"
        r = self.sync("--freeze")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("502", r.stderr + r.stdout)
        self.assertEqual([c for c in self.calls() if "POST" in c and "repos/o/hk/git/refs" in c], [])

    def test_freeze_waits_for_a_running_gate_then_reruns_it(self):
        (self.stub / "prs.json").write_text(json.dumps([{"number": 7, "headRefName": "3-x"}]))
        (self.stub / "runs.json").write_text(json.dumps([{"databaseId": 55, "status": "in_progress"}]))
        (self.stub / "run-views.json").write_text(json.dumps(["in_progress", "completed"]))
        self.env["FREEZE_RERUN_WAIT"] = "5"
        self.env["FREEZE_RERUN_POLL"] = "0"
        r = self.sync("--freeze")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(["run", "rerun", "55", "-R", "o/hk"], self.calls())

    def test_freeze_fails_when_a_gate_is_not_refreshed_but_does_the_other_prs(self):
        (self.stub / "prs.json").write_text(json.dumps([{"number": 7, "headRefName": "3-x"},
                                                        {"number": 8, "headRefName": "4-y"}]))
        (self.stub / "runs-3-x.json").write_text(json.dumps([{"databaseId": 55, "status": "in_progress"}]))
        (self.stub / "runs-4-y.json").write_text(json.dumps([{"databaseId": 66, "status": "completed"}]))
        self.env["FREEZE_RERUN_WAIT"] = "0"
        r = self.sync("--freeze")
        self.assertNotEqual(r.returncode, 0)                       # not a false success
        self.assertIn("#7", r.stderr + r.stdout)
        self.assertIn("still running and may have read the old", r.stdout)
        self.assertIn("run hub gh-sync --freeze again", r.stdout)
        self.assertEqual([c for c in self.calls() if c[:2] == ["run", "rerun"]],
                         [["run", "rerun", "66", "-R", "o/hk"]])  # PR #8 still re-run
        listing = next(c for c in self.calls() if c[:2] == ["run", "list"])
        self.assertIn("databaseId,status", listing)

    def test_freeze_waits_on_one_shared_deadline(self):
        prs = [{"number": n, "headRefName": f"{n}-x"} for n in range(1, 6)]
        (self.stub / "prs.json").write_text(json.dumps(prs))
        (self.stub / "runs.json").write_text(json.dumps([{"databaseId": 55, "status": "in_progress"}]))
        self.env["FREEZE_RERUN_WAIT"] = "3"
        self.env["FREEZE_RERUN_POLL"] = "1"
        r = self.sync("--freeze")
        self.assertNotEqual(r.returncode, 0)
        views = [c for c in self.calls() if c[:2] == ["run", "view"]]
        self.assertLessEqual(len(views), 4, "each PR waited its own 3 s instead of sharing one budget")

    def test_freeze_with_no_prs_or_no_runs_is_fine(self):
        self.assertEqual(self.sync("--freeze").returncode, 0)
        (self.stub / "prs.json").write_text(json.dumps([{"number": 7, "headRefName": "3-x"}]))
        self.assertEqual(self.sync("--freeze").returncode, 0)

    def test_init_makes_the_board_from_the_template(self):
        self.env["GH_REPO_MISSING"] = "1"
        (self.stub / "projects.json").write_text(json.dumps({"projects": [
            {"number": 2, "title": "Hackathon board (template)"}]}))
        r = self.sync("--init")
        self.assertIn("board: https://github.com/users/lead-gh/projects/9", r.stdout)
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        self.assertEqual(cfg["board"]["number"], 9)
        self.assertTrue(any(c[:2] == ["project", "edit"] and "PUBLIC" in c for c in self.calls()))

    def test_sync_updates_the_board_and_a_board_error_only_warns(self):
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        cfg["board"] = {"number": 9, "url": "https://github.com/users/lead-gh/projects/9", "id": "P9"}
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
        self.add_task("T-001")
        r = self.sync()                                   # the stub has no project field-list
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: board not updated", r.stdout)
        self.assertIn("would update board", self.sync("--dry-run").stdout)

    def test_board_gets_issues_created_in_the_same_sync(self):
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        cfg["board"] = {"number": 9, "url": "https://github.com/users/lead-gh/projects/9", "id": "P9"}
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
        (self.stub / "fields.json").write_text(json.dumps({"fields": [
            {"id": "S", "name": "Status", "options": [{"id": "t", "name": "Todo"}, {"id": "p", "name": "In progress"},
                                                      {"id": "r", "name": "In review"}, {"id": "d", "name": "Done"}]},
            {"id": "A", "name": "Agent"}, {"id": "D", "name": "Deadline"}]}))
        self.env["GH_LIST_CREATED"] = "1"
        self.add_task("T-001")
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        adds = [c for c in self.calls() if c[:2] == ["project", "item-add"]]
        self.assertEqual(len(adds), 1, r.stdout)
        self.assertIn("https://github.com/o/hk/issues/1", adds[0])

    def test_freeze_pushes_a_moved_freeze_time_first(self):
        cfg = json.loads((self.hub / "projects" / "hk" / "hackathon.json").read_text())
        cfg["freeze_at_pushed"] = "2026-10-04T13:00:00Z"
        cfg["deadlines"][0]["at"] = "2026-10-04T15:00:00+01:00"
        (self.hub / "projects" / "hk" / "hackathon.json").write_text(json.dumps(cfg))
        self.assertEqual(self.sync("--freeze").returncode, 0)
        calls = self.calls()
        var = [i for i, c in enumerate(calls) if c[:2] == ["variable", "set"]]
        tag = [i for i, c in enumerate(calls) if "POST" in c and "repos/o/hk/git/refs" in c]
        self.assertTrue(var and tag and var[0] < tag[0], calls)
        self.assertIn("2026-10-04T14:00:00Z", calls[var[0]])


if __name__ == "__main__":
    unittest.main()
