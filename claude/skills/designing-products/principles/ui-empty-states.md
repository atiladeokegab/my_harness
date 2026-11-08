# Design the empty state first

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Finishing Touches": "Don't overlook empty
states", pp. 234-236. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** The screen before there is any data is designed, not left over: its call to action is the
most prominent thing on it, and controls that act on nothing are hidden.

## Why it holds

- Designs are usually drawn full of ideal data, so the empty case gets whatever the code falls back to:
  a blank table, headers over nothing, a zero.
- When a feature fills up with what users create, its empty state comes first, not last (p. 235):
  it is the user's first contact with the feature. Use an image or illustration if the guide allows,
  and make the call to action prominent.
- Tabs, filters, sort controls and search that do nothing without data should be hidden or quiet until
  there is content to act on.
- Overlap: `copy-errors-and-empty-states` owns the words (what will appear, the action's label); this
  file is the layout around them.

## What to check on a screen

- Capture each list, table, dashboard and inbox with no data (the fixture's empty case).
- What does the user learn, and what can they do next?

## Pass or fail test

Apply to each empty-state capture on its own: desktop 1280x633 and phone 390x757. If no empty-state
capture exists, the test fails with "no capture".

- **PASS:** the action that adds the first item is the most prominent element in the empty area, and no
  column headers, filters, tabs or sort controls sit over nothing.
- **FAIL:** a blank area, empty table headers, controls that act on nothing, or an action no louder
  than the surrounding text.

Observable: the most prominent element in the empty area, and any control over nothing.

## Used at

**UX** (empty states are designed with the journey) and **critique**.
