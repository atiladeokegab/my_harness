# One personality, chosen on purpose

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Starting from Scratch": "Choose a
personality" and "Limit your choices", pp. 20-32. Paraphrased in our words; anything quoted is marked
and at most one sentence.

**Principle.** Typeface, colour, corner radius and wording carry the product's personality, and all
four must agree; choose them once as a small set and pick only from that set.

## Why it holds

- The levers (pp. 21-26): a serif reads elegant or classic, a rounded sans playful, a neutral sans plain;
  blue reads safe, gold expensive, pink fun; a small radius is fairly neutral, a large one playful, no
  radius serious or formal; impersonal wording reads official, casual wording friendly.
- Square and rounded corners mixed in one interface nearly always look worse than either one (p. 25).
- To decide, look at what the audience's other sites feel like, but borrow little from direct
  competitors, or you look like a lesser copy (p. 26). Our reference captures do this job.
- Picking from unlimited values at every step is slow and drifts. Define systems in advance (sizes,
  weights, line heights, colours, spacing, shadows, radii, borders, opacity) and choose by elimination
  among a few clearly different options (pp. 28-32).
- Overlap: `type-fit` covers choosing the face and `consistency` one token per decision; this file is
  the levers agreeing.

## What to check on a screen

- Corners: all square, or all rounded, with avatars and round icon buttons as the only circles.
- Each component type uses one radius (every button alike, every card alike).
- The type, colour and wording point the same way as the guide's one feeling.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. List the corner treatment of each component type (buttons, cards, inputs, badges, images).
2. Name the personality the type, colour and wording suggest, in one word; compare with the guide.

- **PASS:** no mix of square and rounded components (circles allowed), one radius per component type,
  and the one word matches the guide.
- **FAIL:** square and rounded components side by side, one component type in two radii, or a
  personality word the guide would reject.

Observable: the corner list and the one word.

## Used at

**Look** (the direction card fixes the set) and **critique**.
