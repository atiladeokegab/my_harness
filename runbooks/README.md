# Runbooks

Problems that have already cost real time once, each with the symptom, how to confirm it,
and the fix. **Check here before debugging anything that feels like it should already
work.** Add one whenever a bug takes more than an hour to diagnose and could plausibly
recur — use `templates/runbook.md` in the harness repo, title it by the symptom, and add a
row below.

The installer copies these to `~/hub/runbooks/`. Several were learned on a real product
(Refinery, a Python + Next.js codebase) and keep its specifics as worked examples; the
lesson in each generalises.

| Runbook | Symptom it solves |
|---|---|
| [`codex-sandbox-blocks-hub.md`](codex-sandbox-blocks-hub.md) | A Codex agent reads the board but cannot claim/finish tasks, always reports peers `asleep`, or exits instantly on launch. |
| [`vercel-deploy-blocked.md`](vercel-deploy-blocked.md) | `git push` succeeds but the Vercel site never updates — the commit author isn't on the Vercel team. |
| [`pytest-looks-hung-cobc-compiles.md`](pytest-looks-hung-cobc-compiles.md) | A test run looks hung with 0% CPU; it is compiling in child processes. Plus the `pkill -f` self-match trap. |
| [`headless-browser-css-checks.md`](headless-browser-css-checks.md) | Every headless layout measurement disagrees with what the user sees. Five traps and the same-origin probe that works. |
| [`website-content-invisible.md`](website-content-invisible.md) | Sections lay out but paint nothing — scroll-reveal animations that never fire. |
| [`portal-page-couldnt-load-stale-chunks.md`](portal-page-couldnt-load-stale-chunks.md) | A Next.js app shows "This page couldn't load" or renders with no CSS — stale build chunks. |
| [`tailwind-layer-order.md`](tailwind-layer-order.md) | A Tailwind utility silently loses to a component class. |
| [`screenshot-colour-p3-shift.md`](screenshot-colour-p3-shift.md) | A brand colour sampled from a screenshot looks "changed" while every grey matches. |
