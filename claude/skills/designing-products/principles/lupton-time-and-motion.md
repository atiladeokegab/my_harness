# Time and motion: change that is asked for and readable

Source: Lupton and Phillips, *Graphic Design: The New Basics*, second edition, read in the Spanish
edition *Diseño gráfico: nuevos fundamentos* (Gustavo Gili), ch. "Time and Motion", pp. 232-247. Page
numbers are that edition's. Paraphrased in our words; anything quoted is translated, marked and at
most one sentence.

**Principle.** Treat motion as change over time with a job: pick the quietest mode of change that does
the job (opacity, colour, scale before travel), move only when the user asks or the state really
changes, and keep moving text slow enough to read.

## Why it holds

- p. 233: motion is change over time; on screen it includes entering and leaving, and changes of
  scale, transparency, colour and layer. These other modes suit text on the web, where gratuitous
  movement distracts more than it pleases or informs.
- p. 233: the screen can be a stage where an element stays put while its surroundings change.
- p. 234: stills imply motion too: diagonals look dynamic, shapes parallel to the frame look stable, a
  shape cropped by the edge seems to enter or leave.
- p. 242: animated type must stay legible and keep reading order; timing lets words change at a
  readable pace without lingering. A logo that keeps changing in a banner soon irritates.
- p. 244: storyboards and style frames plan the key moments before production.
- p. 246: an interactive graphic can stay still until the pointer reaches it, coming alive only when
  asked instead of distracting.

## What to check on a screen

- Each animation is named with its trigger and job: a user action, a state change, or a data update.
- Nothing loops or moves at rest except a live indicator of something live.
- Moving or changing text holds still long enough to read before it changes.
- Key moments of a sequence (a tour, an onboarding) are storyboarded as stills first.
- `prefers-reduced-motion` turns travel into a fade or a cut.

## Pass or fail test

Apply to a desktop 1280x633 and a phone 390x757 capture at rest, plus a short recording or frame
sequence of the main action.

- **PASS:** at rest nothing is mid-animation; each motion in the recording follows a user action or a
  state change; text is readable in every frame where it is meant to be.
- **FAIL:** sections caught at different opacities or offsets in a still, a marquee or pulse on
  something not live, or motion with no trigger.

Observable: each motion with its trigger, and anything moving at rest.

## Used at

**Build**, **tour** and **critique**. Feeds rubric T9 and B9 (reduced motion).
