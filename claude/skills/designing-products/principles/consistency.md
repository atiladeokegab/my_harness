# One token per decision, and exceptions in one place

Source: written from first principles for this skill, on public material: the W3C Design Tokens
Community Group format draft (tokens as named decisions with aliases); OKLab distance (Björn Ottosson,
2020). Every threshold is ours.

**Principle.** Each visual decision (a colour role, a size, a space, a radius) is one named token used
everywhere it applies; near-duplicates are merged; an exception is itself a token or a written ignore.

## Why it holds

- Twenty builders each picking "about 12px" give 11, 12 and 13px. Each alone looks fine; together they
  read as a product nobody owned (rubric B11, the contact-sheet test).
- A near-duplicate is worse than a clear difference: two greys an OKLab distance under 2 apart, or radii
  2px apart, look like an error, not a choice. Merge them, or move them apart until the difference reads.
- An alias is not a duplicate: `bg` pointing at the same hex as `neutral-100` names the decision and
  the material. A second token that means the same thing is.
- Exceptions are real (a code-syntax palette, a partner's logo colour). They live in DESIGN.md as tokens,
  or in `.impeccable/config.json` under `ignoreValues` with a `reason`; never in a component, never in
  `ignoreFiles` (it carries no reason). The detector is the lock: anything else fails the smoke.

## What to check

- `make check-design` passes: the pinned `detect` and `check-detect.mjs` on the source and the dev URL,
  and the `tokens.css` and `brand.html` drift checks.
- DESIGN.md: no two spacing values within 2px; no two radii within 2px; no two role colours within
  OKLab distance 2 unless they are the same hex. `palette.mjs` roles and neighbouring ramp steps clear
  it (3.0 or more); the 50 and 950 ends of different ramps converge by design, so use one ramp's ends.
- Every `ignoreValues` entry has a `reason` a reviewer would accept.

## Pass or fail test

Apply to the product repo at the commit under review, then to the capture pair (1280x633, 390x757).

- **PASS:** `make check-design` exits 0; DESIGN.md has no near-duplicate under the thresholds above;
  each ignore has a reason; the same component looks the same at both sizes except for layout.
- **FAIL:** any `design-system-*` finding; an ignore without a reason; an `ignoreFiles` entry; a
  near-duplicate pair; one component in two styles on the same capture.

Observable: the `check-design` exit code and log, and the near-duplicate pairs listed.

## Used at

**Build** (G2: every UI task's `Verify: make check-design`) and **critique** (G3 review).
