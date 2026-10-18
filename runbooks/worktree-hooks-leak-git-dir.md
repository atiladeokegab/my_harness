# A hook run from a linked worktree rewrites the real repo

**Symptom.** After a commit made in a linked worktree (`git worktree add`, `.worktrees/`,
`.claude/worktrees/`), history in the *main* repo changes. It happened to a hub kept in git: every
commit under two directories vanished from `~/hub` after a commit in a worktree of it.

**Cause.** Git runs hooks from a linked worktree with an **absolute** `GIT_DIR` and
`GIT_INDEX_FILE` (the main checkout passes neither). A hook that clones elsewhere and runs git
there still acts on the real repo. The culprit was a post-commit hook that mirrored the repo by
cloning it and running git-filter-repo on the clone; with the leaked `GIT_DIR`, the rewrite hit
the original.

**Confirm.**

```bash
git -C ~/hub worktree list            # any linked worktree of the repo is the risk
ls ~/hub/.git/hooks | grep -v sample  # which hooks would run
```

**Fix and rule.**
- Hook scripts start with `unset $(git rev-parse --local-env-vars)` and refuse to rewrite
  anything but a temp clone. Rewritten history is unrecoverable unless it was pushed somewhere.
- Never make a linked worktree of a repo whose hooks run git elsewhere. To review or test an older
  commit, use a plain clone:
  `git clone -q --no-hardlinks ~/hub /tmp/hub-review && git -C /tmp/hub-review checkout -q <sha>`.
- Any new hook that runs git in another repo must start with the unset line.
- Linked worktrees of repos without such hooks are fine.
