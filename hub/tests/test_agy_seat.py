"""The Hephaestus seat: `hephaestus` launcher (shell.sh), its agy templates and factory.json entry.

Runs the launcher in a temp HOME with fake `tmux` and `agy` on PATH, so nothing real starts.
    env -u HUB_DIR -u HUB_AGENT uv run python -m unittest tests.test_agy_seat
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dispatch  # noqa: E402

TOKEN = "SECRET-TOKEN-CONTENTS"


class AgySeatCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / "hub").symlink_to(ROOT)
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        self.log = self.home / "tmux.jsonl"
        tmux = bin_dir / "tmux"
        tmux.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "if sys.argv[1] == 'has-session': sys.exit(1)\n"
            "with open(os.environ['FAKE_TMUX_LOG'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        agy = bin_dir / "agy"
        # A probe (-p ... --model M) answers SUCCESS only for the models listed in FAKE_AGY_UP.
        agy.write_text("#!/bin/sh\nif [ \"$1\" = -p ]; then case \" $FAKE_AGY_UP \" in *\" $4 \"*) "
                       "echo '{\"status\":\"SUCCESS\"}';; *) echo '{\"status\":\"ERROR\"}';; esac; exit 0; fi\n"
                       "echo \"$FAKE_AGY_VERSION\"\n")
        for f in (tmux, agy):
            f.chmod(0o755)
        self.sandbox = self.home / "code" / "factory-sandbox"
        self.sandbox.mkdir(parents=True)
        self.gemini = self.home / ".gemini"
        cli = self.gemini / "antigravity-cli"
        cli.mkdir(parents=True)
        (cli / "antigravity-oauth-token").write_text(TOKEN)
        (cli / "antigravity-oauth-token").chmod(0o600)
        self.settings = cli / "settings.json"
        self.hooks = self.gemini / "config" / "hooks.json"
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME", "TMUX")}
        self.env = {**env, "HOME": str(self.home), "FAKE_TMUX_LOG": str(self.log),
                    "FAKE_AGY_VERSION": "1.4.2", "HUB_AGY_AGENTS": "Hephaestus", "FAKE_AGY_UP": "", "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def tearDown(self):
        self._tmp.cleanup()

    def launch(self, arg=".", cwd=None):
        cmd = f"source {ROOT / 'shell.sh'}; hephaestus {arg}"
        return subprocess.run(["bash", "-c", cmd], env=self.env, cwd=cwd or self.sandbox,
                              text=True, capture_output=True, timeout=30)

    def seat_launch(self):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return next((c for c in calls if c[:2] == ["new-session", "-d"] and "hub-hephaestus" in c), None)

    def test_launch_merges_templates_and_starts_agy(self):
        self.settings.write_text(json.dumps({"trustedWorkspaces": ["/elsewhere"], "theme": "dark",
                                             "artifactReviewPolicy": "asks-for-review"}))
        self.hooks.parent.mkdir()
        self.hooks.write_text(json.dumps({"other": {"enabled": True}}))
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        settings = json.loads(self.settings.read_text())
        self.assertEqual(settings["theme"], "dark")  # the lead's keys survive
        self.assertEqual(settings["trustedWorkspaces"], ["/elsewhere", str(self.sandbox)])
        self.assertEqual(settings["artifactReviewPolicy"], "always-proceed")
        self.assertIs(settings["useG1Credits"], False)
        self.assertEqual(settings["statusLine"], {
            "type": "command", "command": f"{self.home}/hub/agy-status.sh --agent Hephaestus",
            "stack_with_default": True})

        hooks = json.loads(self.hooks.read_text())
        self.assertEqual(set(hooks), {"other", "hub-Hephaestus"})
        seat = hooks["hub-Hephaestus"]
        self.assertNotIn("PreToolUse", seat)  # one that doesn't print allow blocks every tool
        handlers = seat["PreInvocation"] + seat["Stop"] + seat["PostToolUse"][0]["hooks"]
        self.assertEqual({h["timeout"] for h in handlers}, {10})
        self.assertEqual([h["command"] for h in seat["Stop"]], [
            f"{self.home}/hub/heartbeat.sh --agent Hephaestus --event Stop",
            f"node {self.home}/hub/plugin/hooks/stop-deliver.js --agent Hephaestus --format agy"])
        for text in (self.settings.read_text(), self.hooks.read_text()):
            self.assertNotIn("<", text)
            self.assertNotIn(TOKEN, text)
        self.assertEqual((self.gemini / "antigravity-cli" / "antigravity-oauth-token").read_text(), TOKEN)

        md = self.gemini / "GEMINI.md"
        self.assertTrue(md.is_symlink())
        self.assertEqual(os.readlink(md), f"{self.home}/hub/AGENTS-gemini.md")

        call = self.seat_launch()
        self.assertIsNotNone(call, self.log.read_text())
        for arg in ("HUB_AGENT=Hephaestus", f"HUB_DIR={self.home}/hub", "AGY_CLI_DISABLE_AUTO_UPDATE=true",
                    "HUB_PROJECT="):
            self.assertIn(arg, call)
        self.assertEqual(call[call.index("-x") + 1:call.index("-x") + 4], ["200", "-y", "50"])
        self.assertEqual(call[call.index("-c") + 1], str(self.sandbox))
        self.assertEqual(call[-4:], ["agy", "--dangerously-skip-permissions", "--model", "gemini-3.8-flash-medium"])
        self.assertNotIn("GEMINI_API_KEY", " ".join(c for c in call if "=" in c))

    def test_flash_by_default_argon_only_by_choice_never_claude(self):
        up = "gemini-4-argon-high claude-opus-5-5-high"
        for chosen, want in (("", "gemini-3.8-flash-medium"), ("gemini-4-argon-high", "gemini-4-argon-high"),
                             ("claude-opus-5-5-high", "gemini-3.8-flash-medium"),
                             ("gemini-9-down", "gemini-3.8-flash-medium")):
            with self.subTest(chosen=chosen):
                self.log.unlink(missing_ok=True)
                self.env["FAKE_AGY_UP"] = up
                self.env["HUB_AGY_MODEL"] = chosen
                r = self.launch()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.seat_launch()[-2:], ["--model", want])

    def test_wrong_agy_version_refuses_and_writes_nothing(self):
        self.env["FAKE_AGY_VERSION"] = "1.4.20"
        r = self.launch()
        self.assertEqual(r.returncode, 1)
        self.assertIn("versioned tarball", r.stderr)
        self.assertIsNone(self.seat_launch())
        self.assertFalse(self.settings.exists() or self.hooks.exists() or (self.gemini / "GEMINI.md").exists())

    def test_invalid_settings_left_alone_and_no_launch(self):
        self.settings.write_text("{not json")
        r = self.launch()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.settings.read_text(), "{not json")
        self.assertIsNone(self.seat_launch())

    def test_from_home_without_a_record_starts_in_factory_sandbox(self):
        r = self.launch(arg="", cwd=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        call = self.seat_launch()
        self.assertEqual(call[call.index("-c") + 1], str(self.sandbox))

    def test_without_an_argument_uses_the_watchdog_record(self):
        last = self.home / "work" / "factory-sandbox" / "T-9"
        last.mkdir(parents=True)
        state = self.home / ".local" / "state" / "hub-watchdog"
        state.mkdir(parents=True)
        (state / "Hephaestus").write_text(f"{last}\n")
        r = self.launch(arg="", cwd=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        call = self.seat_launch()
        self.assertEqual(call[call.index("-c") + 1], str(last))

    def test_existing_real_gemini_md_is_kept(self):
        (self.gemini / "GEMINI.md").write_text("mine")
        r = self.launch()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.gemini / "GEMINI.md").read_text(), "mine")


class AgyFilesCase(unittest.TestCase):
    # The author's factory.json; a harness install has none, or one without an agy seat.
    @unittest.skipUnless((ROOT / "factory.json").is_file(), "needs your factory.json with an agy seat")
    def test_factory_lists_hephaestus_as_the_reader(self):
        old = dispatch.HUB
        dispatch.HUB = ROOT
        try:
            agents, _ = dispatch.config()
        finally:
            dispatch.HUB = old
        heph = next(a for a in agents if a["name"] == "Hephaestus")
        # dispatch and reset are rollout switches Zeus flips after live checks; the seat itself is fixed.
        self.assertEqual({k: heph[k] for k in ("name", "kind", "session", "reads")},
                         {"name": "Hephaestus", "kind": "agy", "session": "hub-hephaestus", "reads": True})

    def test_instructions_fit_agy_limit(self):
        text = (ROOT / "AGENTS-gemini.md").read_text()
        self.assertLessEqual(len(text.encode()), 24000)
        for heading in ("## What it is", "## Layout", "## Build, run and test", "## Main flows",
                        "## Risks and surprises", "## Open questions", "hub receive --pending",
                        "Not verified:", "## Evidence", 'hubmsg REVIEWER_NAME "report ready:'):
            self.assertIn(heading, text)


if __name__ == "__main__":
    unittest.main()
