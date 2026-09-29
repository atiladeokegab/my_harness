"""`hub review`: the human's click must come back to Zeus, and nothing else may.

    uv run python tests/test_review.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent


class TestReview(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "approval.html").write_text(
            '<body><p id="status"></p><textarea id="note"></textarea>'
            '<button id="approve">A</button><button id="changes">C</button></body>')
        (self.dir / "c4_context.png").write_bytes(b"PNG")
        env = dict(os.environ, HUB_DIR=str(self.dir))
        env.pop("HUB_AGENT", None)
        self.p = subprocess.Popen([sys.executable, str(HUB / "board.py"), "review",
                                   str(self.dir / "approval.html"), "--name", "approval-1",
                                   "--no-open"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.url = self.p.stderr.readline().split(": ", 1)[1].strip()

    def tearDown(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()
        self.p.stdout.close()
        self.p.stderr.close()

    def post(self, body):
        req = urllib.request.Request(self.url + "decision", data=json.dumps(body).encode(),
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url + path, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, b""

    def test_page_is_wired_and_siblings_served_but_nothing_above(self):
        status, body = self.get("")
        self.assertEqual(status, 200)
        self.assertIn(b'fetch("/decision"', body)
        self.assertNotIn(b'fetch("/decision"', (self.dir / "approval.html").read_bytes())
        self.assertEqual(self.get("c4_context.png"), (200, b"PNG"))
        (self.dir / "private").mkdir()
        (self.dir / "private" / "note.txt").write_text("hidden")
        self.assertEqual(self.get("private/note.txt")[0], 404)
        self.assertEqual(self.get("../../etc/passwd")[0], 404)
        self.assertEqual(self.get("%2e%2e/%2e%2e/etc/passwd")[0], 404)

    def test_bad_decisions_are_refused_and_the_server_keeps_waiting(self):
        self.assertEqual(self.post({"decision": "maybe"}), 400)
        self.assertEqual(self.post({"decision": "changes", "note": "  "}), 400)
        self.assertIsNone(self.p.poll(), "a refused click must not end the review")
        self.assertFalse((self.dir / "reviews" / "approval-1.json").exists())

    def test_approval_is_written_printed_and_ends_the_command(self):
        self.assertEqual(self.post({"decision": "changes", "note": "swap owners"}), 200)
        out = json.loads(self.p.stdout.read())
        self.assertEqual(self.p.wait(timeout=5), 0)
        self.assertEqual((out["decision"], out["note"]), ("changes", "swap owners"))
        saved = json.loads((self.dir / "reviews" / "approval-1.json").read_text())
        self.assertEqual(saved, out)

    def test_builds_review_from_files_with_defaults_and_overrides(self):
        (self.dir / "idea.md").write_text('A <b> tag & a note')
        mockup = self.dir / "mockup"
        mockup.mkdir()
        (mockup / "index.html").write_text('<h1>Mockup</h1>')
        args = [str(self.dir / "c4_context.png"), str(self.dir / "idea.md"), str(mockup / "index.html")]
        for options, name, title, note in (([], "c4_context", "c4_context", "agreed"),
                                           (["--name", "approval-2", "--title", "The idea", "--note", "team agreed"],
                                            "approval-2", "The idea", "team agreed")):
            with self.subTest(name=name):
                p = subprocess.Popen([sys.executable, str(HUB / "board.py"), "review", "--no-open", *options, *args],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    url = p.stderr.readline().split(": ", 1)[1].strip()
                    with urllib.request.urlopen(url, timeout=5) as r:
                        body = r.read().decode()
                    self.assertIn(f"<h2>{title}</h2>", body)
                    self.assertEqual(body.count("<img "), 1)
                    self.assertEqual(body.count("<pre>"), 1)
                    self.assertIn("&lt;b&gt;", body)
                    self.assertEqual(body.count("<iframe "), 1)
                    self.assertIn(f'<textarea id="note">{note}</textarea>', body)
                    for marker in ('id="approve"', 'id="changes"', 'id="status"'):
                        self.assertIn(marker, body)
                    self.assertTrue((self.dir / f"{name}-review.html").is_file())
                    self.assertNotIn('<script>', (self.dir / f"{name}-review.html").read_text())
                    iframe = re.search(r'<iframe src="([^"]+)"', body)
                    with urllib.request.urlopen(url + iframe.group(1).lstrip('/'), timeout=5) as r:
                        self.assertIn(b'Mockup', r.read())
                    req = urllib.request.Request(url + "decision", data=b'{"decision":"approve"}', method="POST")
                    with urllib.request.urlopen(req, timeout=5):
                        pass
                    self.assertEqual(p.wait(timeout=5), 0)
                finally:
                    if p.poll() is None:
                        p.kill()
                    p.wait()
                    p.stdout.close()
                    p.stderr.close()

    def test_missing_input_fails_before_writing_page(self):
        missing = self.dir / "absent.md"
        r = subprocess.run([sys.executable, str(HUB / "board.py"), "review", "--no-open",
                            str(self.dir / "c4_context.png"), str(missing)],
                           capture_output=True, text=True, timeout=5)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(str(missing), r.stderr)
        self.assertFalse((self.dir / "c4_context-review.html").exists())

    def test_built_page_refuses_to_overwrite_an_input(self):
        output = self.dir / "c4_context-review.html"
        output.write_text("source")
        r = subprocess.run([sys.executable, str(HUB / "board.py"), "review", "--no-open",
                            str(self.dir / "c4_context.png"), str(output)],
                           capture_output=True, text=True, timeout=5)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(str(output), r.stderr)
        self.assertEqual(output.read_text(), "source")


if __name__ == "__main__":
    unittest.main()
