# make check: every tests/test_*.py in its own process, JOBS at a time. unittest files run
# as modules (tests.test_x, so cross-module imports work); a file with no TestCase is a
# script with its own runner (test_messaging.py). hub done's default verify runs this.
SHELL := /bin/bash
JOBS ?= 6

# A test that inherits these writes to the live board, tests a non-default roster, or runs git against another repo.
unexport HUB_DIR HUB_AGENT HUB_PROJECT HUB_CODE_DIR HUB_LEAD HUB_REVIEWER HUB_CLAUDE_AGENTS HUB_CODEX_AGENTS CLAUDE_CODE_SESSION_NAME GIT_DIR GIT_WORK_TREE

# One make check at a time (8 cores, several agents): parallel runs time each other out. Workers get
# 9>&- so a daemon a test leaves behind cannot hold the lock. Keep the lock in the shared hub tree.
CHECK_LOCK ?= $(HOME)/hub/state/make-check.lock
# A queued run whose tree is unchanged since the last passing run (tracked files, index, untracked
# non-ignored files outside projects/, uv and python versions) skips the suite: agents' verifies used to re-test the same
# tree back to back, about 6.5 minutes each. Agents write untracked notes under projects/ all the time
# and no test reads them (test_setup guards that). FORCE=1 always runs. Outside a git checkout it never caches.
CHECK_OK ?= $(HOME)/hub/state/make-check.ok
.PHONY: check
check:
	@start=$$SECONDS; out=$$(mktemp -d); trap 'rm -rf "$$out"' EXIT; \
	mods=$$(ls tests/test_*.py | sed 's#/#.#; s#\.py$$##'); \
	printf '%s\n' $$mods | xargs -P $(JOBS) -I{} sh -c \
	  'o=$$1; m=$$2; f=$$(echo "$$m" | tr . /).py; if grep -q TestCase "$$f"; then set -- -m unittest -q -b "$$m"; else set -- "$$f"; fi; \
	   python3 "$$@" >"$$o/$$m.log" 2>&1 || touch "$$o/$$m.fail"' _ "$$out" {}; \
	ran=$$(awk '/^Ran [0-9]+ tests? in /{s+=$$2} /^[0-9]+ passed, [0-9]+ failed$$/{s+=$$1} END{print s+0}' "$$out"/*.log); \
	fails=$$(cd "$$out" && ls *.fail 2>/dev/null | sed 's/\.fail$$//'); \
	for m in $$fails; do echo "=== $$m"; cat "$$out/$$m.log"; done; \
	n=$$(echo $$mods | wc -w); t=$$((SECONDS - start)); \
	if [ -n "$$fails" ]; then rm -f "$(CHECK_OK)"; echo "make check: FAILED $$(echo $$fails | wc -w)/$$n modules ($$(echo $$fails)); $${ran:-0} tests ran, $${t}s"; exit 1; fi; \
	sk=$$(cat "$$out"/*.log | grep -oE 'skipped=[0-9]+' | cut -d= -f2 | awk '{s+=$$1} END{print s+0}'); \
	skm=$$(grep -l '^skipped:' "$$out"/*.log 2>/dev/null | wc -l); \
	skip=""; [ "$$sk$$skm" != "00" ] && skip=" ($$sk tests skipped, $$skm whole modules skipped)"; \
	if [ -n "$$key" ]; then echo "$$key" > "$(CHECK_OK)"; fi; \
	echo "make check: OK, $$ran tests in $$n modules$$skip, $${t}s"
