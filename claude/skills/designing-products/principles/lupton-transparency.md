# Transparency: show what is behind, and pay for it in contrast

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Transparency", pp. 154-165. Page
numbers are that edition's. Paraphrased in our words; anything quoted is translated, marked and at most
one sentence.

**Principle.** Use partial opacity only to keep what lies underneath in view (a scrim over a page, a
sheet over a live map, a fade between states), never to tone down text or decorate a surface.

## Why it holds

- p. 155: a transparent colour square looks dull until it sits over another shape. Transparency is only
  ever seen relative to what is behind, and it raises a question: what is in front and what recedes?
- p. 155: used deliberately, transparency can stand for openness and clarity, provided the elements
  keep their integrity and legibility.
- p. 162: making an image transparent lowers its intensity and its overall contrast; software blends
  the tones of one layer with the other.
- p. 162: in time-based media a fade is transparency over time; video fades to black or to white.
- For us: translucent text or a translucent fill changes colour with whatever scrolls under it, so its
  contrast cannot be checked once and trusted.

## What to check on a screen

- Every translucent surface has a reason: name what behind it must stay visible.
- Secondary text gets a solid colour token, never `opacity` or an alpha ink.
- Text on any translucent surface passes 4.5:1 against the busiest thing that can sit behind it.
- No glass, blur or frosted card where nothing meaningful sits underneath.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757, plus one capture with the
busiest content scrolled under each translucent surface.

- **PASS:** each translucent area names what it reveals, and its text stays readable over the busiest
  backing.
- **FAIL:** opacity used on text or icons for hierarchy, a translucent card over a plain ground, or
  text whose contrast drops below 4.5:1 when content passes under it.

Observable: each translucent element, what it reveals, and its worst-case contrast.

## Used at

**Build** and **critique**. Feeds rubric T2 (glass and blur) and B9 (contrast). Text on colour is
`ui-no-grey-on-colour`; text on photos is `ui-text-on-images`.
