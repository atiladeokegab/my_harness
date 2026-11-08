# Eval log

## Run 1: 2026-11-02, T-1015 (plugin 1.17.11 plus this commit)

Pass rule: each brief reaches `ship` at 22+ with B7 and B8 at 2, the final score held by two fresh blind
judges (median 22+, both 21+), and in the same run the bad set (`../bad/`) all comes back fix or rebuild.

**Result: not passed.** No brief reached `ship` from two judges. Two of three held a score of 22+ from two
judges; every miss is the disposition, not the total.

| Brief | Tournament winner | Finish trail (one fresh judge per round) | Final screens, two judges | Outcome |
|---|---|---|---|---|
| Strata Lifts (`strata/`) | line 27, final 22/24, standard 11 | 21, 22, 22 (stop cap); re-run 22, 23, 23 (stop cap) | 23 `fix` and 24 `ship`; median 23.5 | score held, ship split 1 to 1 |
| Hartwell Battery Desk (`battery/`) | line 2, final 22/24, standard 10 | 19, 22, 20 (stop cap); re-run 20, 23, 23 (stop cap) | 23 `fix` and 22 `fix`; median 22.5 | score held, no ship |
| Rise (`rise/`) | line 1, final 21/24 (B8 1), standard 11 | 19, 19 (stopped at the time cap) | one judge only, 19 | missed, not re-run |

Final per-B scores, B1 to B12:

- Strata, judge A: 2 2 2 2 2 2 2 2 2 2 2 1 = 23 (B12: the headline link's focus ring has no offset).
  Judge B: all 2 = 24, `ship`.
- Battery, judge A: 2 2 2 2 2 2 2 2 2 1 2 2 = 23. Judge B: 2 1 2 2 2 2 2 2 2 1 2 2 = 22.
  Both `fix`, on T7 copy: a back link worded as the action, two ideas in one line.
- Rise, round 2: 2 1 2 1 1 2 1 2 2 1 2 2 = 19. B7 fell from 2 to 1, because the fix pushed the heading off
  the job. A T15 hard-offset shadow on the button survived from round 2 of the tournament to the finish.

Bad set: pass. All four came back `rebuild`. screen-1 (t5-t8) named T5 and T8, bar 7. screen-2 (t14-t15)
named T14 and T15, bar 6. screen-3 (t9-t11) named T9 and T11, bar 4. screen-4 (t1-t4) named T1 and T4, bar 6.

Models: Fable for the round-0 lens lines; Sonnet for the round-1 sketchers; Opus for every judge, round-2
builder, round-3 polisher, finish judge and fixer. The briefs ran in parallel, with at most 6 sub-agents
live at a time. The lead's later ask was Sonnet for the round-1 judges and under 60 minutes; this run did
not meet either.

Blinding: each judge got only the packet folder (`pk*/packet/`) or the capture folder (`fin/rN/`). The
blind-name key `pk*/packet-map.json` sits one level up, outside both. The two final judges on each brief
were two separate fresh sub-agents, never a judge re-scoring after its own fixes.

Motion: battery animates the isolator closing with requestAnimationFrame, which `evidence.mjs` cannot see.
Checked by hand on all four screens: each returns early when `prefers-reduced-motion: reduce` matches.
Strata and Rise use CSS transitions only.

Baseline: build-d11b's fresh blind judge scored T-1013's Strata winner 17/24, `fix`. Its finish loop went
17, 22, 21. This run's Strata line reached 23 and 24 from two fresh judges.

R1 swing: a judge's R1 depends on which reference it picks (build-d11b saw Cesium 2 and Felt 1 on the same
screens). In this run Strata went from R1 1 against Felt to R1 2 against Felt as the screens improved. R1
did not block ship in the final rounds, so naming one R1 reference per brief was not tried; it is the
next change if R1 blocks.

## What the misses were, and the skill changes

1. **B8, a desktop figure shrunk to 390.** T-1013's winner had a 9 px label. `evidence.mjs` now has a
   `text-size` line, which fails under 12 px. B8 scores 2 only when that line passes. The tournament
   builder and polisher rows, T14 and SKILL.md's Never all say to redraw the figure for the phone. After
   this, B8 was 2 on every final screen.
2. **T7 copy tells came back every round.** The fixer cleared the lines the judge quoted, and the next
   fresh judge found new ones. In `judge.md` §6 and the tournament polisher row, a T line is now a class:
   clear every instance on all eight captures. That means every number with its source, or an
   illustrative mark in the same viewport at both sizes, one idea per line, and a state named by what
   happened. Strata and battery were re-run once with this change: both moved from 22 and 20 to 23.
3. **Eval harness: no PRODUCT.md, and no seed line in the contract.** Every finish judge called this a
   material fix, so `fix` could never become `ship`. `scripts/mode1.py` now takes the brief as PRODUCT.md,
   and each contract records the tournament line as its seed. This applied from re-run round 3 on.
4. **Eval harness: the detector rule names printed `?`.** `mkfin.sh` read the wrong JSON key. It now reads
   `antipattern`.

Still open, not closed by this run:

- **Disposition `fix` at 23 to 24.** Any tell or material fix forces `fix` (rubric §7). Fresh judges keep
  finding one more copy line or truth issue, so `ship` needs two judges to find nothing. Next step: a
  copy lint in `evidence.mjs` for the mechanical T7 rules (unlabelled numbers in the viewport, back links
  that repeat an action label).
- **SVG labels touching shapes.** These were Rise "peaked at 13:20" over "2.3 times" and Strata "Bascule"
  on the pier, both at 390. `text-occlusion` does not see them.
- **States (B5).** It was 1 in five of the first six strata and battery judgments, until a fixer drew
  loading and error states.

## Timings (UTC) and agent runs

| Step | Strata | Battery | Rise |
|---|---|---|---|
| Round 0 (3 Fable lens agents per brief) | 12:59 to 13:02 | the same | the same |
| Round 1 (6 sketchers and a judge) | 13:02 to 13:08 | alongside | by 13:55 |
| Round 2 (8 builders and a judge) | 13:10 to 13:30 | alongside | 13:55 to 14:21 |
| Round 3 (2 polishers and a final judge) | 13:31 to 13:48 | alongside | 14:24 to 14:37 |
| Finish loop | 13:51 to 14:23, re-run to 14:59 | the same | 14:41 to 15:00 |

The whole run took about 2 h 05 min. There were about 93 sub-agent runs: 66 tournament agents (9 lens, 21
sketch and judge, 27 build and judge, 9 polish and judge), 4 bad-set judges, and 23 finish judges and fixers. Most took 70k to 140k tokens each, so about 9M sub-agent tokens.
At most 6 ran at once. A judge or fixer takes 4 to 9 min, so a three-round finish loop with a confirm
takes about 35 min of wall clock.

## Run 2 (2026-11-02, 15:04 to 16:05 UTC, plugin 1.17.12)

Changes before the runs:

- **`copy` check in `evidence.mjs`** (the mechanical part of T7). It flags a link whose first word matches a
  button's on the same screen, a line over 25 words or with 4 or more joins, and a figure with no source or
  illustrative mark in the first viewport. `evidence.test.mjs` turns it red on the battery screens' old copy
  (`battery/old-copy.html`). It caught "Suggested window: 17:30 to 19:30, 4 periods, ..." in battery r6.
- **`overlap` check**: an SVG label over another label, at both sizes. It caught battery "655 kW" over
  "Prices updated 15:00." and Rise "Last fed" over "Monday 13:52." at 1280. Shortcut: label against label only;
  a label on a shape's stroke is left to the judge.

| Brief | Trail | Final judge A | Final judge B | Result |
|---|---|---|---|---|
| Battery (finish loop only) | 22, 23, 23 (cap) | 23 fix, B4 1 | 24 ship | Median 23.5, both 21+, B7 and B8 at 2: passes the score bar, dispositions split |
| Rise (end to end, first re-run) | tournament line 14 "Brewer's hydrometer", 22; finish 18, 20, 21 (cap) | 21 fix, B5 B7 B10 at 1 | 22 fix, B1 B5 at 1 | Median 21.5: misses 22 |

- No judge raised a T7 copy tell on battery after the lint went in.
- Rise's R1 stayed at 1 against Things ("flat, not lit or dimensional") in every round. The tournament chose
  a flat direction and no finish round could lift it. Proposed fix, not yet made: the brief names its R1
  reference up front, so the tournament judges against it from round 1.
- Models: Sonnet for round 0 lens (3), sketchers (6) and the round 1 judge; Opus for builders (8), the
  round 2 judge, polishers (2), the final judge and every finish judge and fixer. About 35 sub-agent runs
  (Rise 28, battery 7), at most 4 at once, about 3.5M tokens.
- Not checked in run 2: the bad set (it passed in run 1), Strata (not re-run), Rise reduced motion by hand.
