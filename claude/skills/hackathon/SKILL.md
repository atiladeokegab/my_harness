---
name: hackathon
description: >
  Runs the lead's team-hackathon flow, from a pasted event brief to a team repo whose GitHub Issues
  every teammate's AI agent picks up under the hackathon_teamwork rulebook, and starts the demo
  film's kickoff (§0). Orchestrates hub-planning and hub gh-sync; does not replace them. Use when the
  user says "hackathon", "new hackathon", "event brief", "team repo" or "hackathon teamwork", pastes
  an event description to plan with a team, pastes an event link (lu.ma, devpost, eventbrite and the
  like), or says "I'm on this hackathon" or "I'm doing this hackathon". Not for reviewing an event's
  PRs (hackathon-reviewer), not for a teammate's agent building an issue (the event repo's
  AGENTS.md covers that), and not for work with no team or no event (hub-planning).
---

# Running a hackathon from this PC

The whole team plans together at the lead's laptop (§0 to §6); teammates never touch the hub
themselves. The team repo is made from the template `atiladeokegab/hackathon_teamwork`, whose
`AGENTS.md` makes every agent plan before coding, branch per issue, stay in its area and raise
change-requests. This skill gets the plan onto GitHub as Issues; `hub gh-sync` is the bridge.

Plans, specs and reviews live only in `$HUB_DIR/projects/<project>/`, never in the team repo.

## Current roles and boundaries

The agent names in this skill (and hackathon-reviewer) are the author's roster. Map them onto yours:
Zeus is your lead (`$HUB_LEAD`); Prometheus is your reviewer (`$HUB_REVIEWER`, or the factory.json agent
in phase `reviewer`); Atlas is a second reviewer if you have one (without one, every PR needs only the
one `LGTM`); Hermes is a Claude worker that builds the lead's smaller tasks (any of
`$HUB_CLAUDE_AGENTS` other than the lead and the reviewer); Hephaestus is an agy seat, if you run one.
With the default roster the reviewer is Hermes, so pick another worker for Hermes's building role.

`hub agents` / factory.json and the current task are authoritative for permissions and
ownership. All available agents can build when assigned; reviewers never review their
own changes. Zeus delegates builds and never builds in his own session, so he remains
available to the lead. Run as many builders as your accounts' capacity allows. The reviewer order and required approvals come from current policy.

The event's owners are humans; agents are delegates acting on the lead's account.
They take no pool issues and never `hub done` a task with a GitHub issue: gh-sync closes
it when the issue closes. Teammates post `DONE:`; hub live opens their PRs, merges and
keeps time. One deploy owner; nobody else deploys. Read [roles](reference/roles.md) when
delegating, starting a builder, configuring deployment or relaunching a reviewer.

Every builder brief has a UTC deadline. At it, push green work with the real check exit
code, or report what remains; the lead does not wait beyond it. A role assignment does
not expand merge, deployment, credential or phase permissions.

## Load the current stage

Follow these stages in order. Read only the stage being performed and its named references.
Existing section numbers remain in those references for links from other skills.

| Stage | Required instructions |
|---|---|
| New event, outside brief, room pitches, deadlines, film/deck kickoff, roster (§0–1) | [kickoff](reference/kickoff.md); read the lessons ledger first and show every lesson |
| Idea, day spec, design, spine, submission/test track, assignment and approval (§2–5) | [planning](reference/planning.md); follow hub-planning with the event's stated cuts |
| Public repository setup, invites, issues and starting the crew (§6) | [publish](reference/publish.md); respect outward-facing authorization |
| Live sync, clock, reviews, freeze, questions and take window (§7) | [operating](reference/operating.md), then the relevant situation in [live](reference/live.md) |
| Demo claim and judging the script or film | [demo bar](reference/demo-bar.md) |
| Writing hackathon.json, before `--init` | [schema](reference/hackathon-json.md) |
| Day spec, vertical/task briefs, approval-3 board and mockup | [brief templates](reference/briefs.md) |

## Never

- Fork the template. Use `gh repo create --template`, which `--init` does.
- Put plans, specs or reviews in the team repo. They go to `$HUB_DIR/projects/<project>/`.
- Edit `AGENTS.md` for one event. Event details go in `HACKATHON.md`.
- Merge a PR that doesn't match its issue, `IDEA.md` or its owner's area, or that contains a secret.
- Change the harness or the kit (hub code, this skill, hackathon-reviewer, the `hackathon_teamwork`
  template, the starter) in the 48 h before an event. Every change is proven in a dry run a few days
  before (the author's is the Thursday before) the kit push that night lands only what it proved, and then nothing changes until the event is
  over.
