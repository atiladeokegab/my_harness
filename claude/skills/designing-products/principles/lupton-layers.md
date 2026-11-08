# Layers: each kind of information gets its own channel

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Layers", pp. 140-153. Page numbers
are that edition's. Paraphrased in our words; anything quoted is translated, marked and at most one
sentence.

**Principle.** When a screen stacks several kinds of information on one surface (a map, a chart, a
timeline, an overlay on live content), give each layer one visual channel of its own so it can be read
alone and against the others, and let the user switch layers on and off.

## Why it holds

- p. 141: maps and timelines use superimposed layers so that each level of data adds to the whole
  without losing its own identity.
- p. 148: map makers use colour, line, texture, symbol and type to build distinct levels, so a reader
  can follow one (which road joins two towns) and see how they connect (is the route flat or hilly).
  An aeronautical chart's purple radio lines read as a layer of their own.
- p. 148: Google Earth lets the user set the transparency of an added layer to control how far it
  separates from the base image.
- p. 150: parallel tracks (a score's staves, an editor's timeline) are the basic way to show events
  that happen at the same time.
- p. 141: a layered file lets a designer make variations quickly by turning layers on and off.

## What to check on a screen

- List the layers on the screen and the channel each uses: hue, line style, symbol, type style, value.
- No two layers share a channel; the base layer is the quietest.
- Layers the user may not need at once have a visible toggle, and a legend names every channel.
- Simultaneous series sit on parallel tracks or aligned axes, not interleaved in one list.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757, on any screen with two or
more stacked kinds of information.

- **PASS:** you can name each layer and its one channel, follow a single layer across the screen, and
  find its toggle or legend entry.
- **FAIL:** two layers distinguished only by a slight hue shift, a layer that hides the base where the
  subject is, or a layer with no legend entry.

Observable: the layer and channel table, and each clash.

## Used at

**UX** (what stacks on what), **build** and **critique**. Feeds rubric T2 (blur only where it shows a
real layer) and B5. Opacity between layers is `lupton-transparency`.
