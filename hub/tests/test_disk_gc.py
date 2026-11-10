"""Nightly disk cleanup must preserve work that cannot be recovered from origin."""

import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "disk_gc.py"


def git(*args):
    return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True)


class DiskGCCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.home = Path(self.root.name) / "home"
        self.tmp = Path(self.root.name) / "tmp"
        self.home.mkdir()
        self.tmp.mkdir()
        self.origin = self.home / "origin"
        git("init", "-q", "-b", "main", self.origin)
        (self.origin / "work.txt").write_text("before\n")
        git("-C", self.origin, "add", "work.txt")
        git("-C", self.origin, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "initial")
        bins = self.home / "bin"
        bins.mkdir()
        for name in ("uv", "sudo"):
            command = bins / name
            command.write_text(f'#!/bin/sh\necho "{name} $*" >> "$HOME/calls"\n')
            command.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("HUB_")}
        self.env.update(HOME=str(self.home), TMPDIR=str(self.tmp),
                        PATH=f"{bins}:{os.environ['PATH']}")

    def clone(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "-q", "--no-hardlinks", self.origin, path)
        return path

    def old(self, path, days):
        at = time.time() - days * 86400
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                os.utime(Path(root) / name, (at, at))
            for name in dirs:
                os.utime(Path(root) / name, (at, at))
            os.utime(root, (at, at))

    def run_gc(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], check=False, env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_help_and_unknown_argument_do_not_run_cleanup(self):
        old = self.clone(self.tmp / "scratch-old")
        self.old(old, 2)

        help_result = self.run_gc("--help")
        unknown_result = self.run_gc("--unknown")

        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--dry-run", help_result.stdout)
        self.assertEqual(unknown_result.returncode, 2, unknown_result.stderr)
        self.assertIn("unrecognized arguments", unknown_result.stderr)
        self.assertTrue(old.exists())
        self.assertFalse((self.home / "calls").exists())

    def test_dry_run_reports_candidates_without_removing_or_pruning(self):
        clean = self.clone(self.tmp / "scratch-clean")
        dirty = self.clone(self.tmp / "scratch-dirty")
        (dirty / "work.txt").write_text("after\n")
        leftover = self.tmp / "tmp-leftover"
        leftover.mkdir()
        (leftover / "file").write_text("keep")
        for path in (clean, dirty, leftover):
            self.old(path, 8)

        result = self.run_gc("--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in (clean, dirty, leftover):
            self.assertTrue(path.exists())
            self.assertIn(f"would remove {path}", result.stderr)
        self.assertIn(f"would archive {dirty}", result.stderr)
        self.assertIn("would prune uv cache", result.stderr)
        self.assertFalse((self.home / "hub" / "artifacts").exists())
        calls = (self.home / "calls").read_text().splitlines() if (self.home / "calls").exists() else []
        self.assertFalse(any("prune" in call for call in calls), calls)
        self.assertIn("errors=0", result.stdout)

    def test_dry_run_reports_parent_after_its_checkout(self):
        parent = self.tmp / "tmp-parent"
        repo = self.clone(parent / "scratch-nested")
        self.old(parent, 2)

        result = self.run_gc("--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(repo.exists())
        self.assertTrue(parent.exists())
        self.assertIn(f"would remove {repo}", result.stderr)
        self.assertIn(f"disk-gc would remove {parent}", result.stderr.splitlines())

    def test_dry_run_lists_tmp_named_checkout_once(self):
        repo = self.clone(self.tmp / "tmp-repo")
        self.old(repo, 2)

        result = self.run_gc("--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(repo.exists())
        self.assertEqual(result.stderr.splitlines().count(f"disk-gc would remove {repo}"), 1)

    def test_failed_checkout_reports_path_and_exception(self):
        broken = self.clone(self.tmp / "scratch-broken")
        (broken / ".git" / "HEAD").write_text("ref: refs/heads/missing\n")
        self.old(broken, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 1)
        self.assertIn("errors=1", result.stdout)
        self.assertIn(str(broken), result.stderr)
        self.assertIn("CalledProcessError", result.stderr)
        self.assertIn("returned non-zero exit status", result.stderr)

    def test_checkout_without_origin_is_kept_without_error(self):
        repo = self.clone(self.tmp / "scratch-no-origin")
        git("-C", repo, "remote", "remove", "origin")
        self.old(repo, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(repo.exists())
        self.assertIn("errors=0", result.stdout)

    def test_failed_cache_prune_reports_command_and_exception(self):
        uv = self.home / "bin" / "uv"
        uv.write_text("#!/bin/sh\nexit 9\n")
        uv.chmod(0o755)

        result = self.run_gc()

        self.assertEqual(result.returncode, 1)
        self.assertIn("errors=1", result.stdout)
        self.assertIn("uv cache prune", result.stderr)
        self.assertIn("CalledProcessError", result.stderr)

    def test_removes_only_old_recoverable_checkouts_and_test_dirs(self):
        safe = self.clone(self.tmp / "scratch-safe")
        new = self.clone(self.tmp / "scratch-new")
        unpushed = self.clone(self.tmp / "scratch-unpushed")
        (unpushed / "work.txt").write_text("new commit\n")
        git("-C", unpushed, "add", "work.txt")
        git("-C", unpushed, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "unpushed")
        old_tmp = self.tmp / "tmp-old"
        new_tmp = self.tmp / "tmp-new"
        old_tmp.mkdir()
        new_tmp.mkdir()
        (old_tmp / "leftover").write_text("discard")
        (new_tmp / "leftover").write_text("keep")
        self.old(safe, 2)
        self.old(unpushed, 2)
        self.old(old_tmp, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(safe.exists())
        self.assertTrue(new.exists())
        self.assertTrue(unpushed.exists())
        self.assertFalse(old_tmp.exists())
        self.assertTrue(new_tmp.exists())
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertIn("git=", result.stdout)
        self.assertIn("tmp=", result.stdout)
        self.assertEqual((self.home / "calls").read_text().splitlines(),
                         ["sudo -n true", "uv cache prune", "sudo -n docker builder prune -f"])

    def test_dirty_checkout_waits_seven_days_then_saves_patch_and_untracked(self):
        old = self.clone(self.tmp / "scratch-dirty-old")
        young = self.clone(self.tmp / "scratch-dirty-young")
        for path in (old, young):
            (path / "work.txt").write_text("after\n")
            (path / "notes.txt").write_text("untracked\n")
        self.old(old, 8)
        self.old(young, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old.exists(), result.stdout + result.stderr)
        self.assertTrue(young.exists())
        artifacts = list((self.home / "hub" / "artifacts" / "wip-patches").rglob("changes.patch"))
        self.assertEqual(len(artifacts), 1)
        self.assertIn("+after", artifacts[0].read_text())
        with tarfile.open(artifacts[0].with_name("untracked.tar.gz")) as archive:
            self.assertEqual(archive.extractfile("notes.txt").read(), b"untracked\n")

    def test_url_origin_uses_tracking_refs_and_tmp_dir_keeps_unpushed_repo(self):
        safe = self.clone(self.tmp / "scratch-url-safe")
        parent = self.tmp / "tmp-protected"
        unpushed = self.clone(parent / "repo")
        for path in (safe, unpushed):
            git("-C", path, "remote", "set-url", "origin", "https://example.invalid/repo.git")
        (unpushed / "work.txt").write_text("local commit\n")
        git("-C", unpushed, "add", "work.txt")
        git("-C", unpushed, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "unpushed")
        self.old(safe, 2)
        self.old(parent, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(safe.exists())
        self.assertTrue(unpushed.exists())
        self.assertTrue(parent.exists())

    def test_current_session_scratchpad_is_untouched(self):
        session = self.tmp / "claude-1001" / "project" / "session" / "scratchpad"
        old = self.clone(session / "scratch-repo")
        self.old(old, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(old.exists())

    def test_session_with_recent_sibling_activity_is_untouched(self):
        session = self.tmp / "claude-1001" / "project" / "session"
        old = self.clone(session / "scratchpad" / "scratch-repo")
        activity = session / "activity.log"
        activity.write_text("earlier\n")
        self.old(session, 2)
        activity.write_text("active today\n")

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(old.exists())

    def test_reflog_only_local_commit_is_kept(self):
        repo = self.clone(self.tmp / "scratch-reflog")
        (repo / "work.txt").write_text("local commit\n")
        git("-C", repo, "add", "work.txt")
        git("-C", repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "local")
        git("-C", repo, "reset", "--hard", "HEAD~1")
        self.old(repo, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(repo.exists())

    def test_commit_fetched_into_origin_without_a_ref_is_not_safe(self):
        repo = self.clone(self.tmp / "scratch-fetched")
        (repo / "work.txt").write_text("reviewed but not merged\n")
        git("-C", repo, "add", "work.txt")
        git("-C", repo, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "review")
        commit = git("-C", repo, "rev-parse", "HEAD").stdout.strip()
        git("-C", self.origin, "fetch", "-q", repo, "HEAD")
        self.assertNotIn(commit, git("-C", self.origin, "rev-list", "--all").stdout)
        self.old(repo, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(repo.exists())

    def test_parent_checkout_keeps_nested_unpushed_checkout(self):
        parent = self.clone(self.tmp / "scratch-parent")
        nested = self.clone(parent / "nested")
        (nested / "work.txt").write_text("unpublished\n")
        git("-C", nested, "add", "work.txt")
        git("-C", nested, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-qm", "unpublished")
        self.old(parent, 8)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(parent.exists())
        self.assertTrue(nested.exists())

    def test_old_scratch_worktree_is_removed_through_git(self):
        main = self.clone(self.home / "main")
        scratch = self.tmp / "scratch-worktree"
        git("-C", main, "worktree", "add", "-q", "-b", "scratch", scratch)
        self.old(scratch, 2)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(scratch.exists())
        self.assertNotIn(str(scratch), git("-C", main, "worktree", "list", "--porcelain").stdout)

    def test_refuses_tmpdir_outside_tmp(self):
        protected = self.home / "code"
        protected.mkdir()
        old = protected / "tmp-old"
        old.mkdir()
        (old / "work").write_text("keep")
        self.old(old, 2)
        self.env["TMPDIR"] = str(protected)

        result = self.run_gc()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())

    def test_unavailable_sudo_skips_docker_without_an_error(self):
        sudo = self.home / "bin" / "sudo"
        sudo.write_text("#!/bin/sh\nexit 1\n")
        sudo.chmod(0o755)

        result = self.run_gc()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("docker=0.0MB errors=0", result.stdout)
        self.assertEqual((self.home / "calls").read_text().splitlines(), ["uv cache prune"])


if __name__ == "__main__":
    unittest.main()
