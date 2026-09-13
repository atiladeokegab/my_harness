# Writing a hub task that stands alone

A task is executed by an agent that never saw the conversation which produced it. If it
needs a follow-up question, it was underwritten. Use this shape for `--detail`:

```bash
hub new "P1 <project>: <outcome, not activity>" --project <project> --detail "$(cat <<'EOF'
CONTEXT
Why this matters and what was established in planning. Link the runbook or doc.

FILES (you own these for this cycle; touch nothing else)
- path/to/file.py
- tests/test_file.py

APPROACH
The settled approach, and alternatives already rejected with the reason, so the worker
doesn't re-litigate them.

ACCEPTANCE
- [ ] Concrete, checkable outcomes
- [ ] The check that proves it was shown to FAIL before the fix and PASS after
- [ ] `uv run pytest tests/ -q` green

OUT OF SCOPE
What not to do, even if it looks related.
EOF
)"
```

Chain work with `--dep T-00N` and pre-assign with `--owner <Agent>`. Never write a task
for a Codex agent that assumes Claude-only tools (skills, slash commands, SendMessage).
