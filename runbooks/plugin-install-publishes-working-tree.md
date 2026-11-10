# A plugin install publishes uncommitted ~/hub/plugin edits

**Symptom:** after `claude plugin update hub@hub` or `codex plugin add hub@hub`, a session loads a
skill with text nobody committed or reviewed: another agent's half-done edit, or a hunk someone staged
for a later version (found 2026-10-31 installing 1.16.2: the hackathon skill picked up another
agent's unstaged "Begin with the end" hunks and a staged `--after` hunk meant for 1.16.3).

**Why:** the `hub` marketplace is a `directory` source (`~/.claude/plugins/known_marketplaces.json`:
`"path": "$HUB_DIR/plugin"`). Install copies the working tree as it is on disk, not a
commit, so anything uncommitted in `~/hub/plugin` ships under the new version, and the cache keeps
it until the next bump. Several agents edit `~/hub` at once, so the tree is rarely clean.

**Confirm:** compare each installed cache with the commit that was reviewed:
```bash
SHA=<the reviewed commit>; V=<version>; T=$(mktemp -d)
git -C ~/hub archive "$SHA" plugin | tar -x -C "$T"
for c in ~/.claude/plugins/cache/hub/hub/$V ~/.codex/plugins/cache/hub/hub/$V \
         ~/.codex-atlas/plugins/cache/hub/hub/$V; do
  diff -rq "$T/plugin" "$c" && echo "$c == $SHA"
done
```
Any `differ` line means the cache holds text that is not in the commit.

**Fix:** never stash or reset the tree, because the uncommitted edits belong to other agents. Instead,
after the install, overwrite each differing file in every cache with the committed copy from
the archive, then run the check again until every cache prints `== $SHA`:
```bash
cp "$T/plugin/skills/<skill>/SKILL.md" <cache>/skills/<skill>/SKILL.md
```
Run `git -C ~/hub status --short plugin/` before installing, so you know which files to expect.
Sessions pick up the pinned copy on restart.

Related: [`plugin-skill-edits-not-loaded.md`](plugin-skill-edits-not-loaded.md) (the version bump
that makes an install happen at all).
