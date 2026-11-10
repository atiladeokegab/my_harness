# Day spec, briefs and the designer's mockup

Read when writing the day spec (§2), any task or vertical brief (§2, §4), changing a brief after
approval 3 (§7), or starting the designer's mockup (§2a).

## Contents
- The day spec
- Task briefs
- Vertical briefs
- The approval-3 board
- The designer's mockup (§2a)

## The day spec

A day spec is written against the platform spec (`$HUB_DIR/projects/_hackathon-platform/platform-spec.md`,
track-agnostic, written once): it says only what this event changes. Write it to
`$HUB_DIR/projects/<p>/day-spec.md` in this shape:

    # <event>: day spec
    Changes to the platform spec: <each change and why, or "none">
    ## Assignment                         the event's task, quoted from the brief
    ## Do in this order; stop when time runs out
    - P0 <what>. Why (criterion): <the judging criterion it scores>
    - P1, P2, P3 in the same form
    ## Scenarios                          numbered, one line each (given, when, then); briefs cite S1, S2
    ## Contract                           shapes, endpoints, tools and final states beyond the platform's
    ## Smoke                              the command (the starter's unless changed)
    ## Assumptions                        every decision too small to grill
    ## Lessons applied                    every ledger lesson: the task, check or rule, or "n/a: <why>"

The `Lessons applied` table is required before approval 3 (SKILL.md §0).

## Task briefs

Every task's `--detail` carries these headings, one per line, because teammates' agents rely on them:

```
Context:
Files:        <the area's directories: the owner may change anything inside them>
Approach:
Acceptance:
Verify:
Deadline:     <a deadline name from hackathon.json>
Open:         <what is still undecided and who decides it, or "none">
If this brief disagrees with the case data or merged code, the data and the code win; keep the behaviour and say so in DONE.
```

- Every task's `Files:` is its area's directories.
- Write `Verify:` commands that run on any teammate's machine: `make check` or `uv run …`.
- Quote the lessons that bear on the task's area (SKILL.md §0); the builder's plan comment ends with
  `Lessons applied:`.
- When a brief changes after approval 3 (§7, a change-request), add a dated line at its end, under
  `## Changes since approval`: `- 2026-10-18 14:05 UTC: <what changed and why> (#<change-request>)`.
  Never rewrite approved text silently.

## Vertical briefs

Each area becomes one vertical for its owner
(`hub new "<area>: <what it delivers>" --vertical --owner <person> --project <p>`). Its brief says:

- `Files:` (the area);
- `Acceptance:` (what the vertical must deliver);
- `Contract:` (interfaces it consumes and provides);
- `C4:` (which planning C4 image in the README's Architecture section shows it, and which box is the
  owner's: `C4: docs/architecture/c4_container.png, box "Parser"`);
- `Preferences:` (the lead's preferences for this vertical, or `none`);
- `Design:` (the sections and the mockup it must follow:
  `Design: docs/design.md §Flow, §States; docs/mockup/` or `Design: none`);
- `Deadline:`, `Open:` and the data-and-code line (Task briefs, above).

Only `Files:`, `Acceptance:` and `Contract:` bind the owner, with the line (§7); `Approach:`,
`Preferences:` and any seeded tasks are suggestions, and the owner decides what to build and how (the
lead's decision, 2026-10-10). The web page's vertical says in `Approach:` that its first sub-issue
copies `docs/mockup/` into its area.

## The approval-3 board

`board.md` lists each task by **title**, owner, deadline and `Design:` line: tasks have no issue number
yet, and a T-id never reaches the repo.

## The designer's mockup (§2a)

In parallel with the spec. No multiple-choice design grill (dry run #3: the designer didn't know the
questions were theirs, and a look can't be chosen from words). Straight after the repo is published
(§2):

1. `hub new "Design: design.md + clickable mockup" --owner <designer> --project <p>` with a brief:
   `Files: docs/design.md, docs/mockup/`; `Acceptance:` references first (described and linked, never
   someone else's images committed), `docs/design.md` in the template's shape with the look, and
   `docs/mockup/index.html` (static, fake data, every screen and state clickable, exact copy); for a
   product with a UI (`designing-products` G1), the surface brief with its direction contract and token
   frontmatter, `tokens.css` and the first screen at 1280x633 and 390x757, the screen the film and tour
   open on by 10 s (lesson 37, `designing-products/reference/judge-tour.md`), and `document` at build + 60;
   `Verify:` the placeholder grep on `docs/design.md` prints nothing and the mockup opens in a browser;
   `Deadline:` a deadline named `design`, set to when approval 3 is expected. Then
   `hub gh-sync --project <p>`: it becomes the first issue.
2. Say it to the room **by name**: "<Designer>, as designer, you're up: your agent has issue #N." Their
   agent follows AGENTS.md "If your human is the designer". **When the lead is the designer, Zeus
   builds it** through a builder sub-agent (label `agent:zeus`; a reviewer doesn't build what it
   reviews), so Zeus keeps planning: the sub-agent reports back the references it needs, Zeus puts each
   to the lead and relays the answer.
3. Zeus writes the spec, plan and board meanwhile.
4. **The design PR:** check it out in a throwaway worktree `$d`, copy its design into the project
   folder (the page and the saved decision go next to the first file, and the worktree is thrown away):
   `cp "$d/docs/design.md" $HUB_DIR/projects/<p>/design.md`, then run
   `hub review --name design --title "Design + mockup" --note "team agreed" $HUB_DIR/projects/<p>/design.md "$d/docs/mockup/index.html"`
   (the design shown as text, the mockup embedded). Keep the worktree until the window closes. Before
   approving, check that nothing private leaks: no private text, URLs or images in the mockup or
   `docs/design.md`. On approve, merge it like any PR (§7), then smoke and promote.
5. **Late:** if the mockup PR isn't ready at approval 3, the room approves `docs/design.md` alone (Zeus
   commits it as one of its own commits, [live.md](live.md)), the verticals start on it, and the mockup
   follows on the designer's issue: their PR pulls `integration` first and adds only the mockup and
   approved refinements; when it merges, `hub edit` the affected verticals so their owners get "Brief
   updated".

Then every vertical's brief gets its `Design:` line (Vertical briefs, above).
