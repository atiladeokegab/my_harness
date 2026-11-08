# The direction tournament: 30 rough lines, 8 specimens, 2 finals, one pick

Step 3 of `SKILL.md`. Agents are cheap, so the look is chosen the way a studio chooses one: many rough
directions, cut hard on pictures, the survivors finished, then polished, then judged against the best
products in the field. Three cards could only be as good as the first three ideas; thirty lines reach
the ones nobody reaches first (`principles/rough-before-finished.md`, `steal-from-many.md`). A blind
judge makes every cut; the lead never picks (their answer, 2026-11-02). Measured on Strata Lifts:
`fixtures/tournament/log.md`.

## Contents
- 1 The rounds and their budgets
- 2 What each round's packet holds
- 3 Blinding, renders and verdict files
- 4 How ties break
- 5 Overruns and a failed final
- 6 What the lead sees

## 1 The rounds and their budgets

| Round | Who, in parallel | Makes | Cut | Hackathon cap | Planning cap | Measured |
|---|---|---|---|---|---|---|
| 0 Lines | 3 strongest-model generators, one lens each | 30 one-line directions | none | 3 min | 8 min | 2:05 |
| 1 Sketches | 6 Sonnet sketchers, 5 lines each; the parent renders and blinds | 30 rough one-screen sketches | judge, 30 to 8 | 3 + 1 + 4 min | 8 + 2 + 8 min | 1:33 + 0:47 + 3:13 |
| 2 Specimens | 8 Opus builders, one each; the parent renders and blinds | 8 full specimens at 1280x633 and 390x757 | judge, 8 to 2, with three changes each | 7 + 1 + 6 min | 18 + 2 + 10 min | 5:36 + 0:13 + 4:47 |
| 3 Finals | 2 Opus polishers; the parent renders, measures (`evidence.mjs`) and blinds | the 2 specimens polished into four screens each (first, detail, a state, the action's result) | judge picks, beside the standard card | 8 + 1 + 6 min | 18 + 2 + 12 min | 5:21 + 0:28 + 5:27 |
| | **22 agent runs** (3 + 6 + 1 + 8 + 1 + 2 + 1), about 1.6M sub-agent tokens | | | **40 min**, plus about 1 min of handoff per round: **44** | **88 min** | **30:44** |

- **Lenses.** Lines 1 to 10 steal from the subject's own world (its drawings, signage, logs, materials);
  11 to 20 from other crafts that solve the same job in another medium; 21 to 30 from the best shipped
  products in and out of the field, the library refs and the lead's taste set among them. Each line blends
  three or more sources, at least one from outside the category, none supplying most of it.
- **Line shape.** `<n>. <name> — mechanism: <how the first screen does the job>; memorable: <the one
  thing>; palette: <in words>; type: <in words>; sources: <src (what is taken)>, ...`. No hex, no code.
- **Sketch.** One screen, about 70 lines of HTML, system fonts, flat colours, inline SVG for the memorable
  thing, no images or JS. Rough on purpose: the judge cuts directions, not finish. Round 1 is the only
  round where system fonts are allowed; from round 2 every page sets a real, self-hosted display face
  (the first dry run's specimens all lost a T15 to platform fonts, `fixtures/tournament/log.md`).
- **The standard card.** The parent writes it during round 1 (browser defaults, a heading, the facts in a
  table, the button): the quiet category standard every final must beat (`rubric.md` §8).
- **Planning differs only in time.** Same rounds, same agent runs, longer caps, and one return to the rough
  list when the final fails (§5). The hackathon has none: its 45 minutes are the idea hour's (lesson 26).

## 2 What each round's packet holds

Paths only; each sub-agent reads them. The **content sheet** is written once by the parent from the
surface brief: the product name, the real names and numbers, one name per thing, the one action's exact
words (saying exactly what happens), and the words for the four final screens: the first screen, a
detail, a state as the visitor meets it, and the action's result (`fixtures/tournament/content.md`). Every
sketch and specimen uses it verbatim, so only the direction differs.

| Round | Gets | Must not get | Writes |
|---|---|---|---|
| 0 generator | The surface brief, its lens, the two principles above, the intent step's seven things from the subject's world; lens 3 also the field's library refs and the lead's taste set (desktop captures) | Another generator's lines | 10 lines to `r0/lens-<a-c>.md` |
| 1 sketcher | Its 5 lines, the content sheet, the sketch rules | Anything about which lines anyone likes | `r1/<n>.html` |
| 1 judge | `judge.md` §4, round 1: the contact sheets, the refs, the surface brief, `rubric.md` §2, §3, §5 | Line text, line numbers, authors | `r1-verdict.md` |
| 2 builder | Its line, its sketch, the round-1 judge's one line on it, the content sheet, `rubric.md` §5 and §6, the field's refs, and a real display face: latin woff2 self-hosted beside the page from a pinned `@fontsource` package the way `kit/` does it (`kit/README.md`), never a platform font as the display voice (`craft-floor.md`); at 390 the figure redrawn, no text under 12px | Other directions; any motif imposed on all eight (the dry run's four converged on one) | `r2/<n>.html`, rendered twice at most |
| 2 judge | `judge.md` §4, round 2: the eight at both sizes, the refs, the brief, `rubric.md` §1 to §3, §5, §6, §8, Impeccable's `craft-floor.md` and `critique.md` (`judge.md` §2) | As round 1 | `r2-verdict.md` |
| 3 polisher | Its page and its self-hosted faces, its section of the round-2 verdict and its three changes, the content sheet, the rubric, `craft-floor.md`; preserve the direction, never redesign; four screens from the content sheet, one HTML file each in one frame; a state is drawn where the visitor meets it in plain words, never as a legend explaining the design; at 390 a figure is redrawn for the phone (fewer parts, labels beside it, not on it), never scaled down to fit, and no text goes under 12px; every number carries its source or an illustrative mark in the same viewport at both sizes, one idea per line; `evidence.mjs` over the four until every line is PASS, never by hiding content | The other finalist | `r3/<n>/screen-1..4.html`, three render passes at most |
| 3 judge | `judge.md` §4, the final: the two finals' four screens and the standard card at both sizes, each one's evidence file and focus captures, every ref, `craft-floor.md` and `critique.md` | Which final placed first in round 2 | `r3-verdict.md` |

Refs in every judge packet, per `library.md`: the intent step's captures, 3 to 5 library refs for the field,
and the lead's taste set. The judge opens every one at both sizes (the dry run's round-1 judge skipped four).

## 3 Blinding, renders and verdict files

- **Renders.** The parent renders every page with `fixtures/capture.sh <file-url> <out-prefix>`, eight at a
  time (`xargs -P 8`); round 1 at both sizes too, though its judge cuts on the desktops. In round 3 each
  finalist's screens go in as `<id>-desktop.png` (screen 1) and `<id>-s2-desktop.png` to `-s4`, and the
  parent runs `node evidence.mjs <renders>/<id> <screen urls>` for each finalist and the standard card
  (about 30 s in all); a FAIL line goes back to the polisher once, then into the packet as it stands.
- **Blinding.** `uv run --with pillow python reference/tournament-sheet.py <renders> <packet> <prefix> [per-sheet]`
  copies each capture under a shuffled neutral name (`s01`..., `p01`..., `specimen-01`...; `standard` keeps its
  name), draws contact sheets of six (Kleon's sheets laid out together), and writes the mapping beside the
  packet, never in it, and carries each id's other files (`-s2..-s4`, `-evidence.md`, `-focus-*`) along under
  the neutral name. The judge's brief names the packet directory and the refs, never the directory holding
  the map. A missing mobile capture stops the round: recapture, never a partial packet.
- **Verdict files.** Every sub-agent writes its output to the path named in its brief and replies one word;
  a text reply may not arrive. A missing or malformed verdict gets one re-run, never a second judge for
  reassurance.
- **Work space.** `$HUB_DIR/projects/{p}/direction/` (r0 to r3, the packets and maps). Only the winner, the
  runner-up and the scores go into the planning file.

## 4 How ties break

| Cut | Order | Then |
|---|---|---|
| 30 to 8 | R1 + R2, then fewer direction-level tells | Two sketches of the same direction (same layout idea, same memorable thing) count once: the better stays, the next one up takes the place. The judge names what decided each remaining tie in its `Ties:` lines |
| 8 to 2 | `rubric.md` §8: R1 + R2, then fewer tells, then the bar total | B6, then B7 + B8 |
| The pick | `rubric.md` §8, as above | B6, then the round-2 place. No one's preference breaks a tie; there is no generator pick |

## 5 Overruns and a failed final

- **A sub-agent past its cap** is stopped and its slot dropped: the cut runs on what rendered (a round of
  seven is fine). A judge past its cap gets the one re-run.
- **A final that does not beat the standard card**, or scores R1 0 with "could be any product", is
  `rebuild` for the round (`rubric.md` §8). Planning: go back to the rough list, never another CSS pass;
  round 2 again on round-1 places 9 to 16, then round 3 (about 40 min). Hackathon: polish round-2 places 3
  and 4 into four screens each and judge them (about 15 min); the approval page says the tournament ran over.

## 6 What the lead sees

On the approval-1 page, never a question: the **winner** and the **runner-up**, each at 1280x633 and
390x757, each with R1 (and the ref it names), R2, the tell count and the bar total with B6, B7 and B8; the
ranking line for each; and one line on the field (30 lines, 8 specimens, the wall-clock). The 30 lines and
the round tables sit behind a link. The direction contract (`SKILL.md` step 3) is written from the winner.
The runner-up is shown so the lead can see what the judge weighed, not to be chosen: a lead who wants it
says so as a change, like any other.
