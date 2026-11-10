Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## 2. Design, spec, plan

Follow `hub-planning`, with `--project <project>` on every `hub new`, and two hackathon cuts: **no
separate plan document** (writing-plans) and **no approval 2**. The vertical and task briefs are the
plan. The spec is a **day spec** against the platform spec: it says only what this event changes. Its
template, and the task and vertical brief headings, are in [briefs.md](briefs.md).

**One version plus one review.** Zeus writes the day spec once, a reviewer (Prometheus, or a Zeus sub-agent
with no other context) reviews it once, Zeus revises once, and it goes to approval 3 with the board. No
third version (real-world-agents wrote six, and first code landed at 12:10).

**Begin with the end: could this idea's demo make the case for first place?** Before choosing from the
shortlist or approving an idea, work backward from what the judges will actually watch, within the
event's video limit and judging criteria. For each shortlisted idea, sketch the problem, the spark, the
product action and the proof on screen. Compare these with the strongest plausible rival, criterion by
criterion; explain why our entry could win, where it would lose and what evidence is still missing.
Build difficulty alone does not make an idea competitive.

For the chosen idea, put a short timed storyboard and a criterion-to-evidence table in the existing
`IDEA.md`, shown at approval 1. Each row names the criterion/weight (unknown if unpublished), the exact
product action/result the video will show, the fair comparison or measured proof, and the owner/task
that will produce and record it. Mark planned numbers as unmeasured until verified; never assume an
attractive metric, a winning comparison or a first-place result.

Ask the room at approval 1: **"If judges saw only this demo, would they understand the value and have a
convincing reason to rank it first? What would a stronger rival show?"** If the case depends on
off-screen work, narration without proof, or a feature we cannot build and record in time, reshape the
idea or choose another before locking it. Use this within the existing approval window. Work backward
into scope and tasks: build the winning claim's proof, comparison and recordable product path early;
cut features that do not improve the judging case.

**The idea is fixed at approval 1, not at the end.** Once the grill is agreed, Zeus writes
`$HUB_DIR/projects/<project>/IDEA.md`: the problem, the idea, what we build, what we don't build, the demo
in one line (naming its hero comparison and its one chart, per [demo-bar.md](demo-bar.md)),
and the "Areas and owners" table with the areas and their directories filled in and the Owner and
Issues cells left as `—`. The approval-1 window shows IDEA.md beside the C4 diagrams and Prometheus's
score out of 6 (hub-planning step 0c), and the lead approves both together. The spec, plan and board
then build on an idea the lead has already signed.

At approval 1 Zeus also:
- asks one question: "Needs UDP, a stable IP or a GPU?" If yes, the answer goes in "Changes to the
  platform spec:" with the deploy owner's plan;
- turns the storyboard into the film's story: fills event.json, runs `film.story prepare`, writes
  `criteria-map.md` and applies the lesson that the film is the pitch, per your film pipeline's notes (not shipped)
  "At approval 1";
- **publishes the repo**: runs §6 steps 0–5 straight after it, so the designer's agent has a repo to
  work in (§2a) while Zeus writes the spec, plan and board. The issues for the verticals still wait for
  approval 3 (§6 step 6).

**Areas, core and smoke.** The design names the **areas** (a set of directories each, split by
strength), the **core** (shared contracts; Zeus owns it), and one **smoke command**: the unit tests
plus one end-to-end run on a few sample inputs, under 2 minutes. It runs in a clean checkout with only
`.env` copied in, so it includes its own install step (`uv run …` installs; `npm ci && …`). Until the
pipeline exists, the smoke is the tests alone. Until the first test exists there is nothing to smoke:
publish promotes `main` directly (§6 step 5), and the first code task (usually the core) adds the test
package, e.g. `tests/__init__.py`, so the tests-only smoke can pass. Every task's `Files:` is its
area's directories.


## 2a. The designer's mockup (in parallel with the spec)

Straight after the repo is published, the designer's agent builds `docs/design.md` and a clickable
`docs/mockup/` on the first issue; no multiple-choice design grill. When the lead is the designer,
Zeus builds it through a builder sub-agent (a reviewer doesn't build what it reviews). The five steps (the task, naming the designer to the room, the design PR's
review window, a late mockup) and the verticals' `Design:` lines: [briefs.md](briefs.md)
"The designer's mockup".
For a product with a UI the mockup is gate G1 of `designing-products` ([SKILL.md](../../designing-products/SKILL.md)).


## 2b. The spine (straight after approval 3)

The starter copied in as the first code commit, then `docs/CONTRACT.md`, then the day spec's P0 on the
core with assigned builders within available runtime capacity: smoke-green on one case and deployed (`/health` ok) by the
`spine` deadline. Every vertical extends it. Then the production audit after the first real-provider
deploy. Steps and the copy script: your starter's notes (not shipped).


## 3. Submission track

Always add four tasks:

- **the demo script**, starting from approval 1's storyboard; capture a rough proof cut as soon as the
  spine works, with a complete draft by code freeze, then adjust after the final run;
- **the recording**, `Deadline: submit` (or the demo-video deadline if the event has one), on the film
  pipeline; at the film freeze it submits the last-green film, never a newer red one (brief text and
  pipeline: your film pipeline's notes (not shipped) "Recording on the pipeline");
- **the submission form**, `Deadline: submit`; its Acceptance is "every Submission checklist row done";
- **the README page**, `Deadline: spine + 30 min`: what it is, how to run it, the live URL and a
  screenshot, refreshed after the final run. Docs only, so it merges on a green smoke.

**The demo bar: never go easy on the demo.** We placed 4th at Night Shift on a build the judges called
great, because the demo had "no sparkle". The eight rules (one fair hero comparison, one chart that
proves the claim, problem then spark, polish is table stakes, film on the pipeline, record clean and
frame-check independently, the pitch checklist, score every criterion) and the outside-viewer check at
the rough cut and freeze minus 4 h: [demo-bar.md](demo-bar.md). The demo script's Acceptance
includes every rule (1 to 8).

**Prometheus owns every test task**: the sample data, the unseen sets, the eval
cases and the dry reality test. Prometheus is the reviewer and is never a rules owner: a sample written
by the rules' author only tests what the author already thought of. It writes them from the goal, not
the given dataset: held-out, adversarial and production-shaped cases, per hackathon-reviewer "Tests and
direction" (at the Dwelly hack we tested only the given dataset and undershot; a team that let two LLMs
debate won).

- Prometheus drops a small unseen set on the team at build start + 30 minutes and a second one at build
  start + 60, not only at the reality test (dry run #1's reality test found the gaps an hour too late;
  in dry run #2 the first early set caught two gaps and the reality test still found two more).
- The sample data task's brief says `Every person, company and address is invented; emails and sites
  use .example`, and asks for at least one hard-negative case (looks like a positive, must not act).
- For a sensing or robot idea, the core task adds a local sink for its output protocol.
- Each result says what it verifies, as `Verified:` does.


## 4. Assignment grill

**The board holds verticals, not tasks.** Each area becomes one vertical for its owner
(`hub new "<area>: <what it delivers>" --vertical --owner <person> --project <p>`); its brief fields
are in [briefs.md](briefs.md) "Vertical briefs". Only `Files:`, `Acceptance:` and `Contract:`
bind the owner, with the line (§7); everything else is a suggestion, and the owner decides what to
build and how. Owners break their own vertical into sub-issues in the
room, then live (§6 step 9, [live.md](live.md) "Watching the breakdowns"). The core and the
submission track stay ordinary tasks.

1. Assign **areas first**: one AskUserQuestion per area, recommendation first, based on strengths and
   balanced load; a teammate claiming an area overrides. An area's owner is always a **person** on the
   roster; the lead's areas are built by Zeus (bigger tasks) or Hermes (smaller ones) as delegates. Every task in an area
   inherits its owner.
2. Ask per task only for the core (the lead, delegated to Zeus) and for work outside any area, which
   may go to `pool`: unassigned, whoever finishes early takes it (submission, docs, diagrams).
3. Run `hub assign <id> <person>` (or `hub assign <id> pool`), and for the lead's own tasks
   `hub delegate <id> Zeus|Hermes` (`hub assign` refuses an agent as owner and says which two
   commands to run instead).
4. Approval 3: `hub review --name approval-3 --title "Spec + board" --note "team agreed" <spec.md> <board.md>`,
   with `board.md` as in [briefs.md](briefs.md) "The approval-3 board". No `Lessons applied`
   table, no approval 3 (§0).


## 5. IDEA.md: the gate

IDEA.md was approved with the design (§2). Its **Areas and owners** table is kept by gh-sync: every
sync fills each row's Owner and Issues from the issues whose `Files:` fall in that row's directories,
and commits the change to `integration` (Zeus promotes it after the next green smoke). Re-open IDEA.md
for approval only if the spec, plan or board changed what we build or don't build since approval 1;
say which lines changed. **No issue is synced until `IDEA.md` is approved.**
