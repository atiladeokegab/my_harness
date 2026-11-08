---
name: thinking-from-first-principles
description: Use when writing acceptance tests or an eval set, running a direction check, approving a design or plan, or when a build is green on the data it was given but will be judged on data or users it has not seen (a final test, judges, production). Not for small PRs, typo fixes or mechanical changes.
---

# Thinking from first principles

Reason from the goal and the hard constraints, never from the sample data, convention, or what the
team has already built. The sample is evidence about the target, not the target.

## Which model does the reasoning

The five steps run on the strongest reasoning model you have access to, never the session's default.
- **Claude:** spawn a fresh sub-agent on the strongest model (the Agent tool's `model` option), give it
  this skill's path and the material, and use its output.
- **Codex:** run the steps on the strongest model (`codex exec -m <model>`, or switch with `/model`).
Say in the output which model reasoned.

## Skip it when

The change is on the fast path (small, no protected file), mechanical, or has no unseen target.
Review normally and say nothing about this skill.

## The five steps

1. **Goal.** State the outcome that is actually scored or used: who judges, how, and with what
   weights. Name the function, not the current form ("a correct banking outcome on an unseen
   case", not "our pipeline answers").
2. **Constraints.** Sort every factor into a table:
   - **Hard:** physics, maths, logic, the rules, the time left, the money.
   - **Soft:** conventions, inherited tools, the current architecture, team habits.
   - **Assumption:** believed without evidence. "The samples look like the real set" is always
     on this list until proven.
   Only hard constraints are fixed. Treat soft ones and assumptions as changeable.
3. **The real target, from the domain.** Without looking at the samples, list what the real target
   will contain, using what you know of the domain: the case types, failures, adversaries and
   rule-driven situations that people in that field deal with. Then compare it with the samples
   and with every phrase in the brief that describes the unseen set. **Each gap is a test to
   write.** Also note what the samples hold in only one form, such as a single status, few file
   types or one header layout.
4. **Input surfaces.** List every input the system parses: fields, formats, labels, headers,
   encodings, file types, and any allow-list or enum in the code. For each one, vary it with a
   new format, an unseen label, a missing value or a conflicting value. A fixed list of accepted
   values is where unseen data breaks the system.
5. **Rebuild and compare.** From the hard constraints only, sketch the strongest approach a top
   rival could build in the time left. Compare it with ours on each scored criterion. Then decide:
   **would we beat it?** If not, name the smallest change that closes the gap and what it costs
   against the time left. A pivot is allowed whenever the hard constraints allow it. Rule one
   out only after you have costed it.

## Output, in this order

1. Goal
2. Constraints table, with the assumptions under test
3. Gaps, each with the test it becomes (domain gaps first, then input variations)
4. Strongest rival compared with us, scored criterion by criterion
5. Verdict: `on course`, or `DIRECTION: <goal>, <where we are>, <what closes the gap>`, then the
   top three actions

## Red flags

| Thought | Reality |
|---|---|
| "Tests pass on the data we were given" | That measures the sample. Step 3 measures the target. |
| "Avoid a pivot" before step 5 is costed | Safety is a soft constraint. Cost the alternative first. |
| "Polish the demo" as the main fix | Polish cannot close a gap in what is scored. |
| No test case outside the sample's categories | Step 3 was skipped. |
| "Identity or format checks look strict enough" | Strictness against unseen inputs is untested. Do step 4. |
