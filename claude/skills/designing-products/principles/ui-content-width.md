# Give content the width it needs, not the screen's

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Layout and Spacing": "You don't have to
fill the whole screen" and "Grids are overrated", pp. 76-90. Paraphrased in our words; anything quoted
is marked and at most one sentence.

**Principle.** Each element gets the width that suits it; on a wide screen leave space empty or split
into columns rather than stretching a form, a paragraph or a card to fill the row.

## Why it holds

- Having 1200 to 1400 px does not oblige you to use it: if a thing needs 600 px, give it 600 px.
  Stretching makes an interface harder to read, and margin round the edges costs nothing (pp. 76-78).
- A section need not be full width because the navigation is (p. 77).
- Hard to design something small on a large canvas? Start mobile first on a canvas of about 400 px, then
  widen and fix only what felt compromised (pp. 78-79).
- A narrow element that looks lost in a wide layout can split into columns (a form beside its
  supporting text) instead of growing (pp. 79-81). Equally, don't cram what needs room (p. 82).
- Grids are a tool, not a rule: a sidebar gets a fixed width suited to its content while the main area
  flexes; a card gets a max-width and shrinks only when the screen forces it (pp. 84-90).

## What to check on a screen

- Forms, settings panels, dialogs and login cards have a sensible maximum width.
- Sidebars hold a fixed width at desktop size.
- Wide screens show deliberate space or columns, not elements stretched edge to edge.

## Pass or fail test

Desktop 1280x633 (the 720 px limit is our threshold):
- **PASS:** no single form field, button or paragraph spans more than about 720 px; anything wider
  holds columns, a table or media.
- **FAIL:** a stretched input, a full-width paragraph, or one card filling the row with a few lines.

Phone 390x757:
- **PASS:** no horizontal scroll; tables and code scroll inside their own box.
- **FAIL:** the page scrolls sideways or content is cut off at the right edge.

Observable: the widest single element at each size, with its rough width.

## Used at

**Build** (mobile first, max widths in the layout) and **critique**.
