"""Read-only code call-graph lookup (`hub map`) backed by offline `graphify extract --code-only`."""

from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import board as hb

GRAPHIFY_ENV = {
    "GRAPHIFY_BACKEND": "none",
    "GRAPHIFY_NO_AUTO_REFRESH": "1",
    "GRAPHIFY_NO_CTA": "1",
    "GRAPHIFY_NO_TIPS": "1",
}
EXCLUDES = (
    "projects/",
    "artifacts/",
    "logs/",
    "backup/",
    "tests/fixtures/",
    "state/",
    "inbox/",
)
CALL_RELATIONS = {"calls", "indirect_call"}
STATIC_NOTE = (
    "note: static AST call graph only (subprocess, file, inbox, and systemd hops are not shown; verify with grep)."
)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def _clean_git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}


def _repo_for(project: str) -> Path:
    if not isinstance(project, str) or not hb.PROJECT_RE.fullmatch(project):
        die(f"invalid project name {project!r}")
    repo = Path(hb.HUB_DIR) if project == "hub" else Path.home() / "code" / project
    if not (repo / ".git").exists():
        die(f"no git repository for project {project!r} at {repo}")
    return repo


def _git_head(repo: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        die(f"git rev-parse HEAD timed out after {exc.timeout}s in {repo}")
    except OSError as exc:
        die(f"git rev-parse HEAD failed to execute in {repo}: {exc}")
    if res.returncode != 0:
        die(f"git rev-parse HEAD failed in {repo}: {res.stderr.strip() or res.returncode}")
    return res.stdout.strip()


def _find_graphify() -> str:
    found = shutil.which("graphify")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "graphify"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    die("graphify binary not found on PATH or at ~/.local/bin/graphify")


def _graph_candidates(out_dir: Path) -> tuple[Path, Path]:
    return (out_dir / "graphify-out" / "graph.json", out_dir / "graph.json")


def _read_graph_if_fresh(out_dir: Path, head: str) -> dict | None:
    for candidate in _graph_candidates(out_dir):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("built_at_commit") == head:
            return data
    return None


def load_or_build_graph(project: str) -> dict:
    repo = _repo_for(project)
    head = _git_head(repo)
    out_dir = Path(hb.HUB_DIR) / "state" / "graph" / project
    cached = _read_graph_if_fresh(out_dir, head)
    if cached is not None:
        return cached

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [_find_graphify(), "extract", str(repo), "--code-only", "--out", str(out_dir)]
    for pattern in EXCLUDES:
        cmd.extend(["--exclude", pattern])
    env = {**_clean_git_env(), **GRAPHIFY_ENV}
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        die(f"graphify extract timed out after {exc.timeout}s for {project!r}")
    except OSError as exc:
        die(f"graphify extract failed to execute for {project!r}: {exc}")
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        die(f"graphify extract failed ({res.returncode}): {detail}")

    for candidate in _graph_candidates(out_dir):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                die(f"could not read {candidate}: {exc}")
            if data.get("built_at_commit") != head:
                data["built_at_commit"] = head
                hb._write_json_atomic(str(candidate), data)
            return data
    die(f"graphify extract succeeded but wrote no graph.json under {out_dir}")


def filter_graph(raw: dict) -> tuple[dict[str, dict], list[dict]]:
    """Keep EXTRACTED edges and same-file INFERRED edges; drop cross-file INFERRED."""
    nodes = {
        n["id"]: n
        for n in raw.get("nodes", [])
        if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    raw_links = raw.get("links") if "links" in raw else raw.get("edges", [])
    kept: list[dict] = []
    for link in raw_links or []:
        if not isinstance(link, dict):
            continue
        src = link.get("_src") or link.get("source")
        tgt = link.get("_tgt") or link.get("target")
        if src not in nodes or tgt not in nodes:
            continue
        conf = link.get("confidence", "EXTRACTED")
        src_file = nodes[src].get("source_file") or ""
        tgt_file = nodes[tgt].get("source_file") or ""
        if conf == "EXTRACTED" or (conf == "INFERRED" and src_file and src_file == tgt_file):
            kept.append({**link, "source": src, "target": tgt, "confidence": conf})
    return nodes, kept


def _fmt_loc(file_path: str, loc: str) -> str:
    if not file_path:
        return "(external)"
    if not loc:
        return file_path
    loc_str = str(loc)
    if not loc_str.startswith("L"):
        loc_str = f"L{loc_str}"
    return f"{file_path}:{loc_str}"


def _fmt_node(node: dict) -> str:
    loc = _fmt_loc(node.get("source_file") or "", node.get("source_location") or "")
    label = node.get("label") or node.get("id") or "?"
    return f"{loc} {label}"


def _bare_label(node: dict) -> str:
    label = str(node.get("label") or "")
    return label[:-2] if label.endswith("()") else label


def _file_matches(node_file: str, query_file: str) -> bool:
    if not node_file or not query_file:
        return False
    nf = node_file.strip("/")
    qf = query_file.strip("/")
    if nf == qf or nf.endswith("/" + qf):
        return True
    nf_mod = nf.removesuffix(".py").replace("/", ".")
    qf_mod = qf.removesuffix(".py").replace("/", ".")
    return nf_mod == qf_mod or nf_mod.endswith("." + qf_mod)


def resolve_symbols(nodes: dict[str, dict], query: str) -> list[dict]:
    q = query.strip()
    if not q:
        die("empty symbol query")
    code_nodes = [n for n in nodes.values() if n.get("file_type") != "rationale"]

    if "::" in q:
        file_part, sym_part = q.split("::", 1)
        sym_clean = sym_part.strip().removesuffix("()")
        matches = [
            n
            for n in code_nodes
            if _file_matches(n.get("source_file") or "", file_part)
            and (
                _bare_label(n) == sym_clean
                or _bare_label(n).endswith("." + sym_clean)
                or n.get("id") == sym_clean
            )
        ]
        if matches:
            return sorted(matches, key=_node_sort_key)

    q_clean = q.removesuffix("()")
    # 1. Exact ID or exact label match
    exact = [
        n
        for n in code_nodes
        if _bare_label(n) == q_clean or n.get("id") == q_clean or n.get("label") == q
    ]
    # 2. Dotted module.symbol match (e.g. live_merge.merge_tick or pkg.mod.Class.method)
    if "." in q_clean and not q_clean.endswith(".py"):
        parts = q_clean.split(".")
        for split_idx in range(1, len(parts)):
            mod_part = ".".join(parts[:split_idx])
            sym_part = ".".join(parts[split_idx:])
            dotted = [
                n
                for n in code_nodes
                if _file_matches(n.get("source_file") or "", mod_part)
                and (_bare_label(n) == sym_part or _bare_label(n).endswith("." + sym_part))
            ]
            for n in dotted:
                if n not in exact:
                    exact.append(n)
    if exact:
        internal = [n for n in exact if n.get("source_file")]
        return sorted(internal or exact, key=_node_sort_key)

    # 3. Suffix match on Class.method when user passed bare method name
    suffix = [n for n in code_nodes if _bare_label(n).endswith("." + q_clean)]
    if suffix:
        return sorted(suffix, key=_node_sort_key)

    die(f"symbol not found in graph: {query!r}")


def _node_sort_key(node: dict) -> tuple[int, str, int, str]:
    sfile = node.get("source_file") or ""
    is_test = 1 if (sfile.startswith("tests/") or "/test_" in sfile or sfile.startswith("test_")) else 0
    loc = str(node.get("source_location") or "").lstrip("L")
    line_no = int(loc) if loc.isdigit() else 0
    return (is_test, sfile, line_no, node.get("id") or "")


def _format_caller_line(caller: dict, link: dict) -> str:
    call_file = link.get("source_file") or caller.get("source_file") or ""
    call_loc = link.get("source_location") or caller.get("source_location") or ""
    def_loc = _fmt_loc(caller.get("source_file") or "", caller.get("source_location") or "")
    site_loc = _fmt_loc(call_file, call_loc)
    label = caller.get("label") or caller.get("id")
    conf = link.get("confidence", "EXTRACTED")
    if site_loc != def_loc and caller.get("source_file"):
        return f"  {site_loc} {label} (def {def_loc}) [{conf}]"
    return f"  {site_loc} {label} [{conf}]"


def _format_callee_line(callee: dict, link: dict, caller: dict) -> str:
    call_file = link.get("source_file") or caller.get("source_file") or ""
    call_loc = link.get("source_location") or ""
    site_loc = _fmt_loc(call_file, call_loc)
    conf = link.get("confidence", "EXTRACTED")
    label = callee.get("label") or callee.get("id")
    if callee.get("source_file"):
        def_loc = _fmt_loc(callee.get("source_file") or "", callee.get("source_location") or "")
        return f"  {def_loc} {label} (at {site_loc}) [{conf}]"
    return f"  {site_loc} {label} (external) [{conf}]"


def _cmd_callers(nodes: dict[str, dict], links: list[dict], symbol: str) -> None:
    targets = resolve_symbols(nodes, symbol)
    for target in targets:
        tid = target["id"]
        incoming = [
            (nodes[l["source"]], l)
            for l in links
            if l["target"] == tid and l.get("relation") in CALL_RELATIONS
        ]
        incoming.sort(key=lambda item: _node_sort_key(item[0]))
        print(f"callers of {_fmt_node(target)} ({len(incoming)}):")
        if not incoming:
            print("  (none in static AST graph)")
        for caller, link in incoming:
            print(_format_caller_line(caller, link))
    print(STATIC_NOTE)


def _cmd_callees(nodes: dict[str, dict], links: list[dict], symbol: str) -> None:
    sources = resolve_symbols(nodes, symbol)
    for src in sources:
        sid = src["id"]
        outgoing = [
            (nodes[l["target"]], l)
            for l in links
            if l["source"] == sid and l.get("relation") in CALL_RELATIONS
        ]
        outgoing.sort(key=lambda item: _node_sort_key(item[0]))
        print(f"callees of {_fmt_node(src)} ({len(outgoing)}):")
        if not outgoing:
            print("  (none in static AST graph)")
        for callee, link in outgoing:
            print(_format_callee_line(callee, link, src))
    print(STATIC_NOTE)


def _cmd_explain(nodes: dict[str, dict], links: list[dict], symbol: str) -> None:
    targets = resolve_symbols(nodes, symbol)
    for target in targets:
        tid = target["id"]
        print(f"symbol: {_fmt_node(target)} [id: {tid}]")
        rationales = [
            nodes[l["source"]].get("label")
            for l in links
            if l["target"] == tid and l.get("relation") == "rationale_for"
        ]
        for doc in rationales:
            if doc:
                print(f"  doc: {doc}")
        incoming = [
            (nodes[l["source"]], l)
            for l in links
            if l["target"] == tid and l.get("relation") in CALL_RELATIONS
        ]
        incoming.sort(key=lambda item: _node_sort_key(item[0]))
        print(f"  callers ({len(incoming)}):")
        for caller, link in incoming:
            print("  " + _format_caller_line(caller, link))
        outgoing = [
            (nodes[l["target"]], l)
            for l in links
            if l["source"] == tid and l.get("relation") in CALL_RELATIONS
        ]
        outgoing.sort(key=lambda item: _node_sort_key(item[0]))
        print(f"  callees ({len(outgoing)}):")
        for callee, link in outgoing:
            print("  " + _format_callee_line(callee, link, target))
    print(STATIC_NOTE)


def _bfs_path(adj: dict[str, list[tuple[str, dict]]], start_ids: list[str], goal_ids: set[str]) -> list[tuple[str, dict | None]] | None:
    queue: deque[list[tuple[str, dict | None]]] = deque([[sid] for sid in start_ids])
    visited = set(start_ids)
    while queue:
        current_path = queue.popleft()
        last_node = current_path[-1][0] if isinstance(current_path[-1], tuple) else current_path[-1]
        if last_node in goal_ids and len(current_path) > 1:
            return [( current_path[0], None ), *current_path[1:]]  # type: ignore[list-item]
        for nxt, edge in adj.get(last_node, ()):
            if nxt not in visited:
                visited.add(nxt)
                queue.append([*current_path, (nxt, edge)])
    return None


def _cmd_path(nodes: dict[str, dict], links: list[dict], src_query: str, tgt_query: str) -> None:
    srcs = resolve_symbols(nodes, src_query)
    tgts = resolve_symbols(nodes, tgt_query)
    start_ids = [n["id"] for n in srcs]
    goal_ids = {n["id"] for n in tgts}

    adj: dict[str, list[tuple[str, dict]]] = {}
    for link in links:
        rel = link.get("relation")
        if rel == "rationale_for":
            continue
        u, v = link["source"], link["target"]
        if nodes[u].get("file_type") == "rationale" or nodes[v].get("file_type") == "rationale":
            continue
        adj.setdefault(u, []).append((v, link))
        if rel == "contains":
            adj.setdefault(v, []).append((u, link))
    for k in adj:
        adj[k].sort(key=lambda item: _node_sort_key(nodes[item[0]]))

    found = _bfs_path(adj, start_ids, goal_ids)
    if not found:
        print(f"no path found between {src_query!r} and {tgt_query!r} ({STATIC_NOTE})")
        return

    hops = len(found) - 1
    print(f"path ({hops} {'hop' if hops == 1 else 'hops'}):")
    for idx in range(hops):
        u_id, _ = found[idx]
        v_id, edge = found[idx + 1]
        assert edge is not None
        rel = edge.get("relation", "calls")
        conf = edge.get("confidence", "EXTRACTED")
        site = _fmt_loc(edge.get("source_file") or "", edge.get("source_location") or "")
        print(f"  {_fmt_node(nodes[u_id])} --{rel} [{conf}] ({site})--> {_fmt_node(nodes[v_id])}")
    print(STATIC_NOTE)


def cmd_map(a: argparse.Namespace) -> None:
    if a.action == "path":
        if not a.target:
            die("hub map <project> path requires two symbols: <source> <target>")
    elif a.target is not None:
        die(f"hub map <project> {a.action} takes one symbol, got extra {a.target!r}")

    raw = load_or_build_graph(a.project)
    nodes, links = filter_graph(raw)
    if a.action == "callers":
        _cmd_callers(nodes, links, a.symbol)
    elif a.action == "callees":
        _cmd_callees(nodes, links, a.symbol)
    elif a.action == "explain":
        _cmd_explain(nodes, links, a.symbol)
    elif a.action == "path":
        _cmd_path(nodes, links, a.symbol, a.target)


def register(sub: argparse._SubParsersAction) -> None:
    mp = sub.add_parser(
        "map",
        help="query code call graph (callers, callees, explain, path) via offline graphify (keyed on HEAD; uncommitted edits are not included)",
        description=(
            "Query the static AST code call graph via offline graphify. "
            "The cached graph is keyed on the repository's HEAD commit (built_at_commit), "
            "so uncommitted working-tree edits are not included."
        ),
    )
    mp.add_argument("project", help="project name ('hub' or repo under ~/code/<project>)")
    mp.add_argument("action", choices=("callers", "callees", "explain", "path"))
    mp.add_argument("symbol", help="symbol name, Module.symbol, or file.py::symbol")
    mp.add_argument("target", nargs="?", help="target symbol (for 'path' only)")
    mp.set_defaults(fn=cmd_map)


def run_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="hub")
    sub = parser.add_subparsers(dest="cmd", required=True)
    register(sub)
    args = parser.parse_args(["map", *argv])
    args.fn(args)
