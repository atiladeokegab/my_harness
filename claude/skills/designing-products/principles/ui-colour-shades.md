# Use the defined shades; flip the contrast

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Working with Color": "You need more colors
than you think" to "Don't rely on color alone", pp. 142-168. Paraphrased in our words; anything quoted
is marked and at most one sentence.

**Principle.** Every colour on screen is one of the palette's defined shades, never lightened or darkened
on the spot; a coloured element that should not shout is a light tint with dark same-hue text, not white
on a dark fill; colour is never the only signal.

## Why it holds

- A real UI needs many shades: 8 to 10 greys and 5 to 10 of each primary and accent (pp. 143-147).
  `palette.mjs` builds those ramps; `colour-harmony` and `colour-roles` say which to use where.
- Shades made on the fly (lighten, darken, opacity) breed dozens of near-identical blues; pick from the
  fixed set, and add a shade rarely (pp. 148-151).
- Tints near white lose colour unless saturation rises there (pp. 152-157); a grey-looking tint means
  the ramp step is wrong, not that the component needs its own value.
- White text on colour needs a very dark fill to reach 4.5:1, and that fill grabs attention it should
  not. Flip it: dark text of the hue on a light tint of it (pp. 162-164).
- Colour alone fails colour-blind users: add an icon or a word; in charts vary lightness, not only hue
  (pp. 166-168). `accessibility-basics` and `colour-roles` say the same.

## What to check on a screen

- Badges, alerts, selected rows and status chips: tint with same-hue dark text, or a fill that is the
  one primary action.
- Tints that look grey, and near-identical shades of one hue side by side.
- Every state shown by colour also has a word or icon.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every secondary coloured element (badge, alert, chip, selected row) is a light tint with
  dark same-hue text; no tint looks grey; no two near-identical shades of a hue sit side by side; every
  coloured state carries a word or icon.
- **FAIL:** a secondary element in a dark fill with white text, a grey-looking tint, near-duplicate
  shades side by side, or a state shown by colour alone.

Observable: each coloured element with its fill and text, and any colour-only state.

## Used at

**Look** and **critique**. Building the ramps is `palette.mjs`'s job, not this file's.
