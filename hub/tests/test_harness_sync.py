"""Tests for `hub harness-sync`: the personal-data sweep gate and the three-way sync onto a branch."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import harness_sync as hs  # noqa: E402

# Planted values are assembled at runtime so this file passes the sweep when it is synced itself.
H, AT = "/ho" + "me/", "@" + "gmail.com"

MANIFEST = {
    "map": [{"live": "*.py", "harness": "hub/"}],
    "subs": [[H + "alex/hub\\b", "$HUB_DIR"]],
    "deny": ["\\brobin\\b"],
    "allow": [],
}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def commit(repo, files, msg="c"):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD").strip()


class SweepTest(unittest.TestCase):
    def kinds(self, text):
        return [k for _, k, _ in hs.sweep_text(text, MANIFEST["deny"])]

    def test_planted_email_is_red(self):
        self.assertEqual(self.kinds(f"contact: alex.smith{AT}\n"), ["email"])

    def test_planted_home_path_is_red(self):
        self.assertEqual(self.kinds(f"cd {H}alex/code/webapp\n"), ["home path"])

    def test_keys_phone_whatsapp_and_denied_name_are_red(self):
        self.assertEqual(self.kinds("AKIA" + "IOSFODNN7EXAMPLE"), ["key"])
        self.assertEqual(self.kinds("call +" + "44 7700 900123"), ["phone"])
        self.assertIn("whatsapp id", self.kinds("to 447700900123" + "@s.whatsapp.net"))
        self.assertEqual(self.kinds("ask Robin"), ["denied"])

    def test_placeholders_and_noreply_pass(self):
        clean = ("Co-Authored-By: Claude <noreply@anthropic.com>\n"
                 "1+alex@users.noreply.github.com\ncd /home/you/hub\nuses actions/checkout@v4\n")
        self.assertEqual(hs.sweep_text(clean), [])

    def test_exempt_file_may_carry_fake_keys_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "t.py").write_text("AKIA" + "IOSFODNN7EXAMPLE\n" + f"{H}alex\n")
            hits = hs.sweep_files(Path(d), ["t.py"], {"exempt": {"t.py": ["key"]}})
        self.assertEqual(hits, [f"t.py:2: home path: {H}alex"])


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.live, self.harness = self.tmp / "live", self.tmp / "harness"
        for r in (self.live, self.harness):
            r.mkdir()
            git(r, "init", "-q", "-b", "main")
        self.since = commit(self.live, {"tool.py": f"A\nroot = '{H}alex/hub'\nB\nC\n", "skip.py": "x\n"})
        # The harness carries the adapted file plus an edit of its own, and left skip.py out.
        commit(self.harness, {"hub/tool.py": "A (harness wording)\nroot = '$HUB_DIR'\nB\nC\n"})

    def sync(self):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = hs.run(self.live, self.harness, MANIFEST, init=self.since, branch="sync")
        return rc, err.getvalue()

    def test_merges_live_change_keeps_harness_edit_and_records_commit(self):
        head = commit(self.live, {"tool.py": f"A\nroot = '{H}alex/hub'\nB\nC changed live\n",
                                  "skip.py": "y\n", "new.py": "fresh\n"})
        rc, err = self.sync()
        self.assertEqual(rc, 0, err)
        self.assertEqual(git(self.harness, "show", "sync:hub/tool.py"),
                         "A (harness wording)\nroot = '$HUB_DIR'\nB\nC changed live\n")
        self.assertEqual(git(self.harness, "show", "sync:hub/new.py"), "fresh\n")
        self.assertNotIn("hub/skip.py", git(self.harness, "ls-tree", "-r", "--name-only", "sync"))
        self.assertEqual(json.loads(git(self.harness, "show", "sync:.hub-sync.json"))["live_commit"], head)
        self.assertEqual(git(self.harness, "branch", "--show-current").strip(), "main")
        self.assertEqual(git(self.harness, "status", "--porcelain"), "")

    def test_planted_email_fails_the_sync_and_commits_nothing(self):
        commit(self.live, {"tool.py": f"A\nroot = '{H}alex/hub'\nB\nC\nmail = 'alex{AT}'\n"})
        rc, err = self.sync()
        self.assertEqual(rc, 1)
        self.assertIn(f"hub/tool.py:5: email: alex{AT}", err)
        self.assertNotIn("sync", git(self.harness, "branch", "--list", "sync"))

    def test_planted_home_path_fails_the_sync(self):
        commit(self.live, {"new.py": f"LOG = '{H}robinh/logs'\n"})
        rc, err = self.sync()
        self.assertEqual(rc, 1)
        self.assertIn(f"home path: {H}robinh", err)


class AdversarialTest(unittest.TestCase):
    """Prometheus's T-1053 review fixtures: each one must fail closed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.live, self.harness = self.tmp / "live", self.tmp / "harness"
        for r in (self.live, self.harness):
            r.mkdir()
            git(r, "init", "-q", "-b", "main")
        self.manifest = {**MANIFEST, "map": MANIFEST["map"] + [{"live": "runbooks/*.md", "harness": "runbooks/"}],
                         "allow": ["https://github\\.com/[\\w-]+/my_harness"]}
        self.since = commit(self.live, {"tool.py": "BASE\n"})

    def sync(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                return hs.run(self.live, self.harness, self.manifest, init=self.since, branch="sync"), err.getvalue()
            except SystemExit as e:
                return "exit", str(e)

    def assert_rejected(self):
        rc, err = self.sync()
        self.assertNotEqual(rc, 0, err)
        self.assertEqual(git(self.harness, "branch", "--list", "sync"), "")
        return err

    def test_text_bypasses_are_red(self):
        for text in ["https://github.com/someone/my_harness owner=alex" + AT,
                     "alex" + "@users.noreply.github.com.evil.test",
                     "alice.users.noreply.github.com" + AT,
                     "+" + "44 (7700) 900123",
                     H + "you-real/private",
                     "C:/" + "Users/Alex/private"]:
            self.assertTrue(hs.sweep_text(text, (), self.manifest["allow"]), text)

    def test_allowed_span_does_not_clear_the_line(self):
        commit(self.harness, {"hub/tool.py": "BASE\n"})
        commit(self.live, {"tool.py": "# https://github.com/someone/my_harness owner=alex" + AT + "\n"})
        self.assertIn("email", self.assert_rejected())

    def test_private_filename_is_red(self):
        commit(self.harness, {"hub/tool.py": "BASE\n"})
        commit(self.live, {"runbooks/alex" + AT + ".md": "# harmless\n"})
        self.assertIn("name: email", self.assert_rejected())

    def test_utf16_fails_closed(self):
        commit(self.harness, {"hub/tool.py": "BASE\n"})
        (self.live / "runbooks").mkdir()
        (self.live / "runbooks/u.md").write_bytes(("Contact alex" + AT + "\n").encode("utf-16"))
        commit(self.live, {})
        self.assertIn("u.md: encoding", self.assert_rejected())

    def test_symlink_in_harness_is_never_written_through(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "tool.py").write_text("BASE\n")
        (self.harness / "hub").symlink_to(outside, target_is_directory=True)
        commit(self.harness, {})
        commit(self.live, {"tool.py": "CHANGED\n"})
        self.assertIn("symlink", self.assert_rejected())
        self.assertEqual((outside / "tool.py").read_text(), "BASE\n")

    def test_harness_hooks_do_not_run(self):
        commit(self.harness, {"hub/tool.py": "BASE\n"})
        remote, hooks = self.tmp / "remote.git", self.tmp / "hooks"
        git(self.tmp, "init", "--bare", "-q", str(remote))
        hooks.mkdir()
        (hooks / "post-commit").write_text(f"#!/bin/sh\ngit push -q {remote} HEAD:refs/heads/leak\n")
        (hooks / "post-commit").chmod(0o755)
        git(self.harness, "config", "core.hooksPath", str(hooks))
        commit(self.live, {"tool.py": "CHANGED\n"})
        self.assertEqual(self.sync()[0], 0)
        self.assertEqual(git(remote, "branch", "--list"), "")

    def test_bomless_utf16_and_disguised_binary_fail_closed(self):
        commit(self.harness, {"hub/tool.py": "BASE\n"})
        secret = "Contact alex" + AT + "\n"
        (self.live / "runbooks").mkdir()
        (self.live / "runbooks/le.md").write_bytes(secret.encode("utf-16-le"))
        (self.live / "runbooks/be.md").write_bytes(secret.encode("utf-16-be"))
        commit(self.live, {})
        err = self.assert_rejected()
        self.assertIn("runbooks/le.md: encoding", err)
        self.assertIn("runbooks/be.md: encoding", err)

    def test_binary_extension_is_not_inspection(self):
        with tempfile.TemporaryDirectory() as d:
            secret = "Contact alex" + AT
            (Path(d) / "fake.pdf").write_bytes(secret.encode("utf-16"))
            (Path(d) / "real.pdf").write_bytes(b"%PDF-1.7\n" + secret.encode("utf-16-le"))
            hits = hs.sweep_files(Path(d), ["fake.pdf", "real.pdf"], self.manifest)
        self.assertTrue(any(h.startswith("fake.pdf: encoding") for h in hits), hits)
        self.assertTrue(any(h.startswith("real.pdf:") and "email" in h for h in hits), hits)

    def test_install_gaps_reads_every_name_in_an_import(self):
        commit(self.harness, {"hub/board.py": "import os, helper\nfrom pkg.sub import x\n",
                              "hub/helper.py": "", "hub/pkg.py": "", "install.sh": "cp board.py\n"})
        self.assertEqual(hs.install_gaps(self.harness, self.manifest), ["helper.py", "pkg.py"])

    def test_install_script_missing_an_imported_module_fails(self):
        commit(self.harness, {"hub/tool.py": "BASE\n", "hub/board.py": "import helper\n", "hub/helper.py": "x = 1\n",
                              "install.sh": "for m in board.py tool.py; do cp hub/$m .; done\n"})
        commit(self.live, {"tool.py": "CHANGED\n"})
        self.assertEqual(self.sync()[0], 1)
        git(self.harness, "branch", "-D", "sync") if git(self.harness, "branch", "--list", "sync") else None
        commit(self.harness, {"install.sh": "for m in board.py tool.py helper.py; do cp hub/$m .; done\n"})
        self.assertEqual(self.sync()[0], 0)


if __name__ == "__main__":
    unittest.main()
