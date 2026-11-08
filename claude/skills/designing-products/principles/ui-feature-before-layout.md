# Start with the feature, not the layout

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Starting from Scratch": "Start with a
feature, not a layout", "Detail comes later" and "Don't design too much", pp. 8-19. Paraphrased in our
words; anything quoted is marked and at most one sentence.

**Principle.** Design the thing the product actually does first; the shell around it (navigation,
sidebar, header, footer) comes last and stays smaller than the feature.

## Why it holds

- An app is a set of features (pp. 8-9). Drawing the frame first leaves an empty box that tells you
  nothing about what goes in it, so the frame gets decided before anyone knows what it must hold.
- Working on one real feature (a search form, a result, a booking) forces the real fields, states and
  labels, and those decide the layout.
- Detail comes later: leave typefaces, shadows and icons for now, and work in greyscale so spacing,
  contrast and size carry the hierarchy before colour is added (pp. 12-13). `rough-before-finished`
  makes the same case for staying rough.
- Work in short cycles: design a simple version, build it, fix what the real thing shows. Do not show
  functionality you are not ready to build; design the smallest version that can ship (pp. 16-19).
- Our note: generated products often do the opposite, a polished sidebar, header and empty dashboard
  grid around a feature that is a single grey card. That is a tell that nobody designed the product.

## What to check on a screen

- The feature that does the product's job is the largest working thing on the first screen.
- Navigation, header and footer together take less space than the feature.
- No placeholder panels, empty grids or "coming soon" cards stand where the feature should be.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Shade the area of the product's main feature (the input, result or object the brief names).
2. Shade the area of the chrome: navigation, header, footer, sidebar, logo row.

- **PASS:** the feature area is larger than the chrome area, and the feature shows real content or a
  real input, not a placeholder.
- **FAIL:** chrome is larger, or the feature area is a placeholder, skeleton or empty frame.

Observable: the two shaded areas as rough fractions of the capture.

## Used at

**UX** (the first screen's layout) and **build** (the first vertical builds the feature before the
shell).
