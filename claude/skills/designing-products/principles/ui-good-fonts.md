# Pick a well-made typeface

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Designing Text": "Use good fonts", pp.
108-112. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Shortlist only well-made faces: families with five or more weights, and for interface text
none that is condensed or has a short x-height; display faces stay out of small text.

## Why it holds

- A fairly neutral sans is the book's safe choice for UI (p. 108); our rubric treats an unchosen
  default as a tell, so the safe choice still needs `type-fit`'s written reason.
- Families with five or more weights tend to be made with more care; filtering a font directory to ten
  or more styles (weights plus italics) cuts most of the weak options (pp. 109-110).
- Faces are drawn for a purpose: headline faces are tight with a short x-height, text faces wider with a
  tall one. Avoid condensed, short x-height faces for main UI text (p. 110).
- Popularity and what admired design teams use are good ways to shortlist (pp. 110-112), never the
  reason itself (`type-fit` fails a reason of "popular").
- Overlap: `type-fit` (T-1009) decides which face suits the product from first principles; this file
  is the book's quality floor beneath that choice.

## What to check on a screen

- The body and UI face: legible at small sizes, tall x-height, not condensed.
- The family in use offers several weights (visible as at least two distinct weights used well).
- A display or decorative face appears only at headline sizes.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** the smallest UI text (labels, captions, buttons) is set in a non-condensed face with
  lowercase letters clearly taller than half the capitals, and any decorative face appears only in
  headings.
- **FAIL:** condensed or short x-height text at small sizes, a display face in body or button text, or
  faux bold or italic (smeared or slanted shapes where the family lacks the style).

Observable: the face of the smallest UI text, and where any display face appears.

## Used at

**Look** (the face is chosen with the direction) and **critique**.
