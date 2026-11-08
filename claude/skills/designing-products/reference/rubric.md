# The UI rubric: does not look AI-made

The bar the finish check (`judge.md`) appends to Impeccable's own review, and the scale the direction
judge ranks specimens on. The counterpart of the launch-film standard's section K: the judge reads as
someone who has seen a hundred AI-made UIs, and each tell below fails the screen it appears on.

## Contents
- 1 The first rule: a trait the guide names is never a tell
- 2 R1 and R2: against the reference products, first
- 3 The specificity line
- 4 Scope after Impeccable: what the detector owns
- 5 The tells, T1 to T15 (each with its detector rule and what passes)
- 6 The bar, B1 to B12
- 7 Scoring, the disposition and the verdict format
- 8 Ranking directions
- 9 Sources and licences

## 1 The first rule: a trait the guide names is never a tell

A trait is a tell only when nobody chose it. The brand guide (`DESIGN.md`, the surface brief's direction
contract, or a `<p>-design` skill) names its direction and the reason; a direction the guide names and the
lead signed is never a tell, however common. Refinery's dark ground with one green accent is trait 2 in
Anthropic's calibration list and is still Refinery's brand. A trait the guide does not name is a default,
and is judged as one. Impeccable draws the same line ("the brief wins"; the craft floor's Refuse list is
defaults the brief can earn back) and keeps a few absolute bans no brief earns back; ours are marked
**ban** below.

Before counting tells, list in one line the traits the guide names (`chosen: dark ground, one green
accent, ...`), so a reader can see the rule was applied. A trait the guide names but the screen executes
badly (the accent spent on everything, not on the one action) is a bar finding (B3, B4), not a tell.

## 2 R1 and R2: against the reference products, first

The judge scores against real products, not only the tell list: the bar carries the weight the lead's eye
would have. The intent step names two or three reference products, the best real ones in the subject's
world, and captures their first screen at 1280x633 and 390x757 into `$HUB_DIR/projects/<p>/refs/` (never the
product repo, never this skill: they are other people's work). The judge gets those captures beside the
candidates and answers, before anything else:

| | Question | 0 | 1 | 2 |
|---|---|---|---|---|
| R1 | Would this sit beside the references without reading as the cheaper one? | no | close | yes |
| R2 | What does it have that none of the references has? Name one thing. | nothing | a thing a reference also has, or decoration | one named thing the subject owns |

A screen or a direction passes only with R1 at 2 and R2 at 2. The references are not copied: a candidate
that reads as one of them scores 0 on R2.

Upstream, a direction earns R2 through `make-what-the-references-miss`, `steal-from-many` and `steal-the-thinking` (principles/).

## 3 The specificity line

The verdict opens with Impeccable's critique question, in one line, before any tell is counted: does this
screen feel authored for this product, or could an unrelated product use it unchanged?

## 4 Scope after Impeccable: what the detector owns

Impeccable's craft floor and detector are the first tier and are not restated here. When the packet
carries `impeccable detect` output for the same revision, a tell its detector caught is reported by rule
id from that output and is not re-judged by eye (agree, or call it a false positive in one line). When
no detector ran (captures only, L4 stills, a calibration run), the eye reports the tell and names the
rule that would catch it, so the parent can confirm with `make check-design`. A tell with "eye" in the
detector column has no rule; only the eye catches it.

This file keeps what Impeccable does not cover: the lead's words (T7), the film standard's section K,
our two sizes and the tour (T14), and the bar (B1 to B12).

## 5 The tells

Each fails the screen it appears on. Write it as `T<n> <screen> <size> <where> <what>`.
"Anthropic trait n" is the numbered calibration list in Anthropic's `frontend-design` skill (1 cream and
terracotta; 2 near-black with one acid-green or vermilion accent; 3 broadsheet hairlines, zero radius,
dense columns; 4 the SaaS-card kit; 5 template chrome). Detector rules are Impeccable 4.8.0's ids.

| # | Tell | Detector rule | What passes | Source |
|---|---|---|---|---|
| T1 | A multi-stop or purple-blue gradient as decoration; gradient text; gradient washes behind cards | `gradient-text`, `ai-color-palette`, `radial-halo`, `radial-spotlight-glow` | A flat ground; emphasis from weight or size; a gradient only where it carries data (a depth ramp, a heat scale) | the lead; Anthropic trait 4; K59 |
| T2 | Glass or blur on cards, noise or grain overlays, glow borders, layered glows | `dark-glow`, `radial-halo`; glass and grain: eye | Elevation declared once, by a border or an offset soft shadow; a blur only where it shows a real layer (a sheet over a live map) | the lead; refinery-design "retire" |
| T3 | Emoji as icons; robot, brain, sparkle or "AI" icons; stock AI imagery; particle swirls, glowing grids | `shape-assembled-illustration`, `codex-grid-background`; emoji and AI icons: eye | One drawn icon set at one stroke weight; the real product or the real subject as the picture | the lead; K59 |
| T4 | A centred hero and three equal cards (icon, title, blurb); the SaaS card kit: identical rounded cards, one radius whatever the hierarchy, the same soft grey shadow under each | `icon-tile-stack`, `gpt-thin-border-wide-shadow`; the grid itself: eye | Content in the shape it has: a list, a table, a figure, one dominant item; cards only where items are truly peers and interactive | the lead; Anthropic trait 4 |
| T5 | One family at one weight with no scale; one accented word in a headline; tracked ALL-CAPS eyebrows above every heading; a monospace face for small data labels by default; "a big number, a small label, a gradient accent" as the hero | `flat-type-hierarchy`, `kicker-above-heading`, `hero-eyebrow-chip`, `wide-tracking`; accented word, mono labels, hero metric: eye | A visible scale with real weight steps; the heading carries itself; mono only for code, data or measurement; a big number only when that number is the job | the lead; Anthropic typography and trait 5; `type-fit` |
| T6 | rounded-2xl on every box; one radius regardless of hierarchy | `design-system-radius` (with a `DESIGN.md`); else eye | A radius family: small controls tighter, containers per the guide, the page itself square | the lead |
| T7 | Filler copy: revolutionize, seamless, unlock, game-changer, harness the power, elevate, supercharge, effortlessly, in today's fast-paced world, powerful, runs of three adjectives; invented stats with no source | `marketing-buzzword`, `aphoristic-cadence`, `theater-slop-phrase`, `em-dash-overuse` (advisory); `check-copy.mjs` in the smoke (`copy-banned.txt`, unsourced % and multiples); runs of adjectives: eye | Plain verbs that say what the product does to what; every number with its source or marked illustrative (`copy-no-hype-or-hedge`, `copy-numbers-with-a-source`) | K63; the lead; demo-bar rule 1 |
| T8 | Calibration palettes and chrome nobody chose: cream #F4F1EA with a serif and terracotta #D97757; a broadsheet of hairlines, zero radius and dense columns; tinted near-black (#0B0B0B, #111) standing in for black; meta strings joined with middle dots; "WORD — fragment" labels; a "→" appended to every link or button | `cream-palette`; the rest: eye | A palette with a reason in the guide; meta as a sentence or a real table; an arrow only where the link leaves the page | Anthropic traits 1, 3, 5 |
| T9 | Fade-and-slide-up on every section, hover lift on every card, motion with no reason; more than one move per view. In a still: sections caught at different opacities or offsets, a marquee, a pulse on a dot that is not live | `content-hidden-at-rest`, `bounce-easing`, `pulsing-dot`, `marquee`, `blinking-cursor` | One authored moment per view, from an already-visible default; motion that answers the visitor's action | Anthropic (motion); K60 |
| T10 | Numbered 01 / 02 / 03 markers where the content is not a sequence | `numbered-section-labels` | Numbers only on real steps or a timeline | Anthropic |
| T11 | Placeholder content: lorem, John Doe, "No data" as an empty state, a heading with nothing under it (Strata's empty panel) | `broken-image`; the rest: eye | Real names and data, or labelled illustrative; an empty state that says what to do next | Anthropic (writing); Strata |
| T12 | A component library's defaults unmodified (its radius, its blue, its shadow); the browser focus ring removed and not replaced | `design-system-color` (with a `DESIGN.md`); the focus ring: eye (B9) | The library themed from the guide's tokens; a focus ring in the palette | the lead (modern finish) |
| T13 | A stat-tile dashboard for a product that is not a dashboard; dark mode with no reason in the guide | eye | Light or dark picked from the use scene and named in the guide | Anthropic trait 2 (when unchosen); `colour-roles` |
| T14 | At 390x757: horizontal scroll, body text under 14px, tap targets under 44px, a card or sheet covering the subject, a ring clipped at the edge, two labels overlapping | `text-overflow`, `first-viewport-column-overflow`, `clipped-overflow-container`, `tiny-text`, `undersized-ui-text`, `text-occlusion`, `body-text-viewport-edge` (when `detect` ran at 390 wide); tap targets and covering: eye | The phone layout designed, not shrunk: one column, 16px body, 44px targets, the subject in a clear band; a figure redrawn for 390 (fewer parts, labels moved off it), no label under 12px | Strata's failures |
| T15 | Cards nested in cards (**ban**); a kicker or eyebrow label above a heading (**ban**); a coloured side stripe over 1px on cards, callouts or alerts; a hard offset block shadow outside a world that chose it; grey text on a coloured surface; a 1px border under a wide soft shadow; light or dark picked by category rather than the use scene | `nested-cards`, `kicker-above-heading`, `hero-eyebrow-chip`, `side-tab`, `border-accent-on-rounded`, `hard-offset-shadow`, `gray-on-color`, `gpt-thin-border-wide-shadow`; theme by category: eye | Hierarchy from spacing, type and one divider; a status shown by an icon and a word, not a stripe; secondary text tinted from the surface's hue | Impeccable craft floor and detector |

## 6 The bar (0 none, 1 partly, 2 fully; pass at 20 of 24 with B7 and B8 at 2)

| # | The bar |
|---|---|
| B1 | A type scale: at most six sizes, at most two families clearly distinct, a hierarchy still visible in a greyscale screenshot; line lengths under 80 characters (`type-scale`) |
| B2 | One spacing scale, at most ten steps, everything on it |
| B3 | One accent, spent on the one thing that matters on each screen (the action, the live state) (`colour-harmony`, `colour-roles`) |
| B4 | Restraint: at most two effects in the product, one radius family, one shadow; "remove one accessory" has been done |
| B5 | Real content: real data, real names, real numbers with their source; empty, loading and error states designed as direction |
| B6 | One detail only this subject has, and boldness spent there once |
| B7 | The first screen says what it is in one line and has one big button that runs the main workflow end to end (lesson 20; `flow`) |
| B8 | Holds at 1280x633 and 390x757: no overlap, no clipping, nothing covers the subject; a figure redrawn for the phone, not shrunk. 2 only when the evidence file's text-size line reads PASS (no text under 12px at either size) |
| B9 | Quality floor: visible focus, reduced motion respected, body contrast 4.5:1 or better, tap targets 44px or more, no console errors (`colour-roles`). Scored on the evidence file: 2 only when its focus, reduced-motion, contrast, targets and console lines all read PASS and the focus capture shows the ring |
| B10 | Vocabulary: one name per thing across the UI, README and film; each CTA says exactly what happens; sentence case |
| B11 | Contact-sheet test: eight screenshots (four screens at two sizes: the first screen, a detail, a state, the action's result) read as one product by one team, not a template (`consistency`) |
| B12 | The parts nobody drew still carry the design: text selection, caret, scrollbars, focus rings, underline offset, tabular numerals in data; body measure 65 to 75 characters; tracking no tighter than -0.04em (Impeccable's craft floor). Scored on the evidence file: 2 only when its selection, caret, scrollbar, tabular, measure and tracking lines all read PASS and the captures show nothing against them |

What a still cannot show is measured, never taken on faith. B9, B12, B8's text size and the mechanical part of T7 come from the packet's evidence
file (`judge.md` §2, made by `evidence.mjs` on the same revision): a FAIL line caps its B at 1 and is named
in the reason; with no evidence file both are at most 1, marked `(no evidence)`. The judge never re-measures
and never overrules a PASS by eye, except where a capture plainly contradicts it (name the capture). B11
needs four screens at two sizes; with fewer it is at most 1, marked `(from captures only)`. B10 reads every
word in the packet; at approval 1, before any README or film exists, that is the screens, and from the
finish check on it is the screens, the README and the film.

## 7 Scoring, the disposition and the verdict format

The finish check is Impeccable's `impeccable-finish-reviewer` run by a fresh sub-agent on our captures
(`.impeccable/review/desktop.png` at 1280x633, `mobile.png` at 390x757; on 3D work the L4 stills of the
exact tag), with `critique`'s specificity verdict and design health score on the same revision.
`judge.md` says how. It returns Impeccable's disposition line and five sections, then ours appended:

```
## Rubric verdict
R1 <0|1|2>: <one line against the named references>
R2 <0|1|2>: <the one thing, or "nothing">
Specificity: <authored for this product | could be any product>: <one line>
Chosen: <the traits the guide names, or "no guide">
T<n> <screen> <size> <where> <what> [rule id | eye]
...
| B | Score | Reason |   (B1 to B12, one line each; total /24)
Changes:
1. <verb>: <the change>      (bolder, quieter, distill, typeset, layout, colorize, clarify, adapt, harden, onboard, polish)
2. ...
...
5. ...                         (five, highest gain first; fewer only when fewer remain)
Detector: <count from detect on this revision | not run>
```

The five changes are the ones that raise the score most, in that order (the finish loop applies them,
`judge.md` §6), each named with the Impeccable verb whose playbook makes it. Findings the lead has
accepted live in the committed `.impeccable/critique/ignore.md`, which the judge reads first and drops
silently, so a verdict never re-reports a decision.

**The disposition** stays Impeccable's four words, derived, never felt. Ours tighten it:

| Word | When |
|---|---|
| `recapture` | A capture is missing, blank, the wrong size or the wrong screen (Impeccable's check 0) |
| `rebuild` | Impeccable's rebuild condition fired; or R1 is 0 and the specificity line says any product could use it (the direction itself is the default) |
| `fix` | Any tell, any material fix, any FAIL line in the evidence file, a bar total under 22, B7 or B8 under 2, R1 under 2 or R2 under 2 |
| `ship` | None of the above. In the finish loop one judge's `ship` is not enough: a second blind judge confirms it (`judge.md` §6) |

## 8 Ranking directions

At approval 1 the judge ranks direction specimens, blind to where each came from: the cuts of the
direction tournament (`tournament.md`), and in the final the two finalists and the category-standard card. Each gets R1, R2, the specificity line, its tells and a bar total. Rank by R1 + R2
(higher first), then by the number of tells (fewer first), then by the bar total. The winning direction
must rank above the standard card; when none does, the verdict is `rebuild` for the direction round. The
judge reports the ranking; ties break per `tournament.md` §4, never on anyone's preference.

## 9 Sources and licences

- Anthropic, `frontend-design` skill (`anthropics/skills`, `skills/frontend-design/SKILL.md`), Apache 2.0:
  the five calibration traits are cited by number and paraphrased; "the brief's own words always win" is
  quoted.
- Paul Bakaus, Impeccable 4.8.0 (github.com/pbakaus/impeccable), Apache 2.0 with a `NOTICE.md`: detector
  rule ids used as identifiers; the craft floor's bans, browser surfaces, measure and tracking floor
  paraphrased in T15 and B12; the critique's specificity question; the verb vocabulary; the four-word
  disposition.
- The hub: the lead's words, the launch-film standard section K (K59, K60, K63), the hackathon lessons and
  Strata's tour failures.
