"""hub spec on a fixture repo replaying Linkly, a small example product (tests/fixtures/spec_linkly). Never touches the live board.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT uv run python -m unittest tests.test_spec

The spec (5 requirements) and C-001 are in tests/fixtures/spec_linkly. Eight done tasks are merged on main as
commits with Req:/Task: trailers; T-9 is claimed and unbuilt (A-4.2), so section 9's "every unfinished task is
regenerated" has something to bite on. Every file a task writes carries a `# T-n` line, and each acceptance check
is a script that looks for its builders' lines, so a rewind turns exactly the right checks red.
"""

import hashlib
import json
import shlex
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_check_errors_when_prd_json_and_requirements_json_both_exist(self):
        # Two spec files means two sources of truth: the half-migrated project must fail check, not pick one.
        shutil.copy(self.spec / "requirements.json", self.spec / "prd.json")
        out = self.hub_spec("check", ok=False)
        self.assertIn("both prd.json and requirements.json", out)
        self.approve("C-001")
        before = self.unchanged()
        self.assertIn("both prd.json and requirements.json", self.hub_spec("apply", "C-001", ok=False))
        self.assertEqual(before, self.unchanged())

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
        spec_check = "hub spec check --project linkly --repo ."
        for t in new.values():  # its own lines only, never a sibling's unbuilt check, never make check
            tests = [f"tests/acceptance/test_{r.split('@')[0].replace('-', '_').replace('.', '_')}.py" for r in t["reqs"]]
            mine = ",".join(r.split("@")[0] for r in t["reqs"])  # scoped to its own lines (T-747)
            self.assertEqual(t["verify"].split(" && ")[-1], f"{spec_check} --lines {mine}")
            self.assertEqual([x for x in t["verify"].split(" && ")[:-1] if not any(p in x for p in tests)], [])
            self.assertEqual(len(t["verify"].split(" && ")) - 1, len(tests))
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


class HeldoutSpecTest(Fixture):
    """Living spec section 3: held-out checks live in projects/<p>/heldout/, outside spec/, and never reach a brief,
    an issue body or the product repo. hub spec check warns about them; converge runs them on the live line."""

    def heldout(self, index, body="import sys\nprint('HIDDEN-ASSERT')\nsys.exit(1)\n"):
        root = self.hub / "projects" / "linkly" / "heldout"
        for e in index.values():
            for t in e.get("tests", []):
                (root / t).parent.mkdir(parents=True, exist_ok=True)
                (root / t).write_text("# HELDOUT_CANARY_t575 do not copy\n" + body)
        (root / "heldout.json").write_text(json.dumps(index))
        return root

    def in_hub(self):
        return mock.patch.object(gh_sync.hb, "HUB_DIR", str(self.hub))

    def test_stale_heldout_skipped_and_warned(self):
        root = self.heldout({"A-1.1": {"v": 1, "tests": ["A-1.1/test_a.py"]},
                             "A-2.1": {"v": 1, "tests": ["A-2.1/test_b.py", "A-2.1/test_gone.py"]},
                             "A-9.9": {"v": 1, "tests": ["A-9.9/test_c.py"]}})
        (root / "A-2.1" / "test_b.py").write_text("import sys\n")  # no canary
        (root / "A-2.1" / "test_gone.py").unlink()
        req = self.spec / "requirements.json"
        data = json.loads(req.read_text())
        data["requirements"][0]["acceptance"][0]["v"] = 2  # A-1.1 moved on: its held-out check lags
        req.write_text(json.dumps(data))
        (self.spec / "spec.lock").write_text(json.dumps({"version": 4, "sha256": hashlib.sha256(req.read_bytes()).hexdigest()}))
        out = self.hub_spec("check")  # warnings only: check is in every task's verify
        self.assertEqual([x.strip() for x in out.splitlines() if "warning" in x], [
            "warning: held-out A-1.1 (check v1, line v2): skipped by the gate",
            "warning: held-out A-9.9 (check v1, line not active): skipped by the gate",
            "warning: held-out A-2.1: A-2.1/test_b.py has no HELDOUT_CANARY line",
            "warning: held-out A-2.1: A-2.1/test_gone.py missing"])
        self.assertIn("spec ok: linkly", out)
        with self.in_hub():
            self.assertEqual([label for label, _ in gh_sync.heldout_checks("linkly")], ["held-out A-2.1"])

    def test_converge_heldout_red_opens_task_without_content(self):
        git(self.repo, "push", "-q", "origin", "main:integration")
        self.heldout({"A-1.1": {"v": 1, "tests": ["A-1.1/test_red.py"]},
                      "A-2.1": {"v": 1, "tests": ["A-2.1/test_green.py"]}}, body="")
        (self.hub / "projects/linkly/heldout/A-1.1/test_red.py").write_text(
            "# HELDOUT_CANARY_t575\nimport sys\nprint('HIDDEN-ASSERT')\nsys.exit(1)\n")
        out = self.hub_spec("converge")
        new = [t for tid, t in self.board().items() if int(tid[2:]) > 10]
        held = [t for t in new if "held-out" in t["title"]]
        self.assertEqual([t["title"] for t in held], ["linkly spec drift: held-out A-1.1 red on origin/integration"])
        self.assertEqual((held[0]["owner"], held[0]["status"]), ("Zeus", "open"))
        leak = json.dumps(new) + out
        self.assertFalse([w for w in ("HIDDEN-ASSERT", "test_red", "CANARY") if w in leak], leak)
        self.assertIn("HIDDEN-ASSERT", (self.hub / "projects/linkly/heldout/gate.log").read_text())

    def test_briefs_issue_bodies_and_the_repo_never_carry_the_canary(self):
        """Fergus lesson 2 (Hermes on T-581): a canary in every held-out file proves nothing a builder reads has one."""
        self.heldout({"A-3.2": {"v": 2, "tests": ["A-3.2/test_by_day.py"]},
                      "A-3.3": {"v": 1, "tests": ["A-3.3/test_once_a_day.py"]}})
        self.hub_spec("apply", "C-001")
        generated = [t for t in self.board().values() if t.get("generated_from")]
        self.assertTrue(generated)
        with self.in_hub():
            self.assertEqual([label for label, _ in gh_sync.heldout_checks("linkly")], ["held-out A-3.2", "held-out A-3.3"])
            bodies = [gh_sync.issue_body(t, self.board()) for t in generated]
        self.assertTrue(any("A-3.3@1" in b for b in bodies))
        self.assertFalse([b for b in bodies + [json.dumps(self.board())] if "CANARY" in b])
        for repo in (self.repo, self.origin):
            self.assertNotIn("CANARY", git(repo, "log", "--all", "-p"))
            self.assertEqual(subprocess.run(["grep", "-rl", "CANARY", str(repo)], capture_output=True).returncode, 1)


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

    def test_a_project_without_a_factory_repo_entry_is_skipped(self):
        (self.hub / "factory.json").write_text(json.dumps({"repos": []}))  # archived: off the factory
        r = subprocess.run([sys.executable, str(HUB / "board.py"), "spec", "converge"],  # weekly: every project
                           env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([tid for tid in self.board() if int(tid[2:]) > 10], [])


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


class PrdBriefTest(unittest.TestCase):
    def test_apply_change_preserves_requirement_intent(self):
        before = {"version": 1, "requirements": [{"id": "R-1", "title": "First", "needs": [],
                                                   "why": "old reason", "rank": 1, "touches": ["src/old.py"],
                                                   "acceptance": []}]}
        change = {"id": "C-001", "added": [{"id": "R-2", "title": "Second", "needs": [],
                                            "why": "new reason", "rank": 2, "touches": ["src/new.py"],
                                            "acceptance": []}],
                  "modified": [{"id": "R-1", "why": "better reason", "rank": 2,
                                "touches": ["src/new.py"]}], "removed": []}

        after = spec.apply_change(before, change)

        self.assertEqual(after["requirements"][0]["why"], "better reason")
        self.assertEqual(after["requirements"][0]["touches"], ["src/new.py"])
        self.assertEqual(after["requirements"][1]["why"], "new reason")
        self.assertEqual(after["requirements"][1]["rank"], 2)
        self.assertEqual(after["requirements"][1]["touches"], ["src/new.py"])

    def test_plan_tree_carries_context_and_sequences_declared_touches(self):
        before = {"version": 1, "requirements": [],
                  "constraints": {"stack": "docs/current-stack.md", "limits": ["Keep data local"],
                                  "invariants": ["Never leak tokens"], "offline_tests": True,
                                  "tags": ["trust_boundary"]}}
        change = {"id": "C-001", "added": [
            {"id": "R-2", "title": "Second", "why": "serve leads", "rank": 2, "needs": [],
             "touches": ["src/a*.py"], "acceptance": [{"id": "A-2.1", "text": "do second"}]},
            {"id": "R-3", "title": "Third", "why": "serve ops", "rank": 3, "needs": [],
             "touches": ["src/*b.py"], "acceptance": [{"id": "A-3.1", "text": "do third"}]},
            {"id": "R-1", "title": "First", "why": "serve agents", "rank": 1, "needs": [],
             "touches": ["src/api.py"], "acceptance": [{"id": "A-1.1", "text": "do first"}]}],
                  "modified": [], "removed": []}
        after = spec.apply_change(before, change)
        context = {"version": 1, "header": {"non_goals": ["No accounts"]},
                   "constraints": {"stack": "docs/old-stack.md", "limits": ["Offline only"]},
                   "references": {"spine": {"path": "docs/spine.md", "sha256": "abc"}}}
        an = {"project": "sample", "spec": before, "new": after, "change": change, "k": set(),
              "tasks": [], "revert": [], "cfg": {}, "changed": {}}

        with mock.patch("prd.load", return_value=context) as load:
            plan = spec.plan_tree(an, "C-001", [])

        load.assert_called_once_with("sample")
        first, second = (next(n for n in plan["new"] if n["key"] == rid) for rid in ("R-1", "R-2"))
        self.assertIn("Why: serve agents", first["detail"])
        self.assertIn("No accounts", first["detail"])
        self.assertIn("Keep data local", first["detail"])
        self.assertIn("Never leak tokens", first["detail"])
        self.assertIn("Offline tests: required", first["detail"])
        self.assertIn("trust_boundary", first["detail"])
        self.assertIn("docs/current-stack.md", first["detail"])
        self.assertNotIn("docs/old-stack.md", first["detail"])
        self.assertIn("docs/spine.md", first["detail"])
        self.assertIn("src/api.py", first["detail"])
        self.assertIn("File conflict rule:", first["detail"])
        self.assertIn("R-1", second["deps"])
        third = next(n for n in plan["new"] if n["key"] == "R-3")
        self.assertIn("R-2", third["deps"])


class ApplyScopeTest(unittest.TestCase):
    """a change rebuilds only what it touches; the check-writer is done on expected reds."""

    def plan(self):
        before = {"version": 1, "requirements": [
            {"id": "R-1", "title": "Built", "rank": 1, "needs": [], "acceptance": [{"id": "A-1.1", "v": 1, "text": "shipped, no check", "test": "tests/acceptance/test_A_1_1.py"}]}]}
        change = {"id": "C-002", "added": [
            {"id": "R-2", "title": "New", "rank": 2, "needs": [], "acceptance": [{"id": "A-2.1", "text": "do new"}]}],
                  "modified": [], "removed": []}
        after = spec.apply_change(before, change)
        an = {"project": "sample", "spec": before, "new": after, "change": change, "k": {}, "tasks": [],
              "revert": [], "cfg": {}, "changed": spec.changed_lines(before, change)}
        with mock.patch("prd.load", return_value={}):
            return an, spec.plan_tree(an, "C-002", [])

    def test_untouched_requirement_without_checks_is_reported_not_rebuilt(self):
        _, plan = self.plan()
        self.assertEqual([n["key"] for n in plan["new"]], ["checks", "R-2"])
        self.assertEqual(plan["new"][0]["reqs"], ["A-2.1@1"])
        self.assertEqual(plan["unchecked"], ["A-1.1"])

    def test_check_writer_is_done_on_expected_reds_and_never_builds(self):
        an, plan = self.plan()
        checks = plan["new"][0]
        self.assertIn("fails only for the missing behaviour", checks["detail"])
        self.assertIn("never builds a requirement it writes checks for", checks["detail"])
        self.assertNotIn("Done when each new check passes", checks["detail"])
        gate = spec.own_verify(an, checks["reqs"], "sample", collect=True)
        self.assertIn("--collect-only", gate)
        self.assertTrue(gate.endswith("hub spec check --project sample --repo . --lines A-2.1"))
        self.assertNotIn("--collect-only", spec.own_verify(an, plan["new"][1]["reqs"], "sample"))

    def test_check_writer_title_fits_a_github_issue(self):
        """A change touching 89 lines; listing every id made a 922-character title,
        GitHub refuses one over 256, and a generated title cannot be edited afterwards."""
        before = {"version": 1, "requirements": []}
        change = {"id": "C-001", "added": [{"id": "R-2", "title": "Big", "rank": 1, "needs": [], "acceptance": [
            {"id": f"A-2.{i}", "text": f"line {i}"} for i in range(1, 90)]}], "modified": [], "removed": []}
        after = spec.apply_change(before, change)
        an = {"project": "sample", "spec": before, "new": after, "change": change, "k": {}, "tasks": [],
              "revert": [], "cfg": {}, "changed": spec.changed_lines(before, change)}
        with mock.patch("prd.load", return_value={}):
            title = spec.plan_tree(an, "C-001", [])["new"][0]["title"]
        self.assertLessEqual(len(title), 256)
        self.assertEqual(title, "C-001: land acceptance checks for 89 lines, A-2.1@1 to A-2.89@1")
        _, plan = self.plan()
        self.assertEqual(plan["new"][0]["title"], "C-002: land acceptance checks for A-2.1@1")

    def test_generated_verify_runs_green_on_a_partial_baseline(self):
        """Prometheus on 91ada1b: R-1 shipped without its check file, so the full hub spec check fails;
        the check-writer for R-2 must still be able to finish. Executes the generated verify."""
        an, plan = self.plan()
        an["cfg"] = {"collect_cmd": f"{sys.executable} -m py_compile {{test}}"}
        with tempfile.TemporaryDirectory(prefix="hub-spec-partial-") as tmp:
            root = Path(tmp)
            d = root / "hub" / "projects" / "sample" / "spec"
            d.mkdir(parents=True)
            (d / "requirements.json").write_text(json.dumps(an["new"]))
            (d / "spec.lock").write_text(json.dumps({"version": an["new"]["version"], "sha256": hashlib.sha256(
                (d / "requirements.json").read_bytes()).hexdigest()}))
            repo = root / "repo"
            test = repo / spec.lines_of(an["new"])["A-2.1"][1]["test"]
            test.parent.mkdir(parents=True)
            test.write_text("def test_new():\n    assert False, 'R-2 not built yet'\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
            env["HUB_DIR"] = str(root / "hub")
            hub = f"{shlex.quote(sys.executable)} {shlex.quote(str(HUB / 'board.py'))}"
            run = lambda cmd: subprocess.run(cmd.replace("hub spec", f"{hub} spec"), shell=True, cwd=repo, env=env,
                                             capture_output=True, text=True, timeout=120)
            gate = run(spec.own_verify(an, plan["new"][0]["reqs"], "sample", collect=True))
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            full = run("hub spec check --project sample --repo .")  # the old gap stays visible, unscoped
            self.assertNotEqual(full.returncode, 0)
            self.assertIn("A-1.1: test file missing", full.stdout + full.stderr)
            for bad in ("A-999.1", "A-2.1@1"):  # Prometheus on 717b723: an unknown id must not pass vacuously
                r = run(f"hub spec check --project sample --repo . --lines {bad}")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(f"--lines {bad}: no active acceptance line", r.stdout + r.stderr)
            self.assertEqual(run("hub spec check --project sample --repo . --lines ''").returncode, 0)  # deletion-only


class PrdSourceTest(Fixture):
    def test_approved_set_adds_header_to_locked_legacy_spec(self):
        change = {"id": "C-002", "base_version": 4, "added": [], "modified": [], "removed": [],
                  "set": {"header.problem": "Agents need links that fit in chat",
                          "header.non_goals": ["No accounts"],
                          "constraints.stack": "docs/stack.md",
                          "references.spine": {"path": "docs/spine.md", "sha256": "0" * 64}}}
        self.write_change(change)

        lint = self.hub_spec("lint", "C-002")
        self.assertNotIn("error ", lint)
        self.hub_spec("apply", "C-002")

        path = self.spec / "requirements.json"
        result = json.loads(path.read_text())
        self.assertEqual(result["header"]["problem"], "Agents need links that fit in chat")
        self.assertEqual(result["header"]["non_goals"], ["No accounts"])
        self.assertEqual(result["constraints"]["stack"], "docs/stack.md")
        self.assertEqual(result["references"]["spine"]["path"], "docs/spine.md")
        self.assertEqual(result["version"], 5)
        self.assertFalse((self.spec / "prd.json").exists())
        self.assertEqual(json.loads((self.spec / "spec.lock").read_text())["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        with mock.patch.object(spec.hb, "HUB_DIR", str(self.hub)):
            import prd
            self.assertEqual(prd.load("linkly")["header"]["problem"], result["header"]["problem"])

    def test_prd_json_is_the_only_spec_file_and_its_header_survives_apply(self):
        path = self.spec / "prd.json"
        doc = json.loads((self.spec / "requirements.json").read_text())
        doc["header"] = {"problem": "Keep links short", "non_goals": ["No accounts"]}
        doc["constraints"] = {"stack": "docs/stack.md", "limits": ["Offline only"]}
        for rank, req in enumerate(doc["requirements"], 1):
            req["rank"] = rank
        path.write_text(json.dumps(doc))
        (self.spec / "requirements.json").unlink()
        (self.spec / "spec.lock").write_text(json.dumps({
            "version": doc["version"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
        change = json.loads((self.spec / "changes" / "C-001.json").read_text())
        change["added"][0]["test"] = "tests/acceptance/test_A_3_3.py"
        self.write_change(change)

        self.hub_spec("apply", "C-001")

        result = json.loads(path.read_text())
        self.assertEqual(result["version"], 5)
        self.assertEqual(result["header"], doc["header"])
        self.assertEqual(result["constraints"], doc["constraints"])
        added = next(a for r in result["requirements"] for a in r["acceptance"] if a["id"] == "A-3.3")
        self.assertNotIn("req", added)
        self.assertFalse((self.spec / "requirements.json").exists())
        self.assertEqual(json.loads((self.spec / "spec.lock").read_text())["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        with mock.patch.object(gh_sync.hb, "HUB_DIR", str(self.hub)):
            self.assertEqual(gh_sync.current_lines("linkly")["A-3.2"], 2)


class PrdInitTest(unittest.TestCase):
    def test_init_from_prd_preserves_full_document_and_locks_prd_json(self):
        with tempfile.TemporaryDirectory(prefix="hub-prd-init-") as tmp:
            root = Path(tmp)
            source = root / "source" / "spec" / "prd.json"
            source.parent.mkdir(parents=True)
            source.write_bytes((HUB / "templates" / "prd" / "example.prd.json").read_bytes())
            env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
            env.update(HUB_DIR=str(root / "hub"), HUB_AGENT="Zeus")

            result = subprocess.run([sys.executable, str(HUB / "board.py"), "spec", "init", "sample",
                                     "--from", str(source)], env=env, capture_output=True, text=True, timeout=30)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            path = root / "hub" / "projects" / "sample" / "spec" / "prd.json"
            self.assertEqual(json.loads(path.read_text()), json.loads(source.read_text()))
            self.assertFalse((path.parent / "requirements.json").exists())
            self.assertEqual(json.loads((path.parent / "spec.lock").read_text())["sha256"],
                             hashlib.sha256(path.read_bytes()).hexdigest())


class SpecAutonomyTests(Fixture):
    def small_fix(self):
        """A correction-sized edit of A-1.1: the current text plus a short clarifying tail."""
        d = json.loads((self.spec / "requirements.json").read_text())
        return next(a["text"] for r in d["requirements"] for a in r["acceptance"] if a["id"] == "A-1.1") + " (exactly)"

    def setUp(self):
        super().setUp()
        factory_cfg = {
            "agents": [
                {"name": "Prometheus", "kind": "codex", "phase": "trusted"},
                {"name": "Iris", "kind": "agy", "phase": "trial"},
                {"name": "Hermes", "kind": "claude", "phase": "reviewer"},
                {"name": "Zeus", "kind": "claude", "phase": "lead"},
            ],
            "autonomy": {
                "default_phase": "trial",
                "known_kinds": ["claude", "codex", "agy"],
                "promote_after": 5,
                "phases": {
                    "off": {"dispatch": False, "reset": False, "may": []},
                    "trial": {"dispatch": True, "reset": False, "budget_minutes": 90, "may": ["claim", "push", "open_pr"]},
                    "trusted": {"dispatch": True, "reset": "per-task", "budget_minutes": 180, "may": ["claim", "push", "open_pr", "fast_lane", "done_force", "review"]},
                    "reviewer": {"dispatch": False, "reset": False, "budget_minutes": 120, "may": ["claim", "push", "open_pr", "review", "done_force"]},
                    "lead": {"dispatch": False, "reset": False, "may": ["claim", "push", "open_pr", "review", "done_force", "hand_merge", "spec_apply", "clear_tags"]},
                },
            },
            "repos": [{"repo": "o/linkly", "shared": ["app/models.py"], "migrations": ["migrations/"], "acceptance_cmd": f"{sys.executable} {{test}}"}]
        }
        (self.hub / "factory.json").write_text(json.dumps(factory_cfg))

    def test_apply_allowed_for_any_agent_with_lead_receipt(self):
        # M7: the receipt is the gate; any non-off agent may apply with a valid lead receipt
        self.env["HUB_AGENT"] = "Iris"
        out = self.hub_spec("apply", "C-001", ok=True)
        self.assertIn("applied C-001: spec v5", out)

    def test_apply_refused_for_off_phase_agent(self):
        factory_cfg = json.loads((self.hub / "factory.json").read_text())
        factory_cfg["agents"] = [{"name": "Ghost", "phase": "off"}]
        (self.hub / "factory.json").write_text(json.dumps(factory_cfg))
        self.env["HUB_AGENT"] = "Ghost"
        out = self.hub_spec("apply", "C-001", ok=False)
        self.assertIn("agent Ghost is in phase off; cannot apply spec changes", out)

    def test_apply_refused_without_lead_receipt(self):
        path = self.spec / "changes" / "C-001.json"
        reviews = self.hub / "projects" / "linkly" / "reviews"
        (reviews / "C-001.json").write_text(json.dumps({
            "name": "C-001", "decision": "approve", "reviewer": "Hermes", "approved_path": str(path),
            "approved_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
        self.env["HUB_AGENT"] = "Zeus"
        out = self.hub_spec("apply", "C-001", ok=False)
        self.assertIn("regular change requires lead approval receipt; receipt is from Hermes", out)

    def test_correct_and_propose_ignore_input_id_and_never_overwrite_or_delete_existing_change(self):
        c1_path = self.spec / "changes" / "C-001.json"
        c1_orig = c1_path.read_text()
        draft = self.temp.name + "/probe_c001.json"
        Path(draft).write_text(json.dumps({
            "id": "C-001",
            "modified": [{"id": "A-99.99", "text": "bad id causes error"}]
        }))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertTrue(c1_path.exists())
        self.assertEqual(c1_path.read_text(), c1_orig)

        Path(draft).write_text(json.dumps({
            "id": "C-001",
            "added": [{"id": "A-3.3", "req": "R-3", "text": "a visitor counts once a day"}]
        }))
        self.hub_spec("propose", draft, ok=True)
        c2_path = self.spec / "changes" / "C-002.json"
        self.assertTrue(c2_path.exists())
        c2 = json.loads(c2_path.read_text())
        self.assertEqual(c2["id"], "C-002")
        self.assertEqual(c1_path.read_text(), c1_orig)

    def test_correction_records_author_and_forbids_self_approval(self):
        draft = self.temp.name + "/corr.json"
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": self.small_fix()}]}))
        self.env["HUB_AGENT"] = "Hermes"
        self.hub_spec("correct", draft, ok=True)
        c2 = json.loads((self.spec / "changes" / "C-002.json").read_text())
        self.assertEqual(c2.get("author"), "Hermes")

        out = self.hub_spec("approve", "C-002", ok=False)
        self.assertIn("cannot approve their own correction", out)

    def test_correction_approval_requires_hermes_or_zeus_reviewer_or_lead(self):
        draft = self.temp.name + "/corr.json"
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": self.small_fix()}]}))
        self.env["HUB_AGENT"] = "Iris"
        self.hub_spec("correct", draft, ok=True)

        self.env["HUB_AGENT"] = "Prometheus"
        out = self.hub_spec("approve", "C-002", ok=False)
        self.assertIn("must be approved by Hermes or Zeus", out)

    def test_correction_rejects_disallowed_keys_and_large_edits(self):
        draft = self.temp.name + "/corr_disallowed.json"
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": "code", "fixtures": []}]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("disallowed fields", out)

        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": "code", "previous": {}}]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("disallowed fields", out)

        Path(draft).write_text(json.dumps({"modified": [{
            "id": "A-1.1",
            "text": "This completely replaces the requirement with a novel sentence exceeding eighty changed characters limit."
        }]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("change is too large", out)

    def test_correction_cannot_rewrite_a_short_line_whole(self):
        # Under 80 changed chars but a different line: either bound refuses it (Hermes nit on T-577).
        draft = self.temp.name + "/corr_short.json"
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": "returns 500 on every request"}]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("change is too large", out)

    def test_spec_correct_creates_bounded_correction(self):
        draft = self.temp.name + "/add.json"
        Path(draft).write_text(json.dumps({"added": [{"id": "A-9.9", "text": "bad"}]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("corrections cannot add", out)

        Path(draft).write_text(json.dumps({"modified": [{"id": "A-99.99", "text": "typo"}]}))
        out = self.hub_spec("correct", draft, ok=False)
        self.assertIn("unknown or non-acceptance line", out)

        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": self.small_fix()}]}))
        self.hub_spec("correct", draft, ok=True)
        c2_path = self.spec / "changes" / "C-002.json"
        self.assertTrue(c2_path.exists())
        c2 = json.loads(c2_path.read_text())
        self.assertEqual(c2["kind"], "correction")
        self.assertEqual(c2["base_version"], 4)
        self.assertEqual(c2["based_on_sha256"], hashlib.sha256((self.spec / "requirements.json").read_bytes()).hexdigest())

    def test_spec_correct_applies_with_hermes_receipt_by_any_agent(self):
        draft = self.temp.name + "/corr.json"
        self.env["HUB_AGENT"] = "Iris"
        fixed = self.small_fix()
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": fixed}]}))
        self.hub_spec("correct", draft, ok=True)

        self.env["HUB_AGENT"] = "Hermes"
        self.hub_spec("approve", "C-002", "--why", "LGTM clarity")

        self.env["HUB_AGENT"] = "Iris"
        out = self.hub_spec("apply", "C-002", ok=True)
        self.assertIn("applied C-002: spec v5", out)

        reqs = json.loads((self.spec / "requirements.json").read_text())
        a11 = next(a for r in reqs["requirements"] for a in r["acceptance"] if a["id"] == "A-1.1")
        self.assertEqual(a11["v"], 1)
        self.assertEqual(a11["text"], fixed)

        inbox = (self.hub / "inbox" / "Zeus.jsonl").read_text()
        self.assertIn("Correction C-002 applied on linkly", inbox)

    def test_apply_refuses_correction_with_stale_based_on_hash(self):
        c2 = {
            "id": "C-002",
            "kind": "correction",
            "base_version": 4,
            "based_on_sha256": "0" * 64,
            "modified": [{"id": "A-1.1", "text": self.small_fix()}]
        }
        (self.spec / "changes" / "C-002.json").write_text(json.dumps(c2))
        self.approve("C-002")
        out = self.hub_spec("apply", "C-002", ok=False)
        self.assertIn("was written against spec sha256", out)

    def test_apply_refuses_correction_missing_based_on_hash(self):
        c2 = {
            "id": "C-002",
            "kind": "correction",
            "base_version": 4,
            "modified": [{"id": "A-1.1", "text": self.small_fix()}]
        }
        (self.spec / "changes" / "C-002.json").write_text(json.dumps(c2))
        self.approve("C-002")
        out = self.hub_spec("apply", "C-002", ok=False)
        self.assertIn("missing based_on_sha256", out)

    def test_spec_propose_creates_proposal_and_review_page(self):
        draft = self.temp.name + "/prop.json"
        Path(draft).write_text(json.dumps({
            "added": [{"id": "A-3.3", "req": "R-3", "text": "a visitor counts once a day"}],
            "modified": [{"id": "A-3.2", "text": "stats returns {total, unique, by_day}"}]
        }))
        self.hub_spec("propose", draft, ok=True)
        c2_path = self.spec / "changes" / "C-002.json"
        self.assertTrue(c2_path.exists())
        c2 = json.loads(c2_path.read_text())
        self.assertEqual(c2["kind"], "proposal")
        rev_path = self.spec / "review-C-002.html"
        self.assertTrue(rev_path.exists())
        self.assertIn('data-approves="changes/C-002.json"', rev_path.read_text())

    def test_spec_revert_creates_reversing_correction(self):
        draft = self.temp.name + "/corr.json"
        Path(draft).write_text(json.dumps({"modified": [{"id": "A-1.1", "text": self.small_fix()}]}))
        self.hub_spec("correct", draft, ok=True)

        self.hub_spec("revert", "C-002", ok=True)
        c3_path = self.spec / "changes" / "C-003.json"
        self.assertTrue(c3_path.exists())
        c3 = json.loads(c3_path.read_text())
        self.assertEqual(c3["kind"], "correction")
        self.assertEqual(c3["modified"][0]["id"], "A-1.1")
        self.assertEqual(c3["modified"][0]["text"], "POST /links returns a 6-char code")


if __name__ == "__main__":
    unittest.main()

