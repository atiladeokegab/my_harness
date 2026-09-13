# `uv run pytest tests/` looks hung at ~22% with 0% CPU — it is not

**Repo:** `~/code/refinery`. **First cost:** 2026-09-05, ~40 minutes (Zeus killed two
healthy runs on this misreading; Prometheus hit a related stall the same hour).

## Symptom

`uv run pytest tests/ -q -m "not slow"` prints progress to roughly 22% and appears to
freeze. `ps aux` shows the pytest process alive with **`0:00`–`0:05` CPU time**, which
reads exactly like a hang. It is not one.

## Cause

Refinery's checks 6 and 7 (dynamic output equivalence, exception-handler re-run) shell
out to **GnuCOBOL**. Around the 22% mark the suite hits the PIC-boundary and dynamic
equivalence tests, which compile many small COBOL programs — one `cobc` invocation each,
seconds apiece. The pytest **parent** burns no CPU the whole time because all the work is
in short-lived **child** processes.

A healthy full run is **~5 minutes**. Do not kill it before then.

## Confirm it before doing anything else

Look at the children, not the parent:

```bash
ps -ef --forest | grep -A3 "[p]ytest tests"
```

If you see a live child like

```
 \_ /…/.venv/bin/python /…/bin/pytest tests/ -q -m not slow
     \_ cobc -x /tmp/tmpXXXX/mod_negative.cob -o /tmp/tmpXXXX/mod_bin_negative
```

it is compiling, not stuck. Wait. Only if the progress line has not advanced **and** there
is no running child should you treat it as a real hang.

## Related but distinct: the TestClient stall

Prometheus (Codex) separately reported a FastAPI/Starlette `TestClient` stall inside its
sandbox on the same suite, which cleared once the test permission was approved. That is a
different failure with the same surface reading. Distinguish by which file the progress
stops on: `tests/test_async_runner.py` and friends use `TestClient`; the ~22% cobc section
does not. To validate non-portal work while avoiding the client entirely:

```bash
IGN=""; for f in $(grep -rln "TestClient" tests/); do IGN="$IGN --ignore=$f"; done
uv run pytest tests/ -q -m "not slow" $IGN
```

Note that disabling the Claude Code sandbox did **not** change the ~22% behaviour, which
is what proved the two are unrelated.

## Trap: `pkill -f "pytest tests"` kills the caller

The pattern matches the killing shell's own command line, so the tool call dies with exit
code 144 while the real pytest survives. Bracketing the first character fixes the
self-match:

```bash
pkill -f "[p]ytest tests"
```

But bracketing is **not enough if the same command also runs pytest**. In
`pkill -f "[p]ytest tests"; uv run pytest tests/ …` the shell's command line still contains
the literal `pytest tests/` from the second half, the bracketed pattern matches *that*, and
the command kills itself — exit 144 again, before the suite even starts. Issue the `pkill`
as its own separate command, then run the suite.
