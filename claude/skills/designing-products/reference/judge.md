# The finish check: a fresh judge on our captures

Gate G4. A fresh sub-agent with no build context looks at the screen the way the lead would, before the
lead sees any still, and returns a disposition and an ordered list of fixes. It runs Impeccable's
`impeccable-finish-reviewer` and `critique` on our two sizes and appends the rubric (`rubric.md`). A second
mode ranks the direction specimens at approval 1. The lead never picks the look; this judge stands in for
their eye, so it is calibrated on fixtures that must fail (§5).

## Contents
- 1 When it runs
- 2 The packet: what the judge gets, and what it must not get
- 3 Mode 1: the finish check
- 4 Mode 2: ranking directions
- 5 Calibration: prove it can go red
- 6 The finish loop: fix, a fresh blind re-judge, until 22 is confirmed

## 1 When it runs

At build + 60 on the first screen; on every capture that changes a screen; before any still goes to the
lead (lesson 24); at freeze minus 45 on the main path. Also at approval 1 in mode 2, once per tournament cut.

## 2 The packet

The parent (the lead agent, or the builder's session) assembles paths, then starts a **fresh** sub-agent (never a
fork: a fork carries the build conversation) with the brief in §3 or §4. Paths only; the judge reads them.

**Gets:**

| Input | Where |
|---|---|
| The captures, at our two sizes | `.impeccable/review/desktop.png` (1280x633) and `mobile.png` (390x757), and once the product has them three more screens (a detail, a state, the action's result) as `-s2` to `-s4`; a 3D product's L4 stills of the exact tag instead; the tour sheet when one exists |
| The measured evidence, same revision | `<prefix>-evidence.md` and the focus captures `<prefix>-focus-desktop.png`, `-focus-mobile.png`, from `node reference/evidence.mjs <prefix> <url> [url ...]` over every screen in the packet: one PASS or FAIL line per check (focus, reduced motion, contrast, 44px targets, console, selection, caret, scrollbar, tabular numerals, measure, tracking, text size, overlap, copy) with what it measured. It names no path, so it is blind-safe; its test, `node --test reference/evidence.test.mjs`, turns each check red on a deliberate break |
| The reference products' captures, same sizes | `$HUB_DIR/projects/<p>/refs/<name>-desktop.png`, `-mobile.png` |
| The library refs for the product's field, 3 to 5 | `$HUB_DIR/projects/hub/refs/design-library/<field>/<product>/<product>-desktop.png`, `-mobile.png`, picked by `library.md`, one line each on why it is the bar |
| The lead's taste set, always, whatever the field | the captured entries of `lead_taste` in the library's `manifest.json` (`library.md`) |
| Product truth and the guide | `PRODUCT.md`; `DESIGN.md` (or, before build + 60, the surface brief's direction contract and token frontmatter); a `.claude/skills/<p>-design/SKILL.md` where the lead's repo has one |
| The surface brief | `.impeccable/surfaces/<surface>.md` |
| Accepted findings | `.impeccable/critique/ignore.md` (read first; matches are dropped silently) |
| The detector's count for the same revision | the `make check-design` output, or the line `detector: not run` |
| Impeccable, pinned | `.claude/agents/impeccable-finish-reviewer.md`, `.claude/skills/impeccable/reference/craft-floor.md` and `critique.md` (outside a product: the same three paths under `~/.local/share/impeccable/skill-v4.8.0/`, the pinned tag cloned read-only per `tokens/check-design.md`; check `git -C ~/.local/share/impeccable/skill-v4.8.0 rev-parse HEAD` is `414603bf14c7a344edb466bb1f85690c77ce8b7d` first, and stop if not) |
| The rubric | `~/.claude/skills/designing-products/reference/rubric.md` |

**Must not get:** source code or a diff (the judge reads the screen, not the intent); the build
conversation or a builder's summary of what was fixed (a claimed fix it cannot see is unresolved); in
mode 2, which direction anyone prefers or which line, author or round place a specimen came from, or a
file name, order or caption that gives it away; the fixture key
(`fixtures/key.md`) on a calibration run.

A missing input other than a capture is named in one line above the verdict and the rest is reviewed (no
evidence file: B9 and B12 stay at most 1, `rubric.md` §6). A missing or malformed capture is
`disposition: recapture`, never a partial review.

## 3 Mode 1: the finish check

Brief for the sub-agent (fill the angle brackets; paths absolute):

```
You are the finish check for <product>'s <surface>, run fresh: you have not seen the build.
Read, in this order, and nothing else:
  1. The captures: <desktop.png> (1280x633), <mobile.png> (390x757). Look at them before any text,
     and inventory what the first screen shows in your own words. Then <evidence.md> and the focus
     captures: measured on this revision, not opinions; B9 and B12 are scored from them (rubric.md §6).
  2. The references: <refs/*-desktop.png, *-mobile.png>; then the library refs, best of the field:
     <one line each: field/product: why, and its two paths>; then the lead's taste set: <its paths>.
  3. <ignore.md>, then <PRODUCT.md>, <DESIGN.md or the surface brief>, <the guide skill if any>.
  4. <impeccable-finish-reviewer.md>, <craft-floor.md>, the "Design Specificity Verdict" and
     "Design Health Score" parts of <critique.md>, and <rubric.md>.
  5. The copy- principles listed under "Copy and voice" in <principles/index.md>: read every visible
     word against them; each failing line is a T7 tell, quoted.
Detector: <count and rule ids | not run>.
Act as impeccable-finish-reviewer: checks 0 to 6 in order, on these captures. This is a code-led build
with no approved comp: judge fidelity, TYPE, MATERIAL and GROUND against the direction contract and the
guide. Persistence: PRODUCT.md <exists | is missing>. Then critique's specificity verdict and design health
score from the captures alone (no detector run of your own, no browser).
Apply rubric.md §1 first: list the traits the guide names; they are never tells.
Return exactly: the disposition line ("disposition: <word>", rubric.md §7 decides the word); Impeccable's
five sections; then the "## Rubric verdict" block from rubric.md §7, the B table as rows
"| B1 | <0-2> | <reason> |" to B12, and five changes. R1 names the ref it is measured against and the one
difference that decides it. No praise, no summary prose.
Write the whole verdict to <path>, then reply `written`.
```

The parent reports the disposition word verbatim and may not soften it. Anything but `ship` enters the finish loop (§6): `fix`
goes back to the builder as the ordered list (each change carries its Impeccable verb; the builder runs
that playbook); `rebuild` goes to the lead agent, who re-derives the regions it names (the direction is wrong, not
the details).

## 4 Mode 2: ranking directions

At approval 1, in the direction tournament (`tournament.md`): three blind cuts, each a fresh judge. The
parent renders every page with `fixtures/capture.sh`, blinds it with `tournament-sheet.py` (shuffled
neutral names, contact sheets, the mapping kept to itself) and names a verdict file in the brief. Every
brief carries the refs per §2, which the judge opens at both sizes, and ends "Write the whole verdict to
<path>, then reply `written`." No praise, no summary prose in any round.

**Round 1, 30 rough sketches to 8.** Judge the direction, not the finish.

```
You are the direction judge for <product>, round 1. You rank, you do not design; nobody prefers any of these.
Read: the contact sheets <sheet-1..5.png> (s01 to s30, half size; full captures beside them for a closer
look); the refs <one line each, as in §2>; the surface brief <path>; rubric.md §2, §3 and §5.
These are rough: ignore polish, spacing slips and system fonts. For each sketch: R1 (finished well, would
this direction sit beside the refs?), R2 (the one thing the subject owns, or "nothing"), direction-level
tells only (a template look, a default layout, decoration standing in for the subject).
Return a table: id | R1 | R2 | tells | the thing that decides it. Then "Keep:" 8 ids, best first, by R1+R2,
then fewer tells; two sketches of the same direction count once. Then "Ties:", one line each.
```

**Round 2, 8 specimens to 2.** As the final below, on `p01..p08`, then: "Keep:" the top two, and for each,
"Changes:" the three that raise its score most, each with its Impeccable verb (`rubric.md` §7); "Ties:" as
above.

**The final, 2 polished specimens and the standard card.** The parent names them `specimen-1`,
`specimen-2` in a shuffled order and `standard`. The same brief ranks D2's trio on a calibration run (§5).

```
You are the direction judge for <product>. You rank, you do not design.
Read: the surface brief <path> (it does not say which specimen anyone prefers); the references
<refs/*>, the library refs <one line each: field/product: why, and its paths> and the lead's taste set
<its paths>, opening every one at both sizes; the specimens <specimen-1..n, standard>-desktop.png and
-mobile.png, their screens 2 to 4 (-s2 to -s4) where they have them, and each one's -evidence.md and
-focus-*.png (measured, not opinions); then rubric.md §1, §2, §3, §5, §6 and §8, and craft-floor.md.
For each specimen: R1 (naming the ref it is measured against), R2, the specificity line, its tells as T<n> lines, a bar total (/24) with B6, B7
and B8 shown. Then the ranking per rubric.md §8, best first, one line of reason each, and whether the
winner beats the standard card. No praise, no summary prose.
```

The parent applies the ranking as given; ties break per `tournament.md` §4, never on anyone's preference.
The approval-1 page shows the winner and the runner-up at both sizes with these scores (`tournament.md` §6).

## 5 Calibration: prove it can go red

A judge that passes everything is worth nothing. `fixtures/` holds four deliberately bad screens
(`bad/`), a direction trio with the category-standard card (`trio/`, a synthetic Strata feature), and our
own screens as stand-in references (`refs/`: Strata and Refinery), rendered at both sizes by
`fixtures/capture.sh`. A calibration packet also carries 3 to 5 library refs for each fixture's field,
as a real run would (`library.md`); the key names the field. What each fixture plants and what a correct judge returns is in `fixtures/key.md`,
which the judge never gets (it would be the answer sheet).

Run it like a real check: copy the captures under neutral, shuffled names (`screen-1`, `specimen-1`) into
an empty directory with `rubric.md`, this file, the three Impeccable files, the library refs (copied
under their product names, which give nothing away) and each screen's evidence file and focus captures
(`evidence.mjs` on the fixture page, renamed with the capture); start a fresh sub-agent with
the §3 brief on each bad screen and the §4 final brief on the trio; compare with the key. Re-run after any change
to `rubric.md`, this file or the Impeccable pin, and record the result in the key. The fixtures use only
our own screens and synthetic HTML, never another company's product: this skill is copied to a public repo.

## 6 The finish loop: fix, a fresh blind re-judge, until 22 is confirmed

A check that runs once leaves its own fixes unjudged, which is why skill-built screens landed at 18 to 21.
22 is the gate, not the hope. `finish-loop.py` keeps the books, so a parent agent runs it per brief:

```
uv run python reference/finish-loop.py <trail> round --mode hackathon|planning --screens <dir> --verdict <file>
uv run python reference/finish-loop.py <trail> confirm --verdict <file>
```

`<trail>` is `$HUB_DIR/projects/<p>/finish/<surface>/` (never the product repo); `<dir>` holds this round's
captures, all four screens at both sizes. The first stdout line says what happens next (exit 0 `ship`, 2
keep going, 3 stopped, 1 refused):

- Round 1 is the finish check (§3), recorded with `round`.
- `fix`: the builder applies the verdict's five changes in order (after a `rebuild`, the lead agent re-derives what
  it names), with the brief below; the parent recaptures, re-runs `evidence.mjs` and starts a **fresh**
  blind judge with the §3 brief, never the last round's judge and never told what changed, then records
  the round. A state the builder adds (an error, a stale screen) is captured and measured beside the four.
  The script refuses captures identical to the last round's: a re-judge cannot buy a score without the
  screens changing, so a `rebuild` never becomes a `ship` on the same pixels.
- `confirm`: one judge returned `ship` at 22 or more with B7 and B8 at 2. A second fresh blind judge scores
  the same captures; record it with `confirm`.
- `ship`: the median of the two totals is 22 or more, both judges gave 21 or more, B7 and B8 are 2 from
  both, and neither returned `rebuild`. One lucky judge cannot pass it.
- `stop plateau` (two rounds in a row gained under 1 point) or `stop cap` (3 rounds in a hackathon, 5 in
  planning): stop. Report the score, each missing point by B and why.

The builder's brief (fresh, not blind: it reads code and verdicts):

```
Apply the latest verdict's five changes to <product>'s screens, in order, then fix its T lines. Preserve the
direction; never redesign. A T line is a class, not a quote: clear every instance on all eight captures
(every number with its source or an illustrative mark in the same viewport at both sizes, one idea per line,
a state named by what happened), or the next judge finds the ones not quoted. Read every earlier verdict in <trail>/ too and keep what they scored 2: a fix
that costs another B is a regression (the proof run lost B1 to new type sizes and B7 to a button pushed
below the 390 fold). Word changes go into PRODUCT.md or the content sheet the judge reads, never only into
the page. evidence.mjs over every screen until all PASS; look at every capture at both sizes. Write what
you did per change to <path>, then reply `written`.
```

The lead sees the final screens and `trail.md` (every round's score per B, its gain, the outcome), never a
choice between rounds. G3 checks the trail exists. On 3D or WebGL products every round judges L4 GPU
stills of the exact build (`3d-model-workflow` §8), never software-GL captures; the stills are the
`<dir>`. A round costs the fix (3 to 5 min), capture and evidence (under 1 min) and a judge (about 5 min);
the confirmation adds one judge. It runs in the build window, not the tournament's 45 minutes. Tests:
`uv run python reference/finish-loop.test.py`, each rule shown red on a deliberate break.
Proved once on the tournament winner (`fixtures/tournament/finish-loop/`, its log in `tournament/log.md`):
17, 22, 21 out of 24, `fix` every round with R1 1 against Felt, stopped at the hackathon cap.
