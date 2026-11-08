"""hub prd grill: the grill fills the PRD.

One gap at a time in a fixed order: problem, users, goals, non-goals, constraints (stack, limits, offline tests),
requirements with their why, touches and acceptance lines, then rank. Each gap carries a plain question and a
recommended answer drawn from what is already filled (templates, no model). Each answer writes exactly one field,
is validated, saved atomically to spec/prd.json, and read back in plain words. The cold-read questions are the
gaps phrased as a cold agent would ask them, so any question it would ask is the next grill question; the PRD is
ready when there are none and validate has no errors. Non-interactive, so Zeus can run the conversation:

    hub prd grill <project> [--answer PATH=VALUE] [--json] [--repo DIR]

PATH is dotted with selectors: header.problem, header.goals[+], header.glossary.<term>, requirements[+],
requirements[R-1].why, requirements[R-1].acceptance[+], requirements[R-1].acceptance[A-1.1].test, references.spine.
A list field takes "a | b | c" (or a JSON array; "none" for empty); [+] appends one item.
"""

import copy
import json
import os
import re
import sys

import prd
import spec

LISTS = {"users", "principles", "non_goals", "limits", "invariants", "tags", "touches", "needs", "open_questions",
         "waiting_room"}
FREE = {"glossary", "state", "references"}  # dicts whose keys are the author's, not the schema's
NAMED = {"header": tuple(prd.HEADER), "constraints": tuple(prd.CONSTRAINTS), "references": prd.REFS,
         "status": prd.STATUS}  # the closed key set under each named object; glossary and state stay open
ITEMS = {"requirements": prd.ROW, "acceptance": prd.LINE, "goals": prd.GOAL, "limits": prd.ITEM,
         "invariants": prd.ITEM}  # ... and under each item of a list
VAGUE = re.compile(r"\b(fast|quick(ly)?|easy|easily|simple|nice|intuitive|user[- ]friendly|robust|scalable|seamless"
                   r"|properly|correctly|appropriate(ly)?|good|better|efficient(ly)?|etc)\b", re.I)
SUGGESTED = "suggested:"  # a made-up recommendation; set_field refuses it verbatim
TOKEN = re.compile(r"\.?([^.\[\]]+)|\[([^\]]+)\]")


def blank(v):
    return not str(v or "").strip()


def load(project):
    """The project's PRD for grilling: prd.json, else the legacy spec, else the empty template."""
    if not (os.path.exists(prd.prd_path(project))
            or os.path.exists(os.path.join(spec.spec_dir(project), "requirements.json"))):
        return prd.empty()
    doc = prd.load(project)
    if isinstance(doc, dict):  # a hand-written file may lack whole parts; the grill fills them in place
        for part, default in prd.empty().items():
            doc.setdefault(part, default)
            if isinstance(default, dict) and isinstance(doc[part], dict):
                for k, v in default.items():
                    doc[part].setdefault(k, v)
    return doc


# ---------------------------------------------------------------- gaps

def words(s):
    return set(re.findall(r"[a-z0-9]{3,}", str(s).lower()))


def checkable(text):
    """Deterministic: a line a test can check is specific (4+ words) and not vague unless it carries a number."""
    t = str(text or "")
    return len(t.split()) >= 4 and not (VAGUE.search(t) and not re.search(r"\d", t))


def gaps(doc, bases=None):
    """Every empty or weak field in the grill's fixed order: {path, question, recommended, cold}."""
    out = []

    def add(path, question, recommended, cold):
        out.append({"path": path, "question": question, "recommended": str(recommended), "cold": cold})

    h, c = prd.obj(doc.get("header")), prd.obj(doc.get("constraints"))
    reqs = [r for r in prd.lst(doc.get("requirements")) if isinstance(r, dict)]
    users, goals = prd.lst(h.get("users")), prd.lst(h.get("goals"))
    heads = [str(r.get("title", "")).split(":")[0] for r in reqs if not blank(r.get("title"))]

    if blank(h.get("problem")):
        add("header.problem", "What problem does this solve, in one sentence: who is hurting, and how?",
            "It has to do: " + "; ".join(heads[:4]) if heads else "<who> cannot <do what> today, which costs <what>",
            "What problem is this solving, and for whom?")
    if not users:
        add("header.users", "Who uses it, and what does each of them need from it? One row each, split by |.",
            "<role>: <what they need from it> | <role>: <what they need from it>",
            "Who uses it, and what do they need?")
    if not goals:
        need = str(users[0]).split(":", 1)[-1].strip() if users else "<what the first user needs>"
        add("header.goals[+]", "What is the first goal? Purpose | advantage over today | a measure a test can check.",
            f"{need} | <why that beats today> | <a number a test can check>",
            "What does success look like, and how is it measured?")
    for i, gl in enumerate(goals):
        for k in ("purpose", "advantage", "measure"):
            if blank(prd.obj(gl).get(k)):
                add(f"header.goals[{i}].{k}", f"Goal {i + 1} has no {k}. What is it?",
                    "<a number a test can check>" if k == "measure" else f"<the {k} of goal {i + 1}>",
                    f"What is goal {i + 1}'s {k}?")
    if not prd.lst(h.get("non_goals")):
        add("header.non_goals", "What is out of scope, so no agent builds it? Split by |.",
            "User accounts or login | An admin screen | Anything not in the goals above",
            "What is out of scope?")
    if blank(c.get("stack")):
        add("constraints.stack", "Where is the stack table (Decided / Proposed)? A path in the repo.",
            "docs/stack.md", "Which stack, and where is it decided?")
    if c.get("limits") is None:
        measures = [str(prd.obj(gl).get("measure")) for gl in goals if not blank(prd.obj(gl).get("measure"))]
        add("constraints.limits", "Any hard limits (speed, size, cost, data)? Split by |, or say none.",
            " | ".join(measures) or "none", "Are there limits I must stay within?")
    if c.get("offline_tests") is None:
        add("constraints.offline_tests", "Must the tests run with no network? yes or no.", "yes",
            "Can the tests use the network?")
    if not reqs:
        add("requirements[+]", "What is the first thing it must do? A short title: <name>: <what it does>.",
            str(prd.obj(goals[0]).get("purpose")) if goals else "<name>: <what it does>",
            "What must it do?")

    for r in reqs:
        rid, title = r.get("id"), r.get("title", "")
        if blank(r.get("why")):
            best = max(goals, key=lambda gl: len(words(title) & words(prd.obj(gl).get("purpose"))), default=None)
            add(f"requirements[{rid}].why", f"Why does {rid} '{title}' matter? One line.",
                prd.obj(best).get("purpose") or h.get("problem") or "<the goal it serves>",
                f"{rid}: why does this matter, and which goal does it serve?")
        if not prd.lst(r.get("touches")):
            slug = re.sub(r"[^a-z0-9]+", "_", str(title).split(":")[0].lower()).strip("_") or "feature"
            add(f"requirements[{rid}].touches", f"Which files or areas will {rid} change? Split by |.",
                f"{SUGGESTED} app/{slug}.py (a guess from the title: name the real files)",
                f"{rid}: which files will this change?")
        acc = prd.lst(r.get("acceptance"))
        if not acc:
            add(f"requirements[{rid}].acceptance[+]",
                f"How would a test know {rid} works? One line: <input or action> gives <exact result>.",
                f"<request or action> returns <exact result>, for {title}", f"{rid}: how do I know it is done?")
        for a in acc:
            a = prd.obj(a)
            aid, base = a.get("id"), f"requirements[{rid}].acceptance[{a.get('id')}]"
            if not checkable(a.get("text")):
                add(f"{base}.text", f"{aid} says '{a.get('text', '')}'. What exactly would a test observe?",
                    f"{a.get('text', '')}, measured as <number and unit>",
                    f"{aid}: '{a.get('text', '')}' is not checkable: what exactly passes?")
            if blank(a.get("test")):
                add(f"{base}.test", f"Which test file checks {aid}?", spec.default_test(str(aid)),
                    f"{aid}: which test checks this line?")

    used = {r.get("rank") for r in reqs if isinstance(r.get("rank"), int)}
    free = [n for n in range(1, len(reqs) + 1) if n not in used]
    for r in reqs:
        if r.get("rank") is None:
            add(f"requirements[{r.get('id')}].rank",
                f"Where does {r.get('id')} '{r.get('title', '')}' rank? 1 is built first; when time runs out, "
                "the highest numbers are dropped.", free.pop(0) if free else len(reqs),
                f"{r.get('id')}: is it built before or after the others?")

    for name, ref in prd.obj(doc.get("references")).items():
        path = prd.obj(ref).get("path")
        if bases is None or not isinstance(path, str):
            continue
        found = prd.resolve(path, bases)
        if not found or spec.file_sha(found) != prd.obj(ref).get("sha256"):
            add(f"references.{name}", f"The {name} reference {path} is {'missing' if not found else 'changed'}. "
                "What is its path? (It is pinned to the file's current hash.)", path if found else f"<path to {name}>",
                f"references.{name}: {path} does not resolve to the pinned file. Which is right?")
    return out


def next_gap(doc, bases=None):
    found = gaps(doc, bases)
    return found[0] if found else None


def cold_read_questions(doc, bases=None):
    return [x["cold"] for x in gaps(doc, bases)]


def ready(doc, bases=None):
    return not prd.validate(doc, bases)[0] and not gaps(doc, bases)


# ---------------------------------------------------------------- set_field

def parse(path):
    toks = [(m.group(1), m.group(2)) for m in TOKEN.finditer(path)]
    rebuilt = "".join(f".{n}" if n else f"[{s}]" for n, s in toks).lstrip(".")
    if not toks or rebuilt != path or toks[0][0] is None:
        raise ValueError(f"cannot read the path {path!r}: want e.g. header.problem or requirements[R-1].why")
    return toks


def coerce(key, value):
    if not isinstance(value, str):
        return value
    v = value.strip()
    if key in LISTS:
        if v.startswith("["):
            return json.loads(v)
        return [] if v.lower() in ("", "none", "nothing", "n/a") else [x.strip() for x in v.split("|") if x.strip()]
    if key in ("rank", "v"):
        try:
            return int(v)
        except ValueError:
            raise ValueError(f"{key} must be a whole number, not {v!r}") from None
    if key == "offline_tests":
        if v.lower() not in ("yes", "no", "true", "false", "y", "n"):
            raise ValueError(f"offline_tests takes yes or no, not {v!r}")
        return v.lower() in ("yes", "true", "y")
    if key == "fixtures" or v.startswith("{"):
        return json.loads(v)
    return v


def _new_id(items, prefix):
    nums = [int(m.group(1)) for x in items
            if (m := re.fullmatch(re.escape(prefix) + r"(\d+)", str(prd.obj(x).get("id"))))]
    return f"{prefix}{max(nums, default=0) + 1}"


def _append(container, parent_key, owner, value):
    """One new item for [+]: a requirement row, an acceptance line, a goal, or a list entry."""
    if parent_key == "requirements":
        row = value if isinstance(value, dict) else {"title": str(value).strip()}
        return {"id": _new_id(container, "R-"), "title": "", "why": "", "rank": None, "needs": [],
                "touches": [], "acceptance": [], **row}
    if parent_key == "acceptance":
        line = value if isinstance(value, dict) else {"text": str(value).strip()}
        aid = _new_id(container, f"A-{str(owner.get('id', 'R-0'))[2:]}.")
        return {"id": aid, "v": 1, "test": spec.default_test(aid), **line}
    if parent_key == "goals" and isinstance(value, str):
        parts = [x.strip() for x in value.split("|")] + ["", ""]
        return dict(zip(("purpose", "advantage", "measure"), parts[:3]))
    return value.strip() if isinstance(value, str) else value


def _show(v):
    if isinstance(v, list):
        return f"({len(v)}) " + "; ".join(_show(x) for x in v) if v else "(empty)"
    if isinstance(v, dict):
        return ", ".join(f"{k} {_show(x)}" for k, x in v.items()
                         if k not in ("needs", "acceptance") and x not in ("", [], None))
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v) if str(v).strip() else "(empty)"


def _label(toks):
    return " ".join(f"#{int(s) + 1}" if s and s.isdigit() else s if s and s != "+" else n.replace("_", " ")
                    for n, s in toks if n not in ("header", "constraints", "requirements", "acceptance")).strip()


def locked(project):
    """The refusal for a project whose spec.lock exists, else None."""
    lock = os.path.join(spec.spec_dir(project), "spec.lock")
    if not os.path.exists(lock):
        return None
    try:
        with open(lock) as f:
            version = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        version = "?"
    return f"approved spec (v{version}, locked): changes go through a change file; see hub spec --help"


def set_field(doc, path, value, project=None, bases=None):
    """Write exactly one field, validate, save spec/prd.json atomically when project is given, and return the
    read-back. Raises ValueError, leaving doc and the file untouched, on a bad path or value or on any new error."""
    if project and locked(project):  # the grill bootstraps; an approved spec changes only through C-NNN
        raise ValueError(locked(project))
    if isinstance(value, str) and value.strip().lower().startswith(SUGGESTED):
        raise ValueError(f"{path}: that is a guess from the grill, not an answer; give the real value")
    toks = parse(path)
    new = copy.deepcopy(doc)
    node, owner, parent_key, allowed = new, None, None, prd.TOP
    for i, (name, sel) in enumerate(toks):
        last = i == len(toks) - 1
        if name is not None:
            if not isinstance(node, dict):
                raise ValueError(f"{path}: {name} is not inside an object")
            if allowed is not None and name not in allowed:
                where = "".join(f".{n}" if n else f"[{s}]" for n, s in toks[:i]).lstrip(".")
                raise ValueError(f"{path}: " + prd.unknown_key(where + "." if where else "", name, allowed))
            allowed = prd.REF if parent_key == "references" else NAMED.get(name)
            if last:
                if parent_key == "references":
                    node[name] = _pin(value, bases)
                elif parent_key in FREE:
                    node[name] = value.strip() if isinstance(value, str) else value
                else:
                    node[name] = coerce(name, value)
                item = node[name]
                break
            if node.get(name) is None and name in ("references", "glossary"):
                node[name] = {}
            owner, node, parent_key = node, node.get(name), name
            continue
        if not isinstance(node, list):
            raise ValueError(f"{path}: [{sel}] needs a list")
        allowed = ITEMS.get(parent_key)
        if sel == "+":
            if not last:
                raise ValueError(f"{path}: [+] appends, so it must come last")
            item = _append(node, parent_key, owner, value)
            node.append(item)
            break
        if re.fullmatch(r"\d+", sel):
            idx = int(sel)
        else:
            idx = next((j for j, x in enumerate(node) if prd.obj(x).get("id") == sel), None)
        if idx is None or idx >= len(node):
            raise ValueError(f"{path}: no {sel} in {parent_key}")
        if last:
            node[idx] = value.strip() if isinstance(value, str) else value
            item = node[idx]
            break
        owner, node = node[idx], node[idx]
    before = set(prd.validate(doc, bases)[0])
    added = [e for e in prd.validate(new, bases)[0] if e not in before
             and not (path == "requirements[+]" and e.endswith(": no acceptance lines"))]  # asked for next
    if added:
        raise ValueError(f"{path}: not written, it would add: " + "; ".join(added))
    if project:
        dest = prd.prd_path(project)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        prd.hb._write_json_atomic(dest, new)
    doc.clear()
    doc.update(new)
    if toks[-1][1] == "+" and isinstance(item, dict) and item.get("id"):
        return f"Added {item['id']}: {item.get('title') or item.get('text')}"
    if toks[-1][1] == "+":
        return f"Added to {_label(toks[:-1]) or toks[-2][0]}: {_show(item)}"
    return f"Wrote {_label(toks)}: {_show(item)}"


def _pin(value, bases):
    """references.<name> takes a path (pinned to the file's hash now) or a {path, sha256} object."""
    if isinstance(value, str) and not value.strip().startswith("{"):
        found = prd.resolve(value.strip(), bases or [])
        if not found:
            raise ValueError(f"{value.strip()} not found under {', '.join(bases or []) or 'no base directory'}")
        return {"path": value.strip(), "sha256": spec.file_sha(found)}
    return value


# ---------------------------------------------------------------- CLI

def cmd_grill(a):
    p = prd.hb.valid_project(a.project_name)
    bases = prd.bases(p, a.repo)
    doc = load(p)
    said = None
    if a.answer:
        path, eq, value = a.answer.partition("=")
        if not eq:
            prd.die(f"--answer wants PATH=VALUE, got {a.answer!r}")
        try:
            said = set_field(doc, path.strip(), value, project=p, bases=bases)
        except ValueError as e:
            prd.die(str(e))
    errs = prd.validate(doc, bases)[0]
    found = gaps(doc, bases)
    if a.json:
        print(json.dumps({"readback": said, "locked": locked(p), "ready": not errs and not found,
                          "next": found[0] if found else None, "cold_read": [x["cold"] for x in found], "errors": errs}, indent=2))
        return
    if said:
        print(said)
    if locked(p):
        print(f"{locked(p)}: answers are refused; the gaps below are for a change file")
    if found:
        print(f"next ({len(found)} gap(s) left): {found[0]['path']}\n  {found[0]['question']}\n"
              f"  Recommended: {found[0]['recommended']}")
    for e in errs:
        print(f"  error: {e}")
    if not found and not errs:
        print(f"ready: {p} has no gaps a cold agent would ask about and no errors")
    elif not found:
        print(f"not ready: {len(errs)} error(s) to fix (hub prd check {p})")


def register(s):
    """Under `hub prd` (prd.register calls this), so board.py keeps its one prd line."""
    c = s.add_parser("grill", help="the next gap with a question and a recommended answer; --answer writes one field")
    c.add_argument("project_name", metavar="project")
    c.add_argument("--answer", metavar="PATH=VALUE", help="write exactly one field, e.g. header.problem=...")
    c.add_argument("--json", action="store_true", help="machine output: readback, ready, next, cold_read, errors")
    c.add_argument("--repo", help="where reference paths resolve first (default ~/code/<project>)")
    c.set_defaults(fn=cmd_grill)
