# <Project> — project brief

Read this cold, before touching anything. It records the traps that have already cost
real time on this repo.

<!--
How to use this template: copy it to <repo>/CLAUDE.md, then symlink AGENTS.md to it
(or copy templates/project-AGENTS.md) so Codex agents get the same brief. Keep it
short. It is loaded into every session, so every line must earn its place. Delete
sections that don't apply. Anything that has cost more than an hour goes under "Traps".
-->

## What <Project> is

One paragraph: what it does, for whom, and what it is *not*. Point to the document that
is honest about capability (e.g. `PRODUCT.md`) and say to trust it over the README.

---

## Traps that have already burned this repo

### 1. <Short name of the trap>

What happens, why, and the one command or setting that avoids it. Link the runbook:
`~/hub/runbooks/<name>.md`.

<!-- Examples of traps worth recording:
- The live branch is not the GitHub default branch.
- Commits must be authored as a specific identity or the deploy platform silently
  refuses to build. Include the verification command to run after every push.
- Two independent render paths that must be changed together. -->

---

## Local development

Python via uv. Run everything through `uv run`.

```bash
uv sync --dev
uv run pytest tests/ -q                 # full suite
uv run pytest tests/ -q -m "not slow"   # fast loop
```

State how long a healthy full run takes, so nobody kills a slow suite as hung.

### Environment prerequisites

List every system dependency whose absence silently degrades behaviour, and the one-line
check for each:

```bash
<tool> --version
```

---

## Repository layout

| Path | What lives there |
|---|---|
| `src/` | ... |
| `tests/` | ... |

---

## Coordination

Agent coordination uses the hub (`~/hub/HUB.md`). Run `hub brief` at the start of every
session, claim work before editing, and preserve the file ownership recorded in each
task. Tasks for this repo are tagged `project: <project>`; an agent launched from this
directory is scoped to it automatically. If `echo $HUB_PROJECT` is empty, run
`export HUB_PROJECT=<project>`.
