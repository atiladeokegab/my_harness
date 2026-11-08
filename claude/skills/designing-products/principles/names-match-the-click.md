# The name of a screen matches what was clicked

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 6 "Street signs and
Breadcrumbs" (page names) and ch. 7 (home and persistent navigation). Paraphrased in our words; anything
quoted is marked and at most one sentence.

**Principle.** The screen, panel or step a control opens must be titled with the words on that control,
and a section keeps the same name and order everywhere it appears.

## Why it holds

- Ch. 6: page names are the street signs of a product. Krug praises signs that are big and hang where
  you look, so finding your bearings costs no attention. Every screen needs a name, placed to frame its
  own content and prominent enough to read as that content's heading.
- The unspoken deal with users is that the title of the screen they reach matches the words they
  clicked. Each mismatch makes them stop and wonder why, and many small ones wear down trust in the
  makers. Small differences are fine when the equivalence is obvious ("Gifts for Him" opening "gifts
  for men").
- Ch. 7: the first screen's navigation may be laid out differently from the rest, but the section names
  must keep the same wording, order and grouping. Krug's counter-example renamed, dropped, added and
  reordered sections after the first screen, so users had to learn the navigation twice.
- Breadcrumbs help on deep products but never replace the screen name.

## What to check on a screen

- Every screen, panel, dialog and tour step shows a title.
- The title repeats the key words of the control that opened it (or an obvious synonym).
- Section names match in wording and order on the first screen, the menus, the footer and the tour.

## Pass or fail test

Needs two captures at the same size, desktop 1280x633 or phone 390x757: one showing the control
before the click, one after. In the tour, the card title and the control it spotlights can be in the
same capture.

- **PASS:** the title of the opened screen (or the tour card) contains the key words of the clicked
  label, or an obvious synonym, and is the largest heading in its content area.
- **FAIL:** quote both strings, or name the screen that has no title.

Observable: the label and title pair.

## Used at

**Tour.** Each step's title matches the control or view it shows. The UX step's vocabulary fixes the
names once for every surface.
