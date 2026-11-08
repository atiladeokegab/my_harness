# One harmony, one accent, tinted neutrals

Source: written from first principles for this skill. The colour-wheel schemes are long public
knowledge; hue angles are measured in OKLCH (CSS Color 4; Björn Ottosson, "A perceptual color space
for image processing", 2020, public). Every threshold is ours.

**Principle.** The palette follows one named harmony around the seed's hue; one accent does one job;
the neutrals lean toward the scheme instead of pure grey.

## Why it holds

- **Tonal:** the seed's hue only; calm, the safest for tools people use all day. **Analogous:** the seed
  and a neighbour 30 degrees round; warm or cool, never jarring. **Complementary:** the opposite hue
  (180) as the neutrals' tint or a rare second voice; the most contrast, so it needs the most restraint.
  **Split:** two hues either side of the opposite (150 and 210); contrast with less clash.
- OKLCH keeps lightness perceptual, so the same step in two ramps looks equally light; in HSL a yellow
  and a blue at "50%" are nowhere near each other. That is why `palette.mjs` builds ramps in OKLCH.
- One accent means the eye always knows where to act. Support hues mark identity (a person, a lane, a
  category), never actions; a second action colour splits attention (rubric B3).
- A grey with a trace of the seed's hue (OKLCH chroma about 0.01 to 0.02) reads as chosen; pure
  `#808080` reads as a default. Complementary schemes tint the neutrals with the opposite hue instead.

## What to check

- DESIGN.md's `colors` comment names the harmony, and its ramps match it (`support` exists only for
  analogous, complementary and split).
- Every clickable thing uses the accent, a neutral, or the danger state for destructive actions.
- Greys on the capture are faintly the scheme's hue, not neutral.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** clickable elements use one saturated hue (the accent), plus danger only on a destructive
  action; support hues appear only on non-clickable marks; the largest grey area is tinted.
- **FAIL:** two or more saturated hues on clickable elements; a support hue on a button or link; a hue
  on screen that DESIGN.md's harmony does not produce; neutral greys with no tint at all.

Observable: the list of hues on clickable elements, and the hue of the largest grey area.

## Used at

**Look** (step 3: each card names its harmony; step 4: `palette.mjs --harmony`) and **critique**.
