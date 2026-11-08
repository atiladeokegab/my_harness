"""`hub harness-sync`: carry the private hub into the public harness repo, gated on a personal-data sweep.

harness_sync.json maps live paths (committed files in this repo) to harness paths, with regex
adaptations. Each mapped file is three-way merged: base = the adapted live file at the last synced
commit (recorded in the harness as .hub-sync.json), ours = the harness file, theirs = the adapted
live file at HEAD, so edits made only in the harness survive. The result is committed to a new
branch in a throwaway worktree and never pushed. A sweep hit or a merge conflict commits nothing.
"""

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HUB = Path(__file__).resolve().parent
MANIFEST = HUB / "harness_sync.json"
STATE = ".hub-sync.json"

# Generic patterns; the manifest adds `deny` regexes (names, machine ids, case-insensitive) and `allow` regexes.
SWEEP = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    # A placeholder is a whole path component (you/...), never a prefix of a longer name (you-real).
    "home path": re.compile(r"/home/(?!(?:you|user|me)(?![\w.-])|<)[a-z_][a-z0-9_.-]*"
                            r"|/Users/(?!you(?![\w.-])|<)[A-Za-z][\w.-]*"
                            r"|[A-Za-z]:[\\/]+Users[\\/]+(?!you(?![\w.-])|<)\w+"),
    "phone": re.compile(r"(?<![\w.+])\+\d[\d \-().]{8,20}\d\b"),
    "whatsapp id": re.compile(r"\b\d{8,20}(?:-\d+)?@(?:s\.whatsapp\.net|g\.us|c\.us)\b"),
    "key": re.compile(r"sk-ant-[A-Za-z0-9]|sk_live_[A-Za-z0-9]|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]|github_pat_[A-Za-z0-9]|AIza[0-9A-Za-z_-]{10}"
                      r"|xox[bp]-\d|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:@]+:[^/\s@]+@"),
}
# Emails a public repo may carry, matched against the whole address.
ALLOW_EMAIL = re.compile(r"noreply@anthropic\.com|\d+\+[\w-]+@users\.noreply\.github\.com"
                         r"|[\w.+-]+@example\.(?:com|org|net)|git@github\.com")
# Binary formats the sweep accepts after a byte-level scan; any other non-UTF-8 file fails closed.
# The extension alone is not inspection: the file must also start with its format's magic bytes.
BINARY_OK = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
             ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",), ".ico": (b"\x00\x00\x01\x00",),
             ".woff": (b"wOFF",), ".woff2": (b"wOF2",), ".pdf": (b"%PDF-",)}


def sweep_text(text: str, deny=(), allow=(), skip_kinds=()) -> list[tuple[int, str, str]]:
    """(line number, kind, match) for each personal-data hit."""
    allow_re = [re.compile(a) for a in allow]
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for a in allow_re:  # an allowed span is blanked; the rest of its line is still scanned
            line = a.sub(lambda m: " " * len(m.group()), line)
        for kind, rx in SWEEP.items():
            if kind in skip_kinds:
                continue
            for m in rx.finditer(line):
                if kind == "email" and ALLOW_EMAIL.fullmatch(m.group()):
                    continue
                hits.append((n, kind, m.group()))
        for d in deny:
            m = re.search(d, line, re.I)
            if m:
                hits.append((n, "denied", m.group()))
    return hits


def sweep_files(root: Path, paths, manifest: dict) -> list[str]:
    out = []
    deny, allow = manifest.get("deny", ()), manifest.get("allow", ())
    for p in paths:
        for _, kind, hit in sweep_text(str(p), deny, allow):  # the file's name is published too
            out.append(f"{p}: name: {kind}: {hit}")
        f = root / p
        if f.is_symlink() or not f.is_file():
            continue
        data = f.read_bytes()
        magic = BINARY_OK.get(Path(str(p)).suffix.lower(), ())
        if any(data.startswith(m) for m in magic):
            # Binary: scan its bytes as latin-1, and again with NULs dropped to catch UTF-16 strings inside.
            text = data.decode("latin-1")
            text += "\n" + text.replace("\x00", "")
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is None or "\x00" in text:  # NULs in "UTF-8" text mean BOM-less UTF-16 or a stray binary
                out.append(f"{p}: encoding: not NUL-free UTF-8 (or a binary without its format's magic bytes), "
                           "so it cannot be swept; convert it or exclude it")
                continue
        # `exempt` maps a file glob to sweep kinds it may carry, e.g. a secret scanner's fake test keys.
        skip = [k for g, kinds in manifest.get("exempt", {}).items() if _glob_re(g).match(str(p)) for k in kinds]
        for n, kind, hit in sweep_text(text, deny, allow, skip):
            out.append(f"{p}:{n}: {kind}: {hit}")
    return out


def contained(work: Path, dest: str) -> Path:
    """work/dest, refusing absolute paths, .. and any symlink on the way, before anything reads or writes it."""
    rel = Path(dest)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise SystemExit(f"harness-sync: refusing destination outside the harness: {dest}")
    cur = work
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise SystemExit(f"harness-sync: refusing to write through a symlink in the harness: {cur.relative_to(work)}")
    return cur


def _glob_re(glob: str) -> re.Pattern:
    rx = "".join(".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part)
                 for part in re.split(r"(\*\*|\*)", glob))
    return re.compile(rx + r"\Z")


def target_for(path: str, manifest: dict) -> str | None:
    """Harness path for a live path, or None when unmapped or excluded. First matching entry wins."""
    if any(_glob_re(g).match(path) for g in manifest.get("exclude", ())):
        return None
    for entry in manifest["map"]:
        if _glob_re(entry["live"]).match(path):
            static = entry["live"].split("*")[0]
            prefix = static[: static.rfind("/") + 1]
            return entry["harness"] + path[len(prefix):]
    return None


def adapt(text: str, harness_path: str, manifest: dict) -> str:
    subs = list(manifest.get("subs", ()))
    for glob, file_subs in manifest.get("files", {}).items():
        if _glob_re(glob).match(harness_path):
            subs += file_subs
    for pattern, repl in subs:
        text = re.sub(pattern, lambda m, r=repl: m.expand(r), text, flags=re.M)
    return text


def install_gaps(work: Path, manifest: dict) -> list[str]:
    """Hub modules board.py needs (imports followed transitively) that the harness's install.sh never copies:
    a fresh install would crash on any command."""
    inst, board = work / "install.sh", target_for("board.py", manifest)
    if not inst.is_file() or not board or not (work / board).is_file():
        return []
    hub, script = (work / board).parent, inst.read_text()
    seen, todo, gaps = set(), ["board"], []
    while todo:
        mod = todo.pop()
        if mod in seen or not (hub / f"{mod}.py").is_file():
            continue
        seen.add(mod)
        if mod != "board" and not re.search(rf"(?<![\w.]){re.escape(mod)}\.py\b", script):
            gaps.append(f"{mod}.py")
        for node in ast.walk(ast.parse((hub / f"{mod}.py").read_text())):
            if isinstance(node, ast.Import):
                todo += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                todo.append(node.module.split(".")[0])
    return sorted(gaps)


def _git(repo: Path, *args, check=True) -> str:
    # Hooks off: a harness hook could push (post-commit) or rewrite what the sweep passed.
    r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def _show(repo: Path, commit: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _merge(ours: str, base: str, theirs: str) -> tuple[str, bool]:
    with tempfile.TemporaryDirectory() as d:
        files = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            f = Path(d) / name
            f.write_text(text)
            files.append(str(f))
        r = subprocess.run(["git", "merge-file", "-p", "-L", "harness", "-L", "last-sync", "-L", "live", *files],
                           capture_output=True, text=True)
    if r.returncode < 0 or r.returncode > 127:
        raise SystemExit(f"git merge-file failed: {r.stderr.strip()}")
    return r.stdout, r.returncode > 0


def _decide(cur, old, new):
    """One file's three-way outcome from (harness, last-sync, live), all str or all bytes (binary).

    Returns (action, content): 'skip' (the harness left it out at the last sync), 'delete',
    'write', 'conflict' (content = text with markers, or None) or None (nothing to do).
    """
    if cur is None:
        return ("skip", None) if old is not None else ("write", new)
    if new is None:
        return ("delete", None) if cur == old else ("conflict", None)
    if cur == new:
        return (None, None)
    if isinstance(cur, bytes):  # binary: no merge, take live only where the harness never diverged
        return ("write", new) if cur == old else ("conflict", None)
    merged, conflict = _merge(cur, old or "", new)
    if conflict:
        return ("conflict", merged)
    return (None, None) if merged == cur else ("write", merged)


def plan(live: Path, work: Path, manifest: dict, since: str, head: str):
    """Apply the sync into `work`. Returns (changed, conflicts, deleted, skipped) harness paths."""
    changed, conflicts, deleted, skipped = [], [], [], []
    now = set(_git(live, "ls-tree", "-r", "--name-only", head).splitlines())
    before = set(_git(live, "ls-tree", "-r", "--name-only", since).splitlines())
    for path in sorted(now | before):
        dest = target_for(path, manifest)
        if dest is None:
            continue
        old, new = _show(live, since, path), _show(live, head, path)
        if old == new:
            continue  # unchanged live since the last sync
        f = contained(work, dest)
        cur = f.read_bytes() if f.is_file() else None
        try:
            texts = [None if b is None else b.decode("utf-8") for b in (cur, old, new)]
        except UnicodeDecodeError:
            texts = None
        if texts is not None:
            cur, old, new = texts
            old = None if old is None else adapt(old, dest, manifest)
            new = None if new is None else adapt(new, dest, manifest)
            if old == new:
                continue
        action, content = _decide(cur, old, new)
        if action == "skip":
            skipped.append(dest)
        elif action == "delete":
            f.unlink()
            deleted.append(dest)
        elif action in ("write", "conflict"):
            (changed if action == "write" else conflicts).append(dest)
            if content is not None:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(content) if isinstance(content, bytes) else f.write_text(content)
    return changed, conflicts, deleted, skipped


def run(live: Path, harness: Path, manifest: dict, init: str | None = None, branch: str | None = None) -> int:
    if _git(harness, "status", "--porcelain").strip():
        print(f"harness-sync: {harness} has uncommitted changes; commit or clean them first", file=sys.stderr)
        return 2
    head = _git(live, "rev-parse", "HEAD").strip()
    state_file = harness / STATE
    since = init or (json.loads(state_file.read_text())["live_commit"] if state_file.is_file() else None)
    if not since:
        print(f"harness-sync: no {STATE} in the harness; seed it with --init <live commit of the last port>",
              file=sys.stderr)
        return 2
    since = _git(live, "rev-parse", since).strip()
    if since == head:
        print("harness-sync: nothing new since", head[:7])
        return 0
    branch = branch or f"hub-sync-{head[:7]}"
    work = Path(tempfile.mkdtemp(prefix="harness-sync-"))
    shutil.rmtree(work)
    _git(harness, "worktree", "add", "-q", "-b", branch, str(work), "HEAD")
    keep = False
    try:
        changed, conflicts, deleted, skipped = plan(live, work, manifest, since, head)
        for s in skipped:
            print(f"  skipped (left out of the harness at the last sync): {s}")
        hits = sweep_files(work, changed + conflicts, manifest)
        gaps = install_gaps(work, manifest)
        if gaps:
            print("harness-sync: FAILED, install.sh does not install modules board.py imports (nothing committed): "
                  + ", ".join(gaps) + "; add them to its module list in the harness first", file=sys.stderr)
            return 1
        if hits:
            print("harness-sync: FAILED, personal data in the synced files (nothing committed):", file=sys.stderr)
            for h in hits:
                print("  " + h, file=sys.stderr)
            print("adapt them in harness_sync.json (subs/files), exclude the file, or fix it live", file=sys.stderr)
            return 1
        if conflicts:
            keep = True
            print(f"harness-sync: {len(conflicts)} conflict(s); resolve in {work}, sweep with "
                  f"`hub harness-sync --sweep`, then commit on {branch}:", file=sys.stderr)
            for c in conflicts:
                print("  " + c, file=sys.stderr)
            return 1
        (work / STATE).write_text(json.dumps({"live_commit": head}, indent=2) + "\n")
        _git(work, "add", "-A", "--", *changed, *deleted, STATE)
        _git(work, "commit", "-q", "-m",
             f"hub sync: live {since[:7]}..{head[:7]}\n\n{len(changed)} changed, {len(deleted)} removed.")
        print(f"harness-sync: {len(changed)} changed, {len(deleted)} removed; branch {branch} "
              f"(not pushed): review with git -C {harness} log -p HEAD..{branch}")
        return 0
    finally:
        if not keep:
            _git(harness, "worktree", "remove", "--force", str(work), check=False)
            if not _git(harness, "rev-list", f"HEAD..{branch}", check=False).strip():
                _git(harness, "branch", "-D", branch, check=False)


def cmd_harness_sync(args) -> None:
    manifest = json.loads(Path(args.manifest).read_text())
    if args.sweep:
        hits = sweep_files(Path.cwd(), args.sweep, manifest)
        for h in hits:
            print(h)
        sys.exit(1 if hits else 0)
    harness = Path(args.harness or manifest["harness"]).expanduser()
    sys.exit(run(HUB, harness, manifest, init=args.init, branch=args.branch))


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("harness-sync", help="sync the hub into the public harness on a review branch (never pushes)")
    p.add_argument("--harness", help="harness checkout (default: the manifest's)")
    p.add_argument("--manifest", default=str(MANIFEST))
    p.add_argument("--init", metavar="COMMIT", help="live commit of the last sync, when the harness has no .hub-sync.json")
    p.add_argument("--branch", help="branch name (default hub-sync-<live sha>)")
    p.add_argument("--sweep", nargs="+", metavar="FILE", help="only sweep these files for personal data")
    p.set_defaults(fn=cmd_harness_sync)
