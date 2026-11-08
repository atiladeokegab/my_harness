# Hierarchy levels: one clear signal per step down

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Hierarchy", pp. 128-139. Page numbers
are that edition's. Paraphrased in our words; anything quoted is translated, marked and at most one
sentence.

**Principle.** Decide how many levels the content has, mark the step between each level with a clear
and consistent signal, and cut every signal that repeats what another already says.

## Why it holds

- p. 129: hierarchy is carried by scale, value, colour, spacing and placement. However simple or rich
  it is, it needs clear marks of separation between one level and the next. Without it, communication
  is monotonous and hard to navigate.
- p. 129: in interactive work the user often picks the order, and one structure can take a different
  visual hierarchy on each device.
- p. 130: a weak table of contents repeats the word "Chapter" 24 times, keeps page numbers far from
  their titles, and mixes justified, centred and ragged alignment.
- p. 131: page numbers aligned right beside their titles; chapter numbers dropped because the order
  already shows the sequence.
- p. 132: one family is enough. Each level can be marked by one cue or several: a line break, a style,
  a size, a rule.
- pp. 129 and 136: a newspaper page with its content pixelated still shows its hierarchy.

## What to check on a screen

- Count the levels (page title, section, item, meta). Each level looks the same everywhere it appears.
- Between neighbouring levels there is a visible step; within a level, no variation.
- One alignment system per list or menu; labels and their values sit next to each other.
- No double markers: a numbered list does not also say "Step", a section heading does not also need an
  icon and a coloured bar to say the same thing.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. Blur it until text is unreadable.

- **PASS:** the blurred capture still shows the levels in order, at most four on one screen (our
  threshold), each level styled the same throughout, one alignment per list.
- **FAIL:** two levels that look identical, one level with two styles, a fifth level, mixed
  alignments in one list, or a redundant marker.

Observable: the level list with each one's style, and each break from it.

## Used at

**UX** and **critique**. Feeds rubric B1 and T10 (numbers on content that is not a sequence). The
ranking test is `visual-hierarchy`; weight and grey steps are `ui-hierarchy-by-weight`.
