# `git push` succeeds but the Vercel site never updates

**Applies to:** any Vercel project linked to a git repo. **First cost:** two months of
stale production, without a single visible error.

---

## Symptom

The live site does not change after a push, but **everything looks fine locally**:

- `git push` succeeds and prints a normal `old..new` range
- the commit is on GitHub on the right branch
- Vercel *is* connected — the project is not disconnected or misconfigured
- no CI job fails in a way that mentions the website

The only trace is a commit status on GitHub that nothing surfaces unless you look for it.

## Root cause

Vercel refuses to build when the **git author of the commit** is not a member of the Vercel
team. It does not care who *pushed*. Those are two different identities:

| | Identity | Source |
|---|---|---|
| Who pushes | the account owning your auth token | credential helper / `gh auth` |
| Who authored | resolved from the commit **email** | `git config user.email` |

If you have two GitHub accounts, and the email in your global git config belongs to the one
that is *not* on the Vercel team, every commit is attributed to the wrong account and
Vercel blocks it:

```
Git author <other-account> must have access to the project on Vercel to create deployments.
```

## Diagnose

```bash
# 1. Latest Vercel status on HEAD (the endpoint returns every status,
#    newest first — [0] pins it to the current one)
gh api repos/<owner>/<repo>/commits/HEAD/statuses \
  --jq '[.[] | select(.context=="Vercel")][0] | "\(.state) — \(.description)"'

# 2. Who GitHub thinks authored it
gh api repos/<owner>/<repo>/commits/HEAD --jq '.author.login'

# 3. What this checkout is stamping on commits
git config user.email
```

`author.login` must be the account on the Vercel team. If it is not, this runbook applies.

## Fix

Set this checkout's commit email to the **no-reply address** of the account that owns the
Vercel project (GitHub → Settings → Emails shows it, `<id>+<login>@users.noreply.github.com`):

```bash
git config user.email "<id>+<login>@users.noreply.github.com"
```

Re-authoring is not retroactive, so make a new commit (an empty one is fine) to trigger a
fresh deploy:

```bash
git commit --allow-empty -m "chore: trigger deploy"
git push
```

**Redo this on every fresh clone and every new machine** — a new checkout inherits the
global git config. Write it into the project's `CLAUDE.md` as a trap, with the verify
command below, so agents do it too.

## Verify — after every push that should change the site

```bash
gh api repos/<owner>/<repo>/commits/HEAD/statuses \
  --jq '[.[] | select(.context=="Vercel")][0] | "\(.state) — \(.description)"'
# expect: success — Deployment has completed
curl -s -L https://<your-site> | grep -c "some-string-you-just-changed"
```

A build takes a few minutes; `pending` is normal while it runs. Poll on a long interval;
do not block a session on it.

## Permanent fix

Add the other account to the Vercel team (*Team Settings → Members → Invite*), or accept
the invite link Vercel embeds in the failing commit status. That needs a browser, so route
it to the human.

---

## Different failure: Vercel never picks the commit up at all

Distinguish it from the author block by the **number of statuses**, not their state:

| | Author block | Missed webhook |
|---|---|---|
| `commits/HEAD/statuses` | one `Vercel` status, `error` | **zero statuses** |
| `commits/HEAD/status` `.total` | 1 | **0** |

```bash
gh api repos/<owner>/<repo>/commits/HEAD/status --jq '{state, total:(.statuses|length)}'
```

If the previous commit deployed fine and the author is right, Vercel just never got the
hook. Waiting does not fix it. Push an empty commit; it is usually picked up within a
minute.
