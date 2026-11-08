# Button and link labels name the result

Sources: GOV.UK Design System, "Button", design-system.service.gov.uk; Marieke McCloskey, "Writing
Hyperlinks: Salient, Descriptive, Start with Keyword" (Nielsen Norman Group, 2014), nngroup.com.
Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** A button or link says what the user gets or what happens when they press it, with the key
word first: "Download the certificate", never "Submit", "Click here" or "Learn more".

## Why it holds

- GOV.UK: "Write button text in sentence case, describing the action it performs." Its examples separate
  results the user cares about: "Save and continue" when the service saves, "Continue" when it does not,
  and more words where needed ("Add another address").
- McCloskey's test for a link is what the user will get by following it. Labels such as "Read more" and
  "Click here" fail it, and there is no click on a touch screen.
- People mostly look at the first 2 words of a link (McCloskey), so the key word goes first and a run of
  links does not all start with the same phrase.
- A label that names its result is also a promise the next screen keeps: its title repeats the label
  (`names-match-the-click`).

## What to check on a screen

- Every button and link names a result or an object: verb plus thing ("Run the audit", "Open report 214").
- None of: Submit, OK, Go, Click here, Here, Read more, Learn more, More, Continue (when it saves).
- Sentence case; the first two words carry the meaning; sibling links start differently.
- A destructive action names what it destroys ("Delete 3 programs"), and its cancel says what it keeps.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757. List every button and link label in
view, including icon buttons' accessible names where the capture tool shows them.

- **PASS:** every label names its result or object, and a stranger can say what pressing it does without
  reading the text around it.
- **FAIL:** quote each failing label with the result it should name.

Observable: the label list with each failure marked, or "none".

## Used at

**Critique** (the copy pass), the **UX** step's vocabulary, and the **tour**, where each step's control
label and card title must match.
