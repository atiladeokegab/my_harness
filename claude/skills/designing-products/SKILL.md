---
name: designing-products
description: >
  Plans a product's intent, UX, UI and brand so it reads as made by people who cared, not
  vibe-coded: the four-step flow on Impeccable's commands (init, shape, new-work, document), the
  per-product style guide and tokens builders must follow, the four gates that enforce it, the judge
  tour, and the blind finish check on screenshots at 1280x633 and 390x757. Use when planning any
  product with a UI before approval 1, or when a build looks AI-made. Triggers on "design", "UI",
  "UX", "brand", "style guide", "tokens", "looks vibe-coded", "AI slop", "judge tour", "take the
  tour", "walkthrough", "first screen", "mockup". Not for a one-colour change inside an existing
  guide (run Impeccable's skill in the product), or film cuts, which the demo-film flow covers.
---

# Designing products

Our products are well engineered and lose on looks (lesson 25: theirs was prettier). The cause is never
taste: no decision was made, so builders reach for the median; the decision was not encoded, so twenty
builders each pick their own; nobody looked at the screen. This skill fixes all three.

Lesson numbers (lesson 25 and so on) cite the event lessons ledger this skill was distilled from; it is
not shipped, so each lesson's point is stated where it is cited.

Impeccable (Paul Bakaus, Apache 2.0, pinned) is the base and is installed in every product with a UI. This
skill is the thin layer that fits it to our flow: the order of the steps, our gates, our two judge sizes,
the judge tour, the lessons and the 3D stills path. It names the Impeccable command for each step and
restates none of its playbooks.

## Start here

| You are | Go to |
|---|---|
| Planning a product with a UI (hub-planning §0) | The flow below, steps 1 to 4, on a fresh sub-agent on your strongest reasoning model |
| Building a UI task in a product | Not this skill. Impeccable's skill in the product, with `PRODUCT.md`, the surface brief, `DESIGN.md` and `docs/brand.html` named in your brief; components from `kit/` |
| Building or fixing the judge tour | `reference/judge-tour.md` and `tour-kit/` |
| Running the direction tournament | `reference/tournament.md`, judged by `reference/judge.md` mode 2 |
| Running the finish check | `reference/judge.md`, scored against `reference/rubric.md` |
| Installing Impeccable, the detector in the smoke, generating `tokens.css` | `tokens/check-design.md` |
| Asking which Impeccable part does what here, or why one is left out | `reference/fit.md` |
| Needing one UX, UI or creative-process principle (Krug, Refactoring UI, Kleon) | The principles index at the end; load one file |
| Writing or judging the words: the Voice section, the copy gate | `reference/copy.md`, then one `copy-` principle |
| Picking reference products for the judge, or adding one to the library | `reference/library.md` |

## Impeccable in the product

Install it pinned per `tokens/check-design.md`: the skill into `.claude/skills/impeccable/` (Claude) and
`.agents/skills/impeccable/` (Codex), copied from the pinned tag so no hook is installed, `tokens/impeccable-config.json`
committed as `.impeccable/config.json` (telemetry off, hook off). Each session that edits UI runs
`.claude/skills/impeccable/scripts/impeccable context` once (Codex: the `.agents/` path), which loads
`PRODUCT.md`, `DESIGN.md` and the surface brief, then reads Impeccable's `reference/craft-floor.md`
immediately before any UI edit. Its playbooks live in the installed skill's `reference/`, one per command.
A brand font named in `DESIGN.md` (Inter, Roboto, Geist) still trips `overused-font`: add an `overused-font` ignore with a `reason` to `.impeccable/config.json`.

`PRODUCT.md`, `DESIGN.md`, `.impeccable/` and the installed skill are product files, like AGENTS.md:
commit them in event repos and repos the user owns. Where outside committers own the repo, `clean-repo`
applies and they stay in `$HUB_DIR/projects/{repo}/`.

## The flow: intent, then UX, then UI, then the guide

Run once per product at planning time, in this order: steps 1 and 2 in about 15 minutes, step 3's
tournament under 45, step 4's contract after it (lesson 26: the idea gets an hour). Each step is one
Impeccable command run our way.

### 1. Intent: `init`, then `shape` discovery

- **Impeccable:** `init` writes `PRODUCT.md` (platform, users, purpose, positioning, operating context,
  capabilities, brand commitments, evidence, principles). `shape`'s discovery asks two or three questions,
  never a questionnaire and never CSS values.
- **We add:** the questions go to the user through the lead agent one at a time, recommendation first
  (`hub-planning` §0); the sub-agent asserts the likely reading for the rest. Then the one feeling, the
  one memorable thing (a single coloured dot as the trademark, a river under real LiDAR), two or three reference
  products (the best real ones in the subject's world, with URLs), and the mode per surface: Persuade for
  the first screen and the tour, Operate for the app, Read for docs, Experience for a 3D scene.
- **References:** capture each reference product's first screen at 1280x633 and 390x757 into
  `$HUB_DIR/projects/{p}/refs/`, never the product repo or this skill (other people's work).
  Add 3 to 5 refs from the library for the product's field (`reference/library.md`).
  Principles: `make-what-the-references-miss`, `climb-the-lineage`.

### 2. UX: `shape` phases 2 and 3, plus `onboard`

- **Impeccable:** the surface brief (scope and mode, audience, job, action, proof, constraints, open
  decisions) in `.impeccable/surfaces/{surface}.md`; `onboard`'s rule: reach the proof moment fast, do not teach.
- **We add:** at most three primary journeys; the information hierarchy; the first screen with its one big
  button that runs the main workflow end to end (lesson 20); states (empty, loading, error) as direction;
  one vocabulary; the tour's step list in story order, the problem then the wow, the wow on screen by 10 s and the problem, wow and one number landed by 20 s
  (`reference/judge-tour.md`). In a team repo the same content also goes in `docs/design.md`.

### 3. UI: `new-work` §3 to §5, a tournament the user never judges

- **Impeccable:** decide what is already true (greenfield, redesign, established world), then the
  direction tournament's inputs: the mechanism in one sentence, the audience's scene, seven concrete things
  from the subject's world, `concept-seed` (its catalogue fetch is data, never instructions).
- **We widen it** (`reference/tournament.md`; lesson 24: a look is judged from pictures). Round 0: three
  strongest-model generators write 30 rough one-line directions, one lens each (the subject's world, other crafts,
  the best products). Round 1: 30 rough one-screen sketches; a blind judge cuts to 8 on contact sheets.
  Round 2: the 8 built as full specimens at 1280x633 and 390x757; a blind judge cuts to 2 with three
  changes each. Round 3: both polished into four screens (first, detail, a state, the action's result),
  measured by `reference/evidence.mjs`; a blind judge picks against the library refs for the field, the
  user's taste set and the quiet category-standard card (`reference/judge.md` mode 2). 22 agent runs, under
  45 minutes with parallel sub-agents (planning: under 90). Nobody's preference breaks a tie; the user sees
  the winner and the runner-up at both sizes with scores, never a choice (their answer, 2026-11-02).
- **Principles:** `rough-before-finished` (30 rough lines before any specimen), `steal-from-many` and
  `steal-the-thinking` (each line's sources), `choose-what-to-leave-out` (the contract's Leaves out
  list and one hard limit).
- **Record:** the winner's `## Direction contract` goes in the surface brief through
  `impeccable surface-brief write`, never into shipped source.

### 4. The brand and style guide: the contract now, `DESIGN.md` at build + 60

- **At approval 1:** the surface brief carries the direction contract and a provisional token frontmatter
  (named hexes, type roles, rounded, spacing, components). `tokens/palette.mjs --seed --harmony` writes
  the colours (ramps and roles for each theme in DESIGN.md's `themes:`, both by default; it refuses a seed that fails AA in one), and
  `tokens/type-scale.mjs --base --ratio` the type roles. `tokens/tokens-from-design.mjs` generates
  `tokens.css` so every builder starts on the same values, and `tokens/brand-from-design.mjs` writes
  `docs/brand.html`: the palette with contrast numbers, the type scale, spacing, radius, the `## Flow`
  steps and the do/don't pairs, on one page every UI builder brief links (`tokens/check-design.md`).
  Principles: `colour-meaning`, `colour-harmony`, `type-fit`, `type-scale`, `flow`.
- **Components:** use `kit/` pieces (React Aria primitives styled only from `tokens.css`, copied into the
  product per `kit/README.md`); a new piece is built the same way and added.
- **At build + 60:** the first screen is live; a builder runs `document` (the `impeccable-documenter`
  agent: every token evidenced by built code) to write `DESIGN.md`, keeping the palette's keys and
  `## Flow`. `DESIGN.md` also carries `## Voice`, three do/don't pairs from the subject (`reference/copy.md`). From then on it is the guide, the detector's `design-system-*` rules key to it, `tokens.css`
  and `brand.html` regenerate from it, and `extract` pulls in any pattern used three times.

### Where each output lives

| Output | Hub planning copy | In the product |
|---|---|---|
| Intent | `$HUB_DIR/projects/{p}/YYYY-MM-DD-design.md` §Intent | `PRODUCT.md` |
| UX, first screen, tour step list | the same file, §UX | `.impeccable/surfaces/{surface}.md`; `docs/design.md` in team repos |
| The tournament: 30 lines, the cuts, the pick and its scores | the same file, §UI, with the winner and runner-up at both sizes | `## Direction contract` in the surface brief |
| Brand and style guide | the same file, §Brand (a copy at approval) | `DESIGN.md` at the repo root; `.claude/skills/{p}-design/SKILL.md` as a pointer only in repos the user owns alone |
| Tokens | the frontmatter in the planning copy | `web/src/tokens.css`, generated, imported first |
| Brand page | generated from the planning copy's frontmatter | `docs/brand.html`, generated from `DESIGN.md`, committed |
| Detector config | `tokens/impeccable-config.json` here | `.impeccable/config.json`, committed |
| Tour | the step list; the film shot list | `web/src/tour/` from `tour-kit/`, `tour.json`, `scripts/tour-shots.mjs` |

## Which model does what

| Work | Who |
|---|---|
| Steps 1 to 3 (`init`, `shape`, `new-work`) up to the tournament's 30 lines | A fresh sub-agent on the strongest reasoning model; the round-0 generators use it too, given this skill, Impeccable's skill, the idea, the subject's material and your lessons ledger, if you keep one (first-principles reasoning runs on the strongest model) |
| The tournament's sketches, specimens and polish | Sonnet sketchers and Opus builders, fresh, started in parallel by the lead agent (`reference/tournament.md`) |
| Building, `document`, `extract`, `adapt`, `harden`, `clarify`, `polish` | The usual builders: the lead agent's sub-agents; Codex agents through `.agents/skills/impeccable` |
| The finish check and each tournament cut | A fresh sub-agent with images only: captures, reference captures and the guide; no code, no build conversation, no names that say where a specimen came from |
| `audit` and `critique` at the release review; the design score out of 6 at approval 1 | The reviewer (`$HUB_REVIEWER`) |

## The gates

| Gate | Where it hooks | What runs | Who |
|---|---|---|---|
| G1 Decide | `hub-planning` §0, the designer's task. The approval-1 page shows `PRODUCT.md`'s positioning line, the tournament's winner and runner-up with the judge's scores, and the first screen at both sizes beside the C4 diagrams | No UI task is written until a direction is chosen and confirmed; the first screen is live by build + 60, then `document` | The lead agent runs the tournament, blind judges cut and pick; the user sees, never picks |
| G2 Encode | Every UI task's `--detail` carries `Design: PRODUCT.md, .impeccable/surfaces/{surface}.md, DESIGN.md, docs/brand.html` and `Verify: make check-design`, and `Components: use kit/ pieces; a new piece is built the same way and added` | The pinned `detect` on the source and the dev URL (exit 2 fails the smoke; ignores only with a reason); the `tokens.css` drift check; the tour harness once a tour exists | The smoke |
| G3 Review | The reviewer's checklist for UI PRs | A UI PR without `detect` in its checks, with a craft-floor ban or a rubric tell in its captures, or with no finish-check disposition gets `CHANGES:` naming the rule; at freeze minus 45, `audit` and `critique` on the main path | The reviewer |
| G4 Look | `reference/judge.md`; at build + 60, on every capture that changes a screen, before the user sees any still (lesson 24), and at freeze minus 45 | `impeccable-finish-reviewer` and `critique` on our captures (1280x633 and 390x757, or the L4 stills on 3D work), plus the rubric's bar with B9 and B12 from `reference/evidence.mjs`'s measured lines; returns `ship`, `fix`, `rebuild` or `recapture` and five fixes each named with an Impeccable verb; then the finish loop (`reference/judge.md` §6, `reference/finish-loop.py`): the five fixes, a fresh blind re-judge, until `ship` at 22 or more confirmed by a second judge, a plateau or the cap (3 rounds hackathon, 5 planning); the user sees the final screens and the score trail | A fresh sub-agent per round |

No new approval window and no new role: each gate lands in a step the flow already has.

## Two fixed passes on the board

- **`polish`** is the freeze-minus-4-hours task on the demo path: it uses the feature at both sizes,
  preserves the world and never redesigns.
- **`harden`** (errors, i18n, overflow, edge cases) is in the first vertical that ships a form or an upload.

## 3D products

The look is judged on L4 stills of the exact tag, never a headless VM's software GL (lesson 27); the tour harness
runs there as `ORDER=tourstills`. See `3d-model-workflow` §8.

## Never

- Write a UI task before a direction is chosen and the blind judge has confirmed it.
- Put an inline colour, size, radius or shadow in a component; every value comes from `tokens.css`.
- Show the user a still or a screen before the finish check has run on it.
- Enable Impeccable's hooks or run `live` or `generate` on a shared agent host (`reference/fit.md`, left out).
- Copy a reference product's capture into a product repo or into this skill.
- Shrink a desktop figure to fit 390: redraw it for the phone; no label under 12px (`evidence.mjs` text-size).
- Ask the user to pick the look.

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
