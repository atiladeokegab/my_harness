Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## Files in this skill

| Path | What it holds |
|---|---|
| `reference/fit.md` | Each Impeccable part, where it plugs in, what we adapt; what stays out and why |
| `reference/rubric.md` | What Impeccable's floor and detector do not cover: the tells, the bar, R1 and R2, our two sizes |
| `reference/judge.md`, `reference/evidence.mjs`, `reference/finish-loop.py` | The finish check, its loop and the tournament's cuts, run by fresh sub-agents on captures; the measured evidence in every packet (`node --test reference/evidence.test.mjs`); the loop's books (`uv run python reference/finish-loop.test.py`) |
| `reference/tournament.md`, `reference/tournament-sheet.py` | The direction tournament: rounds, budgets, packets, ties, what the user sees; the blinding and contact-sheet script |
| `reference/judge-tour.md` | The tour's sequence rule, step contract, layout rules and harness |
| `reference/copy.md`, `reference/copy-banned.txt` | The Voice section and the banned-phrase list that `tokens/check-copy.mjs` reads |
| `reference/library.md` | The best-in-field library: picking refs for the judge, adding one |
| `tokens/` | `check-design.md` (install recipe, Makefile lines), `tokens-from-design.mjs`, `palette.mjs`, `type-scale.mjs`, `brand-from-design.mjs`, `impeccable-config.json` |
| `tour-kit/` | `guide.js`, `Guide.jsx`, `guide.css`, `tour.schema.json`, `shots.mjs`, `README.md` |
| `kit/` | The component kit: `ui/` (ten pieces and `kit.css`, copied into products), `fixture/` (two brands, `build.mjs`, `shots.mjs`, `keys.mjs`), `README.md` (the library choice, the copy-in recipe, the token contract). `node_modules` is not shipped: run `npm ci` in `kit/` before the fixture build or its checks |
| `principles/` | One principle per file: the UX and UI books, plus colour, type, consistency and flow; load one at a time |


## Principles index

`principles/index.md` lists every principle file with the flow step that uses it (intent, UX, tour,
look, build, critique). Read the index, then load only the one file your step needs. The rubric cites
them by slug.
