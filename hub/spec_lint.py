"""Deterministic overlap checks for proposed spec changes."""

import difflib
import re

ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/\S*)", re.IGNORECASE)
SHAPE = re.compile(r"\breturns\s*\{([^}]*)\}", re.IGNORECASE)
FILE = re.compile(r"\b[\w./-]+\.\w{1,4}\b")


def normalized(text):
    return " ".join(re.sub(r"[^\w\s/{}<>]", " ", text.lower()).split())


def endpoint(text):
    match = ENDPOINT.search(text)
    if not match:
        return None
    path = match.group(2).split("?", 1)[0].rstrip("/,.;:") or "/"
    path = re.sub(r"<[^>]+>|\{[^}]+\}", "{}", path)
    return match.group(1).upper(), path.lower()


def shape(text):
    endpoint_match = ENDPOINT.search(text)
    match = SHAPE.search(text, endpoint_match.end()) if endpoint_match else None
    if not match:
        return None
    return frozenset(part.split(":", 1)[0].strip().lower()
                     for part in match.group(1).split(",") if part.strip())


def touched(change, before):
    """Acceptance ids and endpoints touched by a change, including removed lines."""
    old = {a["id"]: a for r in before["requirements"] for a in r.get("acceptance", [])}
    ids, endpoints = set(), set()
    for item in change.get("added", []):
        lines = item.get("acceptance", []) if item["id"].startswith("R-") else [item]
        for line in lines:
            ids.add(line["id"])
            if key := endpoint(line.get("text", "")):
                endpoints.add(key)
    for item in change.get("modified", []):
        if item["id"].startswith("A-"):
            ids.add(item["id"])
            if key := endpoint(item.get("text") or old.get(item["id"], {}).get("text", "")):
                endpoints.add(key)
    for item in change.get("removed", []):
        removed = [item] if item.startswith("A-") else [a["id"] for r in before["requirements"]
                                                      if r["id"] == item for a in r.get("acceptance", [])]
        for aid in removed:
            ids.add(aid)
            if key := endpoint(old.get(aid, {}).get("text", "")):
                endpoints.add(key)
    return ids, endpoints


def content_lines(value):
    if isinstance(value, dict):
        return sum(content_lines(item) for item in value.values())
    if isinstance(value, list):
        return sum(content_lines(item) for item in value)
    return max(1, len(str(value).splitlines()))


def requirement_lines(req):
    return (sum(content_lines(req[key]) for key in ("title", "why") if req.get(key))
            + sum(content_lines(line["text"]) for line in req.get("acceptance", []))
            + len(req.get("needs", [])) + len(req.get("touches", [])))


def lint(spec_before, change, pending=(), heldout=None):
    """Return (level, rule, message) findings for an unapplied change."""
    from spec import apply_change, lines_of, set_errors, touches_overlap

    invalid_set = set_errors(change)
    if invalid_set:
        return [("error", "L17", message) for message in invalid_set]

    spec_after = apply_change(spec_before, change)
    lines = lines_of(spec_after)
    old = lines_of(spec_before)
    touched_ids, changed_endpoints = touched(change, spec_before)
    changed = touched_ids & set(lines)
    changed.update(aid for aid in lines if aid in old and lines[aid][1]["v"] != old[aid][1]["v"])
    allowed = {(item["rule"], frozenset(item["lines"])): item.get("why", "")
               for item in change.get("lint_ok", [])}
    findings = []

    def add(level, rule, message, pair=()):
        why = allowed.get((rule, frozenset(pair))) if pair else None
        findings.append(("allowed" if why is not None else level, rule,
                         message + (f" (approved: {why})" if why is not None else "")))

    for aid in sorted(changed):
        rid, line = lines[aid]
        text, key, fields = normalized(line["text"]), endpoint(line["text"]), shape(line["text"])
        for other in sorted(lines):
            if other == aid or (other in changed and other < aid):
                continue
            other_rid, other_line = lines[other]
            other_text = normalized(other_line["text"])
            pair = (aid, other)
            if text == other_text:
                add("error", "L1", f"{aid} and {other} have the same text", pair)
            if key and key == endpoint(other_line["text"]):
                if rid != other_rid:
                    add("error", "L2", f"{aid} vs {other}: {key[0]} {key[1]}", pair)
                other_fields = shape(other_line["text"])
                if fields is not None and other_fields is not None and fields != other_fields:
                    add("error", "L4", f"{aid} vs {other}: {key[0]} {key[1]} returns "
                        f"{sorted(fields)} vs {sorted(other_fields)}", pair)
            if line["test"] and line["test"] == other_line["test"]:
                add("error", "L3", f"{aid} and {other} name test {line['test']}", pair)
            if text != other_text and difflib.SequenceMatcher(None, text, other_text).ratio() >= 0.85:
                add("warn", "L5", f"{aid} and {other} have near text", pair)
            files = sorted(set(FILE.findall(line["text"])) & set(FILE.findall(other_line["text"])))
            if files:
                add("warn", "L7", f"{aid} and {other} both name {', '.join(files)}", pair)

    changed_reqs = {item["id"] for item in change.get("added", []) + change.get("modified", [])
                    if item["id"].startswith("R-")}
    reqs = {r["id"]: r for r in spec_after["requirements"]}
    for rid in sorted(changed_reqs & set(reqs)):
        title = normalized(reqs[rid]["title"].split(":", 1)[0])
        for other in sorted(reqs):
            if other != rid and (other not in changed_reqs or other > rid) \
                    and title == normalized(reqs[other]["title"].split(":", 1)[0]):
                add("error", "L6", f"{rid} and {other} share title head {title!r}", (rid, other))

    visited, active = set(), []

    def visit(rid):
        if rid in active:
            return active[active.index(rid):] + [rid]
        if rid in visited:
            return None
        active.append(rid)
        for need in reqs[rid].get("needs", []):
            if need in reqs and (cycle := visit(need)):
                return cycle
        active.pop()
        visited.add(rid)
        return None

    for rid in sorted(reqs):
        if cycle := visit(rid):
            add("error", "L12", "needs cycle: " + " -> ".join(cycle))
            break

    for rid in sorted(changed_reqs & set(reqs)):
        for other in sorted(reqs):
            if other == rid or (other in changed_reqs and other < rid):
                continue
            overlap = sorted({a for a in reqs[rid].get("touches", [])
                              for b in reqs[other].get("touches", [])
                              if touches_overlap(a, b)})
            if overlap:
                add("warn", "L13", f"{rid} and {other} touches overlap on {', '.join(overlap)}; "
                    "auto-sequence their tasks", (rid, other))

    if content_lines(spec_after.get("header", {})) > 60:
        add("warn", "L14", "header exceeds 60 content lines")
    for rid in sorted(changed_reqs & set(reqs)):
        if requirement_lines(reqs[rid]) > 10:
            add("warn", "L14", f"{rid} exceeds 10 content lines")

    ranks = [r.get("rank") for r in reqs.values()]
    if any(rank is not None for rank in ranks) \
            and (any(type(rank) is not int for rank in ranks) or sorted(ranks) != list(range(1, len(ranks) + 1))):
        add("error", "L15", "rank must be unique and contiguous from 1 to the number of requirements")
    elif "header" in spec_after and ranks and all(rank is None for rank in ranks):
        add("warn", "L15", "requirements are unranked")

    for aid in sorted(changed):
        if not lines[aid][1].get("test"):
            add("error", "L16", f"{aid} has no test path")
    if "header" in spec_after:
        for item in change.get("added", []):
            proposed = item.get("acceptance", []) if item["id"].startswith("R-") else [item]
            for line in proposed:
                if not line.get("test"):
                    add("error", "L16", f"{line['id']} has no explicit test path")

    if heldout is not None:  # {"A-8.1": {"v": 1, ...}}, gh_sync.heldout_index
        for aid in sorted(changed):
            if (heldout.get(aid) or {}).get("v") != lines[aid][1]["v"]:
                add("warn", "L9", f"{aid}@{lines[aid][1]['v']} has no held-out check")

    for item in sorted(pending, key=lambda c: c["id"]):
        if item["id"] == change["id"] or item.get("base_version") != change.get("base_version"):
            continue
        ids, endpoints = touched(item, spec_before)
        overlap = sorted(touched_ids & ids) + [f"{method} {path}" for method, path in
                                         sorted(changed_endpoints & endpoints)]
        if overlap:
            add("warn", "L8", f"{change['id']} overlaps pending {item['id']} on {', '.join(overlap)}")
    return findings
