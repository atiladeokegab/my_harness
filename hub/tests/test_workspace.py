"""Per-task worktrees use a temporary HOME and local bare origin."""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import workspace  # noqa: E402


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-workspace-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        home_env = unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)})
        home_env.start()
        self.addCleanup(home_env.stop)
        self.origin = self.home / "origin.git"
        self.clone = self.home / "code" / "p"
        self.clone.parent.mkdir()
        self.git(self.home, "init", "--bare", str(self.origin))
        self.git(self.home, "clone", str(self.origin), str(self.clone))
        self.git(self.clone, "config", "user.name", "Test")
        self.git(self.clone, "config", "user.email", "test@example.com")
        (self.clone / "README").write_text("integration\n")
        (self.clone / ".gitignore").write_text(".env\n")
        self.git(self.clone, "add", "README", ".gitignore")
        self.git(self.clone, "commit", "-qm", "integration")
        self.git(self.clone, "branch", "-M", "integration")
        self.git(self.clone, "push", "-q", "origin", "integration")
        self.git(self.origin, "symbolic-ref", "HEAD", "refs/heads/integration")
        self.git(self.clone, "switch", "-qc", "change/C-002")
        (self.clone / "README").write_text("change\n")
        self.git(self.clone, "commit", "-qam", "change")
        self.git(self.clone, "push", "-q", "origin", "change/C-002")
        self.git(self.clone, "switch", "-q", "integration")
        (self.clone / ".env").write_text("TOKEN=local-only\n")
        # gc re-reads the board before each remove: point board.py at a temp hub, never ~/hub.
        self.hub = self.home / "hub"
        self.hub.mkdir()
        for name, rel in (("HUB_DIR", ""), ("BOARD", "board.json"), ("EVENTS", "events.jsonl"),
                          ("LOCK", ".board.lock"), ("WAL", ".board.wal")):
            patcher = unittest.mock.patch.object(workspace.hb, name, str(self.hub / rel))
            patcher.start()
            self.addCleanup(patcher.stop)

    def gc(self, tasks, dry_run, board=None):
        """gc against a board that holds `board` (default: the tasks themselves)."""
        (self.hub / "board.json").write_text(json.dumps({"next_id": 99, "tasks": board or tasks}))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            kept = workspace.gc(tasks, dry_run)
        self.output = out.getvalue()
        return kept

    def git(self, cwd, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        result = subprocess.run(["git", "-C", str(cwd), *args], env=env, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def task(self, tid="T-1", generated=False, status="claimed"):
        detail = "Work on branch change/C-002." if generated else "Build the task."
        return {"id": tid, "project": "p", "detail": detail, "status": status}

    def test_generated_task_starts_at_change_branch_and_plain_task_at_integration(self):
        with unittest.mock.patch.dict(os.environ, {"GIT_DIR": "/missing", "GIT_WORK_TREE": "/missing"}):
            generated = workspace.create(self.task(generated=True), self.home)
            plain = workspace.create(self.task("T-2"), self.home)
        self.assertEqual(generated, self.home / "work" / "p" / "T-1")
        self.assertEqual(self.git(generated, "rev-parse", "HEAD"),
                         self.git(self.clone, "rev-parse", "origin/change/C-002"))
        self.assertEqual(self.git(plain, "rev-parse", "HEAD"),
                         self.git(self.clone, "rev-parse", "origin/integration"))
        self.assertEqual((generated / ".env").read_text(), "TOKEN=local-only\n")

    def test_reclaim_preserves_local_work_and_gc_keeps_it(self):
        task = self.task(status="done")
        path = workspace.create(task, self.home)
        (path / "notes.txt").write_text("draft")
        self.assertEqual(workspace.create(task, self.home), path)
        self.gc([{**task, "workspace": str(path)}], False)
        self.assertTrue(path.exists())

    def test_gc_removes_clean_merged_or_unmodified_base_but_keeps_unmerged_commits(self):
        merged = self.task("T-1", status="done")
        base = self.task("T-2", generated=True, status="done")
        unmerged = self.task("T-3", generated=True, status="done")
        paths = [workspace.create(t, self.home) for t in (merged, base, unmerged)]
        self.git(paths[0], "config", "user.name", "Test")
        self.git(paths[0], "config", "user.email", "test@example.com")
        (paths[0] / "README").write_text("merged commit\n")
        self.git(paths[0], "commit", "-qam", "merged")
        self.git(paths[0], "push", "-q", "origin", "HEAD:refs/heads/integration")
        self.git(self.clone, "fetch", "-q", "origin")
        self.git(paths[2], "config", "user.name", "Test")
        self.git(paths[2], "config", "user.email", "test@example.com")
        (paths[2] / "README").write_text("unmerged commit\n")
        self.git(paths[2], "commit", "-qam", "local")
        tasks = [{**t, "workspace": str(p)} for t, p in zip((merged, base, unmerged), paths)]
        self.gc(tasks, True)
        self.assertTrue(all(p.exists() for p in paths))
        self.gc(tasks, False)
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[1].exists())
        self.assertTrue(paths[2].exists())

    def commit(self, path, name):
        self.git(path, "config", "user.name", "Test")
        self.git(path, "config", "user.email", "test@example.com")
        (path / name).write_text(name + "\n")
        self.git(path, "add", name)
        self.git(path, "commit", "-qm", name)
        return self.git(path, "rev-parse", "HEAD")

    def test_gc_removes_squash_merged_work_but_never_uncommitted_changes(self):
        squashed, pushed, dirty = (self.task(f"T-{n}", status="done") for n in (4, 6, 7))
        picked = self.task("T-5", generated=True, status="done")
        paths = [workspace.create(t, self.home) for t in (squashed, picked, pushed, dirty)]
        for path, name in zip(paths, ("squashed", "picked", "pushed", "dirty")):
            self.commit(path, name)
        squashed["merge_sha"] = dirty["merge_sha"] = "0" * 40
        self.git(self.clone, "switch", "-q", "change/C-002")
        self.commit(self.clone, "unrelated")  # so the cherry-pick below gets a new sha with the same patch
        self.git(self.clone, "cherry-pick", self.git(paths[1], "rev-parse", "HEAD"))
        self.git(self.clone, "push", "-q", "origin", "change/C-002")
        self.git(paths[2], "push", "-q", "origin", "HEAD:refs/heads/task/T-6")
        self.git(self.clone, "fetch", "-q", "origin")
        (paths[3] / "dirty").write_text("uncommitted\n")
        tasks = [{**t, "workspace": str(p)} for t, p in zip((squashed, picked, pushed, dirty), paths)]
        kept = self.gc(tasks, False)
        self.assertEqual([p.exists() for p in paths], [False, False, False, True])
        self.assertEqual(kept, [str(paths[3].resolve())])

    def test_gc_keeps_new_commits_on_a_task_reopened_after_its_merge(self):
        task = {**self.task("T-8", status="open"), "merge_sha": "0" * 40}  # live.reverts reopens, keeps merge_sha
        path = workspace.create(task, self.home)
        self.commit(path, "fix after revert")
        kept = self.gc([{**task, "workspace": str(path)}], False)
        self.assertTrue(path.exists())
        self.assertEqual(kept, [str(path.resolve())])

    def test_hub_and_missing_clone_skip_without_touching_hub(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(workspace.create({"id": "T-1", "project": "hub"}, self.home))
            self.assertIsNone(workspace.create({"id": "T-2", "project": "missing"}, self.home))
        self.assertIn("hub", output.getvalue())
        self.assertIn("missing", output.getvalue())
        self.assertFalse((self.home / "work").exists())

    def test_gc_keeps_a_task_re_claimed_after_its_snapshot(self):
        snapshot = {**self.task("T-9", status="done"), "workspace": None}
        snapshot["workspace"] = str(workspace.create(snapshot, self.home))
        kept = self.gc([snapshot], False, board=[{**snapshot, "status": "claimed"}])
        self.assertTrue(Path(snapshot["workspace"]).exists(), self.output)
        self.assertEqual(kept, [str(Path(snapshot["workspace"]).resolve())])
        self.assertIn("re-claimed", self.output)

    def test_register_exposes_path_and_gc(self):
        parser = argparse.ArgumentParser()
        workspace.register(parser.add_subparsers(dest="command"))
        self.assertEqual(parser.parse_args(["ws", "path", "T-1"]).id, "T-1")
        self.assertTrue(parser.parse_args(["ws", "gc", "--dry-run"]).dry_run)


    def test_ws_gc_runs_git_with_the_board_lock_released(self):
        """The nightly gc runs git per task; holding the board lock meanwhile stalls every agent."""
        task = self.task(status="done")
        path = workspace.create(task, self.home)
        hub = self.hub
        (hub / "board.json").write_text(json.dumps({"next_id": 2, "tasks": [{**task, "workspace": str(path)}]}))
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        log = self.home / "lock.log"
        fake = bin_dir / "git"
        fake.write_text(f"""#!/bin/sh
if flock -n {hub / ".board.lock"} true; then echo free >> {log}; else echo held >> {log}; fi
exec {shutil.which("git")} "$@"
""")
        fake.chmod(0o755)
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME", "GIT_DIR", "GIT_WORK_TREE")}
        env.update(HOME=str(self.home), HUB_DIR=str(hub), PATH=f"{bin_dir}:{env['PATH']}")
        r = subprocess.run([str(ROOT / "board.py"), "ws", "gc"], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"workspace: removed {path}", r.stdout)
        self.assertEqual(set(log.read_text().split()), {"free"})

if __name__ == "__main__":
    unittest.main()
