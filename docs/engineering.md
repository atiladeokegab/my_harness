# Engineering defaults

The stack, the tooling and the testing doctrine the agents follow. The short form lives in
`claude/CLAUDE.md`, which is loaded into every session. This page holds the reasoning.

## Stack

| Layer | Default | Notes |
|---|---|---|
| Python | **uv**, CPython 3.11+ | The only Python entry point. See below. |
| Python web | FastAPI (APIs), Django (full apps) | `uv run uvicorn app.main:app --reload` |
| Python tests | pytest | Markers to split the fast loop from slow suites: `-m "not slow"` |
| Frontend | Next.js + React + TypeScript | Next 16 / React 19 at time of writing. **Read the versioned docs in `node_modules/next/dist/docs/` first.** |
| Styling | Tailwind CSS v4 | Layer discipline is mandatory: see `runbooks/tailwind-layer-order.md` |
| Mobile | Expo / React Native | Read the versioned docs for your SDK before writing code |
| Infra | Docker, Kubernetes, Helm | Anything named `prod`/`production` is a sensitive target |
| Deploys | Vercel for web | Verify every deploy, not just every push |
| Shell | bash, tmux | The hub itself |

Swap in your own stack. The doctrine below is what carries over.

## Python: uv, always

```bash
uv sync --dev                       # create/refresh .venv from pyproject.toml + uv.lock
uv run pytest tests/ -q             # run anything inside the project env
uv run python -m mypkg
uv add httpx                        # add a dependency (updates pyproject + lock)
uv add --dev pytest-xdist
uv run --with numpy python - <<'PY' # one-off script with a throwaway dependency
import numpy; print(numpy.__version__)
PY
uvx ruff check .                    # run a tool without installing it
```

- Never bare `pip install`, and never activate a venv by hand. `uv run` makes the command
  itself reproducible: an agent that runs `uv run pytest` gets the same environment you do.
- `pyproject.toml` and `uv.lock` are committed, and `.venv/` is not.
- Put system prerequisites (compilers, native libraries) and a one-line check for each in the
  project `CLAUDE.md`. If a missing tool silently degrades behaviour rather than failing,
  say so loudly in the brief.

## Frameworks move faster than training data

Models are confidently wrong about framework APIs that changed after their cutoff. Next.js
now ships its own docs inside `node_modules/next/dist/docs/` and writes an agent-rules
block into `AGENTS.md`. Keep it, and commit it so it stops reappearing as a diff. The same
applies to Expo, React Native and anything else on a fast release cycle. **Read the
versioned docs before writing code, and heed deprecation notices.**

## Dependencies

Before installing a large or critical dependency (a runtime framework, auth, payments,
cryptography, a global system tool, a third-party agent skill or plugin), review it first:
maintainers, release history, install scripts, permissions, and what it pulls in. Say what
you found. Skip the review for lockfile-only changes, the standard library,
already-vetted packages and trivial well-known utilities.

## Testing doctrine

### A check proves nothing until it has failed

Every automated check gets believed too early, in both directions. In one session, four
probes gave confident PASSes on nothing and four gave confident FAILs on correct code.

**False green**, where the probe couldn't see the defect it was testing for:
- It measured logged-out pages, where error states are narrow, so "no overflow" measured
  nothing.
- It read `documentElement.scrollWidth` under `overflow-x: clip`, which reports the
  unclipped box.
- It measured a page served with **no CSS at all** from a stale build. A page with no
  sidebar and no margins measures as perfectly responsive.
- The hub's first concurrency test also passed against the *pre-fix* code, because
  process-spawn overhead dwarfed the race window.

**False red**, where the probe fired on something correct:
- a carousel, whose track of full-width panels is N× wider by design
- decorative elements positioned outside their card and clipped on purpose
- a "one nav" check that counted an `<aside>` wrapping a `<nav>` as two

**So:** inject the defect and require the check to catch it. Remove it and require the check
to go quiet. Only then believe it. The hub's board suite is checked against a pre-fix commit,
where it produces 8 failures and 2 errors; that is what makes its green mean something.
When a check goes red, **find the element or line it's actually pointing at** before
changing any code.

### A green benchmark can hide defects

In one product, two detection holes were each hidden by a *different* bug, so the benchmark
read green while the check under test did nothing. One class scored 100% only because a
false-positive bug flagged everything. Another generated inputs that never compiled, so the
check skipped them and reported "incomplete", unnoticed for months.

**So:** when a class is at 100%, confirm the named check is what caught it. Treat a rise in
*incomplete* or *skipped* as an error signal, not a neutral one.

### Test the configuration you actually run

The hub's transport suite was 19/19 green over a live bug, because it never ran `hubmsg`
while the relay daemon was up, and production always has the daemon up. If a flag, daemon
or service is always present in production, it's present in the test.

### Execution proves what happened on the inputs you tried

It never proves what would happen on a path nobody drove. An error branch that tests never
reach needs a static check, not a longer run.

### A slow suite isn't a hung suite

A pytest parent that burns 0% CPU for minutes may be waiting on child processes: compilers,
subprocesses, browsers. Before killing it:

```bash
ps -ef --forest | grep -A3 "[p]ytest"
```

A live child means it's working. Write the healthy full-run time into the project brief.

**`pkill -f` matches its own shell.** `pkill -f "pytest tests"` kills the tool call that ran
it (exit 144). Bracket the first character (`pkill -f "[p]ytest tests"`) and run it as its
own command, never chained before another command containing the same text.

## UI verification

- **Trust pixels over computed style.** Under headless virtual time, CSS transitions and
  `requestAnimationFrame` don't advance, smooth scrolling never completes, and `100svh`
  resizes with the capture window. `runbooks/headless-browser-css-checks.md` has the
  same-origin iframe probe that measures correctly.
- **Assert the stylesheet returned 200** before measuring any layout.
- **Strip every `<script>`** from the built page and screenshot it. Motion must fail open.
- **Never read a brand colour off a screenshot.** Use `claude/skills/design-system/scripts/colour.py`.

## Git and deploys

- Commit only when asked. Branch first if you're on the default branch.
- **A successful push is not a successful deploy.** If the platform gates on commit author
  (Vercel does), stamp the right identity per checkout and check the deploy status after
  every push that should change the site. See `runbooks/vercel-deploy-blocked.md`.
- **The GitHub default branch isn't always the live one.** Old repos keep stale defaults.
  Record the real one in the project brief.
- When two code paths produce the same artefact (say, two PDF renderers), write that into
  the brief: a change must land in both, or the outputs drift.
