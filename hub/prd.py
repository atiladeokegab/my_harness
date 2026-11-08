"""hub prd: the PRD file.

projects/<project>/spec/prd.json is one machine file in five parts: header (the lead's one screen), constraints,
requirements (rows with ranked, tested acceptance lines), references (owned files by path + sha256) and a status
layer. A project with only today's requirements.json loads through the same shape with every new field empty, so
validate reports the gaps instead of crashing. The page is rendered from the file, never edited. Standard
library only. Example: templates/prd/example.prd.json.

    hub prd show <project>                Markdown to stdout
    hub prd render <project> [--out F]    the self-contained HTML page
    hub prd check <project> [--repo DIR]  errors (exit 1) and warnings
"""

import difflib
import html
import json
import os
import re
import string
import sys

import board as hb
import spec

TEMPLATE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates", "prd", "page.html")
STATES = ("proposed", "approved", "built")
HEADER_LINES, REQ_LINES = 60, 10  # the size budget: warnings, not errors
KINDS = {str: "a string", list: "a list", dict: "an object", bool: "true or false"}
HEADER = {"problem": str, "users": list, "goals": list, "principles": list, "non_goals": list, "owner": str,
          "glossary": dict}
CONSTRAINTS = {"stack": str, "limits": list, "invariants": list, "offline_tests": bool, "tags": list}
EMPTY = "_(empty)_"
# Closed key sets, so a misspelt key is an error instead of silently dropped data. glossary and status.state are
# the author's own maps and stay open.
TOP = ("version", "header", "constraints", "requirements", "references", "status")
ROW = ("id", "title", "why", "rank", "needs", "touches", "acceptance")
LINE = ("id", "v", "text", "test", "fixtures")
GOAL = ("purpose", "advantage", "measure")
ITEM = ("text", "why", "check")  # a limit or invariant written as an object
REFS, REF = ("spine", "design"), ("path", "sha256")
STATUS = ("state", "open_questions", "waiting_room")


def die(msg):
    sys.exit(f"hub prd: {msg}")


def prd_path(project):
    return os.path.join(spec.spec_dir(project), "prd.json")


def empty():
    return {"version": 1,
            "header": {"problem": "", "users": [], "goals": [], "principles": [], "non_goals": [], "owner": "",
                       "glossary": {}},
            "constraints": {"stack": "", "limits": None, "invariants": [], "offline_tests": None, "tags": []},
            "requirements": [], "references": {},
            "status": {"state": {}, "open_questions": [], "waiting_room": []}}


def from_legacy(old):
    """requirements.json in the prd.json shape: its version, requirements and any part an approved change set
    (header, constraints, references, status) kept; every field it lacks comes from empty()."""
    if not isinstance(old, dict):
        return old
    doc = empty()
    doc["version"] = old.get("version", 1)
    for part in ("header", "constraints", "references", "status"):
        if part in old:
            doc[part] = {**doc[part], **old[part]} if isinstance(old[part], dict) else old[part]
    reqs = old.get("requirements", [])
    doc["requirements"] = [{"why": "", "rank": None, "touches": [], **r} if isinstance(r, dict) else r
                           for r in reqs] if isinstance(reqs, list) else reqs
    return doc


def load(project):
    """spec/prd.json, else the legacy spec/requirements.json mapped into the same shape."""
    for path, legacy in ((prd_path(project), False), (os.path.join(spec.spec_dir(project), "requirements.json"), True)):
        if os.path.exists(path):
            try:
                with open(path) as f:
                    doc = json.load(f)
            except (OSError, ValueError) as e:
                die(f"cannot read {path}: {e}")
            return from_legacy(doc) if legacy else doc
    die(f"no PRD for {project}: no {prd_path(project)} and no requirements.json beside it")


# ---------------------------------------------------------------- validate

def obj(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


def item_text(v):
    """A limit or invariant: a plain string, or {text, why, check}."""
    return v if isinstance(v, str) else str(obj(v).get("text", ""))


def req_gaps(r):
    """What a requirement row is missing, in the words the page and the warnings use."""
    return [g for g, missing in (("why is empty", not str(r.get("why") or "").strip()),
                                 ("touches is empty", not lst(r.get("touches"))),
                                 ("unranked", r.get("rank") is None)) if missing]


def resolve(path, bases):
    p = os.path.expanduser(path)
    for c in [p] if os.path.isabs(p) else [os.path.join(b, p) for b in bases]:
        if os.path.isfile(c):
            return c
    return None


def unknown_key(where, key, allowed):
    """The one wording for a key outside its closed set, shared with prd_grill.set_field."""
    near = difflib.get_close_matches(key, list(allowed), 1)
    return f"unknown key {where}{key}" + (f" (did you mean {near[0]}?)" if near else "")


def _closed(errs, where, d, allowed):
    errs += [unknown_key(where, k, allowed) for k in obj(d) if k not in allowed]


def _shape(errs, where, sec, shape):
    for k, t in shape.items():
        v = sec.get(k)
        if v is not None and not isinstance(v, t):
            errs.append(f"{where}.{k} must be {KINDS[t]}")


def validate(doc, bases=None):
    """(errors, warnings). bases: the directories reference paths resolve against; None skips the file checks."""
    if not isinstance(doc, dict):
        return ["the PRD must be a JSON object"], []
    errs, warns = [], []
    _closed(errs, "", doc, TOP)
    for part, shape in (("header", HEADER), ("constraints", CONSTRAINTS)):
        if not isinstance(doc.get(part, {}), dict):
            errs.append(f"{part} must be an object")
        else:
            _shape(errs, part, doc.get(part, {}), shape)
            _closed(errs, f"{part}.", doc.get(part), shape)
    head, cons = obj(doc.get("header")), obj(doc.get("constraints"))
    for where, items in (("header.users", head.get("users")), ("header.principles", head.get("principles")),
                         ("header.non_goals", head.get("non_goals")), ("constraints.tags", cons.get("tags"))):
        errs += [f"{where}[{i}] must be a string" for i, v in enumerate(lst(items)) if not isinstance(v, str)]
    for i, g in enumerate(lst(head.get("goals"))):
        _closed(errs, f"header.goals[{i}].", g, GOAL)
        errs += [f"header.goals[{i}]: {k} must be a string" for k in ("purpose", "advantage", "measure")
                 if not isinstance(obj(g).get(k), str)]
    errs += [f"header.glossary.{k} must be a string" for k, v in obj(head.get("glossary")).items()
             if not isinstance(v, str)]
    for where in ("limits", "invariants"):
        for i, v in enumerate(lst(cons.get(where))):
            _closed(errs, f"constraints.{where}[{i}].", v, ITEM)
        errs += [f"constraints.{where}[{i}] must be a string or {{text, why, check}}"
                 for i, v in enumerate(lst(cons.get(where)))
                 if not (isinstance(v, str) or isinstance(obj(v).get("text"), str))]
    if not lst(head.get("non_goals")):
        warns.append("header: non_goals is empty")

    reqs = doc.get("requirements", [])
    if not isinstance(reqs, list):
        return errs + ["requirements must be a list"], warns
    rows = []  # the well-formed rows, handed to spec.schema_errors (ids, needs, acceptance ids, v, duplicates)
    for i, r in enumerate(reqs):
        if not isinstance(r, dict):
            errs.append(f"requirements[{i}] must be an object")
            continue
        rid = r.get("id") if isinstance(r.get("id"), str) else repr(r.get("id"))
        _closed(errs, f"{rid}.", r, ROW)
        for k in ("needs", "touches"):
            if not isinstance(r.get(k, []), list) or not all(isinstance(x, str) for x in r.get(k, [])):
                errs.append(f"{rid}: {k} must be a list of strings")
        acc = r.get("acceptance", [])
        if not isinstance(acc, list):
            errs.append(f"{rid}: acceptance must be a list")
            acc = []
        if not acc:
            errs.append(f"{rid}: no acceptance lines")
        lines = []
        for j, a in enumerate(acc):
            if not isinstance(a, dict):
                errs.append(f"{rid}: acceptance[{j}] must be an object")
                continue
            aid = a.get("id") if isinstance(a.get("id"), str) else repr(a.get("id"))
            _closed(errs, f"{aid}.", a, LINE)
            lines.append({**a, "id": aid})
            if isinstance(a.get("test"), str) and not a["test"].strip():
                errs.append(f"{aid}: no test path")
            if "fixtures" in a:
                if not isinstance(a["fixtures"], list):
                    errs.append(f"{aid}: fixtures must be a list")
                else:
                    errs += [f"{aid}: fixtures[{k}] needs input and output" for k, fx in enumerate(a["fixtures"])
                             if not ("input" in obj(fx) and "output" in obj(fx))]
        rows.append({**r, "id": rid, "acceptance": lines,
                     "needs": [n for n in lst(r.get("needs")) if isinstance(n, str)]})
    errs += spec.schema_errors({"version": doc.get("version"), "requirements": rows})

    ranks = {}
    for r in rows:
        rank = r.get("rank")
        if rank is None:
            continue
        if isinstance(rank, bool) or not isinstance(rank, int):
            errs.append(f"{r['id']}: rank must be a whole number")
        elif not 1 <= rank <= len(rows):
            errs.append(f"{r['id']}: rank {rank} is outside 1..{len(rows)}")
        else:
            ranks.setdefault(rank, []).append(r["id"])
    errs += [f"rank {k} is used by {' and '.join(v)}" for k, v in sorted(ranks.items()) if len(v) > 1]

    refs = doc.get("references", {})
    if not isinstance(refs, dict):
        errs.append("references must be an object")
        refs = {}
    _closed(errs, "references.", refs, REFS)
    for name, ref in refs.items():
        _closed(errs, f"references.{name}.", ref, REF)
        path, sha = obj(ref).get("path"), obj(ref).get("sha256")
        if not (isinstance(path, str) and path and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
            errs.append(f"references.{name} must be {{path, sha256}} with a 64-hex sha256")
            continue
        if bases is None:
            continue
        found = resolve(path, bases)
        if not found:
            errs.append(f"references.{name}: {path} not found")
        elif spec.file_sha(found) != sha:
            errs.append(f"references.{name}: sha256 does not match {path} (the file is {spec.file_sha(found)[:12]})")

    status = doc.get("status", {})
    if not isinstance(status, dict):
        errs.append("status must be an object")
        status = {}
    _closed(errs, "status.", status, STATUS)
    ids = {r["id"] for r in rows}
    for rid, st in obj(status.get("state")).items():
        if rid not in ids:
            errs.append(f"status.state names unknown {rid}")
        elif st not in STATES:
            errs.append(f"status.state {rid}: {st!r} is not {', '.join(STATES[:-1])} or {STATES[-1]}")
    for k in ("open_questions", "waiting_room"):
        if not isinstance(status.get(k, []), list):
            errs.append(f"status.{k} must be a list")

    for r in rows:
        warns += [f"{r['id']}: {g}" for g in req_gaps(r)]
    if not errs:  # the budget is measured on the rendered Markdown, so only on a well-formed file
        n = len([x for x in md_header(doc) if x.strip()])
        if n > HEADER_LINES:
            warns.append(f"header: {n} lines, over the ~{HEADER_LINES}-line budget")
        for r in rows:
            n = len([x for x in md_req(r, obj(status.get("state"))) if x.strip()])
            if n > REQ_LINES:
                warns.append(f"{r['id']}: {n} lines, over the ~{REQ_LINES}-line budget")
    return errs, warns


# ---------------------------------------------------------------- Markdown

def _bullets(items, fmt=str):
    return [f"- {fmt(x)}" for x in lst(items)] or [EMPTY]


def _limit(v):
    o = obj(v)
    extra = "".join(f" ({k}: {o[k]})" for k in ("why", "check") if o.get(k))
    return item_text(v) + extra


def md_header(doc):
    h = obj(doc.get("header"))
    return ["## Problem", str(h.get("problem") or EMPTY), "",
            "## Users", *_bullets(h.get("users")), "",
            "## Goals", *_bullets(h.get("goals"), lambda g: "**{}**: {}. Measure: {}".format(
                *(obj(g).get(k, "") for k in ("purpose", "advantage", "measure")))), "",
            "## Principles", *_bullets(h.get("principles")), "",
            "## Non-goals", *_bullets(h.get("non_goals")), "",
            "## Owner", str(h.get("owner") or EMPTY), "",
            "## Glossary", *([f"- **{k}**: {v}" for k, v in obj(h.get("glossary")).items()] or [EMPTY]), ""]


def _meta(r, state):
    rank = r.get("rank")
    return " · ".join(["unranked" if rank is None else f"rank {rank}",
                       f"state {state.get(r.get('id'), 'proposed')}",
                       "needs " + (", ".join(lst(r.get("needs"))) or "nothing"),
                       "touches " + (", ".join(f"`{t}`" for t in lst(r.get("touches"))) or "_(empty)_")])


def md_req(r, state):
    out = [f"### {r.get('id')} {r.get('title', '')}", _meta(r, state),
           f"Why: {r.get('why') or '_(why is empty)_'}"]
    for a in lst(r.get("acceptance")):
        a = obj(a)
        out.append(f"- {a.get('id')}@{a.get('v')} {a.get('text', '')} (`{a.get('test') or 'no test path'}`)")
        out += [f"  - fixture: `{json.dumps(obj(fx).get('input'))}` → `{json.dumps(obj(fx).get('output'))}`"
                for fx in lst(a.get("fixtures"))]
    return out + [""]


def render_md(doc, project=""):
    c, status = obj(doc.get("constraints")), obj(doc.get("status"))
    off = c.get("offline_tests")
    out = [f"# {project or 'PRD'}: PRD v{doc.get('version')}", "", *md_header(doc),
           "## Constraints", f"- Stack: {('`' + c['stack'] + '`') if c.get('stack') else EMPTY}",
           f"- Tests run offline: {EMPTY if off is None else ('yes' if off else 'no')}",
           *[f"- Limit: {_limit(v)}" for v in lst(c.get("limits"))],
           *[f"- Invariant: {_limit(v)}" for v in lst(c.get("invariants"))],
           *[f"- Tag: {t}" for t in lst(c.get("tags"))], "", "## Requirements"]
    reqs = [r for r in lst(doc.get("requirements")) if isinstance(r, dict)]
    for r in sorted(reqs, key=lambda r: (not isinstance(r.get("rank"), int), r.get("rank") or 0)):
        out += md_req(r, obj(status.get("state")))
    out += ["## References", *([f"- {k}: `{obj(v).get('path')}` sha256 {str(obj(v).get('sha256'))[:12]}"
                                for k, v in obj(doc.get("references")).items()] or ["_(none)_"]), "",
            "## Open questions", *_bullets(status.get("open_questions")), "",
            "## Waiting room", *_bullets(status.get("waiting_room")), ""]
    return "\n".join(out)


# ---------------------------------------------------------------- HTML

def _e(v):
    return html.escape(str(v))


GAP = '<span class="gap">{}</span>'


def _text(v):
    return _e(v) if str(v or "").strip() else GAP.format("empty")


def _ul(items, fmt=_e):
    items = lst(items)
    return "<ul>" + "".join(f"<li>{fmt(x)}</li>" for x in items) + "</ul>" if items else GAP.format("empty")


def _sec(title, body):
    return f"<h2>{_e(title)}</h2><section>{body}</section>"


def render(doc, project="", bases=None):
    """The self-contained page: no external assets, light and dark, every empty or weak field marked."""
    errs, warns = validate(doc, bases)
    if not isinstance(doc, dict):
        doc = {}
    h, c, status = obj(doc.get("header")), obj(doc.get("constraints")), obj(doc.get("status"))
    state = obj(status.get("state"))
    reqs = [r for r in lst(doc.get("requirements")) if isinstance(r, dict)]
    n_lines = sum(len(lst(r.get("acceptance"))) for r in reqs)
    b = [f"<h1>{_e(project or 'PRD')}</h1>",
         f'<p class="sub">PRD v{_e(doc.get("version"))} · {len(reqs)} requirements · {n_lines} acceptance lines</p>']
    if errs:
        b.append('<section class="errs"><strong>' + f"{len(errs)} error(s)</strong>" + _ul(errs) + "</section>")
    else:
        b.append('<section><span class="ok">No errors.</span></section>')
    if warns:
        b.append("<section><strong>Still weak</strong><ul>" + "".join(
            f"<li>{GAP.format(_e(w))}</li>" for w in warns) + "</ul></section>")

    goals = lst(h.get("goals"))
    goal_html = ("<table><tr><th>Purpose</th><th>Advantage</th><th>Measure</th></tr>" + "".join(
        "<tr>" + "".join(f"<td>{_text(obj(g).get(k))}</td>" for k in ("purpose", "advantage", "measure")) + "</tr>"
        for g in goals) + "</table>") if goals else GAP.format("empty")
    gloss = obj(h.get("glossary"))
    b += [_sec("Problem", _text(h.get("problem"))), _sec("Users", _ul(h.get("users"))), _sec("Goals", goal_html),
          _sec("Principles", _ul(h.get("principles"))), _sec("Non-goals", _ul(h.get("non_goals"))),
          _sec("Owner", _text(h.get("owner"))),
          _sec("Glossary", "<ul>" + "".join(f"<li><strong>{_e(k)}</strong>: {_e(v)}</li>" for k, v in gloss.items())
               + "</ul>" if gloss else GAP.format("empty"))]

    off = c.get("offline_tests")
    cons = [f'<div class="line"><span class="k">Stack</span>'
            f'{("<code>" + _e(c["stack"]) + "</code>") if c.get("stack") else GAP.format("empty")}</div>',
            f'<div class="line"><span class="k">Tests run offline</span>'
            f'{GAP.format("empty") if off is None else ("yes" if off else "no")}</div>',
            '<div class="line"><span class="k">Limits</span></div>' + _ul(c.get("limits"), lambda v: _e(_limit(v))),
            '<div class="line"><span class="k">Invariants</span></div>' + _ul(c.get("invariants"),
                                                                               lambda v: _e(_limit(v)))]
    if lst(c.get("tags")):
        cons.append('<div class="line"><span class="k">Tags</span></div>' + _ul(c.get("tags")))
    b.append(_sec("Constraints", "".join(cons)))

    b.append("<h2>Requirements</h2>" + ("" if reqs else f"<section>{GAP.format('empty')}</section>"))
    for r in sorted(reqs, key=lambda r: (not isinstance(r.get("rank"), int), r.get("rank") or 0)):
        rank = r.get("rank")
        gaps = "".join(" " + GAP.format(_e(g)) for g in req_gaps(r))
        acc = "".join(
            f'<div class="line"><code>{_e(obj(a).get("id"))}@{_e(obj(a).get("v"))}</code> {_e(obj(a).get("text", ""))} '
            + (f'<code>{_e(obj(a)["test"])}</code>' if str(obj(a).get("test") or "").strip()
               else GAP.format("no test path"))
            + "".join(f'<div class="meta">fixture <code>{_e(json.dumps(obj(fx).get("input")))}</code> → '
                      f'<code>{_e(json.dumps(obj(fx).get("output")))}</code></div>'
                      for fx in lst(obj(a).get("fixtures")))
            + "</div>" for a in lst(r.get("acceptance"))) or GAP.format("no acceptance lines")
        b.append(f'<div class="req"><h3><span class="rank">{"" if rank is None else "#" + _e(rank)}</span>'
                 f'{_e(r.get("id"))} {_e(r.get("title", ""))}{gaps}</h3>'
                 f'<div class="meta">{_e(state.get(r.get("id"), "proposed"))} · needs '
                 f'{_e(", ".join(lst(r.get("needs"))) or "nothing")} · touches '
                 f'{_e(", ".join(lst(r.get("touches"))) or "-")}</div>'
                 f'<div class="line"><span class="k">Why</span>{_text(r.get("why"))}</div>{acc}</div>')

    refs = obj(doc.get("references"))
    b.append(_sec("References", "<ul>" + "".join(
        f"<li>{_e(k)}: <code>{_e(obj(v).get('path'))}</code> sha256 {_e(str(obj(v).get('sha256'))[:12])}</li>"
        for k, v in refs.items()) + "</ul>" if refs else "none"))
    b.append(_sec("Open questions", _ul(status.get("open_questions")) if lst(status.get("open_questions")) else "none"))
    b.append(_sec("Waiting room", _ul(status.get("waiting_room")) if lst(status.get("waiting_room")) else "none"))
    with open(TEMPLATE) as f:
        return string.Template(f.read()).substitute(title=_e(f"{project or 'PRD'} PRD"), body="\n".join(b))


# ---------------------------------------------------------------- CLI

def bases(project, repo=None):
    """Where reference paths resolve: the product repo first, then the project's hub directory."""
    return [os.path.abspath(os.path.expanduser(repo or f"~/code/{project}")),
            os.path.join(hb.HUB_DIR, "projects", project)]


def cmd_show(a):
    p = hb.valid_project(a.project_name)
    print(render_md(load(p), p))


def cmd_render(a):
    p = hb.valid_project(a.project_name)
    page = render(load(p), p, bases(p, a.repo))
    if a.out:
        tmp = a.out + ".tmp"
        with open(tmp, "w") as f:
            f.write(page)
        os.replace(tmp, a.out)
        print(f"wrote {a.out}")
    else:
        sys.stdout.write(page)


def cmd_check(a):
    p = hb.valid_project(a.project_name)
    doc = load(p)
    errs, warns = validate(doc, bases(p, a.repo))
    for e in errs:
        print(f"  error: {e}")
    for w in warns:
        print(f"  warning: {w}")
    src = "prd.json" if os.path.exists(prd_path(p)) else "requirements.json (legacy)"
    if errs:
        die(f"check failed for {p}: {len(errs)} error(s), {len(warns)} warning(s)")
    print(f"prd ok: {p} v{doc.get('version')} from {src}, {len(doc['requirements'])} requirements, "
          f"{len(warns)} warning(s)")


def register(sub):
    p = sub.add_parser("prd", help="the PRD file: show, render, check")
    s = p.add_subparsers(dest="prd_cmd", required=True)
    for name, fn, hlp in (("show", cmd_show, "the PRD as Markdown"),
                          ("render", cmd_render, "the self-contained HTML page"),
                          ("check", cmd_check, "errors (exit 1) and warnings")):
        c = s.add_parser(name, help=hlp)
        c.add_argument("project_name", metavar="project")
        if name != "show":
            c.add_argument("--repo", help="where reference paths resolve first (default ~/code/<project>)")
        if name == "render":
            c.add_argument("--out", help="write the page here (default: stdout)")
        c.set_defaults(fn=fn)
    import prd_grill
    prd_grill.register(s)
