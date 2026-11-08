# uv run python finish-loop.test.py: the loop's decisions, including the one that matters most for
# calibration: a rebuild never becomes a ship on unchanged screens, and one lucky judge never ships alone.
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("finish-loop.py")


def verdict(disposition, scores):
    rows = "\n".join(f"| B{i} | {s} | reason |" for i, s in enumerate(scores, 1))
    return f"disposition: {disposition}\n\n## Rubric verdict\nR1 2: x\n| B | Score | Reason |\n|---|---|---|\n{rows}\n"


SHIP23 = verdict("ship", [2] * 11 + [1])           # 23, B7 and B8 at 2
FIX23_B8 = verdict("fix", [2] * 7 + [1] + [2] * 4)  # 23, B8 at 1
FIX20 = verdict("fix", [2] * 8 + [1] * 4)          # 20, B7 and B8 at 2
SHIP24 = verdict("ship", [2] * 12)
REBUILD5 = verdict("rebuild", [1] * 5 + [0] * 7)   # 5


class FinishLoop(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.n = 0

    def screens(self, content):
        s = self.d / f"screens-{self.n}"
        self.n += 1
        s.mkdir()
        (s / "screen-1-desktop.png").write_text(content)
        return s

    def run_loop(self, action, text, screens=None, mode="hackathon"):
        v = self.d / f"v{self.n}-{action}.md"
        self.n += 1
        v.write_text(text)
        args = [sys.executable, str(SCRIPT), str(self.d / "trail"), action, "--verdict", str(v)]
        if action == "round":
            args += ["--mode", mode, "--screens", str(screens)]
        p = subprocess.run(args, capture_output=True, text=True)
        return p.returncode, p.stdout.splitlines()[0]

    def test_rebuild_never_ships_on_unchanged_screens(self):
        s = self.screens("bad")
        self.assertEqual(self.run_loop("round", REBUILD5, s), (2, "next: fix"))
        code, out = self.run_loop("round", SHIP23, s)  # a lucky re-judge of the same pixels
        self.assertEqual(code, 1)
        self.assertIn("screens unchanged", out)

    def test_one_ship_verdict_needs_a_second_judge(self):
        s = self.screens("a")
        self.assertEqual(self.run_loop("round", FIX20, s), (2, "next: fix"))
        self.assertEqual(self.run_loop("round", SHIP23, self.screens("b")), (2, "next: confirm"))
        self.assertEqual(self.run_loop("confirm", SHIP23), (0, "next: ship"))
        md = (self.d / "trail" / "trail.md").read_text()
        self.assertIn("| 23/24 | +3 |", md)
        self.assertIn("Outcome: ship", md)

    def test_second_judge_under_21_blocks_ship(self):
        self.run_loop("round", SHIP24, self.screens("a"))
        self.assertEqual(self.run_loop("confirm", FIX20), (2, "next: fix"))  # median 22, but one judge at 20

    def test_b8_at_1_is_not_ship_even_at_23(self):
        self.assertEqual(self.run_loop("round", FIX23_B8, self.screens("a")), (2, "next: fix"))
        self.run_loop("round", SHIP24, self.screens("b"))
        self.assertEqual(self.run_loop("confirm", FIX23_B8), (2, "next: fix"))  # median 23.5, median B8 1.5

    def test_plateau(self):
        for c in "abc":
            code, out = self.run_loop("round", FIX20, self.screens(c), mode="planning")
        self.assertEqual((code, out), (3, "next: stop plateau"))  # two gains in a row under 1

    def test_cap(self):
        for c, v in zip("ab", [FIX20, FIX23_B8]):
            self.assertEqual(self.run_loop("round", v, self.screens(c)), (2, "next: fix"))
        self.assertEqual(self.run_loop("round", FIX20, self.screens("c")), (3, "next: stop cap"))
        self.assertEqual(json.loads((self.d / "trail" / "trail.json").read_text())["next"], "stop cap")
        self.assertEqual(self.run_loop("round", SHIP23, self.screens("d"))[0], 1)  # an ended loop stays ended

if __name__ == "__main__":
    unittest.main()
