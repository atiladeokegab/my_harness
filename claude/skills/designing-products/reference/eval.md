# Eval: does the skill still reach 22?

Re-run this after any change to SKILL.md, the rubric, judge.md, tournament.md or evidence.mjs. It runs
three briefs end to end and the bad set, and it passes only when all four pass. Last run and its trail:
`fixtures/eval/log.md`.

## The set

| Brief | Fixture | Kind |
|---|---|---|
| Strata Lifts | `fixtures/eval/strata/` (reuses `fixtures/trio/brief.md`, `fixtures/tournament/content.md`) | Persuade, a map and a mechanism |
| Hartwell Battery Desk | `fixtures/eval/battery/` | Operate dashboard |
| Rise | `fixtures/eval/rise/` | consumer app |
| Bad set | `fixtures/bad/` | four screens that must come back fix or rebuild |

Each brief has `brief.md` (it also stands in for PRODUCT.md), `content.md` with the four screens' words,
and `standard.html`, the card the winner must beat.

## Pass rule

- Each brief: `finish-loop.py` reaches `ship`, at 22+ with B7 and B8 at 2. The final score is held by two
  fresh blind judges: median 22+, both 21+.
- The bad set, in the same run: every screen comes back `fix` or `rebuild`, naming its fixture's tells.
- A brief that misses: name the B items and the skill change that closes them, make it (SKILL.md under
  200 lines), and re-run that brief once. Log both runs.

## How to run

1. Copy `fixtures/eval/scripts/` into a scratch directory `$S` (the scripts write beside themselves,
   never into the repo). For each brief, make `$S/<brief>/` and a `refs.md` listing the brief's refs and
   the taste set.
2. The tournament (`tournament.md`), per brief, at most about 6 sub-agents at once:
   - Round 0: 3 lens agents write 30 lines to `r0/lens-{a,b,c}.md`.
   - Round 1: sketchers follow `sketch-rules.md`. Run `render.sh`, then `tournament-sheet.py <cap1>
     <pk1/packet> s 30`, then one blind judge, which keeps 8.
   - Round 2: run `mkbrief.py <brief> <content.md>`. Builders follow `builder-rules.md`. Run
     `render2.sh`, then `tournament-sheet.py ... p 8`, then a judge, which keeps 2.
   - Round 3: run `mkpolish.py <brief>`. Polishers follow `polish-rules.md`. Run `mkfinal.sh <brief>
     <standard.html>`, then the final judge.
3. The finish loop (`judge.md` §6), on the winner `<n>`:
   - Run `mkfin.sh <brief> <n> <round>`, which captures 4 screens at 1280x633 and 390x757 and runs
     evidence and the detector.
   - Run `python3 mode1.py <fin/rN> <refs.md> "the direction contract in <fin/contract.md>" <name>
     <fin/rN-verdict.md> <brief.md>`. This writes the brief, which goes to a fresh judge.
   - Record each round with `finish-loop.py <fin/trail> round ...`. Run `confirm` on `ship`. On `fix`, a
     fixer follows `fix-rules.md`.
   - Hackathon cap: 3 rounds.
4. The bad set: give each `fixtures/bad/` screen a fresh judge with the same mode-1 brief.
5. Checks: `node --test reference/evidence.test.mjs`.

## Logging

Add a run to `fixtures/eval/log.md`: each brief's winner and finish trail, both judges' final per-B
scores, the bad-set result, the skill changes, the timings and the agent-run count.

A full run takes about 2 hours and 90 sub-agent runs.
