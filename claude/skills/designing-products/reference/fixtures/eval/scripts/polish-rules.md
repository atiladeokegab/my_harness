# Round 3 polish rules (tournament.md §2, "3 polisher")

- Start from your round-2 page (`start.html` in your dir, its faces in `fonts/`). Preserve the direction;
  never redesign. Apply the round-2 judge's three changes to you (`verdict.md` in your dir).
- Build four screens from the content sheet, one HTML file each, one shared look:
  `screen-1.html` the first screen, `screen-2.html` the detail, `screen-3.html` the state,
  `screen-4.html` the action's result. Words verbatim from the content sheet. Every screen holds at
  1280x633 and 390x757.
- A state is drawn where the visitor meets it, in plain words, never as a legend explaining the design.
- At 390 a figure is redrawn for the phone (fewer parts, labels beside it, not on it), never scaled down to
  fit; no text under 12px; body 16px; tap targets 44x44.
- Craft floor: read $HOME/.local/share/impeccable/skill-v4.8.0/skill/reference/craft-floor.md and
  $HOME/.claude/skills/designing-products/reference/rubric.md (§5 tells, §6 bar). Visible :focus-visible ring in the palette, reduced motion
  respected, ::selection, caret-color, scrollbar-color, tabular-nums on every number, body measure 65 to 75ch,
  letter-spacing no tighter than -0.04em, 4.5:1 body contrast. Self-hosted faces only, no CDN, no images.
- Measure, then fix, until every line is PASS (never by hiding content):
  `cd $HOME/.claude/skills/designing-products/reference && node evidence.mjs <your dir>/ev <your dir>/screen-1.html <your dir>/screen-2.html <your dir>/screen-3.html <your dir>/screen-4.html`
  (prints PASS/FAIL per check; writes ev-evidence.md).
- Render to look, three passes at most: `$HOME/.claude/skills/designing-products/reference/fixtures/capture.sh file://<your dir>/screen-N.html <your dir>/look-N`.
- Time cap: 10 minutes.
- Copy: every number carries its source or an illustrative mark in the same viewport at both sizes; one idea
  per line; a state is named by what happened, not by how it is drawn.
