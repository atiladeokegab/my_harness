# Modules: one unit, a few spans, decisions made once

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Modules", pp. 166-185. Page
numbers are that edition's. Paraphrased in our words; anything quoted is translated, marked and at
most one sentence.

**Principle.** Build layouts from one base unit and a small kit of parts that join by one rule; vary
how many units a part spans so the whole is not monotonous; break the unit only where something
earns it.

## Why it holds

- p. 167: a module is a compact element inside a larger system, like a pixel in an image or a brick
  in a wall. A few LEGO bricks with one way of joining make an astonishing number of forms.
- p. 167: a well-defined constraint lightens the work by removing decisions; with a few factors fixed,
  the designer can concentrate on the rest of the problem.
- p. 167: the book itself sits on a square module, which lets it mix images while staying continuous;
  the squares vary in size to avoid monotony, and some images span several modules or leave the grid.
  In the authors' words, "rules are very useful, but it is fun to break them" (translated).
- p. 172: in the modular alphabets the parts could be combined freely, but their relative scale could
  not change.
- p. 182: symbol systems are often built from geometric modules combined into many forms.

## What to check on a screen

- Card, tile and panel sizes are whole multiples of one unit (a column span or a base height).
- A collection of peers uses at least two spans when the items differ in importance; identical spans
  only when they are true peers.
- Icons in one set share a construction grid: stroke, corner and module size.
- Each element that breaks the unit is the one the screen is about.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every block's width snaps to the column unit; spans differ where importance differs; any
  break from the unit is a single, deliberate feature.
- **FAIL:** block widths that fit no common unit, a row of identical cards for items that are not
  peers, an icon set with mixed constructions, or several unrelated grid breaks.

Observable: the unit, each block's span, and each break with its reason.

## Used at

**Look** (the specimen's kit) and **build**. Feeds rubric T4 (identical cards) and B2. Token reuse is
`consistency`; columns and margins are `lupton-grid`.
