# Round 2 specimen rules (tournament.md §2, "2 builder")

- Build the content sheet's Screen 1 as one full specimen: `<your dir>/index.html`, one file, CSS inline,
  no JS needed (a tiny inline script is allowed only if the direction needs it). Its words verbatim from the
  content sheet. It must hold at 1280x633 and at 390x757 (a phone layout designed, not shrunk).
- Keep your own line's memorable thing and layout idea; make it finished: real type scale, one spacing
  scale, one accent spent on the action or the live state, states in place in plain words.
- A real display face, self-hosted: copy latin woff2 files into `<your dir>/fonts/` and @font-face them.
  Already on disk (OFL, pinned): $HOME/.claude/skills/designing-products/kit/node_modules/@fontsource/{literata,jost,ibm-plex-sans,source-sans-3}/files/.
  For another family: `cd <your dir> && timeout 90 npm i -E --no-save @fontsource/<family>` (OFL faces only;
  copy the woff2 out, then delete node_modules). No font CDN, no platform font as the display voice.
- At 390: a figure is redrawn for the phone (fewer parts, labels beside it, not on it), never scaled down to
  fit; no text under 12px; body 16px; tap targets 44x44.
- Craft floor: visible :focus-visible ring in the palette, prefers-reduced-motion respected, ::selection,
  caret-color, scrollbar-color, tabular-nums on numbers, body measure 65 to 75ch, letter-spacing no tighter
  than -0.04em, contrast 4.5:1 for body text.
- No external images. Inline SVG for drawings.
- You may render twice at most to check: `$HOME/.claude/skills/designing-products/reference/fixtures/capture.sh file://<your dir>/index.html <your dir>/check`
  (writes check-desktop.png and check-mobile.png). Look at both.
- Read $HOME/.claude/skills/designing-products/reference/rubric.md §5 and §6 (the tells and the bar) before building.
- Time cap: 7 minutes. Build in one pass, render once, fix what you see, stop. A slot past its cap is dropped.
