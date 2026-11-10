"""gh_board against a fake Gh. Run: uv run python tests/test_gh_board.py"""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gh_board  # noqa: E402
import gh_sync  # noqa: E402
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
        if key == "pr list" and "merged" in args:
            return self.answers.get("pr list merged", "[]")
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
CFG = {"repo": "o/hk", "roster": ROSTER, "deadlines": [{"name": "code freeze"}, {"name": "submit"}],
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
        self.assertEqual(gh_board.status_of({"number": 4, "state": "CLOSED"}, [], ["4-demo"], ["4-demo"]),
                         "In progress")
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
        branches = "\n".join(f"{r.removeprefix('refs/heads/')}\tsha-{r.removeprefix('refs/heads/')}"
                             for r in refs.split()) or "main\tsha-main"
        return FakeGh({"project field-list": FIELDS,
                       "project item-list": json.dumps({"items": items}),
                       "project item-add": json.dumps({"id": "I2"}),
                       "pr list": prs,
                       "api repos/o/hk/branches?per_page=100": branches})

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

    def test_emptied_text_field_is_cleared(self):
        gh = self.gh([{"id": "I1", "content": {"number": 1}, "status": "Todo", "agent": "Zeus",
                       "deadline": "submit"}])
        out = quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk",
                    {1: {"number": 1, "state": "OPEN", "url": "u1"}})
        edits = [c for c in gh.calls if c[:2] == ["project", "item-edit"]]
        self.assertEqual(len(edits), 1, edits)
        self.assertIn("--clear", edits[0])
        self.assertNotIn("--text", edits[0])
        self.assertNotIn("warning", out)

    def test_status_follows_branches_and_prs(self):
        gh = self.gh([{"id": "I1", "content": {"number": 1}, "status": "Todo", "agent": "",
                       "deadline": "submit"}],
                     prs=json.dumps([{"number": 5, "body": "Closes #1"}]), refs="refs/heads/1-x\n")
        quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk",
              {1: {"number": 1, "state": "OPEN", "url": "u1"}})
        edit = next(c for c in gh.calls if c[:2] == ["project", "item-edit"])
        self.assertEqual(edit[edit.index("--single-select-option-id") + 1], "r")

    def test_sync_returns_only_changed_hub_status_and_repeats_no_edit(self):
        task = self.task(1)
        item = {"id": "I1", "content": {"number": 1}, "status": "Todo", "agent": "",
                "deadline": "submit"}
        gh = self.gh([item], refs="refs/heads/1-x\n")
        issue = {1: {"number": 1, "state": "OPEN", "url": "u1"}}
        with contextlib.redirect_stdout(io.StringIO()):
            changes = gh_board.sync_board([task], dict(CFG), gh, "o/hk", issue)
        self.assertEqual(changes, [(task["id"], {"gh_status": "In progress"}, "gh-status")])
        writes = []

        @contextlib.contextmanager
        def isolated_board(write=False):
            writes.append(write)
            yield {"tasks": [task]}, []

        with mock.patch.object(gh_sync.hb, "board", isolated_board), \
                mock.patch.object(gh_sync.hb, "log"), \
                mock.patch.object(gh_sync.hb, "whoami", return_value="Zeus"):
            gh_sync.apply(changes, False)
            self.assertEqual(task["gh_status"], "In progress")
            item["status"] = "In progress"
            gh.answers["project item-list"] = json.dumps({"items": [item]})
            gh.calls.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                changes = gh_board.sync_board([task], dict(CFG), gh, "o/hk", issue)
            gh_sync.apply(changes, False)
        self.assertEqual(writes, [True])
        self.assertEqual(changes, [])
        self.assertFalse(any(c[:2] == ["project", "item-edit"] for c in gh.calls))

    def test_vertical_follows_children_until_its_own_issue_moves(self):
        vertical, done, untouched = self.task(1), self.task(2), self.task(3)
        vertical["kind"] = "vertical"
        done["parent"] = untouched["parent"] = vertical["id"]
        tasks = [vertical, done, untouched]
        items = [{"id": f"I{n}", "content": {"number": n}, "status": status,
                  "agent": "", "deadline": "submit"}
                 for n, status in ((1, "Todo"), (2, "Done"), (3, "Todo"))]
        issues = {n: {"number": n, "state": "CLOSED" if n == 2 else "OPEN", "url": f"u{n}"}
                  for n in (1, 2, 3)}
        gh = self.gh(items)
        with contextlib.redirect_stdout(io.StringIO()):
            changes = gh_board.sync_board(tasks, dict(CFG), gh, "o/hk", issues)
        self.assertEqual(dict((tid, fields["gh_status"]) for tid, fields, _ in changes),
                         {"T-001": "In progress", "T-002": "Done", "T-003": "Todo"})
        status_edit = next(c for c in gh.calls if c[:2] == ["project", "item-edit"])
        self.assertEqual(status_edit[status_edit.index("--single-select-option-id") + 1], "p")

        gh = self.gh(items, prs=json.dumps([{"body": "Closes #1"}]))
        with contextlib.redirect_stdout(io.StringIO()):
            changes = gh_board.sync_board(tasks, dict(CFG), gh, "o/hk", issues)
        self.assertEqual(dict((tid, fields["gh_status"]) for tid, fields, _ in changes)["T-001"],
                         "In review")

    def test_closed_issue_with_unmerged_branch_stays_in_progress(self):
        issue = {1: {"number": 1, "state": "CLOSED", "url": "u1"}}
        gh = self.gh([{"id": "I1", "content": {"number": 1}, "status": "Done"}],
                     refs="refs/heads/1-x\n")
        gh.answers["api repos/o/hk/compare/integration...1-x"] = '{"ahead_by": 1}'
        quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk", issue)
        edit = next(c for c in gh.calls if c[:2] == ["project", "item-edit"])
        self.assertEqual(edit[edit.index("--single-select-option-id") + 1], "p")
        gh.answers["pr list merged"] = '[{"headRefName": "1-x", "headRefOid": "sha-1-x"}]'
        gh.calls.clear()
        quiet(gh_board.sync_board, [self.task(1)], dict(CFG), gh, "o/hk", issue)
        self.assertFalse(any(c[:2] == ["project", "item-edit"] and c[c.index("--field-id") + 1] == "S"
                             for c in gh.calls))

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
