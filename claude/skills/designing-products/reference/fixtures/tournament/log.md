# Dry run: the direction tournament on Strata Lifts (T-1013, 2026-11-02)

The tournament in `../../tournament.md`, run once end to end on the trio's surface brief (`../trio/brief.md`),
to measure its wall-clock and whether it beats D2's trio winner (`a`, 17/24) on the same judge. Every
judge was a fresh sub-agent on Opus 5.5 and saw only neutral shuffled names. Library refs: `maps-geo-3d`
Citymapper, Felt, Cesium and OpenStreetMap, the lead's taste set (Linear, Stripe) and the stand-in refs.

## Result

| | Bar | R1 | R2 | Tells | Ranked |
|---|---|---|---|---|---|
| **Winner**: line 1, Elevation Sheet (one screen; replaced by `finals/winner/`, below) | **20/24** (B6 2, B7 2, B8 2) | 1 vs Felt | 2 | 0 | 1st |
| Runner-up: line 20, Pilot's Chart Table (one screen; replaced by `finals/runner-up/`) | 18/24 (B6 1, B7 2, B8 2) | 1 vs Felt | 2 | 1 (T8 cream and italic serif) | 2nd |
| Control: D2's trio `a`, in the same packet | 16/24 (B6 1, B7 2, B8 2) | 0 vs Felt | 2 | 1 (T14 7px labels at 390) | 3rd |
| The standard card | 12/24 (B6 0, B7 1, B8 2) | 0 | 0 | 2 | 4th |

**Against the target:** 20 against D2's 17 is +3, the target met exactly. The final round ran
`judge.md` §4's final brief with `a` added as a control, so one judge scored both on one run: +4. That brief
has scored `a` 17, 18 and 18 in the three earlier calibration runs, 16 here and 18 in this task's
calibration re-run, so a run moves by up to two points and the margin over `a` is +2 to +4 across runs.

**Re-run with Impeccable's files (2026-11-02, after the lead's check).** The final above ran without
`craft-floor.md` and `critique.md` (not on the VM then). The pinned tag is now cloned read-only at
`~/.local/share/impeccable/skill-v4.8.0/` (HEAD `414603bf`, verified), and the same blind packet was
judged once more by a fresh judge with both files:

| | First final (rubric §6 for the floor) | Re-run with craft-floor.md and critique.md | Round 3 again with real faces, full packet |
|---|---|---|---|
| Winner, line 1 | 20/24, R1 1, 0 tells | **19/24**, R1 2 vs Felt, 3 tells (T8 hairline broadsheet frame; T15 platform sans as the display voice; T15 a borderline "Next lift" kicker) | **19/24**, R1 2, 1 tell (T8 the state legend in designer words) |
| Runner-up, line 20 | 18/24, 1 tell | 18/24, 2 tells (T8 cream and italic serif; T15 platform sans) | 18/24, 1 tell (T5 tracked caps masthead stacking as an eyebrow at 390) |
| Control, trio `a` | 16/24 | 15/24, 3 tells (T15 platform serif, T14 7px labels, T11 harness copy) | 16/24, 1 tell (T14 6px labels) |
| Standard | 12/24 | 9/24 | 10/24 |

Same order, same pick. Against the target the re-run gives 19 against D2's 17, **+2, one short of +3**,
and +4 over `a` in the same packet. Why: the craft floor refuses a platform font as a page's display voice,
and every specimen here is system fonts by the tournament's own rule (no web fonts in a packet rendered
offline). That costs every entry a T15 and B12, the winner included; it is the round-2 brief's limit, not the
direction's. A real run names the product's faces in the content sheet so builders can set them.

**The font fix, proved on round 3 (T-1013).** `tournament.md` now allows system fonts in round-1 sketches
only; round 2 sets a real display face, self-hosted latin woff2 from a pinned `@fontsource` package, and
rounds 2 and 3 judge with `craft-floor.md` and `critique.md`. Round 3 re-ran on the same two finals: both
polishers set faces from `kit/`'s pinned set (the winner IBM Plex Sans 5.3.0; the runner-up Jost over
IBM Plex Sans, on a chart-white ground with upright labels), then one fresh judge with the full packet. The
platform-font T15 is gone from both and the winner's tells fell from 3 to 1, but its bar stayed **19/24**:
the face moved B1 and B12 nowhere they were not already, and what holds it under 20 is B5 and B10, the
state legend written in designer words (lesson 4 above, which the polisher was not asked to fix here), plus
B9, B11 and B12 at 1 from captures only. So 19 against D2's 17 is +2, still one short of +3, and +3 over trio
`a` in the same packet. Removing the legend for in-place states is the next point; no further run was made.

**Not a ship.** The winner's disposition is still `fix`: R1 is 1 (beside Felt the system sans and the
hairline frame read plainer) and B9, B11 and B12 are scored 1 from captures only, which no single still can
lift. A one-screen specimen's practical ceiling is about 21. The tournament picks the direction; the
finish check at build + 60 finishes it.

## The follow-up: the method fixed for 24/24 (T-1013 follow-up, 2026-11-02)

The lead asked how 19 becomes 24 by fixing the method, not the judge. Three changes, then the same blind
final packet (winner, runner-up, the standard card, trio `a` as control, every ref, `craft-floor.md`,
`critique.md`) judged by fresh Opus 5.5 judges:

1. **States in place, not a legend (B5, B10).** `content.md` is the content sheet for four screens, with one
   name per thing (lift, ship, road closed) and every state worded as the visitor meets it ("not confirmed
   yet" in its row, "Times checked 14:02"). The CTA says what happens: "Notify me 15 minutes before it lifts".
2. **Measured evidence (B9, B12).** `../../evidence.mjs` measures each screen at both sizes (focus ring with
   a capture, reduced motion, contrast, 44x44 targets, console, `::selection`, caret, scrollbar, tabular
   numerals, measure, tracking); `../../evidence.test.mjs` shows each check going red on its own break of
   `../evidence/good.html`. The rubric scores B9 and B12 at 2 only on PASS lines.
3. **Four screens (B11).** Round 3 polishers build the first screen, one lift's detail, the end-of-day
   state and the notification set, from the one content sheet. Finals: `finals/winner/`, `finals/runner-up/`,
   each with its four screens at two sizes, `evidence.md` and the focus captures; faces in `finals/fonts/`.

| | Run 1 (fresh judge) | Run 2 (the same judge's Verdict Pass after its own fixes, `judge.md` §3) |
|---|---|---|
| **Winner**, line 1 | **23/24**, R1 2 vs Cesium and Citymapper, R2 2, 1 tell (T14 chain stubs cut at 390 on s2 and s3) | **23/24**, R1 2, R2 2, 1 tell (T14 "61 m clearance when open" about 9px at 390) |
| Runner-up, line 20 | 20/24 (B2, B4, B6, B8 at 1), R1 1 vs Felt, 1 tell | 23/24 (B6 1), R1 1 vs Felt, 0 tells |
| Control, trio `a` | 16/24 (evidence FAIL caret, scrollbar, tabular), 1 tell | 16/24 |
| Standard | 10/24, 2 tells | 10/24, 2 tells (T14 72x21 target, measured) |

Winner per B, run 2: B1 2, B2 2, B3 2, B4 2, B5 2, B6 2, B7 2, **B8 1**, B9 2, B10 2, B11 2, B12 2. B5,
B9, B10, B11 and B12 all moved to 2. **The missing point is B8**: run 1 docked it for the side-span chains
cut at the 390 frame and an orphaned "lifts" in the button; the fix scaled the whole elevation into the
phone frame, which cleared both but shrank its clearance label to about 9px (T14). The phone needs the
figure redrawn for 390, not shrunk. Disposition `fix`, the evidence file has no FAIL line. Two final runs
was the cap, so no third. Ranking unchanged; the winner beats the standard 4 to 0 on R1+R2.

**Calibration with the evidence step** (`../key.md`): the bad set all `rebuild`, each with its tells and the
evidence FAIL lines in B9 and B12 (bars 5, 6, 6 and 7 out of 24). The step did not soften the judge.

**Cost.** Round 3 now takes about 11:46 (polish 5:21, render and evidence 0:28, judge 5:27, blinding the
rest), against 6:53 before; the tournament measures **30:44** in all, about 1.6M tokens, and its hackathon
caps total 40 min (44 with handoffs), inside the 45-minute cap. The fix loop is not in that budget: 3:18
for the slower polisher, 0:30 to re-render and measure, 2:05 for the Verdict Pass.

**A blinding leak, found and closed.** `tournament-sheet.py` writes the name map beside the packet; this
run's first judge was briefed with the directory that held both (it said it did not open the map). The map
was moved before the Verdict Pass, and `tournament.md` now says the judge is never given the map's directory.

## The finish loop, proved on the winner (T-1013 follow-up 2, 2026-11-02)

`judge.md` §6: the finish check, the builder applies the verdict's five changes, a fresh blind §3 judge,
repeated until `ship` at 22 or more confirmed by a second judge, a plateau, or the cap (3 rounds in a
hackathon). `finish-loop.py` kept the books; `finish-loop/trail.md` is the trail and `finish-loop/` holds the
last round's screens and two states. Run on the winner's four screens in hackathon mode:

| Round | Disposition | R1 | Bar | Gain | Lost points |
|---|---|---|---|---|---|
| 1, the finish check | `fix` | 1 vs Felt | 17/24 | | B1 eight sizes, B2, B3 red on a bare arc, B4 the frame, B5, B10 "clearance" two ways, B11 |
| 2 | `fix` | 1 vs Felt | **22/24** | +5 | B5 no error or stale state, B10 "All lifts today" vs "Later today" |
| 3 | `fix` | 1 vs Felt | 21/24 | -1 | B1 seven sizes again, B5 unsourced dimensions, B7 the button below the 390 fold |

**Stopped at the cap, not shipped.** Two things held it:

1. R1 stayed 1. Every finish-check judge measured the elevation against Felt's finished picture, and `fix`
   needs R1 2. Polish moved R1 nowhere in three rounds, and the direction is what decides it. The
   tournament's final judge gave the same direction R1 2 against Cesium, so which ref a judge picks
   swings R1.
2. Fixes regressed. Round 2's builder saw only round 2's verdict. Adding the two states and the mast drawing
   brought back the type sizes round 1 had cut (B1), and pushed the button below the 390 fold (B7). Each
   fresh judge also finds new copy tells (round 3's unsourced numbers). §6's builder brief now hands over
   every earlier verdict and calls a lost 2 a regression.

Read on its own, the winner scored 17 at a one-shot finish check, where the tournament's comparative
final gave it 23. One loop round lifted it to 22.

**Calibration, re-run with the 22 bar and five changes** (`../key.md`): the bad set all `rebuild`, each
with its tells, at 5, 7, 5 and 7 out of 24. Fed through `finish-loop.py`, each of the four printed
`next: fix`. A lucky all-2 `ship` verdict on the same captures was refused ("screens unchanged"), so a
`rebuild` cannot become a `ship` without the screens changing.

**Cost.** Three judges at 5:43, 5:51 and 5:54; two builders at 6:07 and 9:02; about 0:30 to recapture and
measure each round. Round 1 to the stop took 36 minutes, about 660k tokens. A ship round adds one
confirmation judge, about 6 minutes. In a hackathon the loop runs in the build window, so it needs its 36
to 45 minutes planned there.

## Wall-clock

| Round | Started (UTC) | Ended | Took | Agent runs |
|---|---|---|---|---|
| 0 Lines: three Fable generators in parallel | 11:32:56 | 11:35:01 | 2:05 | 3 |
| 1 Sketches: six Sonnet sketchers in parallel, five each | 11:35:15 | 11:36:48 | 1:33 | 6 |
| 1 Render 60 captures (`capture.sh`, eight at a time) and blind | 11:36:48 | 11:37:35 | 0:47 | |
| 1 Cut judge, 30 to 8 | 11:37:35 | 11:40:48 | 3:13 | 1 |
| 2 Specimens: eight Opus builders in parallel | 11:40:57 | 11:46:33 | 5:36 | 8 |
| 2 Re-render and blind | 11:46:33 | 11:46:46 | 0:13 | |
| 2 Cut judge, 8 to 2 | 11:46:46 | 11:51:33 | 4:47 | 1 |
| 3 Polish: two Opus polishers in parallel | 11:51:42 | 11:55:09 | 3:27 | 2 |
| 3 Final judge | 11:55:21 | 11:58:47 | 3:26 | 1 |
| **Total** | | | **25:51** | **22** |

Sub-agent tokens, from the run's usage lines: about 1.5 million (generators and sketchers about 57k each,
builders and polishers 65k to 81k, judges 86k to 108k). The cut judge's 3:13 includes one re-ask: its text
reply never arrived, so it was asked to write the verdict to a file (every judge brief now says so).

## Round 1: the 30 sketches, scored blind on contact sheets

| Line | Name | Blind id | R1 | R2 | Tells | Kept |
|---|---|---|---|---|---|---|
| 1 | Elevation Sheet | s20 | 2 | 2 | 0 | 1 |
| 2 | Engine Room Gauge | s08 | 1 | 1 | 1 | |
| 3 | PLA Notice Board | s26 | 1 | 2 | 1 | 8 |
| 4 | River Signal Lights | s28 | 0 | 2 | 1 | |
| 5 | Tide Ladder | s24 | 1 | 1 | 0 | |
| 6 | Counterweight Section | s01 | 1 | 2 | 0 | 4 |
| 7 | Lift Log Ledger | s11 | 1 | 1 | 1 | |
| 8 | Ship Flag Hoist | s30 | 1 | 2 | 0 | 6 |
| 9 | Paint Schedule Panel | s09 | 1 | 1 | 0 | |
| 10 | Mariner's Approach | s18 | 0 | 1 | 1 | |
| 11 | Split-flap Lift Board | s05 | 0 | 1 | 1 | |
| 12 | Tide Table Page | s03 | 1 | 1 | 0 | |
| 13 | Dot-matrix Platform Sign | s14 | 1 | 1 | 1 | |
| 14 | Station Clock Face | s23 | 1 | 1 | 0 | |
| 15 | FIDS Arrivals Wall | s02 | 1 | 1 | 1 | |
| 16 | Field Notebook Spread | s16 | 0 | 1 | 1 | |
| 17 | Wayfinding Totem | s27 | 0 | 1 | 1 | |
| 18 | Concert Poster Lift | s06 | 1 | 1 | 0 | |
| 19 | Sports Countdown Scoreboard | s12 | 0 | 1 | 1 | |
| 20 | Pilot's Chart Table | s19 | 1 | 2 | 0 | 5 |
| 21 | Bascule Tide Clock | s04 | 1 | 1 | 0 | |
| 22 | Engine Room Gauge | s15 | 1 | 1 | 1 | |
| 23 | River Timetable Board | s29 | 1 | 0 | 1 | |
| 24 | Weather For Bridges | s07 | 0 | 0 | 1 | |
| 25 | Pier Notice | s10 | 1 | 1 | 0 | |
| 26 | Control Cabin View | s22 | 1 | 2 | 0 | 3 |
| 27 | Riverbank Timeline | s13 | 1 | 1 | 0 | |
| 28 | Bascule Angle Poster | s17 | 2 | 2 | 1 | 2 |
| 29 | Tide Ledger | s21 | 0 | 0 | 1 | |
| 30 | Ship Passing Card | s25 | 1 | 2 | 1 | 7 |

The judge counted the three departure boards (lines 13, 15, 23), the three dials (2, 14, 22) and the
two notices (3, 25) as one direction each, as the brief asks. Every lens placed: lines 1 to 10 (the subject's world) four of the eight, 11 to 20 (other
crafts) one, the runner-up, and 21 to 30 (the best products) three.

## Round 2: the eight specimens (`specimens/line-NN.html`), scored blind at both sizes

| Line | Blind id | R1 | R2 | Tells | Bar | Place |
|---|---|---|---|---|---|---|
| 1 Elevation Sheet | p04 | 2 vs Linear | 2 | 0 | 19 | 1, kept |
| 20 Pilot's Chart Table | p08 | 2 vs Felt | 2 | 0 | 18 | 2, kept |
| 6 Counterweight Section | p01 | 1 vs Felt | 2 | 0 | 18 | 3 (tie with 28, broken on the judge's line) |
| 28 Bascule Angle Poster | p03 | 1 vs Cesium | 2 | 0 | 18 | 3 |
| 26 Control Cabin View | p07 | 1 vs Linear | 2 | 1 | 17 | 5 |
| 8 Ship Flag Hoist | p02 | 1 vs Citymapper | 1 | 0 | 18 | 6 |
| 30 Ship Passing Card | p05 | 1 vs Stripe | 1 | 0 | 17 | 7 |
| 3 PLA Notice Board | p06 | 1 vs Citymapper | 1 | 1 | 17 | 8 |

The changes it handed the polishers: line 1, clarify (one verb, "lifts"), harden (empty, unconfirmed and
loading states), layout (next lift and the button first in the right column); line 20, bolder (bascules at
86° on the map, not an inset), polish (labels off the bank line), harden (states, casing).

## What the dry run changed in the method

1. **Do not hand every builder the same motif.** The round-2 brief told all eight to draw the bascules
   correctly and boldest; four of the eight converged on one elevation. `tournament.md` now has each builder
   keep its own line's memorable thing.
2. **Open every ref.** The round-1 judge skipped four of the eight refs and said so; the brief now requires
   every ref opened.
3. **Verdicts go to a file.** Sub-agent text replies did not arrive in this harness; every builder and judge
   writes to a named path.
4. **States as the visitor sees them.** Asked to design states, the winner's polisher drew a legend that
   explains the design ("Rows draw as phantom lines"), which cost B10. The polish brief now says a state is
   shown as the visitor would meet it, never as a legend.
