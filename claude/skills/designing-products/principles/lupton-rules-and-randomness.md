# Rules and randomness: design the rules others will apply

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Rules and Randomness", pp. 248-259.
Page numbers are that edition's. Paraphrased in our words; anything quoted is translated, marked and at
most one sentence.

**Principle.** The design is a set of rules as much as a set of screens: write them so another builder
can make a new screen that is on-brand and still original, and where variety is generated, drive it
from the data, never from chance alone.

## Why it holds

- p. 249: a designer makes rules as well as finished pieces. A magazine's grid and type hierarchy are
  read differently on every page and every issue; well-made rules let other designers produce their
  own original layouts. Rules frame the work without deciding the result.
- p. 249: style sheets are rules for how each part of a document appears; changing one restyles a
  whole site or book, and lets one body of content serve print, screen and phone.
- p. 249: designers are more and more asked to make systems that other people will run and that will
  change over time.
- p. 250: in the phone-book posters, digits set the size and colour of dots on a grid; the designer
  shapes the system more than the final result, and the input gives it an organic quality.
- p. 257: randomising transparency, size or position within a repeat gives a natural feel.

## What to check on a screen

- `DESIGN.md` states rules (grid, scale, roles, when to break them), not only finished examples.
- Generated visuals (avatars, covers, placeholders, chart colours) derive from the item's own data or
  id, so one item looks the same on every screen and every visit.
- Variety inside a repeat (a collection, a feed) stays within the rules: same grid, same scale steps.

## Pass or fail test

Apply to the contact sheet: four screens at desktop 1280x633 and phone 390x757, including one screen
built by a different builder or agent from `DESIGN.md` alone.

- **PASS:** the screen built from the rules alone reads as the same product without copying another
  screen; any generated visual for the same item matches across screens.
- **FAIL:** the rule-built screen drifts off the system or simply clones an existing one, or the same
  item shows a different generated look on reload or on another screen.

Observable: the rule-built screen beside its nearest sibling, and each mismatched generated visual.

## Used at

**Look** (writing the rules) and **build**. Feeds rubric B11 (the contact sheet) and T12 (library
defaults standing in for rules). Token-level reuse is `consistency`.
