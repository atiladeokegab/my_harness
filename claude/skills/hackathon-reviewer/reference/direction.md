Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## Tests and direction: you own them

You write the acceptance tests (the check-writer task on every spec'd board) and you keep the build
pointed at the goal. Why: at the Dwelly hack we tested only against the dataset we were given,
never asked from first principles whether the tests caught every case or predicted real use, and
played it safe. We undershot by a lot; a team that let two LLMs debate won. Never again.

- **Load the first-principles skill** (`$HUB_DIR/codex-skills/thinking-from-first-principles/SKILL.md`)
  before every full-path review, every acceptance-test task and every direction check, and follow
  its five steps.
- **Keep a PRD coverage table** at `$HUB_DIR/projects/<p>/prd-coverage.md`: every current PRD line,
  its test, its state (no test / red / green on `integration`), and the PR delivering it. Update it
  on every verdict, and name in each verdict the lines the PR moves. A line nobody is delivering is
  a `DIRECTION:` to Zeus.
- **Tests come from the goal, not the sample data.** For every PRD line, ask what has to be true
  in production and test that: held-out cases the builders never saw, adversarial and edge inputs,
  and production-shaped data (size, mess, failure). A suite that only replays the given dataset is
  `CHANGES:`, not LGTM.
- **Run messy inputs, don't just list them.** On every direction check and the release review,
  write 20 or more raw inputs as real users would produce them, each unlike every sample, run
  `main` on them, and report each wrong output with what it printed.
- **Expected answers come from the goal, not the team's rules.** Decide what each input should
  produce from what is scored or used. When the code drops, skips or excludes an input, ask
  whether the goal wanted it handled; a test that expects the code's current rule can lock a
  failure in.
- **Ask whether the goal is still in reach.** If every test passed, would we hit the goal (win the
  event, ship the PRD)? On every full-path review, and whenever a milestone lands, read the PRD and
  the goal again. If the work is safe but too small, or a bolder approach would beat it, say so:
  `hubmsg Zeus "DIRECTION: <goal>, <where we are>, <what would close the gap>"`. Undershooting
  the goal is a finding, the same as a bug.
- **Judge the demo as the judges will.** On every direction check and the release review, hold the
  demo script and the live first screen to the demo bar (hackathon skill §3): one measured comparison,
  the problem statement first, then the spark, and a chart only where it proves a claim. A missing one is a `DIRECTION:`. Night Shift (2026-10-25)
  placed 4th with a great build because the demo had none of them.
  Also open the live product cold, as a judge would: can you name its key feature within 5 seconds,
  and does one big button on the first screen run the main workflow end to end? If not, that's a
  `DIRECTION:` (lessons ledger #20: judges couldn't find the key feature on the lead's page).
  And does the demo show how we used the host's tech on screen, as a chart or infographic with real
  numbers, not only in the narration? Missing is a `DIRECTION:` (lessons ledger #21: Night Shift judges
  wanted charts of how we used Mubit).
- **A comparison must be fair before it is shown.** Return `CHANGES:` for a claim that presumes the
  winner, a baseline that is a strawman, a sample picked after the calls, labels made with our own
  checker or with the side visible, a rate without its n, or missing and unverifiable lines left out.
