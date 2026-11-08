#!/usr/bin/env python3
"""Regression tests for clean_repo: every case here is a bug that shipped once.

Each test names who found it. All of them were reproduced by Prometheus from a Codex
session after the code was already committed and believed working -- which is the
argument for the suite existing at all.

    uv run python tests/test_clean_repo.py
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HUB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, HUB)


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def hub(*args, cwd=None, env=None):
    e = dict(os.environ, **(env or {}))
    # Never let a test touch the live board, inbox or projects directory.
    e.pop("HUB_AGENT", None)
    e.pop("HUB_PROJECT", None)
    return subprocess.run([sys.executable, os.path.join(HUB, "board.py"), *args],
                          capture_output=True, text=True, cwd=cwd, env=e)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hubdir = os.path.join(self.tmp, "hub")
        os.makedirs(self.hubdir)
        self.env = {"HUB_DIR": self.hubdir}
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "T")
        os.makedirs(os.path.join(self.repo, "src"))
        Path(os.path.join(self.repo, "src", "a.py")).write_text("x = 1\n")
        Path(os.path.join(self.repo, "README.md")).write_text("# real\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")


class TestNewProject(unittest.TestCase):
    def test_first_commit_works_with_no_global_identity(self):
        """Zeus, 2026-09-21: the Base fixture sets user.name, so this never ran cold."""
        tmp = tempfile.mkdtemp()
        root = os.path.join(tmp, "code", "p")
        env = {"HUB_DIR": os.path.join(tmp, "hub"), "HOME": tmp,
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        r = hub("new-project", "p", "--path", root, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        Path(os.path.join(root, "a.py")).write_text("x = 1\n")
        git(root, "add", "a.py")
        e = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        c = subprocess.run(["git", "-C", root, "commit", "-qm", "first"],
                           capture_output=True, text=True, env=e)
        self.assertEqual(c.returncode, 0, c.stderr)


class TestNewProjectReadOnly(unittest.TestCase):
    def test_unwritable_parent_is_one_line_not_a_traceback(self):
        """Prometheus, T-101: sandboxed Codex got OSError [Errno 30] with a traceback."""
        tmp = tempfile.mkdtemp()
        ro = os.path.join(tmp, "ro")
        os.makedirs(ro)
        os.chmod(ro, 0o555)
        try:
            r = hub("new-project", "p", "--path", os.path.join(ro, "p"),
                    env={"HUB_DIR": os.path.join(tmp, "hub")})
        finally:
            os.chmod(ro, 0o755)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("--path", r.stderr)


class TestClassify(Base):
    def test_runbooks_are_not_harness(self):
        """Over-matching teaches everyone to pass --no-verify."""
        import clean_repo
        self.assertEqual(clean_repo.classify("docs/runbooks/incident.md"), "other")

    def test_pattern_beats_name(self):
        """Prometheus: classify said debate/README.md was product while the hook blocked
        it -- one rule giving two answers."""
        import clean_repo
        self.assertEqual(clean_repo.classify("README.md"), "product")
        self.assertEqual(clean_repo.classify("debate/README.md"), "harness")
        self.assertEqual(clean_repo.classify("docs/superpowers/README.md"), "harness")


class TestCase(Base):
    def test_hook_and_classify_ignore_case(self):
        """Zeus, 2026-09-21: claude.md, HANDOFF.md and docs/Roadmap.md all committed."""
        import clean_repo
        for f in ("claude.md", "HANDOFF.md", "docs/Roadmap.md"):
            self.assertEqual(clean_repo.classify(f), "harness", f)
        hub("init-repo", self.repo, env=self.env)
        os.makedirs(os.path.join(self.repo, "docs"))
        Path(os.path.join(self.repo, "docs", "Roadmap.md")).write_text("x\n")
        git(self.repo, "add", "-f", "docs/Roadmap.md")
        r = subprocess.run(["git", "-C", self.repo, "commit", "-qm", "x"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "hook let docs/Roadmap.md through")


class TestInitRepo(Base):
    def test_installs_and_hook_blocks_then_allows(self):
        r = hub("init-repo", self.repo, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hook = os.path.join(self.repo, ".git", "hooks", "pre-commit")
        self.assertTrue(os.access(hook, os.X_OK))

        Path(os.path.join(self.repo, "CLAUDE.md")).write_text("x\n")
        git(self.repo, "add", "-f", "CLAUDE.md")
        blocked = subprocess.run(["git", "-C", self.repo, "commit", "-m", "h"],
                                 capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0, "harness commit should be refused")

        git(self.repo, "reset", "-q")
        Path(os.path.join(self.repo, "src", "b.py")).write_text("y = 2\n")
        git(self.repo, "add", "src/b.py")
        ok = subprocess.run(["git", "-C", self.repo, "commit", "-m", "real"],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, "real work must not be blocked")

    def test_worktree_does_not_crash(self):
        """Prometheus: NotADirectoryError -- in a worktree .git is a file, not a dir."""
        wt = os.path.join(self.tmp, "wt")
        git(self.repo, "worktree", "add", "-q", "-b", "side", wt)
        r = hub("init-repo", wt, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_core_hookspath_is_honoured(self):
        """Prometheus: it wrote .git/hooks/pre-commit, said 'is set up', and git used a
        different directory -- so the commit went through."""
        alt = os.path.join(self.tmp, "althooks")
        os.makedirs(alt)
        git(self.repo, "config", "core.hooksPath", alt)
        r = hub("init-repo", self.repo, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.access(os.path.join(alt, "pre-commit"), os.X_OK),
                        "hook must go where git actually looks")

        Path(os.path.join(self.repo, "AGENTS.md")).write_text("x\n")
        git(self.repo, "add", "-f", "AGENTS.md")
        blocked = subprocess.run(["git", "-C", self.repo, "commit", "-m", "h"],
                                 capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0, "hook under core.hooksPath must fire")

    def test_foreign_hook_fails_loudly(self):
        """Prometheus: it printed SKIPPED, then 'is set up', then exited 0. False
        enforcement is worse than none."""
        hook = os.path.join(self.repo, ".git", "hooks", "pre-commit")
        Path(hook).write_text("#!/bin/sh\nexit 0\n")
        os.chmod(hook, 0o755)
        r = hub("init-repo", self.repo, env=self.env)
        self.assertEqual(r.returncode, 1, "must exit non-zero when the guard is absent")
        self.assertIn("NOT", r.stdout)


class TestRenameBypass(Base):
    def test_rename_into_a_harness_path_is_caught(self):
        """Prometheus: `git mv notes.md docs/roadmap.md` is R100 -- neither A nor M --
        and walked past the hook and ship-check untouched."""
        hub("init-repo", self.repo, env=self.env)
        Path(os.path.join(self.repo, "notes.md")).write_text("notes\n")
        git(self.repo, "add", "notes.md")
        subprocess.run(["git", "-C", self.repo, "commit", "-m", "notes"],
                       capture_output=True, text=True)

        os.makedirs(os.path.join(self.repo, "docs"), exist_ok=True)
        git(self.repo, "mv", "notes.md", "docs/roadmap.md")
        blocked = subprocess.run(["git", "-C", self.repo, "commit", "-m", "rename"],
                                 capture_output=True, text=True)
        self.assertNotEqual(blocked.returncode, 0,
                            "a rename into a harness path must be refused")

    def test_ship_check_sees_a_renamed_file(self):
        git(self.repo, "checkout", "-q", "-b", "feature")
        Path(os.path.join(self.repo, "notes.md")).write_text("notes\n")
        git(self.repo, "add", "notes.md")
        git(self.repo, "commit", "-qm", "notes")
        os.makedirs(os.path.join(self.repo, "docs"), exist_ok=True)
        git(self.repo, "mv", "notes.md", "docs/roadmap.md")
        git(self.repo, "commit", "-qam", "rename")

        r = hub("ship-check", self.repo, "--base", self.base, env=self.env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("docs/roadmap.md", r.stdout)


class TestShipCheckQuiet(Base):
    def test_silent_without_an_upstream(self):
        r = hub("ship-check", self.repo, "--quiet", env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")

    def test_silent_inside_the_hub_itself(self):
        git(self.hubdir, "init", "-q", "-b", "main")
        r = hub("ship-check", self.hubdir, "--quiet", env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


class TestScrub(Base):
    def test_refuses_to_overwrite_a_different_file(self):
        """Prometheus: copy2 silently overwrote the destination, and two repos with the
        same basename land in the same directory."""
        os.makedirs(os.path.join(self.repo, "docs", "superpowers"))
        Path(os.path.join(self.repo, "docs", "superpowers", "p.md")).write_text("NEW\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "plans")

        dest = os.path.join(self.hubdir, "projects", "repo", "docs", "superpowers")
        os.makedirs(dest)
        Path(os.path.join(dest, "p.md")).write_text("ORIGINAL — must survive\n")

        r = hub("scrub", self.repo, "--apply", env=self.env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("refusing", r.stdout.lower())
        self.assertIn("ORIGINAL", Path(os.path.join(dest, "p.md")).read_text())
        self.assertIn("docs/superpowers/p.md", git(self.repo, "ls-files"),
                      "nothing may be untracked when the copy was refused")

    def test_keep_leaves_a_path_tracked(self):
        Path(os.path.join(self.repo, "CLAUDE.md")).write_text("brief\n")
        git(self.repo, "add", "-f", "CLAUDE.md")
        git(self.repo, "commit", "-qm", "brief", "--no-verify")
        r = hub("scrub", self.repo, "--apply", "--keep", r"^CLAUDE\.md$", env=self.env)
        self.assertIn("CLAUDE.md", git(self.repo, "ls-files"))


class TestScrubAftercare(Base):
    def test_copies_are_committed_and_case_variants_stay_ignored(self):
        """Zeus, 2026-09-21: after scrub, HANDOFF.md came back as `??` (exclude globs
        were case-sensitive) and the hub copy sat uncommitted."""
        git(self.hubdir, "init", "-q", "-b", "main")
        git(self.hubdir, "config", "user.email", "t@t")
        git(self.hubdir, "config", "user.name", "T")
        hub("init-repo", self.repo, env=self.env)
        Path(os.path.join(self.repo, "HANDOFF.md")).write_text("h\n")
        git(self.repo, "add", "-f", "HANDOFF.md")
        git(self.repo, "commit", "-qm", "h", "--no-verify")
        r = hub("scrub", self.repo, "--apply", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.repo, "status", "--short", "--", "HANDOFF.md"), "D  HANDOFF.md")
        self.assertIn("projects/repo/HANDOFF.md", git(self.hubdir, "ls-files"))


class TestScrubReadOnlyHubGit(Base):
    def test_untracks_even_when_the_hub_cannot_commit(self):
        """Prometheus, T-101: in Codex ~/hub/.git is read-only; scrub died after the
        copy and before the untrack."""
        git(self.hubdir, "init", "-q", "-b", "main")
        Path(self.hubdir, ".git", "index.lock").touch()  # git add fails
        Path(self.repo, "HANDOFF.md").write_text("h\n")
        git(self.repo, "add", "-f", "HANDOFF.md")
        git(self.repo, "commit", "-qm", "h", "--no-verify")
        r = hub("scrub", self.repo, "--apply", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("NOT committed", r.stdout)
        self.assertNotIn("HANDOFF.md", git(self.repo, "ls-files"))


class TestDoctrineNames(unittest.TestCase):
    def test_common_agent_write_ups_are_harness(self):
        """Zeus, 2026-09-21: the doctrine said plans and summaries; the hook let
        PLAN.md, ROADMAP.md, docs/specs/ and IMPLEMENTATION_SUMMARY.md through."""
        import clean_repo
        for f in ("PLAN.md", "ROADMAP.md", "web/roadmap.md", "docs/plans/a.md",
                  "docs/specs/b.md", "IMPLEMENTATION_SUMMARY.md", "session-summary.md",
                  ".superpowers/brainstorm/a.html", ".worktrees/x/a.py"):
            self.assertEqual(clean_repo.classify(f), "harness", f)
        for f in ("README.md", "docs/runbooks/x.md", "src/planner.py", "docs/plan-b/x.md"):
            self.assertNotEqual(clean_repo.classify(f), "harness", f)


class TestKeptFileStaysEditable(Base):
    def test_hook_allows_editing_a_tracked_harness_file(self):
        """`scrub --keep CLAUDE.md` kept it tracked, then the hook
        (ACMRT) blocked every edit to it -- a product's CLAUDE.md included. Blocking
        edits to a file the human chose to keep teaches --no-verify."""
        Path(os.path.join(self.repo, "CLAUDE.md")).write_text("team notes\n")
        git(self.repo, "add", "CLAUDE.md")
        git(self.repo, "commit", "-qm", "kept by the human")
        hub("init-repo", self.repo, env=self.env)
        with open(os.path.join(self.repo, "CLAUDE.md"), "a") as f:
            f.write("more\n")
        r = subprocess.run(["git", "-C", self.repo, "commit", "-qam", "edit"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestSessionHook(Base):
    HOOK = os.path.join(HUB, "plugin", "hooks", "session-ship-check.js")

    def setUp(self):
        super().setUp()
        if not os.path.exists(self.HOOK):
            self.skipTest("plugin hook not present")
        # A repo with a real upstream and a real harness file, so the hook has something
        # to SAY. Without this the hook emits nothing and every assertion below is
        # vacuous -- which is exactly what the first version of this test did: it passed
        # 14/14 while exercising no JSON at all. Prometheus caught it.
        self.origin = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", self.origin)
        git(self.repo, "remote", "add", "origin", self.origin)
        git(self.repo, "push", "-q", "-u", "origin", "main")
        os.makedirs(os.path.join(self.repo, "docs"), exist_ok=True)
        Path(os.path.join(self.repo, "docs", "roadmap.md")).write_text("plans\n")
        git(self.repo, "add", "-f", "docs/roadmap.md")
        git(self.repo, "commit", "-qm", "roadmap", "--no-verify")

    def run_hook(self, cwd, **extra):
        env = dict(os.environ, HUB_DIR=self.hubdir, **extra)
        env.pop("PLUGIN_DATA", None)
        env.update(extra)
        return subprocess.run(["node", self.HOOK], capture_output=True, text=True,
                              cwd=cwd, env=env)

    def test_unpushed_branch_is_not_silent(self):
        """Zeus, 2026-09-21: quiet mode and the done nudge needed @{u}, so a local
        feature branch -- where agent work actually happens -- was silent in both
        while plain ship-check said NOT clean."""
        git(self.repo, "checkout", "-q", "-b", "feat")
        r = hub("ship-check", self.repo, "--quiet", env=self.env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("docs/roadmap.md", r.stdout)
        Path(os.path.join(self.hubdir, "board.json")).write_text('{"next_id": 1, "tasks": []}')
        hub("new", "t", env=self.env, cwd=self.repo)
        hub("claim", "T-001", "--as", "W", env=self.env, cwd=self.repo)
        d = hub("done", "T-001", "--as", "W", env=self.env, cwd=self.repo)
        self.assertIn("harness file(s) would ship", d.stdout, d.stdout + d.stderr)

    def test_codex_gets_session_start_json(self):
        r = self.run_hook(self.repo, PLUGIN_DATA="1")
        self.assertEqual(r.returncode, 0, "the hook must never fail session startup")
        self.assertTrue(r.stdout.strip(), "a dirty repo must produce output, or the "
                                          "test proves nothing")
        body = json.loads(r.stdout)
        self.assertEqual(body["systemMessage"], "CLEAN-REPO")
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("docs/roadmap.md", body["hookSpecificOutput"]["additionalContext"])

    def test_claude_gets_raw_text_not_json(self):
        r = self.run_hook(self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("docs/roadmap.md", r.stdout)
        self.assertNotIn("hookSpecificOutput", r.stdout)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(r.stdout)

    def test_silent_on_a_clean_repo_in_both_shapes(self):
        """A guard that fires on a clean repo is a guard people mute."""
        git(self.repo, "rm", "-q", "--cached", "docs/roadmap.md")
        git(self.repo, "commit", "-qm", "untrack", "--no-verify")
        for env in ({}, {"PLUGIN_DATA": "1"}):
            r = self.run_hook(self.repo, **env)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "", f"should be silent with env={env}")

    def test_exits_zero_outside_a_repo(self):
        r = self.run_hook(self.tmp)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    import warnings
    warnings.simplefilter("ignore", ResourceWarning)  # the tests write throwaway files
    unittest.main(verbosity=2)
