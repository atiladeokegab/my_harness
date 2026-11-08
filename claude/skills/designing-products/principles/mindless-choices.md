# Every choice mindless and unambiguous

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 4 "Animal, vegetable,
or mineral?", with ch. 7 on pulldowns and ch. 9 on "kayak" problems. Paraphrased in our words; anything
quoted is marked and at most one sentence.

**Principle.** Make each choice the user faces obvious; how hard each click is matters more than how
many clicks there are.

## Why it holds

- Ch. 4, Krug's second law: people tolerate many clicks if each is effortless and they keep believing
  they are on the right track (Jared Spool's "scent of information"). His rough rate is that three
  mindless clicks are worth one that needs thought. Fewer clicks matter more only for steps repeated
  often or screens that load slowly.
- The model is the guessing game's first question, animal, vegetable or mineral: anything fits one
  answer with no thought. Real interfaces fail that: a Home or Office split when the buyer runs a home
  office; a product listed under an internal abbreviation; two mailboxes where your letter fits both.
- Ch. 7: pulldowns hide their options, so nothing on the list can catch the eye; they are hard to scan
  and twitchy. They suit only lists of known names (countries, states); elsewhere show the list.
- Ch. 9: if half the testers try the wrong category first and everyone finds it on the second try,
  that is acceptable; an item lives in one place, with a cross-link where people also look.

## What to check on a screen

- Sibling options are in the user's words and do not overlap; users can tell which one is theirs.
- Nothing is asked that the system could infer.
- Open-ended choices are visible lists, not dropdowns.
- Each step shows the user they are still on the path (the label they chose echoes on the next screen).

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. Take every visible choice set
(navigation items, tabs, radio groups, buttons side by side, dropdowns).

- **PASS:** no pair of sibling options where a first-time user could reasonably think their item
  belongs under both or under neither, and no dropdown hiding an open-ended list (known names, dates
  and sizes are fine).
- **FAIL:** name the ambiguous pair and an item that falls between them, or the dropdown.

Observable: the ambiguous pair or hidden list, or "none found".

## Used at

**UX.** The information hierarchy, navigation labels and journeys. The critique applies the test.
