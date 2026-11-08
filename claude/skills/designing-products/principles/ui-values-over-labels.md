# Show the value, not a label beside it

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Hierarchy is Everything": "Labels are a
last resort" and "Separate visual hierarchy from document hierarchy", pp. 48-55. Paraphrased in our
words; anything quoted is marked and at most one sentence.

**Principle.** Present data so its format or context explains it; when a label is needed, it is
supporting text. A section title that only names its content can be small.

## Why it holds

- A stack of "label: value" lines gives every datum equal weight, so nothing can be emphasised (p. 48).
- Often the format says what a value is (an email address, a phone number, a price), or the context
  does (a department under a name in a staff list). Without labels, the important data can lead (p. 49).
- A short phrase can fold label and value together: our example, "4 seats left" in place of
  "Seats: 4" (pp. 49-50).
- Where a label is needed (a dashboard of similar figures), quiet it: smaller, lower contrast or
  lighter weight (pp. 50-51). Where users hunt for the label (a spec sheet), the label may lead, but
  only slightly: a darker label, a slightly lighter value (pp. 51-52).
- Heading tags are structure, not size. A panel title like "Account settings" acts as a label; keep it
  small so the content wins, or even hide it visually and keep it for screen readers (pp. 54-55).

## What to check on a screen

- Values are as prominent as their labels or more, except on spec-style lists.
- Label and value pairs are folded into one phrase where that reads naturally.
- Panel and section titles that only name the content are quieter than the content.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. Find every label and value pair, and every titled panel.
2. Compare each label with its value, and each panel title with its first item.

- **PASS:** values at least as prominent as labels (on a spec list the label may lead by colour only),
  and no panel title is the loudest thing in its panel unless the panel's job is to be found by name.
- **FAIL:** labels louder than values on ordinary data, or panel titles that outshout their content.

Observable: the pairs checked and which side wins in each.

## Used at

**Look**, **build** (dashboards, profiles, detail panes) and **critique**.
