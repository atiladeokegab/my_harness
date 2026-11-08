#!/usr/bin/env python3
"""Keep harness output out of repos other people work in.

Three commands, all operating on one list of patterns so the doctrine, the hook and the
checks can never disagree:

    hub init-repo <path>    per-clone ignore rules + a pre-commit hook that refuses
    hub ship-check [path]   what a push would add, bucketed, before you push it
    hub scrub <path>        retrofit: move tracked harness files out, then untrack

The rule these enforce is in ~/hub/CLEAN-REPO.md. The short version: would a teammate who
never used Claude Code open this file on purpose? No -> it does not belong in their repo.

Nothing here rewrites history, and nothing here is destructive without --apply.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HUB_DIR = os.environ.get("HUB_DIR") or os.path.dirname(os.path.realpath(__file__))
PROJECTS = os.path.join(HUB_DIR, "projects")

# Each entry is (regex, gitignore-glob). Paired rather than converted, because
# regex -> glob conversion is lossy: "docs/reviews?/" as a glob means a literal single
# character, which silently ignores nothing. Add to both halves or neither.
#
# Deliberately narrow. docs/runbooks/ is NOT here -- a product's runbooks are real
# operational documentation a human on-call would open at 3am. Over-matching would teach
# everyone to pass --no-verify, which costs more than the slop does.
HARNESS_PAIRS = [
    (r"(^|/)CLAUDE\.md$",                 "CLAUDE.md"),
    (r"(^|/)AGENTS(-[a-z]+)?\.md$",       "AGENTS.md"),
    (r"(^|/)AGENTS-[a-z]+\.md$",          "AGENTS-*.md"),
    (r"(^|/)\.claude/",                   ".claude/"),
    (r"(^|/)docs/superpowers/",           "docs/superpowers/"),
    (r"(^|/)roadmap\.md$",                "roadmap.md"),
    (r"(^|/)plan\.md$",                   "plan.md"),
    (r"(^|/)docs/plans/",                 "docs/plans/"),
    (r"(^|/)docs/specs/",                 "docs/specs/"),
    (r"(^|/)implementation[-_]?summary[^/]*\.md$", "implementation*summary*.md"),
    (r"(^|/)session[-_]?summary[^/]*\.md$",        "session*summary*.md"),
    (r"(^|/)docs/reviews?/",              "docs/review/"),
    (r"(^|/)docs/reviews/",               "docs/reviews/"),
    (r"(^|/)debate/",                     "debate/"),
    (r"(^|/)scratch/",                    "scratch/"),
    (r"(^|/)[^/]*handoff[^/]*\.md$",      "*handoff*.md"),
    (r"(^|/)\.hub/",                      ".hub/"),
    # superpowers: brainstorm mockups and SDD workspaces, and its worktree skill, which
    # edits and commits the shared .gitignore unless git already ignores .worktrees/.
    # A per-clone exclude makes `git check-ignore` pass, so it never touches .gitignore.
    (r"(^|/)\.superpowers/",              ".superpowers/"),
    (r"(^|/)\.worktrees/",              ".worktrees/"),
    (r"(^|/)worktrees/",                  "worktrees/"),
]

HARNESS = [r for r, _ in HARNESS_PAIRS]
def _ci(glob):
    """HANDOFF.md and handoff.md are the same slop, but exclude globs are case-sensitive
    on Linux: scrub untracked HANDOFF.md and it came straight back as `??`."""
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else c for c in glob)


GLOBS = sorted({_ci(g) for _, g in HARNESS_PAIRS})

# Files that are product by name, whatever else matches. A repo is allowed its own docs.
PRODUCT = {
    "README.md", "PRODUCT.md", "DEMO.md", "CHANGELOG.md",
    "CONTRIBUTING.md", "LICENSE", "LICENSE.md", "SECURITY.md",
}

MARK_BEGIN = "# >>> hub clean-repo (managed, per clone, not committed)"
MARK_END = "# <<< hub clean-repo"

_rx = re.compile("|".join(HARNESS), re.I)  # CLAUDE.md and claude.md are the same slop


def classify(path):
    """'harness', 'product', or 'other'.

    Pattern beats name, deliberately. A README at the repo root is product; a README
    inside debate/ or docs/superpowers/ is part of the harness output that directory
    exists to hold. The earlier order said product and disagreed with the hook and the
    ignore file, which both matched on path -- one rule that gave two answers.
    """
    if _rx.search(path):
        return "harness"
    if os.path.basename(path) in PRODUCT:
        return "product"
    return "other"


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def repo_root(path):
    path = os.path.abspath(path or ".")
    if not os.path.isdir(path):
        die(f"not a directory: {path}")
    root = git(path, "rev-parse", "--show-toplevel", check=False)
    if not root:
        die(f"not a git repository: {path}")
    return root


HOOK = """#!/bin/sh
# hub clean-repo pre-commit hook. Managed by `hub init-repo`; per clone, not committed.
#
# Refuses to commit harness output into a repo other people work in. If the human asked
# for one of these files, commit it with --no-verify -- that is a deliberate override,
# which is the point: the hook makes the decision visible, it does not make it for you.
bad=$(git diff --cached --name-only --diff-filter=ACRT | grep -iE '{rx}' || true)
if [ -n "$bad" ]; then
  echo "clean-repo: harness files blocked from this commit:"
  echo "$bad" | sed 's/^/  /'
  echo
  echo "  move them to {projects}/, or commit with --no-verify if the human asked for them"
  exit 1
fi
"""


def cmd_init_repo(a):
    """Install the per-clone ignore rules and the pre-commit hook.

    Exits non-zero if the guard is not actually active afterwards. Printing "is set up"
    over a hook git will never run is worse than printing nothing: it converts an
    unprotected repo into one everybody believes is protected.
    """
    root = repo_root(a.path)
    name = os.path.basename(root)
    failures = []

    # git rev-parse --git-path, not .git/<x>. In a worktree .git is a FILE, so
    # os.path.join(root, ".git", "info") is NotADirectoryError; and core.hooksPath moves
    # hooks somewhere else entirely. Both reproduced by Prometheus.
    def gpath(rel):
        out = git(root, "rev-parse", "--git-path", rel, check=False)
        return out if os.path.isabs(out) else os.path.join(root, out)

    # .git/info/exclude, never .gitignore: editing a shared .gitignore is itself a
    # harness edit to somebody else's repo.
    exclude = gpath("info/exclude")
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    body = Path(exclude).read_text() if os.path.exists(exclude) else ""
    block = "\n".join([MARK_BEGIN, *GLOBS, MARK_END]) + "\n"
    if MARK_BEGIN in body:
        body = re.sub(re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END) + r"\n?",
                      block, body, flags=re.S)
    else:
        body = body.rstrip("\n") + ("\n\n" if body.strip() else "") + block
    Path(exclude).write_text(body)
    print(f"ignore rules  -> {exclude}")

    # The hook is the only layer that binds every vendor -- Claude, Codex, a human in a
    # hurry. Never clobber a hook somebody else wrote.
    hooks_dir = git(root, "config", "--get", "core.hooksPath", check=False)
    if hooks_dir:
        hooks_dir = hooks_dir if os.path.isabs(hooks_dir) else os.path.join(root, hooks_dir)
        print(f"note          -> core.hooksPath is set; git runs hooks from {hooks_dir}")
    else:
        hooks_dir = os.path.dirname(gpath("hooks/pre-commit"))
    hook = os.path.join(hooks_dir, "pre-commit")

    ours = "hub clean-repo pre-commit hook"
    if os.path.exists(hook) and ours not in Path(hook).read_text():
        print(f"pre-commit    -> NOT INSTALLED: a different hook already exists at {hook}")
        print("                 merge by hand, then re-run. Refusing to overwrite it.")
        failures.append("pre-commit hook not installed")
    else:
        os.makedirs(hooks_dir, exist_ok=True)
        Path(hook).write_text(HOOK.format(rx="|".join(HARNESS), projects=os.path.join(PROJECTS, name)))
        os.chmod(hook, 0o755)
        # Verify rather than assume: the path git will actually consult must be ours.
        active = gpath("hooks/pre-commit")
        active = os.path.join(hooks_dir, "pre-commit") if hooks_dir else active
        if os.path.exists(active) and ours in Path(active).read_text() and os.access(active, os.X_OK):
            print(f"pre-commit    -> {hook}")
        else:
            print(f"pre-commit    -> WROTE {hook} but git does not appear to use it")
            failures.append("pre-commit hook written but not active")

    side = os.path.join(PROJECTS, name)
    os.makedirs(side, exist_ok=True)
    print(f"harness output-> {side}")

    if failures:
        print("\n" + name + " is NOT fully guarded: " + "; ".join(failures))
        sys.exit(1)
    print(f"\n{name} is set up. Plans, reviews and roadmaps go to the last path, not the tree.")


def find_base(root):
    """Upstream, else origin/main or origin/master, else None.

    The hook, the `hub done` nudge and ship-check all ask this one function. They used
    to disagree: the first two needed @{u}, so an unpushed feature branch -- the normal
    state of agent work -- was silent in both while ship-check said NOT clean.
    """
    up = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if up:
        return up
    for cand in ("origin/main", "origin/master"):
        if git(root, "rev-parse", "--verify", "--quiet", cand, check=False):
            return cand
    return None


def base_ref(root, given):
    base = given or find_base(root)
    if not base:
        die("no upstream and no origin/main -- pass --base <ref>")
    return base


def cmd_ship_check(a):
    """What a push would add, bucketed, before it lands in somebody else's tree."""
    root = repo_root(a.path)
    # The hub is where harness output belongs; checking it would cry wolf every session.
    if getattr(a, "quiet", False):
        if os.path.realpath(root) == os.path.realpath(HUB_DIR):
            sys.exit(0)
        if not a.base and not find_base(root):
            sys.exit(0)  # nothing to push to yet
    base = base_ref(root, a.base)

    # Three dots, not two. Against a branch that has moved on, `base..HEAD` reports
    # THEIR commits as your modifications -- it diffs the two tips. `base...HEAD` diffs
    # from the merge base, which is the only honest answer to "what would my push add".
    rng = f"{base}...HEAD"
    # ACMRT, not A. A rename is R and a copy is C: `git mv notes.md docs/roadmap.md`
    # is neither added nor modified, and walked straight past both checks until
    # Prometheus reproduced it. --diff-filter reports the DESTINATION path for R and C,
    # which is the path that matters here.
    added = git(root, "diff", "--name-only", "--diff-filter=ACRT", rng).splitlines()
    modified = git(root, "diff", "--name-only", "--diff-filter=M", rng).splitlines()
    commits = git(root, "log", "--oneline", f"{base}..HEAD").splitlines()
    deps = git(root, "diff", "--name-only", rng, "--",
               "package.json", "package-lock.json", "pyproject.toml", "uv.lock",
               "requirements.txt", "Cargo.toml").splitlines()

    buckets = {"harness": [], "other": [], "product": []}
    for f in added:
        buckets[classify(f)].append(f)

    if a.quiet:
        # Session-start hook mode: say nothing unless there is something to say.
        if buckets["harness"]:
            print(f"clean-repo: {len(buckets['harness'])} harness file(s) would ship to "
                  f"{base}: " + ", ".join(buckets["harness"][:4])
                  + ("..." if len(buckets["harness"]) > 4 else ""))
            print("Move them to " + os.path.join(PROJECTS, os.path.basename(root))
                  + "/ before pushing. `hub ship-check` for the full list.")
            sys.exit(1)
        sys.exit(0)

    print(f"against {base} -- {len(commits)} commit(s), {len(added)} added, {len(modified)} modified\n")

    if buckets["harness"]:
        print("HARNESS -- do not ship these:")
        for f in buckets["harness"]:
            print(f"  {f}")
        print()

    docs = [f for f in buckets["other"] if f.endswith((".md", ".txt", ".rst"))]
    if docs:
        print("DOCS added -- did someone ask for each of these?")
        for f in docs:
            print(f"  {f}")
        print()

    if modified:
        print("MODIFIED files that already existed -- theirs, unless you were asked:")
        for f in modified:
            print(f"  {f}")
        print()

    if deps:
        print("DEPENDENCY manifests changed -- that is everyone's build:")
        for f in deps:
            print(f"  {f}")
        print()

    code = [f for f in buckets["other"] + buckets["product"] if f not in docs]
    print(f"{len(code)} other file(s) added.")

    if buckets["harness"]:
        print("\nverdict: NOT clean. Move the harness files to "
              f"{os.path.join(PROJECTS, os.path.basename(root))}/ first.")
        sys.exit(1)
    print("\nverdict: clean of harness.")


def cmd_scrub(a):
    """Retrofit an existing repo: move tracked harness files out, then untrack them."""
    root = repo_root(a.path)
    name = os.path.basename(root)
    tracked = git(root, "ls-files").splitlines()
    hits = [f for f in tracked if classify(f) == "harness"]

    # A doctrine you cannot disagree with is a doctrine people route around. --keep is
    # the escape hatch: a product's root CLAUDE.md may carry traps a fresh clone needs
    # to know about, and that is a better reason to keep it than the rule is to drop it.
    if a.keep:
        keeps = [re.compile(k) for k in a.keep]
        held = [f for f in hits if any(k.search(f) for k in keeps)]
        hits = [f for f in hits if f not in held]
        for f in held:
            print(f"keeping (--keep): {f}")
        if held:
            print()

    if not hits:
        print(f"{name}: no tracked harness files. Nothing to scrub.")
        return

    size = 0
    for f in hits:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            size += os.path.getsize(p)
    print(f"{name}: {len(hits)} tracked harness file(s), {size / 1e6:.1f} MB\n")
    for f in hits[:a.limit]:
        print(f"  {f}")
    if len(hits) > a.limit:
        print(f"  ... and {len(hits) - a.limit} more")

    dest = os.path.join(PROJECTS, name)
    if not a.apply:
        print(f"\ndry run. --apply would copy these to {dest}/ and then `git rm --cached` them.")
        print("Nothing is deleted from history, and the copy happens before the untrack.")
        return

    # Copy first, untrack second. If the copy fails we have not removed anything yet.
    #
    # And refuse to overwrite: two repos share a basename more often than you would
    # think, and a silent copy2 over an existing file destroys the only remaining copy
    # of something already untracked elsewhere. Nothing is removed unless every file
    # can be safely placed.
    clashes = []
    for f in hits:
        src = os.path.join(root, f)
        out = os.path.join(dest, f)
        if os.path.isfile(src) and os.path.exists(out):
            if Path(out).read_bytes() != Path(src).read_bytes():
                clashes.append(f)
    if clashes:
        print(f"\nrefusing to scrub: {len(clashes)} file(s) already exist in {dest}/ "
              "with different content:")
        for f in clashes[:10]:
            print(f"  {f}")
        print("\nNothing was copied and nothing was untracked. Move or rename the existing "
              "copies first --\ntwo repos with the same basename land in the same place.")
        sys.exit(1)

    for f in hits:
        src = os.path.join(root, f)
        if not os.path.isfile(src):
            continue
        out = os.path.join(dest, f)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)
    print(f"\ncopied {len(hits)} file(s) to {dest}/")
    # The copy is only safe if it is versioned: "nothing is lost because ~/hub is a git
    # repo" was false while the copies sat uncommitted.
    # Best effort: a Codex sandbox can write ~/hub but not ~/hub/.git (Prometheus,
    # T-101), and failing here would stop the scrub after the copy but before the
    # untrack. Say so and carry on; the copies are on disk either way.
    if git(HUB_DIR, "rev-parse", "--is-inside-work-tree", check=False) == "true":
        r = subprocess.run(["git", "-C", HUB_DIR, "add", "--", dest], capture_output=True, text=True)
        if r.returncode == 0 and subprocess.run(
                ["git", "-C", HUB_DIR, "diff", "--cached", "--quiet", "--", dest]).returncode:
            r = subprocess.run(["git", "-C", HUB_DIR, "commit", "-q", "-m",
                                f"scrub {name}: {len(hits)} harness file(s) moved out of the tree",
                                "--", dest], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"committed the copies in {HUB_DIR}")
        else:
            print(f"NOT committed in {HUB_DIR} ({r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'git failed'})")
            print(f"  ask someone who can write {HUB_DIR}/.git to commit {dest}/")

    for i in range(0, len(hits), 100):
        git(root, "rm", "--cached", "--quiet", "--", *hits[i:i + 100])
    print(f"untracked {len(hits)} file(s) -- staged, not committed")
    print("\nReview with `git -C %s status`, then commit. The working copies stay on disk;" % root)
    print("the per-clone ignore rules from `hub init-repo` keep them from coming back.")


def commit_identity():
    """(name, email) for a new project: $HUB_GIT_NAME/$HUB_GIT_EMAIL, else your global git config, else
    <user> <user@localhost> -- set the env vars when a host needs a specific account (a deploy bot that
    builds only commits from team members)."""
    def glob(key):
        try:
            r = subprocess.run(["git", "config", "--global", key], capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""
    user = os.environ.get("USER") or "hub"
    return (os.environ.get("HUB_GIT_NAME") or glob("user.name") or user,
            os.environ.get("HUB_GIT_EMAIL") or glob("user.email") or f"{user}@localhost")


def cmd_new_project(a):
    """Create a repo and install the guards, in one step.

    Lives in this module rather than its own because the only thing it does that
    `git init` does not is call init_repo -- a third file for forty lines is the
    over-building ponytail warns about.
    """
    name = a.name
    code = os.environ.get("HUB_CODE_DIR") or os.path.join(os.path.expanduser("~"), "code")
    root = os.path.abspath(a.path or os.path.join(code, name))

    # The launchers resolve a bare project name against $HUB_CODE_DIR/<name> and ~/<name>.
    # Anywhere else and `zeus <name>` will not find it.
    parent = os.path.dirname(root)
    home = os.path.expanduser("~")
    if parent not in (os.path.abspath(code), home):
        print(f"warning: {root} is outside $HUB_CODE_DIR and ~/ -- `zeus {name}` will not find it")

    if os.path.exists(os.path.join(root, ".git")):
        print(f"{root} is already a git repository; installing guards only\n")
    else:
        # A Codex worker's sandbox cannot write ~/code (Prometheus, T-101): say so in
        # one line rather than a traceback, and say what to do instead.
        try:
            os.makedirs(root, exist_ok=True)
        except OSError as e:
            die(f"cannot create {root}: {e.strerror}. If you are sandboxed, pass --path to "
                "a directory you can write, or ask the human -- creating projects is "
                "Zeus's job in hub-planning, not a worker's.")
        git(root, "init", "-q", "-b", "main")
        print(f"repo          -> {root}")

    # The trap this exists to close: committing as the wrong account can attribute the commit
    # to a user a deploy host does not know, and the deploy fails silently. And with no global
    # user.name, the first commit in every new project fails with "empty ident name".
    name_, email = commit_identity()
    git(root, "config", "user.email", email)
    git(root, "config", "user.name", name_)
    print(f"commit identity-> {name_} <{email}>  (HUB_GIT_NAME / HUB_GIT_EMAIL to change)")

    a.path = root
    cmd_init_repo(a)

    print(f"\nNext: `zeus {name}` and plan it before any task exists.")
    print("Zeus will load the hub-planning skill; it knows the rest.")


def register(sub, parent=None):
    np = sub.add_parser("new-project",
                        help="create a repo with the commit identity and guards already set")
    np.add_argument("name")
    np.add_argument("--path", help="where to put it (default: $HUB_CODE_DIR/<name>, else ~/code/<name>)")
    np.set_defaults(fn=cmd_new_project)

    ir = sub.add_parser("init-repo",
                        help="install per-clone ignore rules and a pre-commit hook")
    ir.add_argument("path", nargs="?", default=".")
    ir.set_defaults(fn=cmd_init_repo)

    sc = sub.add_parser("ship-check",
                        help="what a push would add, bucketed, before you push it")
    sc.add_argument("path", nargs="?", default=".")
    sc.add_argument("--base", help="compare against this ref (default: upstream, then origin/main)")
    sc.add_argument("--quiet", action="store_true",
                    help="print nothing unless harness files would ship (for hooks)")
    sc.set_defaults(fn=cmd_ship_check)

    sr = sub.add_parser("scrub",
                        help="retrofit: move tracked harness files out, then untrack them")
    sr.add_argument("path", nargs="?", default=".")
    sr.add_argument("--apply", action="store_true", help="actually do it (default: dry run)")
    sr.add_argument("--limit", type=int, default=20, help="how many paths to list (default 20)")
    sr.add_argument("--keep", action="append", metavar="REGEX",
                    help="leave matching paths tracked (repeatable)")
    sr.set_defaults(fn=cmd_scrub)
