# Line height follows line length; capitals get tracking

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Designing Text": "Baseline, not center",
"Line-height is proportional" and "Use letter-spacing effectively", pp. 118-125 and 132-134. Paraphrased
in our words; anything quoted is marked and at most one sentence.

**Principle.** Beyond the scale's line heights, wide text columns get taller line height, all-capitals
text gets extra letter spacing, and mixed sizes on one line share a baseline.

## Why it holds

- `type-scale` already sets line height by size (tight headings, about 1.5 body) and closes tracking at
  large sizes; the book agrees (pp. 124-125, 133). This file holds what it adds.
- Line height also depends on width: the further the eye travels back, the easier it loses its line, so
  a narrow column can stay near 1.5 while a wide one may need up to 2 (pp. 122-123).
- Letter spacing is the typeface designer's call except in two cases (pp. 132-134): a face drawn for
  small sizes can be tightened for headlines (a headline face never works small), and all-capitals text,
  every letter the same height, needs wider spacing to stay legible.
- When two sizes share a line (a card title with small actions beside it), centring them looks off,
  most when they sit close; align their baselines (pp. 118-120).

## What to check on a screen

- Wide paragraphs (near the top of the 45 to 75 character range): is there more air between lines?
- All-capitals labels, eyebrows and buttons: are the letters spaced out a little?
- Mixed sizes on one line: do they rest on one baseline?

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Find any all-capitals text and any line that mixes two text sizes.
2. Find the widest paragraph and compare its line gap with a narrow one's, if both exist.

- **PASS:** all-capitals text is visibly letter-spaced; mixed sizes share a baseline; the widest
  paragraph's lines are no more cramped than a narrow one's.
- **FAIL:** tightly set capitals, a small label floating at the vertical centre of a big title, or wide
  paragraphs with tighter lines than narrow ones.

Observable: each capitals run, each mixed-size line, and the two paragraphs compared.

## Used at

**Build** (tracking and line height in the tokens) and **critique**.
