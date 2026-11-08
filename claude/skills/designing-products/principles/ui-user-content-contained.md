# Contain what users upload

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Working with Images": "Beware user-
uploaded content", pp. 214-217. Paraphrased in our words; anything quoted is marked and at most one
sentence.

**Principle.** Show user images in fixed-size frames that crop to fit, and give them an edge that keeps
them off the background; the layout must not depend on what people upload.

## Why it holds

- Uploaded photos come in every shape and size. Letting them set their own dimensions breaks rows and
  grids the moment a tall or tiny image arrives.
- A fixed container with crop-to-cover keeps every thumbnail and avatar the same size.
- A photo with a background close to the page's colour bleeds into it. A subtle inner shadow keeps its
  shape, or a semi-transparent inner border; a solid border tends to clash with the image's colours.
- Our extension, not the book's: user text (names, titles, comments) must truncate or wrap without
  breaking the layout. Build fixtures with long and short content, not only the ideal case.

## What to check on a screen

- Avatars, thumbnails and cover images: same size and shape within a set?
- Light images on a light page: is there a visible edge?
- Long names or titles: truncated or wrapped cleanly?

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every image in a set (avatars, cards, gallery) has the same frame size and shape; none is
  stretched or squashed; long user text truncates or wraps inside its box.
- **FAIL:** mixed sizes or aspect ratios in one set, a distorted image, a light image melting into the
  page, or user text overflowing its container.

Observable: the image set checked, its frame sizes, and any overflow.

## Used at

**Build** (fixtures and frames) and **critique**.
