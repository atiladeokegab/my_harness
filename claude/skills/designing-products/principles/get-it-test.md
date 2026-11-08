# Test with a fresh pair of eyes, not a debate

Source: Steve Krug, *Don't Make Me Think!*, 2nd edition (New Riders, 2006), ch. 8 "The Farmer and the
Cowman Should Be Friends" and ch. 9 "Usability testing on 10 cents a day", with ch. 7. Paraphrased in
our words; anything quoted is marked and at most one sentence.

**Principle.** Settle design questions by watching someone new try the thing, not by arguing about what
users like; test early, small and often, and fix by taking things away.

## Why it holds

- Ch. 8: team debates about design are like religious arguments, with personal and professional tastes
  projected onto users. There is no Average User. The useful question is whether this particular
  design, with these words in this context, works for the people likely to use it, and only watching
  someone try it answers that.
- Ch. 9: people who built the thing know too much to see it fresh. One tester beats none, and one
  early beats fifty late. Recruit loosely and allow for differences; three or four per round, with more
  rounds, finds more than one big round. A focus group asks opinions; a usability test watches use.
- Two tests: **get it** (show the screen; do they understand what it is, why it is worth it, how it is
  organised) and **key task** (watch them do something, ideally a task they helped choose).
- The usual findings: they miss the concept, the words they look for are absent, or too much is going on.
- Triage: ignore "kayak" problems (a stumble the user recovers from alone at once); resist adding an
  explanation and take away what obscures the meaning; treat feature requests with suspicion; grab the
  obvious and cheap fixes; check that raising one thing has not sunk another. Ch. 7: only outsiders
  notice when the main point is missing.

## What to check on a screen

How we run it: our fresh judge sub-agent, given images only, plays the new user. It answers the get-it
questions before it sees the brief, and each proposed fix is checked against the triage rules.

## Pass or fail test

Give a fresh judge with no brief and no code the first-screen capture at one size: desktop 1280x633,
then separately phone 390x757. Ask what this is, who it is for, and what they would do first. Compare
the answers with the brief's one-line claim and primary action.

- **PASS:** the judge names the same kind of product and the same first action.
- **FAIL:** either differs; record the judge's words beside the brief's.

Observable: the judge's three answers next to the brief's claim and action.

## Used at

**Critique** (the finish check's method, and its fixes follow the triage rules). **Tour:** the first tour
step must pass the get-it question.
