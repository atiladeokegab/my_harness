# <Symptom, phrased the way you'd first notice it>

<!-- Write a runbook whenever a bug takes more than an hour to diagnose and could recur.
Title it by what you SEE, not by the cause: the next person searches for the symptom.
Save as ~/hub/runbooks/<kebab-case-symptom>.md and add it to runbooks/README.md. -->

**Repo:** `<repo>` (or "any"). **First cost:** <date>, <how long>.

## Symptom

Exactly what you observe, including the misleading parts, e.g. "the process looks hung
with 0% CPU" or "every neutral matches but one accent is off".

## Confirm it

The one or two commands that tell this failure apart from the ones that look like it.

```bash
<command>
# expected output when it IS this bug
```

## Cause

Why it happens, in two or three sentences.

## Fix

The fix, in order. Say which parts are already applied and must not be removed.

## Traps while fixing it

Anything that bit you on the way, such as a cleanup command that kills its own shell.
