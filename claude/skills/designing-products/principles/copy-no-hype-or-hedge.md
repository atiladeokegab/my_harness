# No hyped or hedged words

Sources: GOV.UK, "A to Z style guide" (words to avoid; metaphors), guidance.publishing.service.gov.uk;
Digital.gov, "Plain language guide series: Clear and short" (adapted from PlainLanguage.gov); the lead's
list in rubric tell T7. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Make the claim plainly with its evidence, or cut it. No hype word inflates it and no hedge
softens it.

## Why it holds

- A hype word (seamless, powerful, revolutionary, best-in-class) is a claim the reader cannot check, so
  they discount it, and the page around it. It is also one of the tells that a model wrote the page
  (rubric T7).
- A hedge (can help, may, simply, arguably) says the writer is not sure what the product does. Digital.gov
  asks for direct, active sentences that say who does what; a hedge is the opposite.
- GOV.UK bans abstractions such as robust, leverage and empower for all of its content, and rejects
  metaphors because they do not say what is meant. The fix for both is the same: the fact underneath.
- A number in place of an adjective is the strongest rewrite: "under 2 seconds", with its source
  (`copy-numbers-with-a-source`), beats "blazing fast".

## What to check on a screen

- `make check-design` runs `check-copy.mjs` against `reference/copy-banned.txt` (the lead's words, GOV.UK's
  abstractions and metaphors, the common hedges); a hit is fixed or carries `copy-ok: <reason>`.
- What the list cannot see: runs of three adjectives, "the future of", "for the modern team", praise of
  the user ("smart teams"), and exclamation marks in running text.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. Read all visible text.

- **PASS:** no word from the list and none of the unlisted kinds above, and the copy gate exits `0`.
- **FAIL:** quote each hit with its kind (hype, hedge, abstraction, metaphor) and the fact that should
  replace it, or "cut".

Observable: the quoted hits, or "none".

## Used at

**Build** (the gate in the smoke) and **critique** (the finish check reads what the list misses).
