"""Undeclared dependencies (T-583; living-spec design, Addendum 3 item 4).

A PR that adds a dependency or tool which is not on a Decided row of the product repo's stack table is held, the
same way hub live holds a PR with no Evidence: hub live comments once naming the row to add, and live_merge never
merges it. Adding the row goes through review like any other change.

What counts as added: names in the PR head's dependency files that the base branch's copy does not have.
  pyproject.toml   [project] dependencies and optional-dependencies, [dependency-groups], [tool.uv]
                   dev-dependencies, [build-system] requires
  package.json     dependencies, devDependencies, peerDependencies, optionalDependencies
  Dockerfile*      FROM images (not `scratch`, not an earlier stage)
uv.lock is not read: its new entries are transitive, and a direct dependency always shows in pyproject.toml.

Declared means: the name, lowercased with runs of other characters as "-", appears as whole words in a row whose
Status cell is Decided ("opentelemetry-sdk" is on the row "OpenTelemetry SDK, spans as ..."). The stack table is
the PRD's constraints.stack, else docs/stack.md, read at the PR's base branch. A repo without one is not gated.

Pure apart from `fetch(path, ref)`: text, None when the file does not exist there, or Unreadable raised.
"""

import posixpath
import json
import re
import tomllib

DEFAULT_STACK = "docs/stack.md"


class Unreadable(Exception):
    """A file could not be read (not a plain 404): the PR waits, it is never judged on half the facts."""


def kind(path):
    name = path.rsplit("/", 1)[-1]
    if name == "pyproject.toml":
        return "pyproject"
    if name == "package.json":
        return "package"
    if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
        return "docker"
    return None


def norm(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _pep508(spec):
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec) if isinstance(spec, str) else None
    return m[1] if m else None


def deps(k, text):
    """The dependency names one file declares. Unparsable content raises Unreadable."""
    if text is None:
        return set()
    if k == "pyproject":
        try:
            doc = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise Unreadable(f"pyproject.toml does not parse: {e}")
        doc = doc if isinstance(doc, dict) else {}
        project = doc.get("project") if isinstance(doc.get("project"), dict) else {}
        build_sys = doc.get("build-system") if isinstance(doc.get("build-system"), dict) else {}
        tool = doc.get("tool") if isinstance(doc.get("tool"), dict) else {}
        uv = tool.get("uv") if isinstance(tool.get("uv"), dict) else {}
        groups = [project.get("dependencies") or [], build_sys.get("requires") or [],
                  uv.get("dev-dependencies") or []]
        opt = project.get("optional-dependencies") if isinstance(project.get("optional-dependencies"), dict) else {}
        groups += list(opt.values())
        dep_groups = doc.get("dependency-groups") if isinstance(doc.get("dependency-groups"), dict) else {}
        groups += list(dep_groups.values())  # {include-group = ...} entries are skipped
        return {n for g in groups if isinstance(g, list) for n in map(_pep508, g) if n}
    if k == "package":
        try:
            doc = json.loads(text)
        except ValueError as e:
            raise Unreadable(f"package.json does not parse: {e}")
        doc = doc if isinstance(doc, dict) else {}
        return {n for f in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
                for n in (doc.get(f) or {}) if isinstance(doc.get(f), dict)}
    if k == "docker":
        stages, images = set(), set()
        for line in text.splitlines():
            m = re.match(r"(?i)\s*FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", line)
            if not m:
                continue
            image = m[1]
            if image.lower() not in stages and image != "scratch" and "$" not in image:
                images.add(image.split("@")[0].rsplit("/", 1)[-1].split(":")[0])  # ghcr.io/astral-sh/uv:0.5 -> uv
            if m[2]:
                stages.add(m[2].lower())
        return images
    return set()


def decided(table):
    """Normalised text of every Decided row in a markdown stack table."""
    rows = []
    for line in (table or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if any(c.strip("*_ ").lower() == "decided" for c in cells):
            rows.append(norm(" ".join(cells)))
    return rows


def declared(name, rows):
    n = norm(name)
    return any(f"-{n}-" in f"-{row}-" for row in rows)


def stack_path(spec):
    """The stack table's repo path: the PRD's constraints.stack, else docs/stack.md."""
    stack = ((spec or {}).get("constraints") or {}).get("stack") if isinstance(spec, dict) else None
    return posixpath.normpath(stack.strip()) if isinstance(stack, str) and stack.strip() else DEFAULT_STACK


def undeclared(pr, base, fetch, stack):
    """[(name, path)] the PR adds that no Decided row covers, sorted; [] when the repo has no stack table or the
    PR touches no dependency file. Raises Unreadable when a file it needs cannot be read."""
    files = sorted({f.get("path") or "" for f in pr.get("files") or []} - {""})
    touched = [(p, kind(p)) for p in files if kind(p)]
    if not touched:
        return []
    table = fetch(stack, base)
    if table is None:
        return []
    rows, head, found = decided(table), pr.get("headRefOid"), []
    for path, k in touched:
        base_norm = {norm(b) for b in deps(k, fetch(path, base))}
        for name in sorted(deps(k, fetch(path, head))):
            if norm(name) not in base_norm and not declared(name, rows):
                found.append((name, path))
    return sorted(found)


def message(found, stack):
    names = ", ".join(f"`{n}` ({p})" for n, p in found)
    return (f"Held: this PR adds {names}, not on a Decided row of `{stack}`. Add a row naming "
            f"{'it' if len(found) == 1 else 'each'} (Layer | Choice | Decided | why) to `{stack}` in an earlier PR, "
            "and the reviewer approves it with the rest; nothing is reviewed or merged until then.")


def gh_fetch(run, repo):
    """fetch(path, ref) over the GitHub contents API, through run(argv) -> CompletedProcess."""
    def fetch(path, ref):
        r = run(["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={ref}"])
        if not r.returncode:
            return r.stdout
        if re.search(r"Not Found|HTTP 404", (r.stderr or "") + (r.stdout or "")):
            return None
        raise Unreadable(f"{path}@{ref}: {(r.stderr or '').strip()[:200]}")
    return fetch
