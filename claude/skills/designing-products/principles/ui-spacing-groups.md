# More space between groups than within them

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Layout and Spacing": "Avoid ambiguous
spacing", pp. 96-99. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** The space around a group must be clearly larger than the space inside it, so every label,
heading and caption visibly belongs to one thing.

## Why it holds

- When there is no border or background to group things, spacing is the only grouping signal.
- A form label that sits halfway between two inputs, or a section heading as far from its own content
  as from the section above, makes the reader stop and work out what belongs to what.
- Krug's `visual-hierarchy` asks for grouped things to look grouped; this is the cheapest way to do it.

## What to check on a screen

- Each form label is closer to its own input than to the input above.
- Each heading is closer to the content below it than to the content above it.
- Each list item's parts (title, meta, description) are closer to each other than to the next item.
- Each caption is closer to its image or chart than to the next block.
- In bulleted lists, the gap between bullets is larger than the line spacing inside one bullet (p. 98).
- The same holds side by side: items in a horizontal group sit nearer each other than the next group.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. For every heading, measure the gap above it and the gap below it.
2. For every form label, measure the gap to its input and the gap to the previous field.

- **PASS:** every heading has a gap above at least one and a half times its gap below, and every label
  sits nearer its own input than the previous field.
- **FAIL:** any heading or label equidistant from what is above and below it, or nearer the wrong one.

Observable: the gaps measured, as above and below pairs.

## Used at

**Critique.** A fix names the gap to grow, never a new border.
