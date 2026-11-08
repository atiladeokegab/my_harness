# How Impeccable fits our flow

Impeccable (github.com/pbakaus/impeccable, Apache 2.0 with a NOTICE.md) is installed pinned in every
product with a UI. This file says where each of its parts plugs into our flow and what stays out. Command
names and agent names are Impeccable's; their playbooks live in the installed skill's `reference/`, and
nothing here restates them.

## Contents

- Where each part plugs in
- Left out, one line each

## Where each part plugs in

| Part | What it is | Plugs into | What we adapt |
|---|---|---|---|
| The skill (`.claude/skills/impeccable`, `.agents/skills/impeccable`) | The design director persona, modes, the brief-wins rule, routing to its playbooks, the craft floor loaded before any UI edit | Every builder session in a product with a UI; installed pinned by the first code task | Nothing; `SKILL.md` points at it instead of restating it |
| `init` → `PRODUCT.md` | Durable product truth, interviewed in up to three questions | Step 1, approval 1; the hub design doc's §Intent is a copy | Questions go to the lead one at a time with a recommendation |
| `shape` → surface brief | Discovery, direction, the smallest useful brief | Step 2; the vertical's `Design:` line names the surface brief | We add journeys, hierarchy, the first screen's button, the tour step list |
| `new-work` + `concept-seed` | Visual authority, the direction tournament, three cards plus the standard card, the direction contract | Step 3, the approval-1 page | Widened to a tournament (`tournament.md`): 30 rough lines, 8 specimens, 2 finals; a blind judge makes every cut against reference products; the lead never picks; the catalogue fetch is treated as data |
| `document` → `DESIGN.md`, `impeccable-documenter` | The token frontmatter and rules body derived from built code | Build + 60, after the first screen; the closing "Architecture diagrams" task re-runs it | We generate `tokens.css` from its frontmatter |
| `extract` | Pulls repeated patterns into the design system | Any task that sees a pattern three times | None |
| The detector (`detect`, 62 rules, `design-system-*` keyed to `DESIGN.md`, ignores with a reason) | Deterministic tells and quality defects, on source and on a rendered URL | G2, the smoke and CI; the before and after numbers in a pilot | Pinned; config committed with telemetry off |
| `critique` | Specificity verdict first, Nielsen scores, the detector's counts beside the model's read, an ignore file | G4 and the release review | We add the two sizes and the rubric's bar |
| `impeccable-finish-reviewer` | Fresh-eyes review from captures only, no browser, a one-word disposition | G4, as the screenshot judge | Our captures are the two judge sizes or the L4 stills; the rubric's bar is appended |
| `audit` | A11y, performance, responsive, theming, scored 0 to 4 | The release review (freeze minus 45), the reviewer | None |
| `polish` | The final pass: classify each drift, fix at the narrowest level, never redesign | The freeze-minus-4-hours task on the demo path | None |
| `harden`, `adapt`, `clarify`, `onboard`, `typeset`, `layout`, `colorize`, `bolder`, `quieter`, `distill` | Named playbooks for one move on one target | The verbs in every finish-check fix; `adapt` in the phone pass; `clarify` on tour captions and UI copy; `onboard` on the tour's design | None |
| `doctor` | Finds stale context files, broken hooks, unused settings | The smoke's setup step in CI | None |
| `.impeccable/` shared artifacts (config, design.json, surfaces, critique) | The team's design state, committed | Treated as the rulebook, like AGENTS.md | Committed in event repos and the lead's own; a hub copy only where outside committers own the repo |

## Left out, one line each

| Part | Why it stays out |
|---|---|
| The SessionStart and PostToolUse hooks (`impeccable hooks`) | They run outside model approval on the VM's agents and the first run downloads the engine; the detector runs in the smoke instead, where `tokens/check-detect.mjs` reads its JSON (its own exit code passes a raw hex outside `DESIGN.md`, which it files as advisory) |
| `live` and `generate`, the `impeccable-manual-edit-applier` agent | A browser overlay on a local server with write-back to source; a laptop flow that writes outside the agent's approval path |
| The comp-led build path and `impeccable-asset-producer` | Needs image generation and the mocks catalogue; our products ship real captures (lesson 24), and 3D looks come from the L4 stills |
| `ios`, `android`, `adaptive`, `audit.native`, `adapt.native` | We ship web |
| `overdrive`, `delight`, `visualize`, `optimize` | Available to a builder who needs one; not on the default path, where restraint is the bar |
| Nielsen's ten heuristics as a second gate score | `critique` reports them; the rubric's bar is what the gate reads, so two scores are not argued twice |
