"""`hub host` against a stub `gcloud` on PATH. Never touches a real VM.

    uv run python tests/test_host.py
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import host

STUB = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["GCLOUD_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("GCLOUD_EXIT", "0")))
'''
WHERE = ["--zone=europe-west2-a", "--project=my-hub-project"]


class HostTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "gcloud").write_text(STUB)
        (self.dir / "gcloud").chmod(0o755)
        self.log = self.dir / "calls.jsonl"
        env = mock.patch.dict(os.environ, GCLOUD_LOG=str(self.log),
                              PATH=f"{self.dir}:{os.environ['PATH']}")
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("HUB_REVIEW_PORT", None)

    def host(self, action):
        """Exit code and stdout of `hub host <action>`."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as end:
            host.cmd_host(argparse.Namespace(action=action))
        return end.exception.code, out.getvalue()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_up_down_status_name_the_one_vm(self):
        self.assertEqual(self.host("up")[0], 0)
        self.assertEqual(self.host("down")[0], 0)
        self.assertEqual(self.host("status")[0], 0)
        self.assertEqual(self.calls(), [["compute", "instances", "start", "hub-host", *WHERE],
                                        ["compute", "instances", "stop", "hub-host", *WHERE],
                                        ["compute", "instances", "describe", "hub-host",
                                         "--format=value(status)", *WHERE]])

    def test_ssh_goes_through_iap_and_forwards_the_dashboard_and_reviews(self):
        self.host("ssh")
        os.environ["HUB_REVIEW_PORT"] = "9001"
        self.host("ssh")
        iap = ["compute", "ssh", "hub-host", "--tunnel-through-iap", *WHERE, "--"]
        self.assertEqual(self.calls(), [[*iap, "-L", "8765:localhost:8765", "-L", "8766:localhost:8766"],
                                        [*iap, "-L", "8765:localhost:8765", "-L", "9001:localhost:9001"]])

    def test_tunnel_has_no_shell_and_reconnects_after_a_drop(self):
        runs = mock.Mock(side_effect=[mock.Mock(returncode=255), mock.Mock(returncode=0),
                                      KeyboardInterrupt])
        out = io.StringIO()
        with mock.patch.object(host.subprocess, "run", runs), \
                mock.patch.object(host.time, "sleep") as sleep, contextlib.redirect_stdout(out), \
                self.assertRaises(SystemExit) as end:
            host.cmd_host(argparse.Namespace(action="tunnel"))
        self.assertEqual(end.exception.code, 0)
        self.assertEqual(runs.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        argv = runs.call_args.args[0]
        self.assertEqual(argv[:4], ["gcloud", "compute", "ssh", "hub-host"])
        tail = argv[argv.index("--"):]
        self.assertEqual(tail[:6], ["--", "-N", "-L", "8765:localhost:8765", "-L", "8766:localhost:8766"])
        self.assertIn("ServerAliveInterval=30", tail)
        self.assertIn("ServerAliveCountMax=3", tail)
        text = out.getvalue()
        self.assertEqual(text.count("http://127.0.0.1:8765/"), 1)
        self.assertEqual(text.count("http://127.0.0.1:8766/"), 1)
        self.assertEqual(text.count("tunnel: connecting"), 3)

    def test_a_failed_start_keeps_its_exit_code_and_says_nothing_about_getting_in(self):
        os.environ["GCLOUD_EXIT"] = "1"
        code, out = self.host("up")
        self.assertEqual(code, 1)
        self.assertNotIn("hub host ssh", out)

    def test_no_gcloud_is_one_line(self):
        os.environ["PATH"] = str(self.dir / "empty")
        with self.assertRaises(SystemExit) as end:
            host.cmd_host(argparse.Namespace(action="status"))
        self.assertEqual(end.exception.code, "host: gcloud is not installed on this machine")


if __name__ == "__main__":
    unittest.main()
