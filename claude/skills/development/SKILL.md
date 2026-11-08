---
name: development
description: >
  Use when diagnosing a nontrivial bug, changing behavior across files, or preparing a
  code change for review or completion. Keeps root-cause debugging, focused tests,
  evidence-based review and verification in Hub. Not for greetings, simple questions,
  status checks, or obvious low-risk edits that need no development workflow.
---

# Focused development

Use the relevant part below. A small, clear task goes straight to the change and an
appropriate check: no mandatory brainstorming, plan file, approval round, skill chain,
or sub-agent. Existing user authorization carries forward. Hub ownership, isolation and
review rules still apply. Use `hub-planning` when work actually needs a team plan.

## Debug from evidence

Reproduce the failure and read the full error. Check the runbooks, recent changes,
callers and data crossing the failing boundary. Form a specific root-cause hypothesis
and test it before editing. Change the shared cause, then rerun the reproducer. If a
fix fails, return to the evidence rather than stacking speculative patches.

## Test the behavior that matters

For a bug, first add or run a small regression that fails for the reported reason;
after the fix, confirm it passes. For new nontrivial behavior, test the user-visible
contract and relevant boundaries, failure paths or production-shaped inputs. Use
existing tests and fixtures. Trivial wording or formatting edits need no new tests.

Acceptance checks belong to the independent reviewer (`$HUB_REVIEWER`).
Builders never read held-out checks or edit `tests/acceptance/` or `spec/`.

## Review the connected change

Read the diff with its callers, tests and requirements. Check whether it solves the
user's goal, breaks existing behavior, mishandles untrusted inputs, or adds needless
complexity. Verify each suspected defect with code or a reproducer before reporting it.
When receiving review feedback, check the claim before implementing it; explain a
disagreement with evidence. Never approve your own implementation.

Factory PRs go to the hub's reviewer (`$HUB_REVIEWER`); its review lenses, receipts and
direction checks remain authoritative. Otherwise use the project's normal reviewer.

## Verify before claiming completion

Run the checks appropriate to the final change, inspect their actual exit status and
output, and report what they establish. Tests for behavior, builds for build changes,
and a relevant manual check when automation cannot cover the result. Run long or noisy
checks through `hub sh -- <cmd>` and read the saved log. Broaden checks only for a
failure, new change, or unresolved risk. Report unverified behavior explicitly.

Finish with the diff, checks and remaining limits. Follow Hub's existing handoff and
landing rules; this skill adds no permission to merge, push, deploy or message others.
