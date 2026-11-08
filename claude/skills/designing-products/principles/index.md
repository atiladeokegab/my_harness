# UX principles: index

Pull one principle at a time: open the file for the flow step you are on. Each file gives the principle
in one line, why it holds, what to check on a screen, a pass or fail test for a desktop (1280x633) and
a phone (390x757) capture, and the step that uses it.

| Principle | File | Step |
|---|---|---|
| A first-time user understands the screen without thinking | self-evident.md | critique |
| Build for people who scan, satisfice and muddle through | design-for-scanning.md | UX |
| Prominence matches importance; grouping and nesting are visible | visual-hierarchy.md | critique |
| Use the conventions people already know | use-conventions.md | UX |
| It is obvious what can be clicked or tapped | obvious-clickables.md | critique |
| A few clearly bounded areas, with noise kept down | clear-areas-low-noise.md | critique |
| Every choice is mindless and unambiguous | mindless-choices.md | UX |
| Cut happy talk and instructions, then cut again | omit-needless-words.md | critique |
| Any deep screen passes the trunk test | trunk-test.md | critique |
| A screen's title matches the control that opened it | names-match-the-click.md | tour |
| The first screen says what this is and why it is better | first-screen-says-what-it-is.md | intent |
| The first screen shows where to start | show-where-to-start.md | UX |
| Protect the visitor's reservoir of goodwill | goodwill-reservoir.md | UX |
| Forms ask only what this transaction needs | forms-ask-less.md | UX |
| Accessibility basics: fix confusion first, never colour alone | accessibility-basics.md | critique |
| Settle questions by a fresh judge, not a debate | get-it-test.md | critique |

Source: Steve Krug, *Don't Make Me Think! A Common Sense Approach to Web Usability*, 2nd edition (New
Riders, 2006), paraphrased in our own words with chapter citations. That edition has no mobile chapter,
so the phone tests and every threshold marked "our threshold" or "our adaptation" are ours, not Krug's.

## Creative process principles (Steal Like an Artist)

| Principle | File | Step |
|---|---|---|
| A direction blends several references, some from outside the category; never one | steal-from-many.md | intent, look |
| Take the reason behind a reference's choice and adapt it; never its surface | steal-the-thinking.md | look, critique |
| Climb from the best reference to what it learned from | climb-the-lineage.md | intent, look |
| Name what each reference misses; the memorable thing fills one gap | make-what-the-references-miss.md | intent, critique |
| Many rough options before any styled specimen; stuck means back to rough | rough-before-finished.md | look, UX |
| Name what the direction leaves out and its one hard limit; the first fix is a removal | choose-what-to-leave-out.md | look, critique |

Source: Austin Kleon, *Steal Like an Artist* (Workman, 2012), paraphrased in our own words with chapter
citations. These files test the planning file (§Intent, §UI); `choose-what-to-leave-out` also checks
captures. Every count threshold is
ours, not Kleon's.

## Colour, type and flow (the tokens kit)

| Principle | File | Step |
|---|---|---|
| The seed colour comes from the subject and the feeling; states keep their known meanings | colour-meaning.md | intent, look |
| One named harmony, one accent with one job, tinted neutrals | colour-harmony.md | look, critique |
| Components use roles; every text pair passes AA in each theme; 60-30-10 as a check | colour-roles.md | build, critique |
| The face fits the voice and the reading job; a second family earns its place | type-fit.md | look, critique |
| One modular scale: ratio, six sizes, line height, measure, tracking | type-scale.md | look, build, critique |
| One token per decision, no near-duplicates, exceptions only with a reason | consistency.md | build, critique |
| The main journey as three to seven steps, one job per screen; the tour follows it | flow.md | UX, tour |

Source: written for this skill from public standards (WCAG 2.2, CSS Color 4 and OKLab, the APCA notes,
the W3C design tokens draft, the modular scale article) and our own lessons; no book is paraphrased.
`tokens/palette.mjs`, `tokens/type-scale.mjs` and `tokens/brand-from-design.mjs` make them tokens.

## Copy and voice

| Principle | File | Step |
|---|---|---|
| Name the product's things and say what happens to them; no abstraction stands in | copy-say-what-it-does.md | intent, critique |
| No hyped or hedged words; the claim with its evidence, or cut | copy-no-hype-or-hedge.md | build, critique |
| Numbers as numerals; every claim number with its source or marked illustrative | copy-numbers-with-a-source.md | build, critique |
| One idea per sentence, the point first, 20 words or fewer | copy-one-idea-per-line.md | UX, critique |
| A button or link names its result, key word first | copy-labels-name-the-result.md | UX, tour, critique |
| A heading states the answer to the visitor's question; never a question or a slogan | copy-headings-answer-questions.md | UX, critique |
| An error says what happened and how to fix it; an empty state says what comes here | copy-errors-and-empty-states.md | UX, critique |

Source: paraphrased with attribution from public plain-language guidance (the GOV.UK style guide and
writing guidelines, the GOV.UK Design System, Digital.gov's plain language guide, formerly
plainlanguage.gov, and Nielsen Norman Group's public articles); no book. Thresholds marked ours are ours.
`reference/copy.md` holds the `## Voice` section for `DESIGN.md` and the gate, `tokens/check-copy.mjs`.

## UI principles (Refactoring UI)

| Principle | File | Step |
|---|---|---|
| Design the feature first; the shell stays smaller than it | ui-feature-before-layout.md | UX, build |
| Type, colour, radius and wording carry one chosen personality; no square-and-round mix | ui-one-personality.md | look, critique |
| Rank text by weight and colour before size | ui-hierarchy-by-weight.md | look, critique |
| Emphasise the main thing by quieting its competitors | ui-emphasize-by-deemphasizing.md | critique |
| Show the value; labels and panel titles stay quieter | ui-values-over-labels.md | look, build, critique |
| One solid primary action per view; destructive is not automatically loud | ui-action-hierarchy.md | UX, look, critique |
| Secondary text on a coloured ground takes that ground's hue, never grey | ui-no-grey-on-colour.md | look, critique |
| Every gap from a spacing scale with steps 25% apart; start generous | ui-spacing-scale.md | look, build, critique |
| More space between groups than within them | ui-spacing-groups.md | critique |
| Give content the width it needs, not the screen's; design mobile first | ui-content-width.md | build, critique |
| Large sizes shrink more than small ones on a phone | ui-sizes-dont-scale-together.md | build, critique |
| Shortlist faces with five or more weights; no condensed UI text | ui-good-fonts.md | look, critique |
| Wide columns get taller lines; capitals get tracking; mixed sizes share a baseline | ui-line-height-and-tracking.md | build, critique |
| Left-align by default; centre only short blocks; numbers right | ui-text-alignment.md | critique |
| Defined shades only; quiet colour is a tint with same-hue text; never colour alone | ui-colour-shades.md | look, critique |
| One light source from above; shadow size means elevation | ui-depth-from-light.md | look, critique |
| Text on an image keeps steady contrast; real photos only | ui-text-on-images.md | critique |
| Icons and screenshots at the size they were drawn for | ui-intended-size.md | build, critique |
| User uploads sit in fixed frames and never bleed into the page | ui-user-content-contained.md | build, critique |
| Polish by styling the defaults, not by adding ornament | ui-supercharge-defaults.md | look, critique |
| The empty state leads with its action and hides controls that act on nothing | ui-empty-states.md | UX, critique |
| Separate with space and background before borders; no nested boxes | ui-fewer-borders.md | critique |
| Components shaped to their content: rich table cells, choices as cards | ui-rich-components.md | UX, build, critique |

Source: Adam Wathan and Steve Schoger, *Refactoring UI* (the authors' PDF, 252 pages), paraphrased in our
own words with chapter, section and page citations. Thresholds marked ours are ours, not the book's.
Where the tokens kit already rules (the type scale, line length, colour ramps), the ui- files keep only
what the book adds and name the kit file; where the book disagrees with the kit (a hand-picked type scale
over a modular one), the kit wins.

## Graphic design basics (Lupton and Phillips)

| Principle | File | Step |
|---|---|---|
| Each element is a point, line or plane; alignment draws the lines, not borders | lupton-point-line-plane.md | look, critique |
| Balance by contrast, not mirroring; one structure varied in scale and tone down the page | lupton-rhythm-and-balance.md | UX, critique |
| One element clearly largest, about 2x the next; never stretch | lupton-scale.md | look, critique |
| Colour is relative: check value in greyscale, avoid vibrating pairs | lupton-colour-in-context.md | look, build, critique |
| Figures separate from their ground; empty space is shaped on purpose; like jobs look alike | lupton-figure-ground.md | critique |
| The interface frames the user's work and stays quiet until needed; chrome under a third | lupton-framing.md | UX, critique |
| Count the levels, mark each step with one consistent signal, cut repeated signals | lupton-hierarchy-levels.md | UX, critique |
| Each stacked kind of information gets its own channel and a toggle | lupton-layers.md | UX, build, critique |
| Opacity only to show what is behind; text stays at contrast over the busiest backing | lupton-transparency.md | build, critique |
| One base unit and a few spans; break the unit only on purpose | lupton-modules.md | look, build |
| A declared column grid structures the empty space as well as the content | lupton-grid.md | look, build, critique |
| Every mark in a diagram encodes one stated thing; draw the data's real structure | lupton-diagram.md | UX, build, critique |
| Motion has a trigger and a job; nothing moves at rest; moving text stays readable | lupton-time-and-motion.md | build, tour, critique |
| Ship rules others can build from; generated variety is seeded from the data | lupton-rules-and-randomness.md | look, build |

Source: Ellen Lupton and Jennifer Cole Phillips, *Graphic Design: The New Basics*, second edition, read in
the Spanish edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili); page numbers are that edition's.
Paraphrased in our own words; at most one translated sentence per file. The phone tests and thresholds
marked ours are ours, not the book's. Skipped as already covered: formstorming (`rough-before-finished`),
texture (`lupton-point-line-plane`, `ui-line-height-and-tracking`; decorative grain is rubric T2) and
pattern (decorative backgrounds are rubric T3; repeated rows are `lupton-rhythm-and-balance` and
`lupton-modules`).
