# Numbers as numerals, each with its source

Sources: Jakob Nielsen, "Show Numbers as Numerals When Writing for Online Readers" (Nielsen Norman Group,
2007), nngroup.com; GOV.UK, "A to Z style guide" (numbers), guidance.publishing.service.gov.uk; rubric
tell T7. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Write every number as digits. Every number that makes a claim (a percentage, a multiple,
a saving, a count of users) shows its source beside it, or says it is illustrative.

## Why it holds

- Nielsen: digits stop a scanning eye and draw a fixation; a spelled-out number reads as one more
  word. He uses digits even at the start of a sentence and for big numbers ("2,000,000" over "two
  million"), and spells out only vague amounts ("thousands").
- GOV.UK also uses digits from 2 upward but keeps "one" and spells out a number that opens a sentence.
  For facts on a product screen we follow Nielsen (our choice): the number is the point.
- A number reads as a measurement. Without a source it is an invented stat, rubric tell T7, and the
  judge who checks one stops trusting the rest.
- Sample data counts. A demo dashboard showing "8.3% CPU reduction" is read as a result unless it says it
  is sample data (the baseline in `reference/copy.md`).

## What to check on a screen

- Digits for every fact; words only for vague amounts.
- Each claim number has a visible source next to it (a citation, a footnote mark, a link to the method)
  or an "illustrative" or "sample data" label on the same element.
- The copy gate flags a percentage or multiple with no source marker within a line; counts and money
  claims are the eye's job.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. List every number in view.

- **PASS:** every fact is in digits, and every claim number has its source or label visible in the same
  capture (a footnote mark counts when the note is one tap or scroll away).
- **FAIL:** quote each number that is spelled out or has no source, with what it claims.

Observable: the numbers and their sources, or "none".

## Used at

**Critique** (the copy pass), and **build**: the gate in the smoke catches unsourced percentages and
multiples.
