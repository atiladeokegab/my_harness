# A Next.js app shows "This page couldn't load", or renders with no CSS

**Repo:** any Next.js app served with `next start`.

## Symptom

The route returns 200, but the browser shows *"This page couldn't load — Reload to try
again"*, or the page renders with **no CSS at all** (no layout, 8px body margin, unstyled
text). DevTools shows 500s on `/_next/static/chunks/*.css` or `*.js`.

## Confirm it

Ask what the served HTML points at, then ask for it:

```bash
PORT=3000
CSS=$(curl -s http://localhost:$PORT/ | grep -oP '/_next/static/[^"]*\.css' | head -1)
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:$PORT$CSS"   # 500 => this bug
ls .next/static/chunks/*.css                                             # different hash
```

The served HTML names a chunk that is not on disk.

## Cause

`next build` writes into `.next` while a `next start` is serving from it. The running server
keeps the old build manifest in memory and hands out chunk URLs that the new build has
replaced. Restarting is not always enough: if a second build finishes *after* the server
starts, you are back in the same state. Check for more than one server:
`ps -eo pid,lstart,args | grep next-server`.

## Fix

The order matters:

```bash
for p in $(ss -ltnp | grep ":$PORT" | grep -oP 'pid=\K[0-9]+'); do kill $p; done
sleep 2
rm -rf .next
npx next build                    # finish the build FIRST
npx next start -p $PORT &         # then start ONE server
```

Any environment variable that `next.config` rewrites read (an API base URL, say) must be set
at **build** time: rewrites are baked into `routes-manifest.json`, so building without it
points the app at whatever the default is, often production.

## Traps while fixing it

- It does not look like a build problem. An unstyled page has no sidebar and no margins, so
  an automated responsive check measures it as perfectly responsive and passes. Any check
  against a running Next server should assert the stylesheet returns 200 before it measures
  anything.
- **Never** clean up with `pkill -f "next start -p $PORT"`: the pattern matches the calling
  shell's own command line and kills the shell (exit 144). Kill by PID from `ss`.
