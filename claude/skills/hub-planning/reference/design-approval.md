Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## 0. Grill the design before it is approved (architectural work only)

For a new project, a new subsystem, or anything that will become several tasks: once
the design is concrete and **before** the spec is written, load the
`grilling` skill and run it on that design, until every decision in the tree is
settled. Keep its logic (look facts up yourself, only ask what is unblocked) but NOT its
batched-round format: the user wants **one question per prompt**, through
AskUserQuestion where the tool exists, recommended option first and marked
"(Recommended)", with room to type their own answer. The design approval is given
at the end of grilling: "grilled and agreed", not "looks fine".

This exists because the most common failure is an agent making a wrong design decision
midway through building. The cheapest place to catch it is before any spec exists.

Bounded work skips this; ask for a decision only when existing authorization leaves a
material choice unresolved. The user can ask for a grilling on anything, any time.

**A product with a UI** also runs `init`, `shape` and `new-work` through `designing-products`
(gate G1) on a fresh sub-agent before approval 1. The
approval-1 page shows `PRODUCT.md`'s positioning line, the chosen specimen with the blind judge's
scores and the standard card, and the first-screen mockup at both sizes. No question to the user about the look.


## 0b. Draw it before it is approved (architectural work only)

After grilling, draw the planned system so the user approves a picture, not only prose.
Copy `c4_template.py` from this skill's directory to `$HUB_DIR/projects/<repo>/c4.py`,
replace the example nodes with the planned system, and run `uv run c4.py context
container component`. Show the user the three PNGs next to the spec. Skip level 4 while
planning: classes that do not exist yet are a guess. If it exits saying Graphviz is
missing, ask the user to run `sudo apt install -y graphviz`; do not switch tools.


## 0c. The reviewer rates the architecture (every project)

No design reaches approval 1 until the reviewer (`$HUB_REVIEWER`; a Codex agent such as
Prometheus is a good choice, since a second model family has different blind spots) has
reviewed its C4 diagrams. Put a `review` task on the board for the reviewer naming the three
PNGs, `c4.py` and the design doc, and send it with `hubmsg <Reviewer> "..." --task T-NNN`.
The reviewer answers in the task note with a score out of 6 (6: build it as drawn; 4: sound
with named fixes; 2 or below: rethink) and a short list: missing boxes or flows, a wrong
boundary, a single point of failure, a contract nobody owns, a cheaper shape. The lead revises
the design and diagrams once, then shows the score, the list and what changed on the
approval-1 page. Spend real thinking here: an architecture mistake found now costs minutes,
found mid-build it costs the day. The closing "Architecture diagrams" task gets the same
review against the real code.

**The board always ends with an "Architecture diagrams" task**, depending on every
build task: move `c4.py` to `docs/architecture/c4.py` in the repo, redraw it from the
real code with level 4 included, render all four PNGs beside it, and add an
Architecture section to `README.md` that shows them. That is product documentation a
teammate opens, so it belongs in the repo; the planning copy stays in `$HUB_DIR/projects`.
The same closing task also:
- refreshes the README stub (below) and writes its `Known limitations` from a grep of
  `shortcut:`/`ponytail:` comments (live.py's LIMITS pattern) plus one run against the real target, when the board deploys or ships an artefact. Anything
  not tried is "not tested", and a failure is listed as a failure.
- moves the rules agents broke twice this cycle into the repo's AGENTS.md (for a shared repo,
  into `$HUB_DIR/projects/<repo>/`, per `clean-repo`), with the incident in the commit body.

**A README stub comes with the first working code.** The first task that makes the repo run
also writes a README stub: what it is, how to run it, and its status. Nobody opening the repo
mid-cycle should find nothing.


## Approvals happen in a window, not the terminal

Every approval (design with its diagrams, spec, board) goes on a **lean** review page:
the pictures or three to five short lines, a comment box pre-filled with `agreed` (so the saved
review records the decision even when the user just clicks), Approve / Request changes. The
user found a text-heavy page worse. Write it as plain HTML in `$HUB_DIR/projects/<repo>/`
with elements `#approve`, `#changes`, `#note` and `#status` (no script of your own), then
run, **in the background**:

```bash
hub review $HUB_DIR/projects/<repo>/<page>.html --name approval-1
```

It opens a browser window, and exits when the user clicks. It prints
the decision as one JSON line and saves it to `reviews/approval-1.json` beside the page.
Its exit is what wakes you; do not ask the user to type "decided". Images next to the
page (the C4 PNGs) can be referenced by bare filename. Act only on `"decision":
"approve"`; on `"changes"`, the note says what to fix.
