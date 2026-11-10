#!/usr/bin/env python3
"""paste-intake hook: labels pastes as Wispr dictation or unknown. Drives the real hook.
Run: uv run python tests/test_paste_intake.py"""

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks/paste-intake.js"  # both a checkout and an install have hub/hooks
DICT = "the general idea was to think about different and fresh principles and then see how you put the cards"
DOC = "Section 4.2 of the vendor contract requires all deliverables to be submitted by Friday noon."


def paste(body, pid="ab12"):
    return f'<pasted_content id="{pid}">\n{body}\n</pasted_content id="{pid}">'


def run(prompt, db=None, raw=None, codex=False):
    # HUB_DIR/HUB_AGENT leak into live ~/hub if inherited; PLUGIN_DATA switches output shape.
    env = {k: v for k, v in os.environ.items() if k not in ("HUB_DIR", "HUB_AGENT", "PLUGIN_DATA")}
    env["HUB_WISPR_DB"] = str(db) if db else "/nonexistent/flow.sqlite"
    if codex:
        env["PLUGIN_DATA"] = "/tmp"
    stdin = raw if raw is not None else json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt})
    p = subprocess.run(["node", str(HOOK)], input=stdin, capture_output=True, text=True, env=env, timeout=10)
    assert p.returncode == 0, p.stderr
    return p.stdout


class PasteIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def wispr(self, rows=(), wal=b""):
        db = self.dir / "flow.sqlite"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE History (asrText, formattedText, editedText, timestamp, audio, pastedText)")
        c.executemany("INSERT INTO History VALUES (?, ?, NULL, '2026-09-21 14:00:00.000 +01:00', NULL, NULL)",
                      [(r, r) for r in rows])
        c.commit()
        c.close()
        if wal:
            (self.dir / "flow.sqlite-wal").write_bytes(wal)
        return db

    def test_plain_prompt_is_silent(self):
        self.assertEqual(run("just a question, no paste"), "")

    def test_unknown_paste_asks_for_intake(self):
        out = run("look " + paste(DOC))
        self.assertIn("the intake skill", out)
        self.assertIn("1 of 1 pastes unmatched", out)

    def test_image_asks_for_intake(self):
        self.assertIn("1 images", run("look: [Image #1]"))

    def test_malformed_stdin_is_silent(self):
        self.assertEqual(run(None, raw="{not json"), "")

    def test_dictation_in_checkpointed_rows(self):
        out = run(paste(DICT), db=self.wispr(rows=[DICT.capitalize() + "."]))
        self.assertIn("Wispr Flow dictation", out)
        self.assertNotIn("the intake skill", out)

    def test_dictation_only_in_wal(self):
        db = self.wispr(wal=b"\x00junk" + DICT.upper().encode() + b"\x00more")
        self.assertIn("Wispr Flow dictation", run(paste(DICT), db=db))

    def test_mixed_names_dictated_paste(self):
        out = run(paste(DOC, "a1") + paste(DICT, "b2"), db=self.wispr(rows=[DICT]))
        self.assertIn("1 of 2 pastes unmatched", out)
        self.assertIn("Pastes 2 are", out)

    def test_codex_gets_json(self):
        out = json.loads(run("x " + paste(DOC), codex=True))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("the intake skill", out["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
