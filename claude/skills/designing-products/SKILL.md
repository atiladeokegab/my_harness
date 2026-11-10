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
| Planning a product with a UI (hub-planning §0, hackathon §2a) | [Planning flow](reference/planning.md), steps 1 to 4, on a fresh sub-agent on your strongest reasoning model |
| Building a UI task in a product | Not this skill. Impeccable's skill in the product, with `PRODUCT.md`, the surface brief, `DESIGN.md` and `docs/brand.html` named in your brief; components from `kit/` |
| Building or fixing the judge tour | `reference/judge-tour.md` and `tour-kit/` |
| Running the direction tournament | `reference/tournament.md`, judged by `reference/judge.md` mode 2 |
| Running the finish check | `reference/judge.md`, scored against `reference/rubric.md` |
| Installing Impeccable, the detector in the smoke, generating `tokens.css` | `tokens/check-design.md` |
| Asking which Impeccable part does what here, or why one is left out | `reference/fit.md` |
| Needing one UX, UI or creative-process principle (Krug, Refactoring UI, Kleon) | [Principles index](principles/index.md); load one file |
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

## Planning and resources

For a new product or direction, read [the planning flow](reference/planning.md):
intent → UX → UI tournament → guide, with model roles and output locations. For
existing work, load only its row above and the applicable gate below.
[Resources](reference/resources.md) indexes the scripts, kits and principles.

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
