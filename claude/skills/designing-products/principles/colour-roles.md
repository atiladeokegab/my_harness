# Every colour has a role, and every text pair is checked

Source: written from first principles for this skill, on WCAG 2.2 (W3C, 2023) SC 1.4.3 Contrast
(Minimum), 1.4.11 Non-text Contrast and 1.4.1 Use of Color, and the APCA notes (Myndex, apca-w3, public);
data colours are the dataviz skill's formula and validator. The 60-30-10 split is a public rule of thumb.

**Principle.** Components use role tokens (surface, ink, accent, states, data), never ramp steps or raw
values, and every text and background pair a role allows passes AA in each theme the product ships.

## Why it holds

- Roles are decisions; ramps are raw material. `bg`, `surface`, `border`; `ink`, `muted`; `accent`,
  `on-accent`, `accent-text`; `success`, `warning`, `danger`, `info`; `data-1` to `data-8`. A builder
  who reaches for `accent-300` is making a new decision the guide did not make.
- WCAG 1.4.3 asks 4.5:1 for text, 1.4.11 asks 3:1 for a control against what is around it. The seed is
  the accent in every theme the product ships; with both, it must sit in a narrow luminance band: dark
  enough to be a control on the light page, light enough on the dark one, and still carry a label.
  `palette.mjs` refuses a seed outside it rather than quietly moving the brand colour. A product that
  commits to one theme declares `themes: [dark]` or `[light]` in DESIGN.md and is checked on that one.
- APCA (the candidate for WCAG 3) tracks what people see more closely, mostly for thin text and dark
  themes; where the two disagree, go by APCA for design and by WCAG 2 where conformance is the ask.
- Data colours have their own rules (CVD separation, fixed order); the dataviz validator owns them.
- 60-30-10 (neutrals, secondary, accent by area) is a check that the accent stayed rare, not a law.

## What to check

- Text on a capture sits on one of the pairs `brand.html` lists with a passing number.
- The accent covers about a tenth of the screen or less; it marks the action or the live state.
- The default theme has a reason from the use scene (rubric T13), written in DESIGN.md's Overview.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757, beside the product's `brand.html`.

- **PASS:** every text and background pair on screen is one `brand.html` shows as passing; the accent
  covers 10% of the screen or less by eye (our threshold); no chart colour outside `data-*`.
- **FAIL:** text on a pair `brand.html` lacks or marks as failing (muted on accent is the usual one);
  the accent floods a panel or a hero; a chart in ad hoc colours.

Observable: each text pair named by its roles, and the accent's share of the capture.

## Used at

**Build** (every component takes roles from `tokens.css`) and **critique** (the finish check).
