# The flow: the main journey as steps, one job per screen

Source: written from first principles for this skill, on Impeccable's `onboard` rule (reach the proof
moment fast, do not teach; Apache 2.0, paraphrased) and our own lessons 20 (one big button runs the main
workflow end to end) and 24. Every threshold is ours.

**Principle.** The product's main journey is written as a short list of steps; each step is one screen
(or one state of it) with one job and one primary action; the tour walks the same steps in the same order.

## Why it holds

- A product is judged on whether a first-time user gets from arrival to the proof moment. Writing the
  journey as steps first makes every screen answer "which step am I, and what is my one job?"
- A screen with two jobs has two primary actions, so it has no hierarchy (`visual-hierarchy`); the
  accent then lands twice and means nothing (`colour-roles`).
- The tour is the flow told as a story. If the tour jumps around, the product's own order is wrong or
  the tour is selling features instead of the journey (`reference/judge-tour.md`).
- Three to seven steps fit in memory. More means sub-flows are mixed into the main journey.

## What to check

- DESIGN.md's `## Flow` (and the planning file's §UX): numbered steps, each led by a short name, then
  the screen and its one job in one line. `brand.html` shows them in order.
- Each step's screen has exactly one element in the accent that is the primary action.
- `tour.json`'s steps visit the flow's steps in order; it may skip a step, never go back.

## Pass or fail test

Apply to DESIGN.md's `## Flow` and `tour.json`, then to each step's capture (1280x633, 390x757).

- **PASS:** three to seven steps, each naming one screen and one job; every step's capture has one
  primary action; the tour's order is a subsequence of the flow's order; step 1's screen is the first
  screen and its primary action starts the main workflow.
- **FAIL:** no `## Flow`, over seven steps, a step with two jobs, a capture with two primary actions,
  or a tour that reorders or revisits steps.

Observable: the numbered list, the primary-action count per capture, the tour's step order.

## Used at

**UX** (step 2: the journeys and the first screen) and **tour** (the step list in story order).
