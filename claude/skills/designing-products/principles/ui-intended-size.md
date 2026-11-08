# Use images and icons at the size they were drawn for

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Working with Images": "Everything has an
intended size", pp. 208-213. Paraphrased in our words; anything quoted is marked and at most one
sentence.

**Principle.** Icons, screenshots and illustrations look right only near the size they were made for;
do not blow small icons up or shrink full screenshots down.

## Why it holds

- Icons drawn at 16 to 24 px look chunky and crude at three or four times that. If a feature row needs a
  big icon, put the small icon inside a larger tinted shape, or use icons drawn for large sizes.
- A full-app screenshot shrunk to fit a card turns its text into illegible noise. Capture it at
  a smaller layout (a tablet width), crop to the part that matters, or draw a simplified version with
  small text replaced by lines (pp. 210-212).
- Scaling down fails too: a logo drawn large turns to mush at favicon size, so redraw a simplified
  version at 16 px (pp. 212-213).
- On our sites the product is shown, not described; a picture of it is wasted if it is unreadable.

## What to check on a screen

- Icons larger than about 32 px: drawn for that size, or sitting in a shape?
- Product screenshots: is their text readable at this capture size?
- Any blurred or pixelated raster.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every icon has clean, even strokes at its shown size; every product screenshot shows readable
  text or is a crop or simplified drawing; no blurred or pixelated image.
- **FAIL:** a thin-line icon blown up so its strokes look heavy or blunt, a whole-app screenshot shrunk
  until its text is unreadable, or a pixelated image.

Observable: the worst offending icon or screenshot, and its approximate size.

## Used at

**Build** (choose the asset for its size) and **critique**.
