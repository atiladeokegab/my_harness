Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
