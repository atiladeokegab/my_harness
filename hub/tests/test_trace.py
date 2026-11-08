"""hub trace (T-573; living-spec design section 2) on a temp hub and a tiny product repo. Never reads the live hub.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT uv run python -m unittest tests.test_trace

Project demo: C-001 adds R-2 / A-2.1, C-002 removes R-2 (the C-003 / C-006 shape), C-003 adds R-3 / A-3.1. T-101 built
A-3.1 (merge_sha, PR #7 merge_event, Task:/Req: trailers on origin/main); T-102 cites the removed A-2.1; T-103 is done
with nothing that says where it landed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
STRIP = ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME", "GIT_DIR", "GIT_WORK_TREE")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=1))


def tree_digest(root):
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            h.update(str(p).encode() + p.read_bytes())
    return h.hexdigest()


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.hub = self.tmp / "hub"
        spec = self.hub / "projects" / "demo" / "spec"
        changes = {
            "C-001": {"id": "C-001", "base_version": 1, "modified": [], "removed": [], "reason": "add x",
                      "added": [{"id": "R-2", "title": "X endpoint", "needs": [],
                                 "acceptance": [{"id": "A-2.1", "text": "GET /x returns {x}"}]}]},
            "C-002": {"id": "C-002", "base_version": 2, "added": [], "modified": [], "removed": ["R-2"],
                      "reason": "R-2 duplicates R-1"},
            "C-003": {"id": "C-003", "base_version": 3, "modified": [], "removed": [], "reason": "add sum",
                      "added": [{"id": "R-3", "title": "Sum endpoint", "needs": [],
                                 "acceptance": [{"id": "A-3.1", "text": "GET /sum returns {sum}"}]}]},
        }
        line = lambda aid, text: {"id": aid, "v": 1, "text": text, "test": f"tests/acceptance/test_{aid}.py"}
        git(self.tmp, "init", "-q", str(self.hub))
        for v in (1, 2, 3, 4):
            reqs = [{"id": "R-1", "title": "Ping", "needs": [], "acceptance": [line("A-1.1", "GET /ping")]}]
            if v == 2:
                reqs.append({"id": "R-2", "title": "X endpoint", "needs": [],
                             "acceptance": [line("A-2.1", "GET /x returns {x}")]})
            if v == 4:
                reqs.append({"id": "R-3", "title": "Sum endpoint", "needs": [],
                             "acceptance": [line("A-3.1", "GET /sum returns {sum}")]})
            write(spec / "requirements.json", {"version": v, "requirements": reqs})
            if v > 1:
                cid = f"C-{v - 1:03d}"
                cpath = spec / "changes" / f"{cid}.json"
                write(cpath, changes[cid])
                write(spec / "reviews" / f"{cid}-review.json", {
                    "name": f"{cid}-review", "decision": "approve", "note": "approved by the lead",
                    "at": "2026-10-19T11:07:10+00:00", "approved_path": str(cpath.resolve()),
                    "approved_sha256": hashlib.sha256(cpath.read_bytes()).hexdigest()})
            git(self.hub, "add", "-A")
            git(self.hub, "commit", "-q", "-m", f"spec demo v{v}: {cid} applied" if v > 1 else "spec demo v1")

        self.repo = self.tmp / "code" / "demo"
        git(self.tmp, "init", "-q", str(self.repo))
        write(self.repo / "app.py", "sum\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "feat: sum (#7)\n\nTask: T-101\nReq: A-3.1@1")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        write(self.repo / "app.py", "sum\nfmt\n")
        git(self.repo, "commit", "-qam", "chore: formatting")
        self.bare = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")

        task = lambda tid, reqs, status, **kw: {"id": tid, "title": f"{tid} title", "status": status,
                                                "owner": "Prometheus", "project": "demo", "reqs": reqs,
                                                "generated_from": "v4", "deps": [], "notes": [], **kw}
        write(self.hub / "board.json", {"next_id": 4, "tasks": [
            task("T-101", ["A-3.1@1"], "done", issue=5, merge_sha=self.sha, agent="Prometheus"),
            task("T-102", ["A-2.1@1"], "open", tags=["stale"]),
            task("T-103", ["A-1.1@1"], "done"),
        ]})
        events = [{"at": "2026-10-19T11:20:00+00:00", "by": "Zeus", "event": "created", "task": "T-101"},
                  {"at": "2026-10-19T11:21:00+00:00", "by": "Prometheus", "event": "claimed", "task": "T-101"},
                  {"at": "2026-10-19T11:58:00+00:00", "by": "Prometheus", "event": "done", "task": "T-101",
                   "note": "built the sum endpoint", "verify": "passed"},
                  {"at": "2026-10-19T11:13:48+00:00", "by": "Zeus", "event": "stale", "task": "T-102",
                   "change": "C-002"}]
        write(self.hub / "events.jsonl", "".join(json.dumps(e) + "\n" for e in events))
        write(self.hub / "projects" / "demo" / "live-state.json", {"merge_events": [
            {"at": "2026-10-19T12:08:07+00:00", "pr": 7, "issue": 5, "event": "merged", "base": "change/C-003",
             "sha": self.sha, "task": "T-101"}]})

    def trace(self, *args, **extra):
        env = {k: v for k, v in os.environ.items() if k not in STRIP}
        env.update(HUB_DIR=str(self.hub), HOME=str(self.tmp), **extra)
        return subprocess.run([sys.executable, str(HUB / "board.py"), "trace", *args], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_line_chain(self):
        before = tree_digest(self.tmp)
        r = self.trace("A-3.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for want in ("A-3.1@1", "GET /sum returns {sum}", "R-3 Sum endpoint", "added by C-003 (v3 -> v4): add sum",
                     "receipt spec/reviews/C-003-review.json, bytes match", "approved by the lead",
                     "C-003 applied", "built by T-101", "claimed", "built the sum endpoint", "PR #7",
                     self.sha[:12], "Req: A-3.1", "fetched"):
            self.assertIn(want, out)
        self.assertEqual(tree_digest(self.tmp), before, "trace wrote something")

    def test_removed_line_shows_add_and_remove(self):
        r = self.trace("A-2.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("added by C-001", r.stdout)
        self.assertIn("removed by C-002 (v2 -> v3): R-2 duplicates R-1", r.stdout)
        self.assertLess(r.stdout.index("added by C-001"), r.stdout.index("removed by C-002"))
        self.assertIn("not in the current spec", r.stdout)
        self.assertIn("cited by T-102", r.stdout)

    def test_missing_receipt_says_not_approved(self):
        self.assertNotIn("NOT approved", self.trace("A-3.1").stdout)
        (self.hub / "projects" / "demo" / "spec" / "reviews" / "C-003-review.json").unlink()
        self.assertIn("NOT approved", self.trace("A-3.1").stdout)

    def test_sha_without_trailer_is_untraced(self):
        r = self.trace(self.bare[:10])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("untraced: no Task: trailer, no merge_sha, no merge_event", r.stdout)
        r = self.trace("T-103")
        self.assertIn("untraced: no Task: trailer, no merge_sha, no merge_event", r.stdout)
        self.assertIn("A-1.1@1", r.stdout)
        self.assertIn("untraced: no change touches A-1.1", r.stdout)

    def test_unknown_id_exits_1(self):
        for ref in ("A-99.1", "R-99", "T-999", "abcdef1234", "#99", "nonsense"):
            self.assertEqual(self.trace(ref).returncode, 1, ref)

    def test_pr_number_via_merge_events(self):
        for ref in ("#7", "PR#7"):
            r = self.trace(ref)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("PR #7", r.stdout)
            self.assertIn("T-101", r.stdout)
            self.assertIn("added by C-003", r.stdout)

    def test_task_and_sha_walk_up(self):
        for ref in ("T-101", self.sha[:8]):
            r = self.trace(ref)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("T-101", r.stdout)
            self.assertIn("added by C-003", r.stdout)
            self.assertIn("approved", r.stdout)

    def test_requirement_walks_its_lines(self):
        r = self.trace("R-2", "--project", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("R-2 X endpoint", r.stdout)
        self.assertIn("A-2.1", r.stdout)
        self.assertIn("removed by C-002", r.stdout)

    def test_same_line_in_two_projects_prints_a_block_each(self):
        write(self.hub / "projects" / "other" / "spec" / "requirements.json", {"version": 1, "requirements": [
            {"id": "R-1", "title": "Other ping", "needs": [],
             "acceptance": [{"id": "A-1.1", "v": 1, "text": "GET /other-ping", "test": "t.py"}]}]})
        r = self.trace("A-1.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[demo]", r.stdout)
        self.assertIn("[other]", r.stdout)
        self.assertLess(r.stdout.index("[demo]"), r.stdout.index("GET /ping"))
        self.assertLess(r.stdout.index("[other]"), r.stdout.index("GET /other-ping"))
        for scoped in (self.trace("A-1.1", "--project", "other"), self.trace("A-1.1", HUB_PROJECT="other")):
            self.assertEqual(scoped.returncode, 0, scoped.stderr)
            self.assertIn("GET /other-ping", scoped.stdout)
            self.assertNotIn("GET /ping", scoped.stdout)
            self.assertNotIn("[other]", scoped.stdout)
        self.assertEqual(self.trace("A-3.1", HUB_PROJECT="other").returncode, 1)  # scoped means scoped

    def test_prd_json_project_is_traced_through_the_rename(self):
        # demo migrates to prd.json; its applied-change history still lives on requirements.json's commits
        spec = self.hub / "projects" / "demo" / "spec"
        git(self.hub, "mv", str(spec / "requirements.json"), str(spec / "prd.json"))
        git(self.hub, "commit", "-q", "-m", "spec demo: migrate to prd.json")
        write(self.hub / "projects" / "other" / "spec" / "prd.json", {"version": 1, "requirements": [
            {"id": "R-1", "title": "Other ping", "needs": [],
             "acceptance": [{"id": "A-1.1", "v": 1, "text": "GET /other-ping", "test": "t.py"}]}]})
        r = self.trace("A-3.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        for want in ("A-3.1@1", "GET /sum returns {sum}", "R-3 Sum endpoint", "C-003 applied", "built by T-101"):
            self.assertIn(want, r.stdout)
        r = self.trace("A-1.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[other]", r.stdout)
        self.assertIn("GET /other-ping", r.stdout)


class StdlibTraceTest(unittest.TestCase):
    def test_board_survives_stdlib_trace_imported_first(self):
        # coverage, profilers and some runners import the stdlib trace before board.py's lazy import runs
        code = ("import sys, trace; assert hasattr(trace, 'Trace'); sys.path.insert(0, sys.argv[1]); import board; "
                "sys.argv = ['hub', '--help']; board.main()")
        env = {k: v for k, v in os.environ.items() if k not in STRIP}
        r = subprocess.run([sys.executable, "-c", code, str(HUB)], env=env, capture_output=True, text=True,
                           timeout=60, cwd=tempfile.gettempdir())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("trace", r.stdout)


if __name__ == "__main__":
    unittest.main()
