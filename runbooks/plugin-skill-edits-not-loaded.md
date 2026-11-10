# Skill edits in ~/hub/plugin don't reach sessions

**Symptom:** you edit `~/hub/plugin/skills/<skill>/SKILL.md`, commit it, and a session that
loads the skill still gets the old text (found 2026-09-29: the hackathon skill served the
27 Sep version, missing two days of fixes).

**Why:** Claude Code installs the `hub` plugin into `~/.claude/plugins/cache/hub/hub/<version>/`
and serves that copy. The cache is keyed by the version in `plugin/.claude-plugin/plugin.json`;
if the version doesn't change, the copy is never refreshed.

**Confirm:**
```bash
diff ~/.claude/plugins/cache/hub/hub/$(sed -n 's/.*"version": "\(.*\)".*/\1/p' ~/hub/plugin/.claude-plugin/plugin.json)/skills/hackathon/SKILL.md \
     ~/hub/plugin/skills/hackathon/SKILL.md | head
```

**Fix:** bump `version` in `plugin/.claude-plugin/plugin.json`, then
```bash
claude plugin validate ~/hub/plugin
claude plugin marketplace update hub
claude plugin update hub@hub      # then restart sessions that should see it
```
Do this whenever a skill change should take effect, as part of committing it.

**Codex seat (added 2026-10-18):** Codex reads `plugin/.codex-plugin/plugin.json`, which carries its own
`version`. Bump both files together, then `codex plugin add hub@hub` (it reinstalls at the new version).
The plugin sat at 1.12.4 from 12 Oct to 18 Oct while skill edits piled up, because nobody bumped it.
