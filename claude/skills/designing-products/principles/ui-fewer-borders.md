# Separate with space and background, not borders

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Finishing Touches": "Use fewer borders",
pp. 238-241; ch. "Creating Depth", p. 191. Paraphrased in our words; anything quoted is marked and at
most one sentence.

**Principle.** When two things need separating, try more space, a different background shade or a soft
shadow before a border; never nest a bordered box inside another.

## Why it holds

- Borders are the easy default, and a screen full of them looks busy and cluttered.
- A box shadow outlines an element more softly (best when the element's colour differs from the page);
  two slightly different backgrounds mark an area without a line, and if both a background change and a
  border are there, drop the border; extra space alone often separates groups (pp. 239-241).
- Our addition: a card inside a card inside a panel, each with its own border, is a strong sign the
  layout was assembled rather than designed.
- Krug's `clear-areas-low-noise` wants clearly bounded areas; this file bounds them without lines.
- Rows in a list can be told apart by spacing or alternating backgrounds instead of a rule under each.

## What to check on a screen

- Count bordered boxes; look for boxes inside boxes.
- Lists with a line under every row.
- Places where a border sits right beside a background change or a shadow, doing the same job twice.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** no bordered container sits inside another bordered container (inputs inside a card are
  allowed), and no element has both a border and a shadow or background change doing the same job.
- **FAIL:** two or more levels of nested bordered boxes, or most elements on the screen outlined.

Observable: the deepest nesting of bordered boxes, and the count of outlined elements.

## Used at

**Critique.** A fix names the border to drop and what replaces it.
