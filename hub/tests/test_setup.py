"""Small offline checks for the hub's setup scripts."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SetupTest(unittest.TestCase):
    def test_make_check_uses_one_lock_across_checkouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            lock = home / "hub" / "state" / "make-check.lock"
            for name in ("first", "second"):
                checkout = root / name
                checkout.mkdir()
                shutil.copyfile(ROOT / "Makefile", checkout / "Makefile")
                result = subprocess.run(["make", "-n", "check"], cwd=checkout,
                                        env={**os.environ, "HOME": str(home)},
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'exec 9>>"{lock}"', result.stdout)

    def test_make_check_caches_an_unchanged_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "tests").mkdir(parents=True)
            shutil.copyfile(ROOT / "Makefile", repo / "Makefile")
            (repo / "pyproject.toml").write_text('[project]\nname = "t"\nversion = "0"\nrequires-python = ">=3.11"\n'
                                                 'dependencies = []\n[tool.uv]\npackage = false\n')
            (repo / ".gitignore").write_text(".venv/\nuv.lock\n__pycache__/\n")
            test = repo / "tests" / "test_ok.py"
            test.write_text("import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "VIRTUAL_ENV"))}
            for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t"]):
                subprocess.run(["git", *cmd], cwd=repo, env=env, check=True, capture_output=True)
            ok = Path(tmp) / "make-check.ok"

            def check(*extra):
                r = subprocess.run(["make", "-s", "check", f"CHECK_LOCK={tmp}/lock", f"CHECK_OK={ok}", *extra],
                                   cwd=repo, env=env, capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                return "cached" in r.stdout

            self.assertFalse(check(), "first run must run the suite")
            self.assertTrue(check(), "an unchanged tree hits the cache")
            test.write_text(test.read_text() + "# touched\n")
            self.assertFalse(check(), "a touched tracked file misses")
            self.assertTrue(check())
            (repo / "tests" / "test_new.py").write_text("import unittest\n")
            self.assertFalse(check(), "a new untracked file misses")
            self.assertFalse(check("FORCE=1"), "FORCE=1 always runs")
            self.assertTrue(check())
            (repo / "projects").mkdir()
            (repo / "projects" / "notes.md").write_text("agent notes\n")
            self.assertTrue(check(), "untracked files under projects/ are not in the key")

    def test_no_test_reads_untracked_hub_projects(self):
        # make check's cache key leaves untracked projects/ files out; that is only safe while every
        # test that reads the real hub's projects/ reads a tracked file (tracked files stay in the key).
        seg = r'(?:\s*/\s*"[^"]+")*'
        real = re.compile(r'\b(?:HUB|ROOT)\s*/\s*"(projects(?:/[^"]*)?)"(' + seg + ')')
        home = re.compile(r'home\(\)[^\n]*"projects|expanduser\([^)]*hub/projects')
        for f in sorted((ROOT / "tests").glob("*.py")):
            if f.name == "test_setup.py":
                continue
            text = f.read_text()
            self.assertIsNone(home.search(text), f"{f.name} reads ~/hub/projects through the home directory")
            for m in real.finditer(text):
                path = "/".join([m.group(1)] + re.findall(r'"([^"]+)"', m.group(2)))
                tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], cwd=ROOT,
                                         capture_output=True).returncode == 0
                self.assertTrue(tracked, f"{f.name} reads {path}, which is not tracked: make check's cache "
                                         "would miss a change to it (track it or drop the projects/ exclusion)")

    def test_hubaccounts_reads_claude_seats_from_factory_with_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hub = home / "hub"
            hub.mkdir()
            factory = hub / "factory.json"
            factory.write_text(json.dumps({"agents": [
                {"name": "Zeus", "kind": "claude"},
                {"name": "Hephaestus", "kind": "agy"},
                {"name": "Ares", "kind": "claude"}]}))
            env = {**os.environ, "HOME": str(home)}

            def accounts():
                return subprocess.run(["bash", "-c", f"source {ROOT / 'shell.sh'}; hubaccounts"],
                                      env=env, capture_output=True, text=True, timeout=10)

            result = accounts()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ares", result.stdout)
            self.assertNotIn("Apollo", result.stdout)
            self.assertNotIn("Athena", result.stdout)
            self.assertIn("Hephaestus", result.stdout)

            factory.unlink()
            result = accounts()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Zeus", result.stdout)
            self.assertIn("Hermes", result.stdout)
            self.assertNotIn("Ares", result.stdout)

    def test_idle_check_includes_agy_brain_only_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, bin_dir = root / "home", root / "bin"
            brain = home / ".gemini" / "antigravity-cli" / "brain"
            brain.mkdir(parents=True)
            (home / "hub").mkdir()
            (home / ".codex" / "sessions").mkdir(parents=True)
            bin_dir.mkdir()
            for name, body in {
                "curl": "printf on\n",
                "cut": "case \"$*\" in *uptime*) echo 10801;; *) echo 0.00;; esac\n",
                "who": ":\n",
                "find": "printf '%s\\n' \"$@\" > \"$FIND_ARGS\"\n",
            }.items():
                path = bin_dir / name
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)
            args = root / "find-args"
            env = {**os.environ, "HUB_IDLE_HOME": str(home), "FIND_ARGS": str(args),
                   "PATH": f"{bin_dir}:{os.environ['PATH']}"}

            def idle_check():
                return subprocess.run(["/bin/bash", str(ROOT / "cloud" / "startup.sh"), "check", "--dry-run"],
                                      env=env, capture_output=True, text=True, timeout=10)

            result = idle_check()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("idle: would stop the VM", result.stdout)
            self.assertIn(str(brain), args.read_text().splitlines())

            brain.rmdir()
            result = idle_check()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(str(brain), args.read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
