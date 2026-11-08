# Components do not have to look like their defaults

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Finishing Touches": "Think outside the
box", pp. 242-246. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Shape each component to its content: a table cell can hold a hierarchy, a dropdown can
have sections and icons, a set of options can be a set of cards.

## Why it holds

- The mental default for a component (a table is a grid of plain text, a dropdown is a white list, radio
  buttons are a stack of circles) is rarely the best version.
- Tables: a column that need not be sortable can merge with a related one (a name with its email
  under it in grey); add images or colour where they enrich the data (pp. 244-245).
- Dropdowns can be split into sections, carry icons and a line of help per item, or use columns.
- Important choices (a plan, a delivery speed) work better as selectable cards with room to explain each
  option than as bare radio buttons.
- Keep the convention recognisable: Krug's `use-conventions` still applies; richer, not stranger.

## What to check on a screen

- Tables with many plain columns of equal weight.
- Choices with consequences shown as tiny radios or a bare select.
- Lists where every row is one line of identical text.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every table with five or more columns either groups related fields in one cell or gives
  the key column more weight; choices that change price or outcome are shown with room to explain them.
- **FAIL:** a table of five or more equal-weight plain text columns, or a choice with consequences
  offered only as an unexplained select or radio list.

Observable: the table or choice checked and how it is shown.

## Used at

**UX** (choices as cards), **build** and **critique**.
