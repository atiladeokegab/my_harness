"""hub prd (T-590, plan row A1): the PRD file, its legacy load, validate and render. Never touches the live hub.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT uv run python -m unittest tests.test_prd
"""

import copy
import hashlib
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


def example():
    return json.loads(EXAMPLE.read_text())


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        p = mock.patch.object(prd.hb, "HUB_DIR", str(self.root))
        p.start()
        self.addCleanup(p.stop)

    def put(self, project, name, data):
        d = self.root / "projects" / project / "spec"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(data))
        return d

    def errors(self, doc, base=None):
        return prd.validate(doc, [str(base or EXAMPLE.parent)])[0]

    def bad(self, mutate):
        doc = example()
        mutate(doc)
        return self.errors(doc)


class TestExample(Base):
    def test_full_example_validates_clean(self):
        errs, warns = prd.validate(example(), [str(EXAMPLE.parent)])
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

    def test_example_has_every_part(self):
        doc = example()
        for part in ("header", "constraints", "requirements", "references", "status"):
            self.assertTrue(doc[part], part)
        self.assertTrue(doc["references"]["spine"]["sha256"])

    def test_empty_template_has_no_errors_only_gaps(self):
        errs, warns = prd.validate(prd.empty(), [])
        self.assertEqual(errs, [])
        self.assertIn("header: non_goals is empty", warns)


class TestLoad(Base):
    def test_prd_json_wins_over_legacy(self):
        self.put("p", "requirements.json", {"version": 1, "requirements": []})
        self.put("p", "prd.json", example())
        self.assertEqual(prd.load("p")["header"]["problem"], example()["header"]["problem"])

    def test_factory_sandbox_loads_through_legacy_path_and_renders(self):
        self.put("factory-sandbox", "requirements.json", json.loads(LEGACY.read_text()))
        doc = prd.load("factory-sandbox")
        legacy = json.loads(LEGACY.read_text())
        self.assertEqual([r["id"] for r in doc["requirements"]], [r["id"] for r in legacy["requirements"]])
        self.assertEqual(doc["version"], legacy["version"])
        self.assertEqual(doc["header"]["problem"], "")
        errs, warns = prd.validate(doc, [])
        self.assertEqual(errs, [])
        self.assertIn("R-1: why is empty", warns)
        self.assertIn("header: non_goals is empty", warns)
        page = prd.render(doc, "factory-sandbox")
        self.assertIn("R-9", page)
        self.assertIn('class="gap"', page)  # the empty header is marked, not hidden
        self.assertIn("R-9", prd.render_md(doc, "factory-sandbox"))

    def test_legacy_keeps_parts_an_approved_change_set(self):
        """T-592: a change that sets header/constraints/references/status in requirements.json must survive load."""
        legacy = json.loads(LEGACY.read_text())
        ex = example()
        legacy.update(header={"problem": "Links break in chat", "owner": "the lead"}, constraints=ex["constraints"],
                      references=ex["references"], status={"open_questions": ["Which region?"]})
        self.put("fs", "requirements.json", legacy)
        doc = prd.load("fs")
        self.assertEqual(doc["header"]["problem"], "Links break in chat")
        self.assertEqual(doc["header"]["users"], [])  # the rest of the part still comes from empty()
        self.assertEqual(doc["constraints"], ex["constraints"])
        self.assertEqual(doc["references"], ex["references"])
        self.assertEqual(doc["status"]["open_questions"], ["Which region?"])
        self.assertEqual(doc["status"]["waiting_room"], [])

    def test_no_spec_is_a_clear_exit(self):
        with self.assertRaises(SystemExit) as e:
            prd.load("nothing")
        self.assertIn("no PRD for nothing", str(e.exception))

    def test_unreadable_json_is_a_clear_exit(self):
        d = self.root / "projects" / "p" / "spec"
        d.mkdir(parents=True)
        (d / "prd.json").write_text("{nope")
        with self.assertRaises(SystemExit) as e:
            prd.load("p")
        self.assertIn("prd.json", str(e.exception))


class TestValidate(Base):
    def test_not_an_object(self):
        self.assertEqual(prd.validate([], [])[0], ["the PRD must be a JSON object"])

    def test_duplicate_requirement_id(self):
        errs = self.bad(lambda d: d["requirements"].append(copy.deepcopy(d["requirements"][0])))
        self.assertTrue(any("duplicate id R-1" in e for e in errs), errs)

    def test_rank_must_be_unique(self):
        def m(d):
            d["requirements"][1]["rank"] = d["requirements"][0]["rank"]
        self.assertTrue(any("rank 1 is used by R-1 and R-2" in e for e in self.bad(m)), self.bad(m))

    def test_rank_must_be_in_range(self):
        def m(d):
            d["requirements"][0]["rank"] = 9
        self.assertIn("R-1: rank 9 is outside 1..3", self.bad(m))

    def test_rank_must_be_an_integer(self):
        def m(d):
            d["requirements"][0]["rank"] = "high"
        self.assertIn("R-1: rank must be a whole number", self.bad(m))

    def test_acceptance_line_needs_a_test_path(self):
        def m(d):
            d["requirements"][0]["acceptance"][0]["test"] = ""
        self.assertIn("A-1.1: no test path", self.bad(m))

    def test_unknown_need(self):
        def m(d):
            d["requirements"][0]["needs"] = ["R-99"]
        self.assertIn("R-1 needs unknown R-99", self.bad(m))

    def test_requirement_not_an_object(self):
        self.assertIn("requirements[1] must be an object", self.bad(lambda d: d["requirements"].insert(1, "R-x")))

    def test_acceptance_not_a_list(self):
        def m(d):
            d["requirements"][0]["acceptance"] = "GET / works"
        self.assertIn("R-1: acceptance must be a list", self.bad(m))

    def test_header_field_types(self):
        def m(d):
            d["header"]["users"] = "everyone"
            d["header"]["goals"][0].pop("measure")
        errs = self.bad(m)
        self.assertIn("header.users must be a list", errs)
        self.assertIn("header.goals[0]: measure must be a string", errs)

    def test_reference_must_resolve(self):
        def m(d):
            d["references"]["design"] = {"path": "DESIGN-missing.md", "sha256": "0" * 64}
        self.assertIn("references.design: DESIGN-missing.md not found", self.bad(m))

    def test_reference_hash_must_match(self):
        def m(d):
            d["references"]["spine"]["sha256"] = "0" * 64
        errs = self.bad(m)
        self.assertTrue(any(e.startswith("references.spine: sha256 does not match") for e in errs), errs)

    def test_status_state_names_real_requirements(self):
        def m(d):
            d["status"]["state"] = {"R-1": "done-ish", "R-42": "built"}
        errs = self.bad(m)
        self.assertIn("status.state R-1: 'done-ish' is not proposed, approved or built", errs)
        self.assertIn("status.state names unknown R-42", errs)

    def test_fixtures_are_input_output_pairs(self):
        def m(d):
            d["requirements"][0]["acceptance"][0]["fixtures"] = [{"input": "x"}]
        self.assertIn("A-1.1: fixtures[0] needs input and output", self.bad(m))


class TestClosedKeys(Base):
    """Hermes's probes on c63d124: a misspelt key used to validate clean and silently drop its data."""

    def test_misspelt_header_is_an_error(self):
        doc = example()
        doc["heder"] = doc.pop("header")
        self.assertIn("unknown key heder (did you mean header?)", self.errors(doc))

    def test_misspelt_acceptance_is_an_error_not_zero_lines(self):
        def m(d):
            d["requirements"][0]["acceptence"] = d["requirements"][0].pop("acceptance")
        errs = self.bad(m)
        self.assertIn("unknown key R-1.acceptence (did you mean acceptance?)", errs)
        self.assertIn("R-1: no acceptance lines", errs)

    def test_misspelt_requirements_names_the_key(self):
        doc = example()
        doc["requirments"] = doc.pop("requirements")
        self.assertEqual(self.errors(doc)[0], "unknown key requirments (did you mean requirements?)")

    def test_every_level_is_closed(self):
        def m(d):
            d["header"]["problme"] = "x"
            d["constraints"]["limit"] = []
            d["requirements"][0]["acceptance"][0]["tst"] = "x"
            d["header"]["goals"][0]["mesure"] = "x"
            d["status"]["waiting"] = []
            d["references"]["desgin"] = d["references"]["spine"]
        errs = self.bad(m)
        for want in ("unknown key header.problme (did you mean problem?)",
                     "unknown key constraints.limit (did you mean limits?)",
                     "unknown key A-1.1.tst (did you mean test?)",
                     "unknown key header.goals[0].mesure (did you mean measure?)",
                     "unknown key status.waiting (did you mean waiting_room?)",
                     "unknown key references.desgin (did you mean design?)"):
            self.assertIn(want, errs)

    def test_free_form_maps_stay_open(self):
        doc = example()
        doc["header"]["glossary"]["anything"] = "a term"
        self.assertEqual(self.errors(doc), [])

    def test_no_acceptance_lines_is_an_error(self):
        def m(d):
            d["requirements"][2]["acceptance"] = []
        self.assertIn("R-3: no acceptance lines", self.bad(m))


class TestWarnings(Base):
    def test_requirement_over_size_budget(self):
        doc = example()
        r = doc["requirements"][0]
        r["acceptance"] = [{"id": f"A-1.{i}", "v": 1, "text": "x", "test": "t.py"} for i in range(1, 13)]
        warns = prd.validate(doc, [str(EXAMPLE.parent)])[1]
        self.assertTrue(any(w.startswith("R-1: ") and "over the ~10" in w for w in warns), warns)

    def test_header_over_size_budget(self):
        doc = example()
        doc["header"]["principles"] = [f"principle {i}" for i in range(70)]
        warns = prd.validate(doc, [str(EXAMPLE.parent)])[1]
        self.assertTrue(any(w.startswith("header: ") and "over the ~60" in w for w in warns), warns)

    def test_missing_why_and_touches(self):
        doc = example()
        doc["requirements"][0]["why"] = ""
        doc["requirements"][0]["touches"] = []
        warns = prd.validate(doc, [str(EXAMPLE.parent)])[1]
        self.assertIn("R-1: why is empty", warns)
        self.assertIn("R-1: touches is empty", warns)


class TestRender(Base):
    def test_html_is_self_contained_and_theme_aware(self):
        page = prd.render(example(), "linkly")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("prefers-color-scheme: dark", page)
        for ext in ("src=", "<link", "@import", "url("):
            self.assertNotIn(ext, page)

    def test_html_escapes_text(self):
        doc = example()
        doc["header"]["problem"] = "<script>alert(1)</script>"
        page = prd.render(doc, "linkly")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_weak_fields_are_marked(self):
        doc = example()
        doc["requirements"][0]["why"] = ""
        doc["requirements"][0].pop("rank")
        self.assertIn("unranked", prd.render(doc, "linkly"))
        self.assertIn("why is empty", prd.render(doc, "linkly"))

    def test_markdown_lists_every_line(self):
        md = prd.render_md(example(), "linkly")
        for r in example()["requirements"]:
            for a in r["acceptance"]:
                self.assertIn(f"{a['id']}@{a['v']}", md)


class TestCli(Base):
    def hub(self, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME")}
        env.update(HUB_DIR=str(self.root), HOME=str(self.root))
        return subprocess.run([sys.executable, str(HUB / "board.py"), "prd", *args], env=env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL, timeout=60)

    def test_check_show_render(self):
        d = self.put("linkly", "prd.json", example())
        shutil.copy(EXAMPLE.parent / example()["references"]["spine"]["path"], d.parent)
        r = self.hub("check", "linkly")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("prd ok: linkly", r.stdout)
        r = self.hub("show", "linkly")
        self.assertIn("A-1.1@1", r.stdout)
        out = self.root / "page.html"
        r = self.hub("render", "linkly", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("<!doctype html>", out.read_text())

    def test_check_fails_on_errors(self):
        doc = example()
        doc["requirements"][0]["acceptance"][0]["test"] = ""
        self.put("linkly", "prd.json", doc)
        r = self.hub("check", "linkly")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A-1.1: no test path", r.stdout)

    def test_hash_of_spine_in_example_is_current(self):
        ref = example()["references"]["spine"]
        self.assertEqual(hashlib.sha256((EXAMPLE.parent / ref["path"]).read_bytes()).hexdigest(), ref["sha256"])


if __name__ == "__main__":
    unittest.main()
