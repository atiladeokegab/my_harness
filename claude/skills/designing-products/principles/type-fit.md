# The face fits the voice and the reading job

Source: written from first principles for this skill, on public material: WCAG 2.2 (W3C, 2023) SC 1.4.12
Text Spacing and 1.4.8 Visual Presentation; the open font licences of the faces named. No book is
paraphrased. Every threshold is ours.

**Principle.** The typeface is chosen from two things written down first: the brand's voice (PRODUCT.md's
one feeling) and the reading job (scanning status, reading long text, comparing numbers); a second family
earns its place by doing a job the first cannot.

## Why it holds

- Type is the voice before the words are read. A face picked because it is the default (rubric T5) gives
  the median product's voice; Impeccable's detector flags the overused ones, which then need a reason.
- The reading job decides the measurable traits: long reading wants a generous x-height and open shapes
  at 16px or more; dense tools want clear figures, `tabular-nums` in tables and distinct `1`, `l`, `I`;
  a display face only has to work large and short.
- Pairing works by contrast of role, not by mood: a display face for headings and a text face for
  reading, or a serif and a sans that share proportions. Two faces that look alike look like a mistake.
- One family is enough when it has the weights and widths for both jobs; a tool for operators usually
  needs one family and a monospace for code, nothing else.

## What to check

- DESIGN.md's Typography section names each family with one line: the voice it carries or the job it
  does. A face on the overused list has its `overused-font` ignore and the same reason.
- At most two families, plus a monospace only where code or IDs appear.
- The captures render in the named faces, not a fallback (compare against `brand.html`).

## Pass or fail test

Apply to DESIGN.md, then to each capture (1280x633, 390x757) beside `brand.html`.

- **PASS:** each family has a reason tied to the voice or the reading job; two families or fewer, plus
  an optional monospace for code; headings and body on the capture match `brand.html`'s faces.
- **FAIL:** a reason of "modern", "clean" or "popular"; three or more families; a monospace used for
  ordinary small text (T5); a capture in a system fallback where DESIGN.md names a web face.

Observable: the family list with its reasons, and the capture's letterforms beside `brand.html`'s.

## Used at

**Look** (step 3: each direction card names its faces and why) and **critique**.
