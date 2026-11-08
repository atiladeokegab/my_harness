# Grid: columns that structure the empty space as well as the content

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Grids", pp. 186-199. Page numbers are
that edition's. Paraphrased in our words; anything quoted is translated, marked and at most one sentence.

**Principle.** Every screen sits on a declared column grid with fixed margins and gutters, chosen for
the content's density; use it to make asymmetric layouts that leave areas open, and let one element
break it only on purpose.

## Why it holds

- p. 187: consistent margins and columns create an underlying structure that unifies the pages. The
  grid also organises the white space, which stops being a passive void and joins the rhythm.
- p. 187: dividing space into equal units makes the whole page usable, so the edges matter as much as
  the centre. Grids encourage active, asymmetric layouts over centred, static ones, and leaving some
  areas open rather than filling everything.
- p. 187: switch guides off now and then, because they give a false sense of fullness and order.
- p. 196: the number of columns follows the content: one for continuous text, two for dense reference,
  three or more for magazines. A skilled designer uses the grid actively and sometimes leaves it.
- p. 197: a responsive grid changes with the output device.
- p. 198: automated grids for collections (search results, boards) take an irregular pulse from the
  varied shapes of the content.

## What to check on a screen

- The grid is declared: column count, gutter and margin per breakpoint, in `DESIGN.md` or the CSS.
- Block edges land on column lines; the empty columns are as deliberate as the full ones.
- The layout is not a centred stack by default; the open space has a place on the grid.
- On phone the grid collapses to its own column count, not a squeezed desktop grid.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757, with column guides overlaid
from the declared grid.

- **PASS:** block edges fall on column lines, margins are equal on both sides, and at least one area
  is left open by choice on desktop.
- **FAIL:** no declared grid, edges that miss the columns by a few pixels, unequal margins, or every
  section centred with the sides empty by default.

Observable: the overlay capture and each edge off the grid.

## Used at

**Look**, **build** and **critique**. Feeds rubric B2, B8 and T14 (the phone layout designed, not
shrunk). Element widths are `ui-content-width`; line length is `type-scale`.
