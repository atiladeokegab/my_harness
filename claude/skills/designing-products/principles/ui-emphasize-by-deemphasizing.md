# Emphasise by quieting the rest

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Hierarchy is Everything": "Emphasize by
de-emphasizing" and "Balance weight and contrast", pp. 46-47 and 56-59. Paraphrased in our words;
anything quoted is marked and at most one sentence.

**Principle.** When the main element does not stand out, turn its competitors down instead of turning
it up.

## Why it holds

- Making the primary thing louder starts an arms race: everything grows, bolds and brightens, and the
  screen gets louder without getting clearer.
- Lowering the competitors gives the main element contrast for free: inactive nav items in a softer
  colour, or a competing sidebar with no fill of its own, sitting on the page background (pp. 46-47).
- Krug's `clear-areas-low-noise` asks for less noise; this is how to lower it without deleting.
- Weight and contrast balance each other (pp. 56-59): a solid icon covers more area than the text
  beside it, so give it a softer colour; a 1 px border too faint in a soft colour gets more width
  rather than a harsher colour.

## What to check on a screen

- The element that matters most is the only one at full strength in its area.
- Icons sitting beside text are no louder than the text they label.
- Secondary panels (sidebars, filters, toolbars) are visually quieter than the content they serve.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Name the screen's most important element (from the brief or its heading).
2. Blur or squint at the capture until text is unreadable; list what still stands out.

- **PASS:** the most important element is among the first two things still visible when blurred, and
  no sidebar, icon row or decoration stands out more than it does.
- **FAIL:** a secondary panel, icon set or decoration is the strongest shape when blurred.

Observable: what stands out when blurred, in order.

## Used at

**Critique.** A fix names the competitor to turn down, not the element to turn up.
