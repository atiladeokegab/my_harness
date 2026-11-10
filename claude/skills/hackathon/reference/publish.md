Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## 6. Publish

Steps 0–5 run at approval 1 (§2); steps 6–10 after approval 3.

0. **Visibility.** `--init` makes a **public** repo. Check the event rules (and sponsor IP terms) allow
   that, and that every teammate is fine with public code. If public is not allowed, stop and tell the
   lead: the kit needs a private-repo variant, and private repos on a free account lose branch
   protection.
1. Check `hackathon.json` has `event`, `title`, `summary` and `smoke` (§1), then run
   `hub gh-sync --project <p> --init --dry-run` and read what it would do.
2. Run `hub gh-sync --project <p> --init`. This creates the repo from the template, invites the
   roster, and sets up labels, milestones and branch protection.
3. `--init` fills the clone itself: IDEA.md from `$HUB_DIR/projects/<p>/`, HACKATHON.md (both time
   columns, the team table, the lead's agents, the board link), README.md (title, intro, the clone
   line, the planning C4 PNGs in Architecture). `docs/design.md` is left for the designer's PR (§2a).
   It runs the placeholder and image check; any leftover `<…>` stops it before a push.
4. Read what step 1's `--dry-run` said it would write and push, and **confirm with the lead**: the push
   is outward-facing.
5. Step 2 commits "docs: fill in the event" on `integration` and pushes `integration` and `main`. Do
   this before Prometheus is relaunched in that checkout.
6. After approval 3, run `hub gh-sync --project <p>`. Every task becomes an issue.
7. gh-sync ends with an `owners (for IDEA.md):` block and, when the table changed, "IDEA.md owners
   table updated": it has already committed the table to `integration`. An issue that fits no row
   prints a warning: add a row (or fix the issue's `Files:`). From now on, in this project, every hub
   command takes the issue number: `hub show 5`, `hub edit 5`, `hub claim 5` (`T-…` ids still work).
8. **Share and invite.** Give the lead the repo URL and the board URL (`--init` printed
   `board: <url>`, also on HACKATHON.md's `Board:` line) to share with the team. The board is public:
   a column per status, a lane per owner.
   - List who hasn't accepted the invite yet: `gh api repos/<repo>/invitations --jq '.[].invitee.login'`.
     GitHub can't assign an issue to someone who hasn't accepted: gh-sync creates their issues
     unassigned, warns, and assigns them on the first sync after they accept.
   - Tell each teammate to accept before they tell their agent to pick up work, to log in with
     `gh auth login` (browser), and to start their agent with only "Read AGENTS.md, then pick up my
     issue": it keeps itself going with `scripts/team-inbox.sh`.
   - A fine-grained personal access token (`github_pat_…`) can't accept the invite, and fails in a repo
     it doesn't own with "Resource not accessible by personal access token".
   - Show the board's **By vertical** view (grouped by Parent issue) in the room. It comes from the
     template board; if it's missing there, add it once by hand (the GitHub API can't create views).
     Until then, show each vertical's sub-issues:
     `gh api repos/<repo>/issues/<V>/sub_issues --jq '.[] | "#\(.number) \(.title)"'`.
9. **Breakdowns, in the room.** First say it to the room: whatever a vertical's brief suggests
   (`Approach:`, `Preferences:`, any seeded tasks) is a suggestion, not an order; each owner decides
   what to build and how. Fixed are only `Files:`, `Acceptance:` and `Contract:`, and the line (§7)
   still applies. Each owner starts their agent on their own laptop; it shows them their C4 box,
   deliverables, preferences and contract, asks what *they* would build, grills their plan one question
   at a time (each with its recommendation) until it holds, and from their answers opens 2–6 sub-issues
   under their vertical (AGENTS.md "Break down your vertical, live"). The grill is written inline in
   AGENTS.md so any tool can follow it; never ship a skill file into the repo. The room watches the By
   vertical view on the lead's screen. Zeus does the lead's verticals the same way and the lead okays
   them in the terminal. Check each against the line (§7) as it appears. The session ends when every
   vertical has its first sub-issues and §2a's design is in.
10. **Start the live crew** before the room breaks up:
    `tmux new -d -s hub-live-<p> "hub live --project <p>"`; `hermes <p>` with one line: "You build the
    lead's smaller tasks for <p> (label agent:hermes). Run hub inbox."; and, by hubmsg to Prometheus
    (relaunched in the event repo, [roles.md](roles.md)) and Atlas: "You are the reviewer
    for <p>. Load the hackathon-reviewer skill, then run hub inbox." Leave each window with
    `Ctrl-b d`, never `Ctrl-c`.
