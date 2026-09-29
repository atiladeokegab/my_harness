"""gh_board against a fake Gh. Run: uv run python tests/test_gh_board.py"""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gh_board  # noqa: E402
from gh_sync import GhError  # noqa: E402


class FakeGh:
    """Answers by the first two words of the call; records every call."""

    def __init__(self, answers, fail=()):
        self.answers, self.fail, self.calls, self.dry = answers, set(fail), [], False

    def __call__(self, *args, write=True, **kw):
        self.calls.append(list(map(str, args)))
        key = " ".join(map(str, args[:2]))
        if key in self.fail:
            raise GhError(f"{key} failed")
        return self.answers.get(key, "")

    def json(self, *args):
        return json.loads(self(*args, write=False) or "null")


FIELDS = json.dumps({"fields": [
    {"id": "S", "name": "Status", "options": [{"id": "t", "name": "Todo"},
                                              {"id": "p", "name": "In progress"},
                                              {"id": "r", "name": "In review"},
                                              {"id": "d", "name": "Done"}]},
    {"id": "A", "name": "Agent"}, {"id": "D", "name": "Deadline"}]})
ROSTER = [{"name": "Alex", "github": "lead-gh", "lead": True}]
CFG = {"repo": "o/hk", "roster": ROSTER,
       "board": {"number": 7, "url": "https://github.com/users/lead-gh/projects/7", "id": "PID"}}


def quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


class StatusTest(unittest.TestCase):
    def test_four_states_and_reopen(self):
        open_i = {"number": 4, "state": "OPEN"}
        self.assertEqual(gh_board.status_of(open_i, [], []), "Todo")
        self.assertEqual(gh_board.status_of(open_i, [], ["4-demo"]), "In progress")
        self.assertEqual(gh_board.status_of(open_i, [{"body": "Closes #4"}], ["4-demo"]), "In review")
        self.assertEqual(gh_board.status_of(open_i, [{"body": "fixes #4."}], []), "In review")
        self.assertEqual(gh_board.status_of({"number": 4, "state": "CLOSED"}, [], ["4-demo"]), "Done")
        # A reopened issue is OPEN again and falls back by itself.
        self.assertEqual(gh_board.status_of({"number": 4, "state": "OPEN"}, [], ["4-demo"]), "In progress")

    def test_other_numbers_do_not_match(self):
        open_i = {"number": 4, "state": "OPEN"}
        self.assertEqual(gh_board.status_of(open_i, [{"body": "Closes #41"}], ["41-x", "14-y"]), "Todo")


class InitTest(unittest.TestCase):
    def test_copies_links_makes_public_once(self):
        gh = FakeGh({"project list": json.dumps({"projects": [
                        {"number": 3, "title": "Something else"},
                        {"number": 2, "title": "Hackathon board (template)"}]}),
                     "project copy": json.dumps({"number": 9, "url": "U", "id": "P9"})})
        cfg = {"repo": "o/hk", "roster": ROSTER}
        out = quiet(gh_board.init_board, cfg, gh, "o/hk")
        self.assertEqual(cfg["board"], {"number": 9, "url": "U", "id": "P9"})
        copy = next(c for c in gh.calls if c[:2] == ["project", "copy"])
        self.assertEqual(copy[2], "2")
        self.assertIn("hk board", copy)
        self.assertTrue(any(c[:2] == ["project", "link"] and "o/hk" in c for c in gh.calls))
        self.assertTrue(any(c[:2] == ["project", "edit"] and "PUBLIC" in c for c in gh.calls))
        self.assertIn("board: U", out)
        n = len(gh.calls)
        gh_board.init_board(cfg, gh, "o/hk")
        self.assertEqual(len(gh.calls), n)

    def test_without_template_warns_and_makes_nothing(self):
        gh = FakeGh({"project list": json.dumps({"projects": []})})
        cfg = {"repo": "o/hk", "roster": ROSTER}
        out = quiet(gh_board.init_board, cfg, gh, "o/hk")
        self.assertNotIn("board", cfg)
        self.assertIn("warning", out)

    def test_failure_warns(self):
        gh = FakeGh({}, fail={"project list"})
        cfg = {"repo": "o/hk", "roster": ROSTER}
        self.assertIn("warning: board not made", quiet(gh_board.init_board, cfg, gh, "o/hk"))
        self.assertNotIn("board", cfg)

    def test_dry_run_makes_no_project_calls(self):
        gh = FakeGh({})
        gh.dry = True
        cfg = {"repo": "o/hk", "roster": ROSTER}
        self.assertIn("would copy", quiet(gh_board.init_board, cfg, gh, "o/hk"))
        self.assertEqual(gh.calls, [])


class SyncTest(unittest.TestCase):
    def task(self, n, agent=None, deadline="submit"):
        return {"id": f"T-00{n}", "issue": n, "agent": agent, "status": "open",
                "detail": f"Context: x\nDeadline: {deadline}"}

    def gh(self, items, prs="[]", refs=""):
        return FakeGh({"project field-list": FIELDS,
                       "project item-list": json.dumps({"items": items}),
                       "project item-add": json.dumps({"id": "I2"}),
                       "pr list": prs,
                       f"api repos/o/hk/git/matching-refs/heads/": refs})

    def test_adds_missing_items_and_edits_only_what_changed(self):
        gh = self.gh([{"id": "I1", "content": {"number": 1}, "status": "Todo", "agent": "",
                       "deadline": "submit"}])
        issues = {1: {"number": 1, "state": "OPEN", "url": "u1"},
                  2: {"number": 2, "state": "OPEN", "url": "u2"}}
        quiet(gh_board.sync_board, [self.task(1), self.task(2, agent="Zeus")], dict(CFG), gh, "o/hk", issues)
        adds = [c for c in gh.calls if c[:2] == ["project", "item-add"]]
        edits = [c for c in gh.calls if c[:2] == ["project", "item-edit"]]
        self.assertEqual(len(adds), 1)
        self.assertIn("u2", adds[0])
        self.assertTrue(edits and all("I2" in c for c in edits), edits)
        agent_edit = next(c for c in edits if "A" in c)
        self.assertEqual(agent_edit[agent_edit.index("--text") + 1], "Zeus")

    def test_status_follows_branches_and_prs(self):
        gh = self.gh([{"id": "I1", "content": {"number": 1}, "status": "Todo", "agent": "",
                       "deadline": "submit"}],
                     prs=json.dumps([{"number": 5, "body": "Closes #1"}]), refs="refs/heads/1-x\n")
        quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk",
              {1: {"number": 1, "state": "OPEN", "url": "u1"}})
        edit = next(c for c in gh.calls if c[:2] == ["project", "item-edit"])
        self.assertEqual(edit[edit.index("--single-select-option-id") + 1], "r")

    def test_no_board_no_calls(self):
        gh = FakeGh({})
        gh_board.sync_board([self.task(1)], {"repo": "o/hk", "roster": ROSTER}, gh, "o/hk", {})
        self.assertEqual(gh.calls, [])

    def test_failure_only_warns(self):
        gh = FakeGh({}, fail={"project field-list"})
        out = quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk",
                    {1: {"number": 1, "state": "OPEN", "url": "u"}})
        self.assertIn("warning: board not updated", out)

    def test_too_many_items_warns(self):
        items = [{"id": f"I{i}", "content": {"number": 1000 + i}} for i in range(500)]
        gh = self.gh(items)
        self.assertIn("more than 499", quiet(gh_board.sync_board, [], dict(CFG), gh, "o/hk", {}))


if __name__ == "__main__":
    unittest.main()
