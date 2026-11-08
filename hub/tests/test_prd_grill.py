"""hub prd grill (T-591, plan row A2): next_gap, set_field, cold_read_questions. Never touches the live hub.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT uv run python -m unittest tests.test_prd_grill
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HUB = Path(__file__).resolve().parent.parent
EXAMPLE = HUB / "templates" / "prd" / "example.prd.json"
LEGACY = Path(__file__).parent / "fixtures" / "prd" / "legacy-requirements.json"
sys.path.insert(0, str(HUB))
import prd  # noqa: E402
import prd_grill as g  # noqa: E402

BASES = [str(EXAMPLE.parent)]
ANSWERS = {  # what the lead says to each question when walking an empty template
    "header.problem": "Support staff paste long URLs into chats, where they wrap and break",
    "header.users": "Support agents: shorten a link in one step | Support leads: see click counts",
    "header.goals[+]": "Every shared link fits on one line | no broken URLs in chat | a link is made in under 1 second",
    "header.non_goals": "User accounts | Vanity codes",
    "constraints.stack": "docs/stack.md",
    "constraints.limits": "p95 redirect under 50 ms",
    "constraints.offline_tests": "yes",
    "requirements[+]": "Shorten: a URL becomes a short link",
    "requirements[R-1].why": "Agents need one-line links",
    "requirements[R-1].touches": "app/routes/links.py",
    "requirements[R-1].acceptance[+]": "POST /api/links {url} returns 201 {code} with a 6-character code",
    "requirements[R-1].rank": "1",
}


def example():
    return json.loads(EXAMPLE.read_text())


def flat(v, path=""):
    """Every leaf as path -> value, to prove a write touched exactly one field."""
    if isinstance(v, dict):
        return {k: x for key, sub in v.items() for k, x in flat(sub, f"{path}.{key}").items()} or {path: {}}
    if isinstance(v, list):
        return {k: x for i, sub in enumerate(v) for k, x in flat(sub, f"{path}[{i}]").items()} or {path: []}
    return {path: v}


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        p = mock.patch.object(prd.hb, "HUB_DIR", str(self.root))
        p.start()
        self.addCleanup(p.stop)

    def changed(self, before, after):
        a, b = flat(before), flat(after)
        return sorted(k for k in a.keys() | b.keys() if a.get(k, KeyError) != b.get(k, KeyError))


class TestWalk(Base):
    def test_empty_template_walks_the_fixed_order(self):
        doc, seen = prd.empty(), []
        while (gap := g.next_gap(doc)) is not None:
            self.assertNotIn(gap["path"], seen, "a written field came back as a gap")
            self.assertTrue(gap["question"] and gap["recommended"], gap)
            seen.append(gap["path"])
            g.set_field(doc, gap["path"], ANSWERS[gap["path"]])
        self.assertEqual(seen, list(ANSWERS))
        self.assertEqual(g.cold_read_questions(doc), [])
        self.assertTrue(g.ready(doc))

    def test_each_requirement_is_finished_before_ranking(self):
        doc = example()
        for r in doc["requirements"]:
            r["rank"] = None
        doc["requirements"][1]["why"] = ""
        self.assertEqual(g.next_gap(doc)["path"], "requirements[R-2].why")
        g.set_field(doc, "requirements[R-2].why", "so the link lands")
        self.assertEqual([g.next_gap(doc)["path"]], ["requirements[R-1].rank"])

    def test_legacy_spec_starts_at_the_problem_with_a_recommendation_from_its_titles(self):
        d = self.root / "projects" / "fs" / "spec"
        d.mkdir(parents=True)
        shutil.copy(LEGACY, d / "requirements.json")
        gap = g.next_gap(g.load("fs"))
        self.assertEqual(gap["path"], "header.problem")
        self.assertIn("Version endpoint", gap["recommended"])


class TestRecommendations(Base):
    def test_limits_come_from_the_goal_measures(self):
        doc = prd.empty()
        for path in ("header.problem", "header.users", "header.goals[+]", "header.non_goals", "constraints.stack"):
            g.set_field(doc, path, ANSWERS[path])
        gap = g.next_gap(doc)
        self.assertEqual(gap["path"], "constraints.limits")
        self.assertIn("under 1 second", gap["recommended"])

    def test_why_is_the_goal_the_title_shares_most_words_with(self):
        doc = example()
        doc["requirements"][2]["why"] = ""
        doc["header"]["goals"][1]["purpose"] = "Leads see each link's click count"
        gap = g.next_gap(doc)
        self.assertEqual(gap["path"], "requirements[R-3].why")
        self.assertIn("Leads see each link's click count", gap["recommended"])

    def test_rank_recommends_the_next_free_rank(self):
        doc = example()
        doc["requirements"][1]["rank"] = None
        gap = g.next_gap(doc)
        self.assertEqual((gap["path"], gap["recommended"]), ("requirements[R-2].rank", "2"))


class TestSetField(Base):
    def test_writes_exactly_one_field_and_reads_it_back(self):
        doc = example()
        before = copy.deepcopy(doc)
        said = g.set_field(doc, "requirements[R-2].why", "Customers must land on the page")
        self.assertEqual(self.changed(before, doc), [".requirements[1].why"])
        self.assertIn("R-2", said)
        self.assertIn("Customers must land on the page", said)

    def test_list_answer_splits_on_bars_and_none_means_empty(self):
        doc = prd.empty()
        g.set_field(doc, "header.users", "Agents: shorten | Leads: count")
        self.assertEqual(doc["header"]["users"], ["Agents: shorten", "Leads: count"])
        g.set_field(doc, "constraints.limits", "none")
        self.assertEqual(doc["constraints"]["limits"], [])
        self.assertNotIn("constraints.limits", [x["path"] for x in g.gaps(doc)])

    def test_append_requirement_and_acceptance_line(self):
        doc = example()
        before = copy.deepcopy(doc)
        said = g.set_field(doc, "requirements[+]", "Expiry: links stop after 30 days")
        self.assertEqual(doc["requirements"][-1]["id"], "R-4")
        self.assertTrue(all(k.startswith(".requirements[3]") for k in self.changed(before, doc)))
        self.assertIn("R-4", said)
        g.set_field(doc, "requirements[R-1].acceptance[+]", "POST /api/links twice with one URL returns one code")
        line = doc["requirements"][0]["acceptance"][-1]
        self.assertEqual((line["id"], line["v"], line["test"]), ("A-1.3", 1, "tests/acceptance/test_A_1_3.py"))

    def test_new_requirement_may_wait_for_its_first_line(self):
        doc = example()
        g.set_field(doc, "requirements[+]", "Expiry: links stop after 30 days")
        self.assertIn("R-4: no acceptance lines", prd.validate(doc)[0])
        self.assertFalse(g.ready(doc))
        self.assertEqual(g.next_gap(doc)["path"], "requirements[R-4].why")
        with self.assertRaises(ValueError):  # only the append itself is excused
            g.set_field(doc, "requirements[R-1].acceptance", [])

    def test_glossary_term(self):
        doc = example()
        g.set_field(doc, "header.glossary.expiry", "the day a link stops redirecting")
        self.assertEqual(doc["header"]["glossary"]["expiry"], "the day a link stops redirecting")

    def test_refuses_unknown_field_bad_selector_and_new_errors(self):
        doc = example()
        before = copy.deepcopy(doc)
        for path, value, why in (("header.problme", "x", "unknown key header.problme (did you mean problem?)"),
                                 ("heder.problem", "x", "unknown key heder (did you mean header?)"),
                                 ("requirements[R-1].wyh", "x",
                                  "unknown key requirements[R-1].wyh (did you mean why?)"),
                                 ("requirements[R-1].acceptance[A-1.1].tst", "x", "(did you mean test?)"),
                                 ("status.waiting", "x", "unknown key status.waiting (did you mean waiting_room?)"),
                                 ("requirements[R-9].why", "x", "no R-9"),
                                 ("requirements[R-1].rank", "high", "whole number"),
                                 ("requirements[R-1].rank", "2", "rank 2 is used by R-1 and R-2"),
                                 ("constraints.offline_tests", "maybe", "yes or no")):
            with self.assertRaises(ValueError) as e:
                g.set_field(doc, path, value, project="linkly", bases=BASES)
            self.assertIn(why, str(e.exception))
        self.assertEqual(doc, before)
        self.assertFalse(os.path.exists(prd.prd_path("linkly")))

    def test_saves_prd_json_atomically(self):
        doc = g.load("fresh")
        g.set_field(doc, "header.problem", "Links break in chat", project="fresh")
        self.assertEqual(prd.load("fresh")["header"]["problem"], "Links break in chat")
        self.assertFalse(os.path.exists(prd.prd_path("fresh") + ".tmp"))

    def test_reference_by_path_is_pinned_to_its_hash(self):
        doc = example()
        doc["references"]["spine"]["sha256"] = "0" * 64
        gap = g.next_gap(doc, BASES)
        self.assertEqual(gap["path"], "references.spine")
        g.set_field(doc, "references.spine", gap["recommended"], bases=BASES)
        self.assertEqual(doc["references"]["spine"]["sha256"], example()["references"]["spine"]["sha256"])


class TestLocked(Base):
    """An approved, locked spec changes only through a change file; the grill is for bootstrap (Hermes on 83507ba)."""
    LOCK = LEGACY.parent / "spec.lock"

    def lock(self, project="factory-sandbox"):
        d = self.root / "projects" / project / "spec"
        d.mkdir(parents=True)
        shutil.copy(LEGACY, d / "requirements.json")
        shutil.copy(self.LOCK, d / "spec.lock")
        return d

    def test_set_field_refuses_every_write(self):
        d = self.lock()
        version = json.loads(self.LOCK.read_text())["version"]
        for path, value in (("header.problem", "x"), ("requirements[R-1].why", "x"),
                            ("requirements[R-1].acceptance[A-1.1].text", "GET /version returns {commit, branch}")):
            doc = g.load("factory-sandbox")
            with self.assertRaises(ValueError) as e:
                g.set_field(doc, path, value, project="factory-sandbox")
            self.assertIn(f"approved spec (v{version}, locked): changes go through a change file; see hub spec --help",
                          str(e.exception))
        self.assertFalse((d / "prd.json").exists())

    def test_hermes_probe_writes_nothing(self):
        d = self.lock()
        before = (d / "requirements.json").read_bytes()
        for answer in ("header.problem=Ops needs a status API",
                       "requirements[R-1].acceptance[A-1.1].text=GET /version returns {commit, branch}"):
            r = TestCli.hub(self, "factory-sandbox", "--answer", answer)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("locked): changes go through a change file", r.stderr)
            self.assertFalse((d / "prd.json").exists())
            self.assertEqual((d / "requirements.json").read_bytes(), before)
        out = json.loads(TestCli.hub(self, "factory-sandbox", "--json").stdout)
        self.assertIn("locked", out["locked"])

    def test_unlocked_bootstrap_still_writes(self):
        d = self.root / "projects" / "boot" / "spec"
        d.mkdir(parents=True)
        shutil.copy(LEGACY, d / "requirements.json")
        g.set_field(g.load("boot"), "header.problem", "Ops needs a status API", project="boot")
        self.assertTrue((d / "prd.json").exists())


class TestSuggested(Base):
    def test_touches_guess_is_labelled_and_cannot_be_written_verbatim(self):
        doc = example()
        doc["requirements"][0]["touches"] = []
        gap = g.next_gap(doc)
        self.assertEqual(gap["path"], "requirements[R-1].touches")
        self.assertTrue(gap["recommended"].startswith("suggested: app/shorten.py"), gap["recommended"])
        with self.assertRaises(ValueError) as e:
            g.set_field(doc, gap["path"], gap["recommended"])
        self.assertIn("a guess", str(e.exception))
        self.assertEqual(doc["requirements"][0]["touches"], [])


class TestColdRead(Base):
    def test_example_is_ready(self):
        self.assertEqual(g.cold_read_questions(example(), BASES), [])
        self.assertTrue(g.ready(example(), BASES))

    def test_each_hole_is_a_question(self):
        doc = example()
        doc["header"]["users"] = []
        doc["header"]["non_goals"] = []
        doc["requirements"][0]["why"] = ""
        doc["requirements"][0]["acceptance"][1]["text"] = "it should be fast and easy"
        doc["requirements"][1]["acceptance"][0]["test"] = ""
        doc["requirements"][2]["rank"] = None
        doc["references"]["design"] = {"path": "DESIGN.md", "sha256": "0" * 64}
        qs = "\n".join(g.cold_read_questions(doc, BASES))
        for want in ("Who uses it", "out of scope", "R-1: why", "A-1.2", "A-2.1: which test", "R-3", "DESIGN.md"):
            self.assertIn(want, qs)
        self.assertFalse(g.ready(doc, BASES))

    def test_validate_errors_block_ready_even_without_gaps(self):
        doc = example()
        doc["requirements"][1]["rank"] = 1
        self.assertEqual(g.cold_read_questions(doc, BASES), [])
        self.assertFalse(g.ready(doc, BASES))


class TestCli(Base):
    def hub(self, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME")}
        env.update(HUB_DIR=str(self.root), HOME=str(self.root))
        return subprocess.run([sys.executable, str(HUB / "board.py"), "prd", "grill", *args], env=env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL, timeout=60)

    def test_grill_is_non_interactive(self):
        r = self.hub("new", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["ready"], out["next"]["path"]), (False, "header.problem"))
        r = self.hub("new", "--answer", "header.problem=Links break in chat", "--json")
        out = json.loads(r.stdout)
        self.assertIn("Links break in chat", out["readback"])
        self.assertEqual(out["next"]["path"], "header.users")
        self.assertEqual(json.loads((self.root / "projects/new/spec/prd.json").read_text())["header"]["problem"],
                         "Links break in chat")
        r = self.hub("new")
        self.assertIn("header.users", r.stdout)
        self.assertIn("Recommended:", r.stdout)

    def test_bad_answer_exits_nonzero_and_writes_nothing(self):
        r = self.hub("new", "--answer", "header.problme=x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown key header.problme (did you mean problem?)", r.stderr)
        self.assertFalse((self.root / "projects/new/spec/prd.json").exists())

    def test_ready_project(self):
        d = self.root / "projects" / "linkly"
        (d / "spec").mkdir(parents=True)
        (d / "spec" / "prd.json").write_text(EXAMPLE.read_text())
        shutil.copy(EXAMPLE.parent / "example-spine.md", d)
        r = self.hub("linkly")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ready", r.stdout)


if __name__ == "__main__":
    unittest.main()
