"""hub spec on a fixture repo replaying Linkly, a small example product (tests/fixtures/spec_linkly). Never touches the live board.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT uv run python -m unittest tests.test_spec

The spec (5 requirements) and C-001 are in tests/fixtures/spec_linkly. Eight done tasks are merged on main as
commits with Req:/Task: trailers; T-9 is claimed and unbuilt (A-4.2), so section 9's "every unfinished task is
regenerated" has something to bite on. Every file a task writes carries a `# T-n` line, and each acceptance check
is a script that looks for its builders' lines, so a rewind turns exactly the right checks red.
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
FIXTURE = HUB / "tests" / "fixtures" / "spec_linkly"
sys.path.insert(0, str(HUB))
import gh_sync  # noqa: E402
import spec  # noqa: E402  (pure helpers only: its board import points at the live hub)

# (task, cited lines, files: path -> "append" | ("replace", old, new))
TASKS = [
    ("T-1", ["A-1.1@1", "A-2.1@1"], {"app/store.py": "append", "app/models.py": "append"}),
    ("T-2", ["A-1.1@1"], {"app/routes/links.py": "append"}),
    ("T-3", ["A-2.1@1"], {"app/routes/redirect.py": "append"}),
    ("T-4", ["A-3.1@1"], {"app/routes/redirect.py": "append", "app/store.py": "append",
                          "migrations/001_clicks.py": "append", "app/models.py": ("add", "clicks = 'int'")}),
    ("T-5", ["A-3.2@1"], {"app/routes/stats.py": "append"}),
    ("T-6", ["A-4.1@1"], {"app/routes/redirect.py": "append", "app/store.py": "append"}),
    ("T-7", ["A-5.1@1"], {"app/routes/dashboard.py": "append", "web/dashboard.html": "append",
                          "app/models.py": ("replace", "clicks = 'int'", "clicks = 'int'  # on the dashboard")}),
    ("T-8", ["A-5.2@1"], {"web/dashboard.js": "append", "web/dashboard.html": "append"}),
]
CHECKS = {  # line -> [(file, marker)] it needs
    "A-1.1": [("app/routes/links.py", "T-2")],
    "A-2.1": [("app/routes/redirect.py", "T-3"), ("app/store.py", "T-1")],
    "A-3.1": [("app/routes/redirect.py", "T-4")],
    "A-3.2": [("app/routes/stats.py", "T-5")],
    "A-4.1": [("app/routes/redirect.py", "T-6")],
    "A-4.2": [("app/store.py", "ttl")],  # never built: T-9 holds it
    "A-5.1": [("web/dashboard.html", "T-7")],
    "A-5.2": [("web/dashboard.js", "T-8")],
}
# The planted hidden dependency: expiry's check secretly needs the stats endpoint, which C-001 rewinds.
HIDDEN = [("app/routes/stats.py", "T-5")]
CHECK_PY = """import sys
def has(path, marker):
    try:
        return marker in open(path).read()
    except OSError:
        return False
sys.exit(0 if all(has(p, m) for p, m in {need!r}) else 1)
"""


def git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-10-01T12:00:00Z"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def build_repo(repo, hidden=False, check_in=None, trailers=None, squash=()):
    """check_in: {line: task} lands that line's check in the task's commit; trailers: {task: [extra Req:]};
    squash: tasks merged as a squash commit with no trailers at all."""
    check_in, trailers = check_in or {}, trailers or {}
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    def write_check(aid):
        p = repo / spec.default_test(aid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(CHECK_PY.format(need=CHECKS[aid] + (HIDDEN if hidden and aid == "A-4.1" else [])))
    for aid in CHECKS:
        if aid not in check_in:
            write_check(aid)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "acceptance checks for spec v4")
    for task, reqs, files in TASKS:
        for path, op in files.items():
            p = repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            text = p.read_text() if p.exists() else ""
            if op == "append":
                text += f"# {task}\n"
            elif op[0] == "add":
                text += op[1] + "\n"
            else:
                text = text.replace(op[1], op[2])
            p.write_text(text)
        for aid in [a for a, t in check_in.items() if t == task]:
            write_check(aid)
        git(repo, "add", "-A")
        req = "".join(f"\nReq: {r}" for r in reqs + trailers.get(task, []))
        git(repo, "commit", "-q", "-m", f"{task}: build (#{task[2:]})" if task in squash
            else f"{task}: build\n\nTask: {task}{req}")


def task(n, status, reqs, owner=None):
    return {"id": f"T-{n:03d}", "title": f"Linkly task {n}", "detail": "", "status": status, "owner": owner,
            "deps": [], "created_by": "Zeus", "created": "2026-10-01T12:00:00+00:00",
            "updated": "2026-10-01T12:00:00+00:00", "notes": [], "project": "linkly", "reqs": reqs}


class Fixture(unittest.TestCase):
    hidden, check_in, trailers, squash, merge_sha = False, None, None, (), {}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-spec-test-")
        root = Path(self.temp.name)
        self.hub, self.repo = root / "hub", root / "linkly"
        self.spec = self.hub / "projects" / "linkly" / "spec"
        shutil.copytree(FIXTURE, self.spec)
        (self.spec / "spec.lock").write_text(json.dumps(
            {"version": 4, "sha256": hashlib.sha256((self.spec / "requirements.json").read_bytes()).hexdigest()}))
        tasks = [task(i + 1, "done", reqs) for i, (_, reqs, _) in enumerate(TASKS)]
        tasks.append({**task(9, "claimed", ["A-4.2@1"], owner="Prometheus"), "agent": "Hermes"})
        tasks.append({**task(10, "open", []), "project": "other"})  # another project: never touched
        (self.hub / "board.json").write_text(json.dumps({"next_id": 11, "tasks": tasks}))
        (self.hub / "factory.json").write_text(json.dumps({"repos": [{
            "repo": "o/linkly", "shared": ["app/models.py"], "migrations": ["migrations/"],
            "acceptance_cmd": f"{sys.executable} {{test}}"}]}))
        (self.hub / "inbox").mkdir()
        build_repo(self.repo, self.hidden, self.check_in, self.trailers, self.squash)
        if self.merge_sha:  # {board task: [fixture tasks whose commit it records]}, as live_merge will
            sha = lambda n: git(self.repo, "log", "--format=%H", f"--grep=^{n}: build", "main").strip()
            board = json.loads((self.hub / "board.json").read_text())
            for t in board["tasks"]:
                if t["id"] in self.merge_sha:
                    t["merge_sha"] = [sha(n)[:7] for n in self.merge_sha[t["id"]]]
            (self.hub / "board.json").write_text(json.dumps(board))
        self.origin = root / "origin.git"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "origin", "main")
        self.approve("C-001")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("HUB_") and k != "CLAUDE_CODE_SESSION_NAME"}
        self.env.update(HUB_DIR=str(self.hub), HUB_AGENT="Zeus")

    def tearDown(self):
        self.temp.cleanup()

    def hub_spec(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(HUB / "board.py"), "spec", *args, "--project", "linkly",
                            "--repo", str(self.repo)], env=self.env, capture_output=True, text=True, timeout=120)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        else:
            self.assertNotEqual(r.returncode, 0, r.stdout)
        return r.stdout + r.stderr

    def board(self):
        return {t["id"]: t for t in json.loads((self.hub / "board.json").read_text())["tasks"]}

    def radius(self, out):
        lines = out.split("\n")
        i = next(n for n, line in enumerate(lines) if line.startswith("radius:"))
        k = {}
        for line in lines[i + 1:]:
            if not line.startswith("  "):
                break
            unit, reason = line.strip().split("  ", 1)
            k[unit] = reason
        return k

    def approve(self, cid):
        """What `hub review` writes when the lead approves a page whose data-approves names the change file."""
        path = self.spec / "changes" / f"{cid}.json"
        reviews = self.hub / "projects" / "linkly" / "reviews"
        reviews.mkdir(exist_ok=True)
        (reviews / f"{cid}.json").write_text(json.dumps({
            "name": cid, "decision": "approve", "approved_path": str(path),
            "approved_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))

    def write_change(self, change):
        (self.spec / "changes" / f"{change['id']}.json").write_text(json.dumps(change, indent=2))
        self.approve(change["id"])

    def unchanged(self):
        return ((self.hub / "board.json").read_bytes(), (self.spec / "requirements.json").read_bytes(),
                (self.spec / "spec.lock").read_bytes(), git(self.repo, "branch", "--list"),
                git(self.origin, "branch", "--list"))


class SpecTest(Fixture):
    def test_check_passes_then_catches_each_problem(self):
        self.assertIn("spec ok: linkly v4, 8 acceptance lines", self.hub_spec("check"))
        (self.repo / "tests/acceptance/test_A_4_2.py").rename(self.repo / "tests/acceptance/test_A_9_9.py")
        out = self.hub_spec("check", ok=False)
        self.assertIn("A-4.2: test file missing: tests/acceptance/test_A_4_2.py", out)
        self.assertIn("tests/acceptance/test_A_9_9.py maps to no active acceptance line", out)
        req = json.loads((self.spec / "requirements.json").read_text())
        req["requirements"][4]["needs"] = ["R-9"]
        (self.spec / "requirements.json").write_text(json.dumps(req))
        out = self.hub_spec("check", ok=False)
        self.assertIn("R-5 needs unknown R-9", out)
        self.assertIn("spec.lock: sha256 does not match", out)

    def test_radius_is_exactly_T5_T7_T8_and_repeats_byte_identical(self):
        out = self.hub_spec("impact", "C-001")
        self.assertEqual(self.radius(out), {"T-005": "cites A-3.2@1 (modified)",
                                            "T-007": "cites A-5.1@1 (modified)",
                                            "T-008": "entangled with T-007 via web/dashboard.html"})
        self.assertIn("radius: 3 of 8 done tasks", out)
        self.assertIn("(approved, receipt reviews/C-001.json)", out)
        self.assertIn("migrations kept: -", out)
        self.assertIn("suspect, re-verify: R-5", out)
        self.assertEqual(out, self.hub_spec("impact", "C-001"))
        before = (self.hub / "board.json").read_bytes(), (self.spec / "requirements.json").read_bytes()
        dry = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertEqual(dry, self.hub_spec("rewind", "C-001", "--dry-run"))
        self.assertEqual(self.radius(dry), self.radius(out))
        self.assertIn("4 of 4 kept checks green", dry)
        self.assertNotIn("hidden dependency", dry)
        self.assertIn("dry run: nothing written", dry)
        self.assertEqual(before, ((self.hub / "board.json").read_bytes(), (self.spec / "requirements.json").read_bytes()))
        self.assertNotIn("change/C-001", git(self.repo, "branch", "--list"))

    def test_apply_refuses_an_unapproved_change(self):
        path = self.spec / "changes" / "C-001.json"
        change = json.loads(path.read_text())
        change["reason"] += " (edited after approval)"
        path.write_text(json.dumps(change))
        before = (self.hub / "board.json").read_bytes()
        self.assertIn("C-001 is not approved", self.hub_spec("apply", "C-001", ok=False))
        self.assertEqual(before, (self.hub / "board.json").read_bytes())
        self.assertEqual(json.loads((self.spec / "requirements.json").read_text())["version"], 4)

    def test_a_self_hash_without_a_receipt_is_refused(self):
        (self.hub / "projects" / "linkly" / "reviews" / "C-001.json").unlink()
        path = self.spec / "changes" / "C-001.json"
        change = json.loads(path.read_text())
        body = json.dumps(change, sort_keys=True, separators=(",", ":")).encode()
        change["approved_sha256"] = hashlib.sha256(body).hexdigest()  # anyone with write access can do this
        path.write_text(json.dumps(change, indent=2))
        before = self.unchanged()
        self.assertIn("C-001 is not approved: no `hub review` receipt", self.hub_spec("apply", "C-001", ok=False))
        self.assertEqual(before, self.unchanged())

    def test_a_write_tree_failure_leaves_no_branch_and_nothing_written(self):
        before = self.unchanged()
        boom = ("import sys; sys.path.insert(0, sys.argv[1]); import board, spec\n"
                "def boom(*a, **k):\n"
                "    with board.board(write=True) as (data, events):\n"
                "        data['tasks'] = []\n"
                "        raise SystemExit('boom')\n"
                "spec.write_tree = boom\n"
                "sys.argv = ['hub'] + sys.argv[2:]\n"
                "board.main()\n")
        r = subprocess.run([sys.executable, "-c", boom, str(HUB), "spec", "apply", "C-001", "--project", "linkly",
                            "--repo", str(self.repo)], env=self.env, capture_output=True, text=True, timeout=120)
        self.assertIn("boom", r.stderr)
        self.assertEqual(before, self.unchanged())  # no change/C-001 locally or on origin

    def test_a_push_that_times_out_after_landing_is_deleted_from_origin(self):
        hook = self.origin / "hooks" / "post-receive"  # origin takes the ref, then hangs; deletes pass
        hook.write_text("#!/bin/sh\nread old new ref\n[ \"$new\" = 0000000000000000000000000000000000000000 ] "
                        "|| sleep 4\n")
        hook.chmod(0o755)
        before = self.unchanged()
        slow = ("import sys; sys.path.insert(0, sys.argv[1]); import board, spec\n"
                "spec.NET_TIMEOUT = 2\n"
                "sys.argv = ['hub'] + sys.argv[2:]\n"
                "board.main()\n")
        r = subprocess.run([sys.executable, "-c", slow, str(HUB), "spec", "apply", "C-001", "--project", "linkly",
                            "--repo", str(self.repo)], env=self.env, capture_output=True, text=True, timeout=120)
        self.assertIn("timed out after 2s", r.stderr)
        self.assertEqual(before, self.unchanged())

    def test_apply_refuses_when_origin_has_the_branch_or_is_unreachable(self):
        git(self.repo, "push", "-q", "origin", "main:change/C-001")
        before = self.unchanged()
        self.assertIn("change/C-001 already exists on it", self.hub_spec("apply", "C-001", ok=False))
        self.assertEqual(before, self.unchanged())
        git(self.origin, "branch", "-q", "-D", "change/C-001")
        git(self.repo, "remote", "set-url", "origin", str(self.origin) + "-missing")
        before = self.unchanged()
        self.assertIn("origin unreachable", self.hub_spec("apply", "C-001", ok=False))
        self.assertEqual(before, self.unchanged())

    def test_a_failed_notice_keeps_the_apply_and_is_reported(self):
        boom = ("import sys; sys.path.insert(0, sys.argv[1]); import board\n"
                "def boom(agent, text, message_id=None):\n"
                "    raise OSError('inbox is read-only')\n"
                "board.deliver = boom\n"
                "sys.argv = ['hub'] + sys.argv[2:]\n"
                "board.main()\n")
        r = subprocess.run([sys.executable, "-c", boom, str(HUB), "spec", "apply", "C-001", "--project", "linkly",
                            "--repo", str(self.repo)], env=self.env, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("C-001 is applied, but these superseded notices failed", r.stderr)
        self.assertIn("Hermes: inbox is read-only", r.stderr)
        self.assertIn("stale", self.board()["T-009"]["tags"])
        self.assertEqual(json.loads((self.spec / "requirements.json").read_text())["version"], 5)
        self.assertEqual(json.loads((self.spec / "spec.lock").read_text())["version"], 5)
        self.assertIn("change/C-001", git(self.repo, "branch", "--list"))

    def test_init_writes_v1_and_its_lock(self):
        run = lambda *a: subprocess.run([sys.executable, str(HUB / "board.py"), "spec", "init", *a],
                                        env=self.env, capture_output=True, text=True, timeout=60)
        r = run("fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.hub / "projects" / "fresh" / "spec"
        self.assertEqual(json.loads((d / "requirements.json").read_text()), {"requirements": [], "version": 1})
        self.assertEqual(json.loads((d / "spec.lock").read_text())["sha256"],
                         hashlib.sha256((d / "requirements.json").read_bytes()).hexdigest())
        self.assertIn("already has a spec", run("fresh").stderr)
        seed = self.hub / "seed.json"
        seed.write_text((FIXTURE / "requirements.json").read_text())
        self.assertEqual(run("seeded", "--from", str(seed)).returncode, 0)
        seeded = json.loads((self.hub / "projects" / "seeded" / "spec" / "requirements.json").read_text())
        self.assertEqual((seeded["version"], len(seeded["requirements"])), (1, 5))
        seed.write_text(json.dumps({"requirements": [{"id": "R-1", "title": "x", "needs": ["R-2"]}]}))
        self.assertIn("R-1 needs unknown R-2", run("bad", "--from", str(seed)).stderr)
        self.assertFalse((self.hub / "projects" / "bad").exists())

    def test_checks_time_out_red_and_never_see_the_hub(self):
        (self.repo / "tests/acceptance/test_A_1_1.py").write_text("import time\ntime.sleep(30)\n")
        (self.repo / "tests/acceptance/test_A_2_1.py").write_text(
            "import os, sys\nsys.exit(1 if {'HUB_DIR', 'HUB_AGENT'} & set(os.environ) else 0)\n")
        git(self.repo, "commit", "-qam", "checks: slow and env-sensitive")
        git(self.repo, "push", "-q", "origin", "main")
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["repos"][0]["acceptance_timeout"] = 1
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertIn("hidden dependency: A-1.1", out)
        self.assertNotIn("A-2.1 red", out)
        self.assertIn("3 of 4 kept checks green", out)

    def test_apply_regenerates_the_whole_tree(self):
        out = self.hub_spec("apply", "C-001")
        # PRD v5 and its lock
        req = json.loads((self.spec / "requirements.json").read_text())
        self.assertEqual(req["version"], 5)
        v = {a["id"]: a["v"] for r in req["requirements"] for a in r["acceptance"]}
        self.assertEqual((v["A-3.2"], v["A-3.3"], v["A-5.1"], v["A-5.2"]), (2, 1, 2, 1))
        lock = json.loads((self.spec / "spec.lock").read_text())
        built = lambda n: git(self.repo, "log", "--format=%H", f"--grep=^{n}: build", "main").strip()
        self.assertEqual(lock, {"version": 5, "change": "C-001", "sha256": hashlib.sha256(
            (self.spec / "requirements.json").read_bytes()).hexdigest(),  # rewound: never walked again
            "rewound": {"C-001": [built("T-8"), built("T-7"), built("T-5")]}})
        # change/C-001: one rewind commit on main; kept work intact
        self.assertEqual(git(self.repo, "log", "--format=%s", "main..change/C-001").splitlines(),
                         ["Rewind for C-001: T-005, T-007, T-008"])
        tree = git(self.repo, "ls-tree", "-r", "--name-only", "change/C-001").split()
        for gone in ("app/routes/stats.py", "web/dashboard.js", "web/dashboard.html", "app/routes/dashboard.py"):
            self.assertNotIn(gone, tree)
        self.assertIn("migrations/001_clicks.py", tree)
        self.assertEqual(git(self.repo, "show", "change/C-001:app/routes/redirect.py"), "# T-3\n# T-4\n# T-6\n")
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD").strip(), "main")
        self.assertEqual(git(self.origin, "rev-parse", "change/C-001"), git(self.repo, "rev-parse", "change/C-001"))
        # the tree: carried over, stale, regenerated
        b = self.board()
        for tid in ("T-001", "T-002", "T-003", "T-004", "T-006"):
            self.assertEqual(b[tid]["status"], "done")
            self.assertNotIn("stale", b[tid].get("tags") or [])
            self.assertEqual(b[tid]["generated_from"], "v5")
        self.assertEqual(b["T-001"]["reqs"], ["A-1.1@1", "A-2.1@1"])
        for tid, status in (("T-005", "done"), ("T-007", "done"), ("T-008", "done"), ("T-009", "claimed")):
            self.assertEqual(b[tid]["status"], status)
            self.assertIn("stale", b[tid]["tags"])
            self.assertEqual(b[tid]["notes"][-1]["text"], "superseded by C-001")
        self.assertNotIn("tags", b["T-010"])  # another project's task
        new = {tid: t for tid, t in b.items() if t.get("created_by") == "Zeus" and t["created"] != b["T-001"]["created"]}
        self.assertEqual(sorted(new), ["T-011", "T-012", "T-013", "T-014"])
        self.assertEqual([(new[t]["reqs"], new[t]["deps"], new[t]["owner"]) for t in sorted(new)], [
            (["A-3.2@2", "A-3.3@1", "A-5.1@2"], [], "Zeus"),       # check-writer first
            (["A-3.2@2", "A-3.3@1"], ["T-011"], None),
            (["A-4.2@1"], ["T-011"], None),                        # T-9's unfinished line, regenerated
            (["A-5.1@2", "A-5.2@1"], ["T-011", "T-012"], None),    # R-5 needs R-3
        ])
        self.assertTrue(all(t["generated_from"] == "v5" and t["status"] == "open" for t in new.values()))
        self.assertTrue(all(t.get("kind") == "factory" for t in new.values()))  # claimable by a builder
        self.assertTrue(all(t["verify"] == "make check && hub spec check --project linkly --repo ." for t in new.values()))
        self.assertNotIn("clicks", "".join(t["title"] + t["detail"] for t in new.values()))
        files = {t: gh_sync.file_paths(new[t]["detail"]) for t in sorted(new)}  # the rewound commits' files
        self.assertEqual(files, {"T-011": [], "T-012": ["app/routes/stats.py"], "T-013": [],  # T-9 built nothing
                                 "T-014": ["app/models.py", "app/routes/dashboard.py", "web/dashboard.html",
                                           "web/dashboard.js"]})
        self.assertIn("`make check`", new["T-011"]["detail"])  # the check-writer lints its checks too
        self.assertIn("superseded by C-001", (self.hub / "inbox" / "Hermes.jsonl").read_text())  # hb.actor
        self.assertIn("applied C-001: spec v5", out)
        self.assertIn("written against v4, the spec is v5", self.hub_spec("apply", "C-001", ok=False))

    def test_apply_keeps_migrations_and_reconciles_shared_files(self):
        self.write_change({"id": "C-002", "base_version": 4, "added": [], "removed": [],
                           "modified": [{"id": "A-3.1", "text": "total rises by one per unique redirect"}],
                           "reason": "count unique redirects"})
        out = self.hub_spec("apply", "C-002")
        self.assertEqual(self.radius(out), {"T-004": "cites A-3.1@1 (modified)",
                                            "T-006": "entangled with T-004 via app/routes/redirect.py"})
        self.assertIn("migrations kept: migrations/001_clicks.py", out)
        self.assertIn("shared, rebuild must reconcile: app/models.py", out)
        self.assertEqual(git(self.repo, "show", "change/C-002:migrations/001_clicks.py"), "# T-4\n")
        self.assertEqual(git(self.repo, "show", "change/C-002:app/store.py"), "# T-1\n")
        self.assertEqual(git(self.repo, "show", "change/C-002:app/models.py"),
                         "# T-1\nclicks = 'int'  # on the dashboard\n")
        new = {t["title"].split()[0]: t for t in self.board().values() if t.get("generated_from") == "v5"
               and t["status"] == "open"}
        self.assertEqual(gh_sync.file_paths(new["R-3"]["detail"]),  # the migration is kept, so not listed
                         ["app/models.py", "app/routes/redirect.py", "app/store.py"])
        self.assertEqual(gh_sync.file_paths(new["R-4"]["detail"]), ["app/routes/redirect.py", "app/store.py"])

    def test_tasks_sharing_files_without_a_needs_edge_are_ordered(self):
        self.write_change({"id": "C-002", "base_version": 4, "added": [], "removed": [],
                           "modified": [{"id": "A-3.1", "text": "total rises by one per unique redirect"}],
                           "reason": "count unique redirects"})
        dry = self.hub_spec("rewind", "C-002", "--dry-run")
        line = ("files shared by R-3 and R-4 without a needs edge: app/routes/redirect.py, app/store.py; "
                "R-4 now waits on R-3")
        self.assertIn(line, dry)
        self.assertIn("deps checks, R-3", dry)
        self.assertEqual(dry, self.hub_spec("rewind", "C-002", "--dry-run"))  # deterministic
        self.assertIn(line, self.hub_spec("apply", "C-002"))
        new = {t["title"].split()[0]: t for t in self.board().values() if t.get("generated_from") == "v5"
               and t["status"] == "open"}
        self.assertIn(new["R-3"]["id"], new["R-4"]["deps"])
        self.assertNotIn(new["R-4"]["id"], new["R-3"]["deps"])

    def test_c001_has_no_overlap_and_no_unowned_file(self):
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertNotIn("files shared by", out)  # R-5 already needs R-3
        self.assertNotIn("no task owns", out)

    def test_a_cascade_only_commit_reports_its_unowned_files(self):
        (self.repo / "web/dashboard.js").write_text((self.repo / "web/dashboard.js").read_text() + "// hotfix\n")
        (self.repo / "web/theme.css").write_text("/* hotfix */\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "hotfix: dashboard theme")  # no Task:, no Req:
        git(self.repo, "push", "-q", "origin", "main")
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertRegex(out, r"\n  [0-9a-f]{12}  entangled with T-008 via web/dashboard.js\n")
        self.assertIn("  rewound files no task owns: web/theme.css\n", out)


class HubCommitTest(Fixture):
    """The hub dir is a git repo: apply commits the spec's exact paths there, nothing else."""

    def setUp(self):
        super().setUp()
        for args in (("init", "-q", "-b", "main"), ("config", "user.name", "hub"),
                     ("config", "user.email", "hub@example.invalid"), ("add", "board.json"), ("commit", "-qm", "hub")):
            git(self.hub, *args)
        (self.hub / "notes.txt").write_text("staged by someone else\n")
        git(self.hub, "add", "notes.txt")

    def test_apply_commits_exactly_the_spec_paths(self):
        self.hub_spec("apply", "C-001")
        self.assertEqual(git(self.hub, "log", "-1", "--format=%s").strip(), "spec linkly v5: C-001 applied")
        self.assertEqual(sorted(git(self.hub, "show", "--name-only", "--format=", "HEAD").split()), [
            "projects/linkly/reviews/C-001.json", "projects/linkly/spec/changes/C-001.json",
            "projects/linkly/spec/requirements.json", "projects/linkly/spec/spec.lock"])
        status = git(self.hub, "status", "--porcelain")
        self.assertIn(" M board.json", status)  # the board is not the spec's to commit
        self.assertIn("A  notes.txt", status)  # someone else's staged work stays staged
        self.assertIn("?? factory.json", status)  # untracked, and no `git add .` swept it in

    def test_spec_already_committed_with_the_same_bytes_is_not_a_failure(self):
        """Hermes on 4b090a7: a re-run after a hand commit has nothing to commit, and that is fine."""
        self.hub_spec("apply", "C-001")
        head = git(self.hub, "rev-parse", "HEAD")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import board as hb, spec
        old = hb.HUB_DIR
        hb.HUB_DIR = str(self.hub)
        try:
            self.assertIs(spec.commit_spec("linkly", "C-001", 5, "reviews/C-001.json"), False)
        finally:
            hb.HUB_DIR = old
        self.assertEqual(git(self.hub, "rev-parse", "HEAD"), head)

    def test_a_failed_commit_is_reported_and_keeps_the_apply(self):
        hook = self.hub / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n")
        hook.chmod(0o755)
        out = self.hub_spec("apply", "C-001", ok=False)
        self.assertIn("C-001 is applied, but committing its spec in the hub failed", out)
        self.assertIn("hook says no", out)
        self.assertEqual(json.loads((self.spec / "requirements.json").read_text())["version"], 5)
        self.assertIn("change/C-001", git(self.repo, "branch", "--list"))
        self.assertEqual(git(self.hub, "log", "-1", "--format=%s").strip(), "hub")


class ChangeLedgerTest(Fixture):
    """Hermes on 4773cc5: what C-001's rewind reverted is skipped only once that rewind is on the walked line."""
    C002 = {"id": "C-002", "base_version": 5, "added": [], "removed": [],
            "modified": [{"id": "A-3.2", "text": "stats returns {total, unique, by_week}"}], "reason": "weekly"}

    def t5(self):
        return git(self.repo, "log", "--format=%H", "--grep=^T-5: build", "main").strip()

    def test_an_abandoned_change_hides_nothing_c002_still_reverts_t5s_original_commit(self):
        self.hub_spec("apply", "C-001")
        self.assertEqual(json.loads((self.spec / "spec.lock").read_text())["rewound"],
                         {"C-001": [git(self.repo, "log", "--format=%H", f"--grep=^{n}: build", "main").strip()
                                    for n in ("T-8", "T-7", "T-5")]})
        git(self.repo, "push", "-q", "origin", "--delete", "change/C-001")  # abandoned: never merged
        self.write_change(self.C002)
        out = self.hub_spec("rewind", "C-002", "--dry-run")
        self.assertIn(f"T-005 {self.t5()[:12]}", out)  # T-5's code is still live, so C-002 reverts it
        self.assertNotIn("has not landed", out)

    def test_apply_is_refused_while_another_change_branch_is_open_on_origin(self):
        self.hub_spec("apply", "C-001")
        self.write_change(self.C002)
        before = self.unchanged()
        self.assertIn("C-001 has not landed: merge or abandon it first", self.hub_spec("apply", "C-002", ok=False))
        self.assertEqual(before, self.unchanged())
        self.assertIn("C-001 has not landed: merge or abandon it first", self.hub_spec("rewind", "C-002", "--dry-run"))
        self.assertIn(f"T-005 {self.t5()[:12]}", self.hub_spec("impact", "C-002"))  # not landed: nothing hidden
        git(self.repo, "merge", "-q", "--no-ff", "-m", "Merge change/C-001: its suite is green", "change/C-001")
        git(self.repo, "push", "-q", "origin", "main")  # landed; its branch is still on origin
        out = self.hub_spec("rewind", "C-002", "--dry-run")
        self.assertNotIn("has not landed", out)
        self.assertNotIn(self.t5()[:12], out)  # C-001's rewind is on the line now: T-5's commit is not live code


class HiddenDependencyTest(Fixture):
    """The same Linkly, but A-4.1's check secretly needs the stats endpoint C-001 rewinds."""
    hidden = True

    def test_planted_hidden_dependency_turns_red_and_joins_the_rebuild(self):
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertEqual(set(self.radius(out)), {"T-005", "T-007", "T-008"})  # T-6 is not reverted
        self.assertIn("3 of 4 kept checks green", out)
        self.assertIn("hidden dependency: A-4.1 red after the rewind; joins the rebuild", out)
        self.assertIn("new [R-4] R-4 expiry: A-4.1@1, A-4.2@1  deps checks", out)
        self.assertIn("carried over: T-001, T-002, T-003, T-004, T-006", out)


class CheckLandedInRewoundCommitTest(Fixture):
    """A-4.1 is kept, but its check landed in T-8's commit, which C-001 rewinds."""
    check_in = {"A-4.1": "T-8"}

    def test_a_kept_check_added_by_a_rewound_commit_is_restored(self):
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        self.assertIn("kept checks restored from the base: tests/acceptance/test_A_4_1.py", out)
        self.assertIn("4 of 4 kept checks green", out)
        self.assertNotIn("hidden dependency", out)

    def test_a_rebuild_never_lists_a_protected_check_in_its_files(self):
        self.hub_spec("apply", "C-001")
        [r5] = [t for t in self.board().values() if t["title"].startswith("R-5") and t["status"] == "open"]
        self.assertEqual(gh_sync.file_paths(r5["detail"]),  # T-8's commit also added tests/acceptance/test_A_4_1.py
                         ["app/models.py", "app/routes/dashboard.py", "web/dashboard.html", "web/dashboard.js"])


class TrailerSeedTest(Fixture):
    """T-6's commit cites A-3.2@1 in a Req: trailer although its board task does not list it."""
    trailers = {"T-6": ["A-3.2@1"]}

    def test_a_req_trailer_citing_a_changed_line_seeds_the_radius(self):
        k = self.radius(self.hub_spec("impact", "C-001"))
        self.assertEqual(set(k), {"T-005", "T-006", "T-007", "T-008"})
        self.assertRegex(k["T-006"], r"^commit [0-9a-f]{12} trailer Req: A-3.2@1 \(modified\)$")


class SquashMergeTest(Fixture):
    """T-5 was squash-merged (no trailers); live_merge recorded its merge_sha. T-6 also claims that commit."""
    squash = ("T-5",)
    merge_sha = {"T-005": ["T-5"], "T-006": ["T-5", "T-6"]}

    def test_merge_sha_maps_a_squash_commit_and_a_shared_commit_counts_for_both(self):
        out = self.hub_spec("rewind", "C-001", "--dry-run")
        k = self.radius(out)
        self.assertEqual(set(k), {"T-005", "T-006", "T-007", "T-008"})
        self.assertRegex(k["T-006"], r"^shares commit [0-9a-f]{12} with T-005$")
        self.assertRegex(out, r"rewind, newest first: T-008 \w+, T-007 \w+, T-006 \w+, T-005\+T-006 \w+\n")


class BootstrapShaTest(Fixture):
    squash = ("T-5",)

    def test_bootstrap_sha_records_merge_sha_once_and_logs_it(self):
        short = git(self.repo, "log", "--format=%h", "--grep=^T-5: build", "main").strip()
        full = git(self.repo, "rev-parse", short).strip()
        out = self.hub_spec("impact", "C-001")
        self.assertIn("T-005", self.radius(out))
        self.assertNotRegex(out, r"T-005 [0-9a-f]{12}")  # in K, but the squash commit is nobody's: nothing reverts
        before = self.unchanged()
        self.assertIn("is not a commit", self.hub_spec("bootstrap-sha", "T-5=deadbeef", ok=False))
        git(self.repo, "checkout", "-q", "-b", "side", "main~3")  # a pre-squash tip: a commit, but off the line
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "T-5 work in progress")
        tip = git(self.repo, "rev-parse", "--short", "HEAD").strip()
        git(self.repo, "push", "-q", "origin", "side")
        git(self.repo, "checkout", "-q", "main")
        self.assertIn(f"{tip} is not on origin/main's first-parent line",
                      self.hub_spec("bootstrap-sha", f"T-5={tip}", ok=False))
        before = self.unchanged()
        self.assertIn("no task T-010 in linkly", self.hub_spec("bootstrap-sha", f"T-5={short}", f"T-10={short}",
                                                              ok=False))
        self.assertEqual(before, self.unchanged())
        self.assertIn(f"T-005 merge_sha {full}", self.hub_spec("bootstrap-sha", f"T-5={short}"))
        self.assertEqual(self.board()["T-005"]["merge_sha"], full)
        ev = [json.loads(x) for x in (self.hub / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(e.get("event") == "merge_sha" and e.get("task") == "T-005" and e.get("sha") == full
                            for e in ev))
        self.assertRegex(self.hub_spec("impact", "C-001"), rf"T-005 {full[:12]}")
        other = git(self.repo, "rev-parse", "main~1").strip()
        self.assertIn("already has merge_sha", self.hub_spec("bootstrap-sha", f"T-5={other}", ok=False))


class ConvergeTest(Fixture):
    """The weekly converge reads origin's live line in a fresh clone, never the local checkout, and never the spec."""

    def setUp(self):
        super().setUp()
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["repos"][0]["acceptance_timeout"] = 1
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        acc = self.repo / "tests" / "acceptance"
        (acc / "test_A_1_1.py").unlink()  # line with no test
        (acc / "test_A_9_9.py").write_text("")  # test with no line
        (acc / "test_A_2_1.py").write_text("import time\ntime.sleep(30)\n")  # times out: red
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "drift")
        git(self.repo, "push", "-q", "origin", "main:integration")
        git(self.repo, "reset", "-q", "--hard", "main~1")  # the local checkout has no drift at all

    def test_one_task_per_drift_deduped_by_title_and_the_spec_untouched(self):
        before = (self.spec / "requirements.json").read_bytes(), (self.spec / "spec.lock").read_bytes()
        self.hub_spec("converge")
        new = {tid: t for tid, t in self.board().items() if int(tid[2:]) > 10}
        self.assertEqual(sorted(t["title"] for t in new.values()), [
            "linkly spec drift: A-1.1: test file missing: tests/acceptance/test_A_1_1.py",
            "linkly spec drift: A-2.1@1: acceptance check red on origin/integration: tests/acceptance/test_A_2_1.py",
            "linkly spec drift: A-4.2@1: acceptance check red on origin/integration: tests/acceptance/test_A_4_2.py",
            "linkly spec drift: tests/acceptance/test_A_9_9.py maps to no active acceptance line",
        ])  # A-4.2 was never built (T-9 holds it)
        self.assertTrue(all(t["owner"] == "Zeus" and t["status"] == "open" and t["project"] == "linkly"
                            for t in new.values()))
        self.assertIn("hub spec converge opened", (self.hub / "inbox" / "Zeus.jsonl").read_text())
        out = self.hub_spec("converge")  # a repeat run opens nothing new
        self.assertEqual(len(self.board()), 10 + len(new), out)
        self.assertIn("already open", out)
        self.assertEqual(before, ((self.spec / "requirements.json").read_bytes(), (self.spec / "spec.lock").read_bytes()))
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")


class ConvergeRetryTest(Fixture):
    """A red check is re-run; only red every time opens a task. Every check red is the environment: one task."""

    def setUp(self):
        super().setUp()
        self.count = Path(self.temp.name) / "runs"
        (self.repo / "tests/acceptance/test_A_2_1.py").write_text(  # red, green, red...: flaky
            f"import pathlib, sys\np = pathlib.Path({str(self.count)!r})\nn = int(p.read_text()) if p.exists() else 0\n"
            "p.write_text(str(n + 1))\nsys.exit(1 if n % 2 == 0 else 0)\n")
        git(self.repo, "commit", "-qam", "a flaky check")
        git(self.repo, "push", "-q", "origin", "main:integration")

    def titles(self):
        return sorted(t["title"] for tid, t in self.board().items() if int(tid[2:]) > 10)

    def test_a_flaky_check_is_reported_not_opened(self):
        out = self.hub_spec("converge")
        self.assertEqual(self.titles(), [  # A-4.2 is red every time: never built
            "linkly spec drift: A-4.2@1: acceptance check red on origin/integration: tests/acceptance/test_A_4_2.py"])
        self.assertIn("flaky: A-2.1", out)
        self.assertEqual(self.count.read_text(), "2")  # red, then green: no third run

    def test_every_check_red_opens_one_environment_task(self):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["repos"][0]["acceptance_cmd"] = "false {test}"
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        self.hub_spec("converge")
        self.assertEqual(self.titles(), ["linkly spec drift: converge could not run checks on origin/integration"])


class LiveLineTest(Fixture):
    """origin/integration is the live line; origin/main lags one promotion; the local main is staler still."""

    def setUp(self):
        super().setUp()
        git(self.repo, "push", "-q", "origin", "main:integration")
        git(self.repo, "push", "-q", "--force", "origin", "main~1:main")
        self.integration = git(self.repo, "rev-parse", "main").strip()
        git(self.repo, "reset", "-q", "--hard", "main~2")  # before T-7 and T-8
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/integration")  # apply must fetch it

    def test_the_base_is_origins_integration_never_a_stale_local_ref(self):
        out = self.hub_spec("impact", "C-001")
        self.assertIn(f"base: origin/integration {self.integration[:12]}", out)
        self.assertEqual(set(self.radius(out)), {"T-005", "T-007", "T-008"})
        self.hub_spec("apply", "C-001")
        self.assertEqual(git(self.origin, "rev-parse", "change/C-001^").strip(), self.integration)
        self.assertEqual(git(self.origin, "log", "-1", "--format=%s", "change/C-001").strip(),
                         "Rewind for C-001: T-005, T-007, T-008")

    def test_base_branch_in_factory_json_wins(self):
        cfg = json.loads((self.hub / "factory.json").read_text())
        cfg["repos"][0]["base_branch"] = "main"
        (self.hub / "factory.json").write_text(json.dumps(cfg))
        out = self.hub_spec("impact", "C-001")
        self.assertIn("base: origin/main ", out)
        self.assertEqual(set(self.radius(out)), {"T-005", "T-007"})  # T-8 is not on origin/main yet


if __name__ == "__main__":
    unittest.main()
