# A spacing scale, starting generous

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Layout and Spacing": "Start with too much
white space" and "Establish a spacing and sizing system", pp. 66-74. Paraphrased in our words; anything
quoted is marked and at most one sentence.

**Principle.** Every gap, padding and fixed size comes from a short scale whose neighbouring steps differ
by about a quarter or more, and the first draft uses too much space, then removes some.

## Why it holds

- Adding space until a thing stops looking cramped leaves it only just uncramped. Starting with too
  much and taking some away ends somewhere that looks deliberate.
- Picking each value by eye is slow and gives near-duplicates (14, 15, 16 px) that make a layout feel
  slightly off without anyone knowing why.
- The book's rule (p. 72): no two neighbouring values closer than about 25%, built from a 16 px base,
  tightly packed at the small end and spreading out higher up. Our example (the book shows its own as a
  picture): 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256.
- Dense screens (dashboards) may tighten, but as a deliberate decision, not by default (p. 69).
- In our flow `tokens.css` holds the scale; G2's drift check fails inline values, and `consistency`
  covers merging near-duplicates of any token.

## What to check on a screen

- Repeated elements (list rows, cards, form fields) have identical gaps between them.
- Card and panel padding is comfortable; text does not sit within a few pixels of an edge.
- Gaps fall on a handful of clearly different sizes.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Measure, roughly, the gaps between five repeated elements and the inner padding of three containers.
2. Note the smallest distance between any text and its container's edge.

- **PASS:** repeated gaps are equal, the measured values group into at most five distinct sizes, and no
  text sits closer than 12 px to its container edge (8 px inside small chips and badges).
- **FAIL:** unequal gaps between like items, near-duplicate gaps (within 2 px) used side by side, or
  text crammed against an edge.

Observable: the measured gaps and paddings.

## Used at

**Look** (the scale goes in the tokens), **build** and **critique**.
