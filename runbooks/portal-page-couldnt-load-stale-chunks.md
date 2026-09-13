# "This page couldn't load" in the portal — stale build chunks

**Symptom.** The portal at :3001 returns 200 for the route, but the browser shows
*"This page couldn't load — Reload to try again"*, or renders with **no CSS at all**
(no sidebar, 8px body margin, unstyled text). DevTools shows 500s on
`/_next/static/chunks/*.css` or `*.js`.

**Confirm it in one command.** Ask what the served HTML points at, then ask for it:

```bash
CSS=$(curl -s http://localhost:3001/login | grep -oP '/_next/static/[^"]*\.css' | head -1)
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3001$CSS"   # 500 => this bug
ls portal/frontend/.next/static/chunks/*.css                            # different hash
```

The served HTML names a chunk that is not on disk.

**Cause.** `next build` writes into `.next` while a `next start` is serving from it.
The running server keeps the old build manifest in memory and hands out chunk URLs
that the new build has replaced. Restarting is not always enough — if a second build
finishes *after* the server starts, you are back in the same state. Check for more
than one server: `ps -eo pid,lstart,args | grep next-server`.

**Fix — the order matters.**

```bash
cd portal/frontend
for p in $(ss -ltnp | grep :3001 | grep -oP 'pid=\K[0-9]+'); do kill $p; done
sleep 2
rm -rf .next
FASTAPI_URL=http://localhost:8080 npx next build          # finish the build FIRST
FASTAPI_URL=http://localhost:8080 npx next start -p 3001 & # then start ONE server
```

`FASTAPI_URL` must be set at **build** time: `next.config.ts` rewrites are baked into
`routes-manifest.json`, so building without it points the portal at the production
Render host and every API call returns 503 *Service Suspended*.

**Why this deserves a runbook.** It does not look like a build problem. It looks like
a broken page, or — worse — like a page that is fine. An unstyled page has no sidebar
and no margins, so a responsive check measures it as perfectly responsive: this cost a
32/32 PASS on a layout that had not been tested at all. Any automated check against a
running Next server should assert the stylesheet returns 200 before it measures
anything. `scripts/portal_responsive/measure_layout.py` in the refinery repo does.

**Never** run `pkill -f "next start -p 3001"` to clean up — the pattern matches the
calling shell's own command line and kills the shell (exit 144). Kill by PID from `ss`.
