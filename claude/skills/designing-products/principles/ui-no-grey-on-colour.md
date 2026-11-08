# No grey text on a coloured ground

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Hierarchy is Everything": "Don't use grey
text on colored backgrounds", pp. 42-44; ch. "Working with Color": "Greys don't have to be grey", pp.
158-160. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** On a coloured background, lower the contrast of secondary text by moving it toward the
background's own hue, never by making it grey.

## Why it holds

- On white, grey is a way to get less contrast. On a coloured panel, grey looks washed out and dirty,
  because it is a different hue from everything around it.
- Pick a lighter or darker shade of the background's hue (light-on-dark: a pale tint of the hue; dark-on-
  light: a deep shade of it), chosen by hand rather than by setting white to partial opacity, so it does
  not let a busy image or pattern show through.
- Greys need not be grey at all: a little blue reads cool, a little yellow or orange warm, with more
  saturation at the light and dark ends to hold the temperature (pp. 158-160). `colour-harmony` sets
  this cast in the tokens.

## What to check on a screen

- Secondary text on any coloured panel, hero, banner or button shares the panel's hue.
- The greys used on the neutral ground share one temperature.
- No text uses partial opacity over an image or a pattern.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Find every area with a saturated or tinted background (hero, banner, coloured card, footer).
2. Look at the secondary text in each.

- **PASS:** secondary text in each coloured area is a tint or shade of that area's hue, or full white or
  full ink; none looks a neutral grey.
- **FAIL:** neutral grey text on a coloured area, or greys of clearly different temperatures side by side.

Observable: each coloured area and the colour of its secondary text.

## Used at

**Look** (the tokens give each coloured ground its own muted text colour) and **critique**.
