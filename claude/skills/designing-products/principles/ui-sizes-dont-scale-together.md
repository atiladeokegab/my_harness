# Sizes do not shrink together

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Layout and Spacing": "Relative sizing
doesn't scale", pp. 92-95. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** On a small screen, large things shrink much more than small things: a headline drops
sharply while body text barely moves, so no size should be defined as a fixed multiple of another.

## Why it holds

- The book's example (pp. 92-94): 18 px body with a 45 px headline (2.5 times) on desktop. On a phone
  the body may drop to 14 px, and 2.5 times that is 35 px, far too big; 20 to 24 px fits, only 1.5 to
  1.7 times. The ratio was never a real relationship.
- So the biggest elements must shrink fastest, and the gap between big and small narrows (p. 94).
- The same inside a component (pp. 94-95): a large button wants more generous padding than its font
  growth alone gives, a small one tighter, or the sizes look like zoom levels, not sizes.
- Our captures come in pairs (1280x633 and 390x757) exactly so this shows. `type-scale` already fails a
  heading of four lines at 390; this file adds the ratio and the action above the fold.

## What to check on a screen

- The phone headline is smaller in proportion to body text than the desktop one.
- The phone first screen still shows the headline, a line of support and the main action.
- Large and small buttons differ in padding, not only in font size.

## Pass or fail test

Compare the pair: desktop 1280x633 and phone 390x757 (line counts are our thresholds).
1. Estimate the headline's size against body text at each size.
2. Count the lines the headline takes on the phone; note whether the main action shows without scrolling.

- **PASS:** the headline-to-body ratio is clearly smaller on the phone, the phone headline takes at most
  three lines, and the main action is visible on both captures.
- **FAIL:** the same ratio at both sizes, a phone headline of four or more lines, or the main action
  pushed below the phone fold.

Observable: the two ratios, the phone headline's line count, and whether the action is on screen.

## Used at

**Build** (responsive sizes in the tokens) and **critique**.
