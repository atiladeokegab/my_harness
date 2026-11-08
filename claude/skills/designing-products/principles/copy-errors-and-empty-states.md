# Errors say how to fix it; empty states say what comes here

Sources: GOV.UK Design System, "Error message", design-system.service.gov.uk; Nielsen Norman Group,
"Error-Message Guidelines" (2023) and Kate Kaplan, "Designing Empty States in Complex Applications: 3
Guidelines" (2021), nngroup.com. Paraphrased in our words; anything quoted is marked and at most one
sentence.

**Principle.** An error message says what happened and what to do next, in the product's own words. An
empty state says what will appear here and offers the action that fills it.

## Why it holds

- GOV.UK: "Describe what has happened and tell them how to fix it." An instruction beats a description:
  "Enter your first name", not "First name must have an entry".
- GOV.UK drops words that add nothing or mislead: "please" implies a choice, "sorry" fixes nothing,
  "valid" and "invalid" say nothing, "oops" is too casual, and "forbidden", "illegal" and "you forgot"
  blame. "An error occurred" and "This field is required" are too generic to act on.
- NN/g: show the error next to its cause, never by colour alone; be precise and constructive; keep a
  nonjudgmental tone with no humour; keep what the user typed.
- Kaplan: an empty area should still report status (never "No records" while data is loading), teach what
  could appear and how to add it, and give a direct path into the main task. Do not leave it blank.

## What to check on a screen

- Trigger each error the main journey can hit (empty submit, wrong file, network off, server error) and
  each empty list or first-run screen.
- Each error names the field or thing, the problem in the product's words, and the fix; it sits next to
  its cause; the user's input is still there.
- Each empty state says what will appear, why it is empty, and has one button that fills it.
- Loading has its own words; "No results" appears only after the load finished.

## Pass or fail test

Needs captures of each triggered error and each empty state, at desktop 1280x633 and phone 390x757.

- **PASS:** every error says what happened and how to fix it with none of the words above, and every
  empty state names what will appear and offers the action that adds it.
- **FAIL:** quote each failing message and name what is missing (cause, fix, action) or which word to cut.

Observable: the messages with each failure marked, or "none".

## Used at

**UX** (states as direction) and **critique**; `harden` writes them in the first vertical with a form.
The `## Voice` section's third pair is an error or empty state (`reference/copy.md`).
