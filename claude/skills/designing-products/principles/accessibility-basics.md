# Accessibility basics

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 11 "Accessibility,
Cascading Style Sheets, and you", with ch. 6 on colour. Paraphrased in our words; anything quoted is
marked and at most one sentence.

**Principle.** A product is not usable unless it is accessible: first fix what confuses everyone, then
do the few basics that matter most.

## Why it holds

- Ch. 11: unless you have decided that people with disabilities are not your audience, you cannot call
  the product usable without accessibility. Krug's reason is simply that it is right and changes lives:
  a blind person can now read the daily paper alone.
- Fix confusion first. Whatever confuses most users confuses users of assistive technology at least as
  much, and recovering is harder for them. A standards-compliant but confusing product still fails.
- Screen-reader users scan with their ears (Theofanos and Redish's study, which Krug urges everyone to
  read). They hear the first words of a link or line and move on, so the key word must come first.
- The basics he lists, still valid: alt text on images (empty for decoration); labels tied to form
  fields; a skip-to-content link; everything works by keyboard; text that resizes; content in reading
  order in the source. His three-second test is enlarging the text: if nothing changes, it fails.
- Ch. 6: never rely on colour alone. About 1 man in 12 and 1 woman in 200 cannot see some colour
  differences, and many more people do not notice colour coding at all.

## What to check on a screen

- In code: alt text, labels, skip link, keyboard reach and visible focus, text zoom, source order.
- On screen: every colour-coded meaning has a second cue (text, icon, shape, weight).
- Link and button labels make sense out of context, lead with their key word, and are not repeated
  for different targets ("Learn more" twice).

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. List every meaning carried by
colour (errors, active state, status, chart series) and read every link and button label.

- **PASS:** each colour-carried meaning also has a non-colour cue; no two controls share a label for
  different targets; each label's first two words say where it goes.
- **FAIL:** name the colour-only meaning or the vague or duplicated label.

If a capture at 200% text zoom is supplied, it also fails on any clipped or overlapping text.
Observable: the colour cues and labels, each marked ok or failing.

## Used at

**Critique.** The finish check runs it on every screen; the code checks belong to the build's own tests.
