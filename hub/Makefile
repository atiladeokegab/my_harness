# make check: every tests/test_*.py in its own process, JOBS at a time. unittest files run
# as modules (tests.test_x, so cross-module imports work); a file with no TestCase is a
# script with its own runner (test_messaging.py). hub done's default verify runs this.
SHELL := /bin/bash
JOBS ?= 4

# A test that inherits these writes to the live board, tests a non-default roster, or runs git against another repo.
unexport HUB_DIR HUB_AGENT HUB_PROJECT HUB_CODE_DIR HUB_LEAD HUB_REVIEWER HUB_CLAUDE_AGENTS HUB_CODEX_AGENTS CLAUDE_CODE_SESSION_NAME GIT_DIR GIT_WORK_TREE

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
	if [ -n "$$fails" ]; then echo "make check: FAILED $$(echo $$fails | wc -w)/$$n modules ($$(echo $$fails)); $${ran:-0} tests ran, $${t}s"; exit 1; fi; \
	echo "make check: OK, $$ran tests in $$n modules, $${t}s"
