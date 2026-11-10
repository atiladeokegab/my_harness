# The spine (§2b, straight after approval 3)

Read at §0 when checking the event's rules on pre-existing code, and straight after approval 3.

## Contents
- The starter and the spine
- When a starter is not allowed
- Steps 1 to 5: copy, contract, build, done, production audit

## The starter and the spine

The starter is your own pre-existing work, rehearsed before the event and kept in a private repo
(here `$HUB_CODE_DIR/hackathon-starter`): for an agent product, say, an app factory, store, tool
gateway, agent loop, case runner, eval skeleton and `make deploy`. None ships with this harness; build
yours between events. The spine is the starter plus this event's contract, smoke-green on one case and
deployed, by the `spine` deadline. Every vertical extends it. With no starter, follow the next section.

## When a starter is not allowed

Read the event's rules on pre-existing code before anything else is planned (§0). If a full starter is
not allowed (or you have none), publish without it (skip step 1, the starter copy) and build the spine
from the platform spec at the event. Record that under "Changes to the platform spec:" in the day spec.
The spine's first code commit then adds a `Makefile` whose offline `smoke` target passes: until one
exists, every merge after the first project file is red and reverted.

## Steps

1. **Copy the starter as the first code commit**, before any vertical's first sub-issue is built
   (teammates branch from `integration`). In a throwaway worktree:
   ```bash
   P=$HUB_CODE_DIR/<p>; S=$HUB_CODE_DIR/hackathon-starter
   git -C "$S" pull -q --ff-only && s=$(git -C "$S" rev-parse --short=12 HEAD)
   git -C "$P" fetch -q origin && d=$(mktemp -d) && git -C "$P" worktree add -q --detach "$d" origin/integration
   git -C "$S" archive HEAD | tar -x -C "$d" --anchored --exclude=AGENTS.md --exclude=CLAUDE.md \
     --exclude=README.md --exclude=.github --exclude=.gitignore --exclude=docs/CONTRACT.md
   git -C "$S" show HEAD:.gitignore >>"$d/.gitignore" 2>/dev/null
   git -C "$d" add -A && git -C "$d" commit -q -m "chore: pre-existing starter from hackathon-starter@$s" \
     -m "Written and rehearsed before the event, copied in unchanged; see README, Pre-existing work."
   git -C "$d" push origin HEAD:integration; git -C "$P" worktree remove --force "$d"
   ```
   The excludes keep the kit's own files: the starter must never overwrite the kit's AGENTS.md,
   README.md or `.github/` (`--anchored` limits them to the top level, so a nested README.md still
   copies). Keep the starter free of an AGENTS.md (the hub's guard blocks one in a repo): put its
   system rules in a "System rules" section of its README; an event repo gets them from the kit's
   AGENTS.md §1. The kit's README declares the pre-existing work, and the kit's `docs/CONTRACT.md` is
   the template. Then smoke and promote ([live.md](live.md) "Zeus's own commits").
2. **Contract.** Fill `docs/CONTRACT.md` from the day spec: `## Assignment` first, then its Contract
   section under the template's headings, including the final states. Commit (`docs: contract`), smoke,
   promote. Only Zeus changes it; it is a gated path.
3. **Build the spine** with assigned builders within available runtime capacity ([roles.md](roles.md)):
   the day spec's P0 on the core, i.e. the event's case format in the runner, its shapes in the store,
   its tools in the gateway.
4. **Done** when the smoke is green on `main` with one sample case answered end to end, and the deploy
   owner's `make deploy` from `main` returns a URL whose `/health` is ok (not `/healthz`: Cloud Run
   reserves it). Post the URL to the lead and on the core's issue. At `spine` without that, tell the
   lead what's missing; the verticals keep building against `docs/CONTRACT.md`.
5. **Production audit** after the first deploy that uses a real provider (model key, email, voice): run
   the sample cases against the deployed URL and write what failed, as failures, in the README's
   `Known limitations`, with anything not tried listed as "not tested", never as a pass. Count effects
   from the gateway's `Effects:` line, not the agent's answer (a stronger team's agent misreported how
   many emails it sent).
