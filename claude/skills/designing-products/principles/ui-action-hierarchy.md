# One primary action per view

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Hierarchy is Everything": "Semantics are
secondary", pp. 60-62. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Style actions by their importance on this screen: one solid primary, quieter secondary
actions, link-styled tertiary ones; a destructive action is big and red only when it is the main job.

## Why it holds

- Giving every button a solid fill by its meaning (blue for save, red for delete, grey for cancel) makes
  them all equal, and the user has to read each one to find the next step.
- Primary: solid, high-contrast fill. Secondary: outline or low-contrast fill. Tertiary: looks like a
  link. The levels follow what the user most likely wants to do here.
- Delete on a settings page is rare, so it can be a secondary or tertiary button; the confirm dialog
  that follows makes it primary and red, because there it is the main action.
- Tertiary actions styled as links must still read as clickable (Krug's `obvious-clickables`).
- Lesson 20 in our ledger (one big button that runs the main workflow) rests on this.

## What to check on a screen

- Exactly one solid, high-contrast action per view or per dialog.
- Secondary actions are visibly quieter; tertiary ones read as links.
- A red or destructive style appears only where destroying is the screen's main job.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. List every button and button-like link, and mark which have a solid, saturated fill.
2. Name the screen's main action from the brief.

- **PASS:** one solid fill per view (a sticky header's single call to action may add a second), it is the
  main action, and no destructive action is solid unless destroying is the main action.
- **FAIL:** two or more equal solid buttons competing in one view, the main action not the solid one,
  or a solid red button on a screen whose job is not deleting.

Observable: the button list with fills, and the main action.

## Used at

**UX** (each screen's one action), **look** (the three button tiers in the tokens) and **critique**.
