# hackathon.json

Read when writing `$HUB_DIR/projects/<project>/hackathon.json` (§1) and before `--init` (§6). The roster
rules are in SKILL.md §1.

```json
{"repo": "you/<event-repo>", "timezone": "Europe/London",
 "deadlines": [{"name": "spine", "at": "..."}, {"name": "code freeze", "at": "..."},
               {"name": "submit", "at": "..."}],
 "roster": [{"name": "...", "github": "...", "lead": true, "strengths": "...", "tool": "...",
             "bring": "...", "agents": [{"name": "Zeus"}, {"name": "Hermes"},
                        {"name": "Prometheus"}, {"name": "Atlas"}]},
            {"name": "...", "github": "...", "strengths": "...", "tool": "...", "bring": "...",
             "agents": [{"name": "cursor"}]}],
 "event": "<event name>", "title": "<product name>", "summary": "<one paragraph: what, which track>",
 "smoke": "make smoke",
 "rules": "<link or 'the event brief'>", "judging": ["..."],
 "runner": "scripts/run_cases.py",
 "review_before": ["<hackathon-reviewer's default list, plus this event's paths>"],
 "deploy": {"owner": "Zeus", "command": "make deploy"},
 "checks": ["freeze-gate", "smoke"]}
```

The lead's `agents` are Zeus, Hermes, Prometheus and Atlas (SKILL.md Roles), so gh-sync makes an
`agent:<name>` label for each.

- **`event`, `title`, `summary` and `smoke`** are needed before `--init` (§2): gh-sync writes
  HACKATHON.md and README.md from them and refuses to publish without them. `title` and `summary` come
  from the brainstorm; fill them in when approval 1 is agreed. The `smoke` above is the starter's;
  change it only if the day spec does.
- **`runner`** is the script that writes the answers (hub live checks it exists at the freeze sha).
- **`review_before`** lists the gated paths: copy the default list from the hackathon-reviewer skill
  (`fnmatch` globs: `*` crosses `/`), and at approval 3 add this event's runner, safety and verify
  paths. Never leave the key out: `--init` refuses it, and without it hub live gates every PR.
- **`deploy`** is the one person or agent who deploys and the command hub live runs after each promote
  ([roles.md](roles.md) "The deploy owner").
- **`checks`** lists the CI checks every PR must report (default `freeze-gate`; `smoke` is the kit
  template's smoke workflow, a required check): after the first merge hub live tells Zeus once if one
  never did.
- **`bring`** becomes the `Bring` column of HACKATHON.md's team table.
- **`deadlines`** also take the film deadlines ([film.md](film.md) item 1) and the `design`
  deadline ([briefs.md](briefs.md) "The designer's mockup").
