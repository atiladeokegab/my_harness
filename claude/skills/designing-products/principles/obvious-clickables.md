# Make it obvious what is clickable

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 1 and ch. 3 "Billboard
Design 101", with an example from ch. 7. Paraphrased in our words; anything quoted is marked and at
most one sentence.

**Principle.** At a glance, without hovering or trying, a user must be able to tell what can be clicked
or tapped and what cannot.

## Why it holds

- Ch. 1: no one should spend even a moment wondering whether something is a button. The pointer that
  changes on hover is no defence: every such question still adds load. (On a phone there is no hover
  at all; that note is ours.)
- Ch. 3: most of what people do on a screen is look for the next thing to click. Krug's examples: a
  campaign site that coloured all of its text, so its eighteen links could not be told apart from
  prose; a search button that did not look like one, its arrow pointing away from its label.
- Making people think about something that should be automatic spends the small store of patience and
  goodwill each visitor brings.
- The reverse also costs: in ch. 7 testers tried to click numbered steps that were not links.

## What to check on a screen

- One link style, never used for plain text or headings.
- Buttons look pressable (shape, fill or border) and are labelled with a verb.
- Nothing decorative looks actionable: numbered steps, shadowed cards with no action, coloured headings.
- On phone, each tap target looks at least about 44px in both directions (our threshold).

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. If the builder supplied the list
of interactive elements, compare against it; otherwise judge by look alone.

- **PASS:** every actionable element shows its affordance without hover (button shape, underline or a
  colour used only for links, chevron, input box) and nothing non-actionable shares that look. On phone,
  no tap target looks clearly smaller than a fingertip.
- **FAIL:** any element whose clickability you would have to test by hovering or trying, or a mismatch
  with the supplied list.

Observable: each ambiguous or mismatched element, with what it looks like and what it is.

## Used at

**Critique.** The finish check runs it on every screen.
