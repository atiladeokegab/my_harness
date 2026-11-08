# Hierarchy by weight and colour, not size alone

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Hierarchy is Everything": "Not all
elements are equal" and "Size isn't everything", pp. 36-41. Paraphrased in our words; anything quoted is
marked and at most one sentence.

**Principle.** Rank text with two or three greys or tints and two weights before reaching for a bigger
size; the most important line is the darkest and boldest, not only the largest.

## Why it holds

- An interface where every element competes looks busy even when the spacing is fine. Hierarchy is the
  main thing that makes a screen look designed.
- Leaning on size alone gives primary text that is too big and secondary text that is too small to read.
  Weight and colour separate levels without either problem.
- In practice (p. 40): a dark colour for primary, a grey for secondary, a lighter grey for tertiary;
  a normal weight (400 or 500) for most text and a heavier one (600 or 700) for emphasis. Weights under
  400 suit only large headings; to quiet text, use a lighter colour or a smaller size instead.
- Krug's `visual-hierarchy` asks whether prominence matches importance; this file is how to build it.

## What to check on a screen

- Body and secondary text are distinguished by colour and weight, not by a third and fourth size.
- Three text colours at most in one region; two weights at most for UI text (headings may add one).
- No weight under 400 except in large headings.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Pick the largest content region (a card, list or form). Count the distinct text sizes in it.
2. Count the distinct text colours and weights in the same region.

- **PASS:** at most three sizes in the region, and levels are also told apart by colour or weight (two
  lines of the same size differ in colour or weight when they differ in importance).
- **FAIL:** four or more sizes in one region, or every line the same colour and weight so only size
  ranks them.

Observable: the region named, with its size, colour and weight counts.

## Used at

**Look** (the tokens hold the text colours and weights) and **critique**.
