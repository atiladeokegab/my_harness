# <Project> — agent brief (Codex)

Codex reads `AGENTS.md`; it never reads `CLAUDE.md`. **`CLAUDE.md` in this directory is
the full project brief — read it first.** This file exists so a Codex agent does not start
work without the traps below.

<!-- Simplest option: `ln -s CLAUDE.md AGENTS.md` and delete this file. Use a separate
file only when Codex needs different instructions (it has no skills, no SendMessage). -->

## Traps that have already cost real time

1. **<trap>.** <one-paragraph summary; full detail in CLAUDE.md>

## Before debugging anything that feels like it should already work

Check `~/hub/runbooks/`. Each file is a problem that has already cost real time once,
with the symptom, how to confirm it, and the fix.

## Local development

```bash
uv run pytest tests/ -q
```

## Coordination

Hub protocol is in `~/.codex/AGENTS.md` (symlinked to `~/hub/AGENTS-codex.md`). Work here
is tagged `project: <project>`; if `echo $HUB_PROJECT` is empty, set it.
