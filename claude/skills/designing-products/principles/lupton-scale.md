# Scale: one decisive size contrast, nothing stretched

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Scale", pp. 60-66. Page numbers are
that edition's. Paraphrased in our words; anything quoted is translated, marked and at most one sentence.

**Principle.** Give each screen one clear contrast of size between its main element and the rest, use
space and cropping to make things feel large, and never scale an image, logo or letter out of
proportion.

## Why it holds

- p. 61: when every element is about the same size, the design turns monotonous and static.
- p. 61: scale depends on context. A small element alone in a large space gains importance from the
  space around it; type that seems to run off the page reads as huge.
- p. 62: size is relative to neighbours. Contrast of size creates depth and movement; small things
  recede and large things come forward. A shape cropped by the page edge looks bigger than it is.
- p. 63: changes of scale can show differences in importance.
- p. 66: scaling width and height unequally distorts letters and images; strokes turn too heavy or too
  thin. Use a family's real condensed or wide styles instead.
- p. 61: what looks right on screen can look wrong at its final size; judge at the size it ships.

## What to check on a screen

- The largest element is the screen's subject, and it is clearly larger than the next thing down.
- Small important things sit in enough space to read as important.
- Every photo, logo and icon keeps its aspect ratio (`object-fit`, no forced width and height).
- No faux condensed or stretched type (`transform: scale` on text, a squashed logo).

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** one element is at least about twice the height of the next-largest text (our threshold),
  and it is the screen's subject; nothing is visibly stretched or squashed.
- **FAIL:** the three largest elements are within a step of each other, the largest is chrome or
  decoration, or any image, logo or glyph is distorted.

Observable: the three largest elements with their rendered heights, and any distorted asset.

## Used at

**Look** and **critique**. Feeds rubric T5 (no scale) and B6 (boldness spent once). The size steps
themselves come from `type-scale`; on a phone, `ui-sizes-dont-scale-together` sets how they shrink.
