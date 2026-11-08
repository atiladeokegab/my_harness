# Forms ask for less

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 12 (the letter on
asking for personal data), ch. 10, ch. 11 and ch. 6. Paraphrased in our words; anything quoted is
marked and at most one sentence.

**Principle.** A form asks only for what this transaction needs, accepts input however people type it,
and shows what they get in return.

## Why it holds

- Ch. 12: at every field people ask why it is wanted. When the honest answer is "not for this", they
  conclude the makers are either clueless or after their data. Three costs follow: people lie (Krug's
  marketing list full of cartoon names), fewer forms get finished, and the product looks bad.
- Krug's guidelines: require only what completes this transaction; keep optional fields few, since a
  long form discourages people on sight; show the value received in exchange (a sample, exactly what
  signing up gives). More data can be asked for later, once trust exists.
- Ch. 10: never make people format data for you (spaces in card numbers, dashes in phone numbers);
  write the small bit of code that cleans it up.
- Ch. 11: tie each prompt to its field with a real label so screen readers announce it.
- Ch. 6: on a form, trim the navigation to identity, a way out and any help with the form.
- Ch. 9: show any new form to someone nearby before shipping it.

## What to check on a screen

- Each field maps to a step of this transaction; optional fields are few and marked.
- Input is normalised (spaces, dashes, case), not rejected.
- Every field has a visible label outside the box, not a placeholder alone.
- What the user gets is stated next to the submit button.

## Pass or fail test

Apply to each capture with a form on it, desktop 1280x633 and phone 390x757; a capture with no form is
not applicable. For each visible field, write the step of this transaction that needs it.

- **PASS:** every field has a need; no more than two optional fields (our threshold), each marked;
  every field has a visible label outside the input; the form says what the user gets.
- **FAIL:** name the field with no need, the unlabelled field, or the missing statement of value.

Observable: the table of field to need, with any gap.

## Used at

**UX** (journeys and states that collect input). The critique applies the test.
