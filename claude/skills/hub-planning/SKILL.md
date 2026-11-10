---
name: hub-planning
description: >
  Use when substantial work needs planning and assignment to hub agents: it says where
  the spec and plan go ($HUB_DIR/projects/<repo>/, never the repo) and turns an approved plan
  into hub board tasks with owners, instead of executing it in one session. Also use for
  a new project, "put this on the board", "who should build this", or waking workers.
  Not for a one-line fix, or for work one session will finish alone.
---

# Planning on this hub

This workflow is self-contained. Small, clear fixes go straight to implementation and
an appropriate check under the `development` skill; they need no design document or extra
approval. For substantial work, use the relevant steps below. An explicit instruction
to proceed is authorization: do not ask the user to approve the same decision again.

## The workflow

Before assigning substantial work, inspect the relevant code and requirements, settle
the approach and risks, then decompose it into reviewable tasks. Ask only for missing
decisions that materially change the result. Recommend an approach and explain its
tradeoff when there is a real choice; resolve routine details yourself.

1. **Design.** State the goal, scope, constraints, approach and testable success criteria.
2. **Grill it.** New or multi-agent work only: the `grilling` skill, one question per prompt (step 0).
3. **Draw it.** C4 levels 1 to 3 from `c4_template.py` (step 0b), then the reviewer
   (`$HUB_REVIEWER`) rates the architecture out of 6 and the lead revises once before
   approval 1 (step 0c).
4. **Approval 1** in a `hub review` window, not the terminal.
5. **Spec** to `$HUB_DIR/projects/<repo>/`, then **approval 2**.
6. **Plan**: write concrete steps, owned files, dependencies and verification, same place.
7. **Board**: tasks with one owner per file, then **approval 3**.
8. **Wake the workers.**
9. **Review each result before committing it.** Code, tests, config and dependencies are
   reviewed first; a docs, README or media-only diff commits on its pasted evidence and is
   reviewed after. The last task always puts real C4 in the README.

Keep review pages lean: pictures and a few lines. Run `hub review` in the background; its
exit carries the decision.

## Before substantial work

Start from the project's PRD and intent, including for non-hackathon work. When none
exists, start a draft from `$HUB_DIR/templates/prd/project.json` and complete the approved
spec workflow before generating the board. The template is a draft, not approval or
a bypass of the spec lock. Small, clear fixes keep the fast path above.

For UI work link the approved design, `PRODUCT.md`, the surface brief, `DESIGN.md`,
tokens/brand page and judge evidence into testable spec acceptance; include
`make check-design` in UI task verification. The product's intent and main user
journey determine what the checks prove, alongside the design gates.

## Read the current stage

| Work | Required reference |
|---|---|
| New project/subsystem, grilling, C4, architecture score and approval windows (§0–0c) | [design and approval](reference/design-approval.md) |
| Writing a spec/plan, seeding acceptance checks, task ownership and dependencies (§1–3) | [spec and board](reference/spec-board.md) |
| Setting up or closing a project, README and real architecture diagrams | [spec and board](reference/spec-board.md); closing task depends on all builders |

Planning copies live under `$HUB_DIR/projects/<repo>/`, never the product repo. Keep
one file owner for the whole cycle and task details complete for a fresh worker.
Existing authorization takes precedence over repeated approval requests; phase,
merge and deployment permissions still apply.
