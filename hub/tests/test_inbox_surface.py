#!/usr/bin/env python3
"""`hub inbox --unseen` and the inbox-surface hook that feeds it to an attached agent.
Run (hub env stripped, so nothing touches the live ~/hub):
  S=$(mktemp -d); env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT HOME=$S python3 tests/test_inbox_surface.py"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "board.py"
HOOK = ROOT / "hooks/inbox-surface.js"
STOP = ROOT / "hooks/stop-deliver.js"
NODE = shutil.which("node")
AGY = ROOT / "tests/fixtures/agy"  # agy 1.4.2 hook payloads
STRIP = ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "HUB_LEAD", "CLAUDE_CODE_SESSION_NAME", "PLUGIN_DATA", "CLAUDECODE")


class HubBed(unittest.TestCase):
    """Fixtures only, so a subclass does not re-run another class's tests."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if k not in STRIP}
        self.env["HUB_DIR"] = str(d / "hub")
        self.env["CLAUDECODE"] = "1"  # the hook runs only inside Claude Code
        os.makedirs(self.env["HUB_DIR"])
        # The hook calls `hub` off PATH; point it at this checkout's board.py.
        (d / "bin").mkdir()
        shim = d / "bin/hub"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{BOARD}" "$@"\n')
        shim.chmod(0o755)
        self.env["PATH"] = f"{d / 'bin'}:{self.env['PATH']}"

    def tearDown(self):
        self.tmp.cleanup()

    def hub(self, *args, check=True):
        p = subprocess.run([sys.executable, str(BOARD), *args], capture_output=True, text=True,
                           env=self.env, timeout=30)
        if check:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def send(self, text, to="Zeus"):
        self.hub("notify", to, text, "--as", "Tester")

    def run_js(self, script, payload, *args, **env_extra):
        env = {**self.env, **env_extra}
        p = subprocess.run([NODE, str(script), *args], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout


class InboxSurface(HubBed):
    def unseen(self, agent="Zeus"):
        return self.hub("inbox", "--unseen", "--as", agent)

    def hook(self, event="UserPromptSubmit", agent="Zeus"):
        env = dict(self.env)
        if agent:
            env["HUB_AGENT"] = agent
        p = subprocess.run([NODE, str(HOOK)], input=json.dumps({"hook_event_name": event, "prompt": "hi"}),
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_unseen_prints_new_then_nothing(self):
        self.send("Smoke failed on integration at abc123")
        self.assertIn("Smoke failed on integration at abc123", self.unseen())
        self.assertEqual(self.unseen(), "")
        self.send("second alert")
        out = self.unseen()
        self.assertIn("second alert", out)
        self.assertNotIn("Smoke failed", out)

    def test_cursor_is_per_agent(self):
        self.send("for zeus")
        self.send("for hermes", to="Hermes")
        self.assertIn("for zeus", self.unseen("Zeus"))
        self.assertIn("for hermes", self.unseen("Hermes"))

    def test_noise_is_skipped(self):
        self.send("webapp: not accepted the invite yet: alice")
        self.send("webapp deployed 0123456789ab: https://x.example")
        self.send("deploy started at 0123456789ab")
        self.send("Smoke failed on integration at 0123456789ab")
        out = self.unseen()
        self.assertIn("Smoke failed", out)
        for noise in ("not accepted the invite", "deployed 0123456789ab", "deploy started"):
            self.assertNotIn(noise, out)

    def test_cap_and_truncation(self):
        for i in range(10):
            self.send(f"alert {i:02d} " + "x" * 400)
        out = self.unseen()
        lines = [l for l in out.splitlines() if l.strip().startswith("·")]
        self.assertEqual(len(lines), 8)
        # hub notify always mints a message id, and an id'd message is shown whole, never cut
        self.assertTrue(all("x" * 400 in l for l in lines), [len(l) for l in lines])
        self.assertIn("(+2 more, shown next time)", out)
        self.assertIn("alert 09", out)  # the newest are the ones shown
        rest = self.unseen()  # 2026-10-21: the overflow used to be marked seen and never shown
        self.assertIn("alert 00", rest)
        self.assertIn("alert 01", rest)
        self.assertNotIn("alert 09", rest)
        self.assertEqual(self.unseen(), "")

    def test_plain_inbox_unchanged(self):
        self.send("keep me")
        self.unseen()
        self.assertIn("keep me", self.hub("inbox", "--as", "Zeus"))
        self.assertIn("cleared 1 message(s)", self.hub("inbox", "--clear", "--as", "Zeus"))
        self.send("after clear")
        self.assertIn("after clear", self.unseen())

    def test_hook_without_hub_agent_is_silent(self):
        self.send("hidden")
        self.assertEqual(self.hook(agent=None), "")

    def test_hook_surfaces_once_as_additional_context(self):
        self.send("Smoke failed on integration at abc123")
        out = json.loads(self.hook("PostToolUse"))["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        self.assertTrue(out["additionalContext"].startswith("[hub inbox] new since last check:"))
        self.assertIn("Smoke failed", out["additionalContext"])
        self.assertEqual(self.hook("UserPromptSubmit"), "")

    def test_post_tool_use_spawns_hub_only_when_mail_arrived(self):
        """Token review 2026-10-20: the fs-stat gate, not the hub spawn, answers a tool call with no new mail."""
        self.send("for hermes", to="Hermes")
        shim = Path(self.tmp.name) / "bin/hub"
        calls = Path(self.tmp.name) / "hub-calls"
        shim.write_text(f'#!/bin/sh\necho x >> "{calls}"\n' + shim.read_text().split("\n", 1)[1])
        self.assertIn("for hermes", self.hook("PostToolUse", agent="Hermes"))
        self.assertEqual(self.hook("PostToolUse", agent="Hermes"), "")
        self.assertEqual(calls.read_text().count("x"), 1)  # the second tool call never spawned hub

    def test_watchdog_health_changes_are_noise(self):
        self.send("[watchdog] Hermes: healthy -> permission prompt (❯ 1. Yes). The watchdog never relaunches")
        self.send("[watchdog] Your session died and was relaunched at 12:00Z.")
        out = self.unseen()
        self.assertNotIn("permission prompt", out)
        self.assertIn("relaunched at 12:00Z", out)

    def test_hook_survives_a_broken_hub(self):
        self.env["PATH"] = "/nonexistent"
        self.assertEqual(self.hook(), "")

    def test_codex_payload_needs_an_explicit_agent(self):
        """Codex hooks run in a shared daemon: its HUB_AGENT may be anyone's, so only --agent counts."""
        self.send("for prometheus", to="Prometheus")
        codex = {"hook_event_name": "UserPromptSubmit", "turn_id": "t-1", "prompt": "hi"}
        self.assertEqual(self.run_js(HOOK, codex, HUB_AGENT="Prometheus"), "")
        out = json.loads(self.run_js(HOOK, codex, "--agent", "Prometheus", CLAUDECODE=""))
        self.assertIn("for prometheus", out["hookSpecificOutput"]["additionalContext"])

    def test_agy_format_injects_an_ephemeral_step_only_when_new(self):
        """agy runs this before every model call (PreInvocation): silent with nothing new, and `hub` is not spawned
        while the inbox file is older than the --unseen cursor."""
        pre = json.loads((AGY / "hook-PreInvocation.json").read_text())
        hook = lambda: self.run_js(HOOK, pre, "--agent", "Iris", "--format", "agy", CLAUDECODE="")
        self.assertEqual(hook(), "")
        self.send("review the factory-sandbox report", to="Iris")
        out = json.loads(hook())
        self.assertEqual(list(out), ["injectSteps"])
        msg = out["injectSteps"][0]["ephemeralMessage"]
        self.assertTrue(msg.startswith("[hub inbox] new since last check:"))
        self.assertIn("review the factory-sandbox report", msg)
        shim = Path(self.tmp.name) / "bin/hub"
        shim.write_text(f'#!/bin/sh\ntouch "{self.tmp.name}/hub-ran"\nexec "{sys.executable}" "{BOARD}" "$@"\n')
        self.assertEqual(hook(), "")
        self.assertFalse(Path(self.tmp.name, "hub-ran").exists())
        self.send("second", to="Iris")
        self.assertIn("second", json.loads(hook())["injectSteps"][0]["ephemeralMessage"])


class StopDeliver(HubBed):
    """Agent OS §5.2: at turn end, hand the agent its unreceived messages with a Stop block."""

    def setUp(self):
        super().setUp()
        # A fake tmux, so no test ever asks the live server about a real hub-* session. It records
        # the target it was asked about and answers #{session_attached} from $FAKE_TMUX.
        fake = Path(self.tmp.name) / "bin/tmux"
        fake.write_text('#!/bin/sh\necho "$@" >> "$HUB_DIR/tmux-calls"\n'
                        '[ "$FAKE_TMUX" = fail ] && { echo "no server running" >&2; exit 1; }\n'
                        'echo "$FAKE_TMUX"\n')
        fake.chmod(0o755)
        self.env["FAKE_TMUX"] = "0"

    def notify(self, text, mid, to="Hermes"):
        self.hub("notify", to, text, "--message-id", mid, "--as", "Tester")

    def stop(self, *args, active=False, codex=False, **env):
        payload = {"hook_event_name": "Stop", "stop_hook_active": active}
        if codex:
            payload["turn_id"] = "t-1"
        return self.run_js(STOP, payload, *args, **env)

    def test_pending_messages_block_once_then_silence(self):
        self.notify("review T-9 please", "m-1")
        self.notify("and T-10", "m-2")
        out = json.loads(self.stop(HUB_AGENT="Hermes"))
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("[hub inbox]"))
        self.assertIn("review T-9 please", out["reason"])
        self.assertIn("and T-10", out["reason"])
        self.assertTrue((Path(self.env["HUB_DIR"]) / "inbox/.received/Hermes/m-1").exists())
        self.assertEqual(self.stop(active=True, HUB_AGENT="Hermes"), "")

    def test_codex_uses_the_agent_flag_and_ignores_daemon_env(self):
        self.notify("for prometheus", "m-3", to="Prometheus")
        self.notify("for hermes", "m-4")
        # The daemon was started from Hermes's shell: without --agent the hook must not act as Hermes.
        self.assertEqual(self.stop(codex=True, HUB_AGENT="Hermes"), "")
        out = json.loads(self.stop("--agent", "Prometheus", codex=True, HUB_AGENT="Hermes", CLAUDECODE=""))
        self.assertIn("for prometheus", out["reason"])
        self.assertNotIn("for hermes", out["reason"])
        self.assertIn("for hermes", json.loads(self.stop(HUB_AGENT="Hermes"))["reason"])

    def test_zeus_is_exempt(self):
        """Zeus holds the lead's conversation: a block after every answer would push it into peer mail."""
        self.notify("for zeus", "m-6", to="Zeus")
        self.assertEqual(self.stop(HUB_AGENT="Zeus"), "")
        self.assertEqual(self.stop("--agent", "zeus", codex=True), "")
        self.assertFalse((Path(self.env["HUB_DIR"]) / "inbox/.received/Zeus/m-6").exists())

    def test_attached_session_is_left_alone(self):
        """The lead talking to an agent directly must not have every answer roll into peer mail."""
        self.notify("while the lead is attached", "m-7")
        receipt = Path(self.env["HUB_DIR"]) / "inbox/.received/Hermes/m-7"
        self.assertEqual(self.stop(HUB_AGENT="Hermes", FAKE_TMUX="1"), "")
        self.assertFalse(receipt.exists())
        self.assertIn("-t hub-hermes", (Path(self.env["HUB_DIR"]) / "tmux-calls").read_text())
        self.assertIn("while the lead is attached", json.loads(self.stop(HUB_AGENT="Hermes", FAKE_TMUX="fail"))["reason"])
        self.assertTrue(receipt.exists())

    def test_detached_session_gets_the_block(self):
        self.notify("nobody attached", "m-8")
        self.assertIn("nobody attached", json.loads(self.stop(HUB_AGENT="Hermes", FAKE_TMUX="0"))["reason"])

    def surface(self):
        return self.run_js(HOOK, {"hook_event_name": "UserPromptSubmit"}, HUB_AGENT="Hermes")

    def test_message_surfaced_mid_turn_is_not_delivered_again(self):
        """Live rollout: inbox-surface showed a message mid-turn, then the Stop hook delivered it again."""
        self.notify("shown mid-turn", "m-9")
        self.assertIn("shown mid-turn", self.surface())
        self.assertEqual(self.stop(HUB_AGENT="Hermes"), "")

    def test_message_delivered_at_stop_is_not_surfaced_again(self):
        self.notify("delivered at stop", "m-10")
        self.assertIn("delivered at stop", json.loads(self.stop(HUB_AGENT="Hermes"))["reason"])
        self.assertEqual(self.surface(), "")

    def test_long_message_surfaces_whole_and_once(self):
        """2026-10-21: a cut message was left for the Stop hook, which Zeus never gets, so 22 went unreceived."""
        self.notify("long " + "x" * 400 + " END", "m-11")
        self.assertIn("END", self.surface())
        self.assertEqual(self.stop(HUB_AGENT="Hermes"), "")

    def test_long_message_to_zeus_is_received(self):
        self.notify("long " + "x" * 400 + " END", "m-13", to="Zeus")
        self.assertIn("END", self.run_js(HOOK, {"hook_event_name": "UserPromptSubmit"}, HUB_AGENT="Zeus"))
        self.assertTrue((Path(self.env["HUB_DIR"]) / "inbox/.received/Zeus/m-13").exists())

    def test_agy_format_continues_once_then_silence(self):
        """agy's Stop payload has no stop_hook_active and no turn_id; {"decision":"continue"} runs one more turn."""
        self.notify("for iris", "m-12", to="Iris")
        stop = json.loads((AGY / "hook-Stop.json").read_text())
        args = ("--agent", "Iris", "--format", "agy")
        out = json.loads(self.run_js(STOP, stop, *args, CLAUDECODE=""))
        self.assertEqual(out["decision"], "continue")
        self.assertIn("for iris", out["reason"])
        self.assertEqual(self.run_js(STOP, {**stop, "executionNum": 1}, *args, CLAUDECODE=""), "")

    def test_a_probe_marked_hub_no_hooks_takes_no_mail(self):
        """Hermes on 7146895: the launcher's probe fires PreInvocation and Stop as the seat; HUB_NO_HOOKS keeps the mail."""
        self.notify("for the real seat", "m-13", to="Iris")
        stop = json.loads((AGY / "hook-Stop.json").read_text())
        pre = json.loads((AGY / "hook-PreInvocation.json").read_text())
        args = ("--agent", "Iris", "--format", "agy")
        self.assertEqual(self.run_js(HOOK, pre, *args, CLAUDECODE="", HUB_NO_HOOKS="1"), "")
        self.assertEqual(self.run_js(STOP, stop, *args, CLAUDECODE="", HUB_NO_HOOKS="1"), "")
        out = json.loads(self.run_js(STOP, stop, *args, CLAUDECODE=""))  # the real seat still gets it
        self.assertIn("for the real seat", out["reason"])

    def test_silent_without_identity_or_hub(self):
        self.notify("hidden", "m-5")
        self.assertEqual(self.stop(), "")
        self.env["PATH"] = "/nonexistent"
        self.assertEqual(self.stop(HUB_AGENT="Hermes"), "")


if __name__ == "__main__":
    unittest.main()
