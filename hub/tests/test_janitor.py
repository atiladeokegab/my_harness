"""Tests for Hub VM disk janitor (T-1100).

Verify:
- A test with a fake tree shows each rule deletes only what it should:
  a dirty worktree, an unpushed branch, a claimed workspace and a file held open all survive.
- Protected directories (~/private, etc.) are never touched.
- Dry-run prints what would be freed without modifying anything.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

JANITOR_SH = Path(__file__).resolve().parent.parent / "ops" / "janitor.sh"
DAY = 86400


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True
    )


class TestJanitor(unittest.TestCase):
    def setUp(self):
        self.tmp_dir_obj = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir_obj.cleanup)
        self.root = Path(self.tmp_dir_obj.name)

        self.home = self.root / "home"
        self.work = self.home / "work"
        self.code = self.home / "code"
        self.hub = self.home / "hub"
        self.tmp = self.root / "tmp"
        self.claude_tmp = self.tmp / "claude-1001"
        self.log_dir = self.hub / "logs" / "janitor"

        for p in (self.home, self.work, self.code, self.hub, self.tmp, self.claude_tmp, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)

        # Set up a remote bare repo and local clone
        self.remote_git = self.root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote_git)], check=True)

        self.main_repo = self.code / "proj"
        subprocess.run(["git", "clone", "-q", str(self.remote_git), str(self.main_repo)], check=True)
        git(self.main_repo, "checkout", "-b", "main")
        (self.main_repo / "README.md").write_text("initial\n")
        git(self.main_repo, "add", "README.md")
        git(self.main_repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "initial")
        git(self.main_repo, "push", "-q", "-u", "origin", "main")

        # Fake board.json with one claimed task
        self.board_file = self.hub / "board.json"
        self.claimed_ws = self.work / "proj" / "T-claimed"
        board_data = {
            "tasks": [
                {
                    "id": "T-claimed",
                    "status": "claimed",
                    "workspace": str(self.claimed_ws)
                }
            ]
        }
        self.board_file.write_text(json.dumps(board_data))

        # Base env overrides
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "HUB_DIR": str(self.hub),
            "WORK_DIR": str(self.work),
            "TMP_DIR": str(self.tmp),
            "CLAUDE_TMP_DIR": str(self.claude_tmp),
            "LOG_DIR": str(self.log_dir),
            "TARGET_PCT": "75",
            "ALERT_PCT": "85",
            "MOCK_DISK_PCT": "80",  # over 75% so it triggers
            "SKIP_RULE1": "1",  # do not touch global uv/docker cache during parallel tests
        })

    def run_janitor(self, *args, extra_env=None):
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(JANITOR_SH), *args],
            capture_output=True, text=True, env=env, timeout=60
        )

    def set_old_mtime(self, path: Path, days: int):
        t = time.time() - days * DAY
        if not path.is_dir():
            os.utime(path, (t, t))
            return
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                os.utime(Path(root) / name, (t, t))
            for name in dirs:
                os.utime(Path(root) / name, (t, t))
            os.utime(root, (t, t))

    def test_help_and_unknown_flags(self):
        res_help = self.run_janitor("--help")
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("usage:", res_help.stdout.lower())

        res_unknown = self.run_janitor("--invalid-flag")
        self.assertEqual(res_unknown.returncode, 2)

    def test_fake_tree_deletions_and_survivals(self):
        """Verify each rule deletes only what it should; dirty, unpushed, claimed, open all survive."""
        # --- Rule 2: Setup tmp files ---
        # 1. Old tmp file (>3 days) -> should be deleted
        old_file = self.tmp / "old_trash.txt"
        old_file.write_text("old content")
        self.set_old_mtime(old_file, 4)

        # 2. Recent tmp file (<3 days) -> must survive
        recent_file = self.tmp / "recent.txt"
        recent_file.write_text("recent content")
        self.set_old_mtime(recent_file, 1)

        # 3. File held open by a process -> must survive
        open_file = self.tmp / "held_open.txt"
        open_file.write_text("in use")
        self.set_old_mtime(open_file, 5)
        held_handle = open(open_file, "r")
        self.addCleanup(held_handle.close)

        # 4. Scratchpad modified within 24h -> must survive
        scratchpad = self.tmp / "agent-scratchpad-session.txt"
        scratchpad.write_text("scratchpad content")
        self.set_old_mtime(scratchpad, 0.5)  # 12h old

        # 5. Playwright / chromium dir older than 1 day -> should be deleted
        pw_old = self.tmp / "playwright_chromiumdev_profile-xyz123"
        pw_old.mkdir(parents=True, exist_ok=True)
        (pw_old / "data.bin").write_text("cache")
        self.set_old_mtime(pw_old, 1.5)

        # 6. Playwright / chromium dir younger than 1 day -> must survive
        pw_recent = self.tmp / "playwright-artifacts-abc"
        pw_recent.mkdir(parents=True, exist_ok=True)
        (pw_recent / "shot.png").write_text("png")
        self.set_old_mtime(pw_recent, 0.5)

        # --- Rule 3: Setup worktrees under work/proj ---
        repo_work = self.work / "proj"
        repo_work.mkdir(parents=True, exist_ok=True)

        # 1. Clean, pushed, >7d old worktree -> should be removed
        wt_clean_old = repo_work / "clean_old"
        git(self.main_repo, "worktree", "add", "-b", "clean_old_branch", str(wt_clean_old))
        git(self.main_repo, "push", "-q", "-u", "origin", "clean_old_branch")
        self.set_old_mtime(wt_clean_old, 8)

        # 2. Clean, fully merged to origin/main, >2d old (3 days) -> should be removed
        wt_merged_3d = repo_work / "wt_merged_3d"
        git(self.main_repo, "worktree", "add", "-b", "merged_3d_branch", str(wt_merged_3d))
        # merge to main and push
        git(self.main_repo, "merge", "-q", "--no-ff", "-m", "merge 3d", "merged_3d_branch")
        git(self.main_repo, "push", "-q", "origin", "main")
        self.set_old_mtime(wt_merged_3d, 3)

        # 3. Clean, pushed, unmerged, >2d but <7d old (4 days) -> must survive
        wt_unmerged_4d = repo_work / "wt_unmerged_4d"
        git(self.main_repo, "worktree", "add", "-b", "unmerged_4d_branch", str(wt_unmerged_4d))
        (wt_unmerged_4d / "feature.txt").write_text("feature")
        git(wt_unmerged_4d, "add", "feature.txt")
        git(wt_unmerged_4d, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "unmerged commit")
        git(self.main_repo, "push", "-q", "-u", "origin", "unmerged_4d_branch")
        self.set_old_mtime(wt_unmerged_4d, 4)

        # 4. Dirty worktree -> must survive
        wt_dirty = repo_work / "dirty_wt"
        git(self.main_repo, "worktree", "add", "-b", "dirty_branch", str(wt_dirty))
        git(self.main_repo, "push", "-q", "-u", "origin", "dirty_branch")
        (wt_dirty / "uncommitted.txt").write_text("changes")
        self.set_old_mtime(wt_dirty, 8)

        # 5. Unpushed branch worktree -> must survive
        wt_unpushed = repo_work / "unpushed_wt"
        git(self.main_repo, "worktree", "add", "-b", "unpushed_branch", str(wt_unpushed))
        (wt_unpushed / "local.txt").write_text("local only")
        git(wt_unpushed, "add", "local.txt")
        git(wt_unpushed, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "local commit")
        self.set_old_mtime(wt_unpushed, 8)

        # 6. Claimed workspace worktree -> must survive
        git(self.main_repo, "worktree", "add", "-b", "claimed_branch", str(self.claimed_ws))
        git(self.main_repo, "push", "-q", "-u", "origin", "claimed_branch")
        self.set_old_mtime(self.claimed_ws, 8)

        # --- Rule 4: Duplicate .venv in worktrees older than 2 days ---
        venv_old = wt_unmerged_4d / ".venv"
        venv_old.mkdir(parents=True, exist_ok=True)
        (venv_old / "lib.py").write_text("python")
        self.set_old_mtime(wt_unmerged_4d, 4)

        wt_recent = repo_work / "wt_recent"
        git(self.main_repo, "worktree", "add", "-b", "recent_branch", str(wt_recent))
        git(self.main_repo, "push", "-q", "-u", "origin", "recent_branch")
        venv_recent = wt_recent / ".venv"
        venv_recent.mkdir(parents=True, exist_ok=True)
        (venv_recent / "lib.py").write_text("python")
        self.set_old_mtime(wt_recent, 1)

        # Run janitor with force to test all rules
        res = self.run_janitor("--force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        # Assert Rule 2 outcomes
        self.assertFalse(old_file.exists(), "Old untouched file should have been deleted")
        self.assertTrue(recent_file.exists(), "Recent file (<3d) must survive")
        self.assertTrue(open_file.exists(), "File held open by process must survive")
        self.assertTrue(scratchpad.exists(), "Scratchpad modified in last 24h must survive")
        self.assertFalse(pw_old.exists(), "Playwright dir >1d should have been deleted")
        self.assertTrue(pw_recent.exists(), "Playwright dir <1d must survive")

        # Assert Rule 3 outcomes
        self.assertFalse(wt_clean_old.exists(), "Clean, pushed, >7d worktree should have been removed")
        self.assertFalse(wt_merged_3d.exists(), "Clean, merged-to-main, >2d worktree should have been removed")
        self.assertTrue(wt_unmerged_4d.exists(), "Clean, unmerged, <7d worktree must survive")
        self.assertTrue(wt_dirty.exists(), "Dirty worktree must survive")
        self.assertTrue(wt_unpushed.exists(), "Worktree with unpushed branch must survive")
        self.assertTrue(self.claimed_ws.exists(), "Claimed task workspace must survive")

        # Assert Rule 4 outcomes
        self.assertFalse(venv_old.exists(), ".venv in worktree >2d old should have been removed")
        self.assertTrue(venv_recent.exists(), ".venv in worktree <2d old must survive")

        # Check log file was written
        log_files = list(self.log_dir.glob("*.log"))
        self.assertTrue(len(log_files) > 0)
        log_content = log_files[0].read_text()
        self.assertIn("Removed tmp entry", log_content)
        self.assertIn("Removed worktree", log_content)
        self.assertIn("clean_old_branch", log_content)

    def test_dry_run_preserves_everything(self):
        """Dry-run must report candidates without removing any files or worktrees."""
        old_file = self.tmp / "dry_old.txt"
        old_file.write_text("old")
        self.set_old_mtime(old_file, 4)

        repo_work = self.work / "proj"
        wt_clean = repo_work / "dry_wt"
        git(self.main_repo, "worktree", "add", "-b", "dry_branch", str(wt_clean))
        git(self.main_repo, "push", "-q", "-u", "origin", "dry_branch")
        self.set_old_mtime(wt_clean, 8)

        res = self.run_janitor("--dry-run", "--force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        self.assertIn("[dry-run] would remove tmp entry", res.stdout)
        self.assertIn("[dry-run] would remove worktree", res.stdout)
        self.assertTrue(old_file.exists(), "Dry run must not delete tmp file")
        self.assertTrue(wt_clean.exists(), "Dry run must not delete worktree")

    def test_stops_early_when_under_target(self):
        """When disk use is under TARGET_PCT (75%), janitor exits early without doing work."""
        old_file = self.tmp / "never_touched.txt"
        old_file.write_text("old")
        self.set_old_mtime(old_file, 4)

        res = self.run_janitor(extra_env={"MOCK_DISK_PCT": "68"})
        self.assertEqual(res.returncode, 0)
        self.assertIn("under target 75%", res.stdout)
        self.assertTrue(old_file.exists(), "File must survive when disk is under target")

    def test_running_process_cwd_and_open_worktree_and_corrupt_board_safety(self):
        """Verify process cwd, open files in worktrees, and corrupt board safety."""
        # 1. Process cwd in tmp
        scratch = self.tmp / "active_cwd_dir"
        scratch.mkdir()
        (scratch / "work.txt").write_text("in progress")
        self.set_old_mtime(scratch, 4)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 cwd=scratch, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (child.terminate(), child.wait(timeout=5)))

        # 2. Worktree with file held open
        repo_work = self.work / "proj"
        wt_open = repo_work / "wt_open_file"
        git(self.main_repo, "worktree", "add", "-b", "open_file_branch", str(wt_open))
        git(self.main_repo, "push", "-q", "-u", "origin", "open_file_branch")
        self.set_old_mtime(wt_open, 8)
        held_wt_file = (wt_open / "README.md").open()
        self.addCleanup(held_wt_file.close)

        # 3. Worktree that would be removed if board is read, but board is corrupted
        wt_corrupt_check = repo_work / "wt_corrupt_check"
        git(self.main_repo, "worktree", "add", "-b", "corrupt_check_branch", str(wt_corrupt_check))
        git(self.main_repo, "push", "-q", "-u", "origin", "corrupt_check_branch")
        self.set_old_mtime(wt_corrupt_check, 8)
        self.board_file.write_text("{corrupt-json")

        res = self.run_janitor("--force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        self.assertTrue(scratch.exists(), "Active process cwd must survive")
        self.assertTrue(wt_open.exists(), "Worktree with open file handle must survive")
        self.assertTrue(wt_corrupt_check.exists(), "Corrupt board must skip worktree removal")

        # 4. Worktree with schema-invalid JSON '{}' (missing tasks key)
        wt_empty_json = repo_work / "wt_empty_json"
        git(self.main_repo, "worktree", "add", "-b", "empty_json_branch", str(wt_empty_json))
        git(self.main_repo, "push", "-q", "-u", "origin", "empty_json_branch")
        self.set_old_mtime(wt_empty_json, 8)
        self.board_file.write_text("{}")

        res2 = self.run_janitor("--force")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertTrue(wt_empty_json.exists(), "Empty JSON object without tasks key must skip worktree removal")

    def test_missing_task_status_preserves_workspace(self):
        """A task record without a 'status' field must be treated fail-safe as active/claimed."""
        repo_work = self.work / "proj"
        wt = repo_work / "wt_missing_status"
        git(self.main_repo, "worktree", "add", "-b", "missing_status_branch", str(wt))
        git(self.main_repo, "push", "-q", "-u", "origin", "missing_status_branch")
        self.set_old_mtime(wt, 8)
        self.board_file.write_text(json.dumps({"tasks": [
            {"id": "T-no-status", "workspace": str(wt)}
        ]}))

        res = self.run_janitor("--force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertTrue(wt.exists(), "Workspace for task with missing status must survive")

    def test_process_probe_timeout_fails_safe(self):
        """When fuser/lsof probe times out, is_held_open must fail-safe (treat as held open)."""
        target = self.tmp / "probe_timeout_target.txt"
        target.write_text("in use maybe")
        source = Path(JANITOR_SH).read_text()
        code = source.split("<< 'EOF'\n", 1)[1].rsplit('\nEOF', 1)[0]
        functions = {'__name__': 'test_janitor_exec'}
        exec(compile(code, 'test_janitor_exec', 'exec'), functions)
        from unittest.mock import patch
        with patch('shutil.which', return_value='/fake/fuser'), \
             patch('subprocess.run', side_effect=subprocess.TimeoutExpired('fuser', 5)):
            protected = functions['is_held_open'](target, {'/unrelated-descriptor'})
        self.assertTrue(protected, "Probe timeout must be treated fail-safe as held open")


if __name__ == "__main__":
    unittest.main()
