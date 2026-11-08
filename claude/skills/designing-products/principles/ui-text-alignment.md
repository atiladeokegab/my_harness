# Align text for reading

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Designing Text": "Align with readability
in mind", pp. 128-131. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Left-align text by default; centre only short blocks of a few lines, right-align numbers
in tables, and justify only with hyphenation.

## Why it holds

- Left-aligned text gives every line the same starting point; centred paragraphs give each line a new
  one, so they tire the reader after two or three lines.
- Centring suits a headline or a short independent block. If a centred block grows long, shorten it or
  left-align it.
- Numbers in a column compare by their decimal places, which only line up when right-aligned.
- Justified text without hyphenation leaves uneven gaps between words.
- Krug's ch. 6 note in `visual-hierarchy` (left or right alignment shows structure better than
  centring) agrees.

## What to check on a screen

- Centred blocks: how many lines do they run?
- Tables and lists of amounts: do the digits line up on the right?
- Justified paragraphs: are there rivers of space?

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** no centred text block runs past three lines; numeric table columns are right-aligned; no
  justified paragraph shows visibly uneven word gaps.
- **FAIL:** a centred paragraph of four or more lines, a left-aligned column of amounts with ragged
  decimals, or justified text with gaps.

Observable: the longest centred block's line count, and each numeric column's alignment.

## Used at

**Critique.**
