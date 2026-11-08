"""Autonomy phases (living spec §4, T-576): what each factory.json agent may do alone, and for how long.

  hub agents                                   each agent's phase and record, then the phase table
  hub agent phase <name> <phase> --why "..."   change a phase (lead phase only), logged as a `phase` event
  hub approve <repo>#<pr> <sha>                record a review approval on the board (Addendum 2, M4)
  hub changes <repo>#<pr> <sha> "why"          record a request for changes

factory.json's "autonomy" block holds the phases and each agent names one with "phase". Without the block there
are no phase rules (hand-set dispatch/reset, as before), and an agent not in factory.json has none either.
--force on claim/release/block/assign/edit and tag clearing stay Zeus's or the lead's by convention (M5/M6).
"""

import json
import os
import re
import subprocess
import sys

import board as hb

OFF = {"dispatch": False, "reset": False, "budget_minutes": None, "may": []}
# Every key a phase may carry: (accepts, what is allowed, what a bad value falls back to, and how that reads).
PHASE_KEYS = {
    "dispatch": (lambda v: isinstance(v, bool), "true or false", False, "treated as off"),
    "reset": (lambda v: v is False or v == "per-task", 'false or "per-task"', False, "treated as off"),
    "budget_minutes": (lambda v: type(v) is int and v > 0, "whole minutes above 0", None, "no budget"),
    "may": (lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v), "a list of action names", [],
            "may nothing"),
}
REF = re.compile(r"(?:([\w.-]+)/)?([\w.-]+)#(\d+)")


def factory_path():
    return os.path.join(hb.HUB_DIR, "factory.json")


def factory():
    try:
        with open(factory_path()) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def table(cfg):
    """(the autonomy block with every bad setting at its safe default, one line per problem); None without one."""
    auto = cfg.get("autonomy")
    if auto is None:
        return None, []
    auto = auto if isinstance(auto, dict) else {}
    raw = auto.get("phases") if isinstance(auto.get("phases"), dict) else {}
    bad = [] if raw else ["factory.json: autonomy.phases is missing or not an object; every agent is off"]
    phases = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            bad.append(f"factory.json: autonomy phase {name} is not an object; treated as off")
            spec = {}
        for k in spec.keys() - PHASE_KEYS.keys():
            bad.append(f"factory.json: autonomy phase {name}: unknown key {json.dumps(k)}; ignored")
        phases[name] = {}
        for k, (ok, allowed, fallback, means) in PHASE_KEYS.items():
            if k in spec and not ok(spec[k]):
                bad.append(f"factory.json: autonomy phase {name}: {k}={json.dumps(spec[k])} is not allowed "
                           f"(allowed: {allowed}); {means}")
            phases[name][k] = spec[k] if k in spec and ok(spec[k]) else fallback
    phases.setdefault("off", OFF)
    default = auto.get("default_phase", "off")
    if default not in phases:
        bad.append(f"factory.json: autonomy.default_phase={json.dumps(default)} is not a phase; off used")
        default = "off"
    kinds = auto.get("known_kinds", [])
    promote = auto.get("promote_after", 5)
    return {"phases": phases, "default_phase": default,
            "known_kinds": kinds if isinstance(kinds, list) else [],
            "promote_after": promote if type(promote) is int and promote > 0 else 5}, bad


def agents(cfg):
    return [a for a in cfg.get("agents") or [] if isinstance(a, dict) and isinstance(a.get("name"), str)]


def entry(name, cfg=None):
    """The agent's factory.json entry, or None."""
    return next((a for a in agents(factory() if cfg is None else cfg)
                 if a["name"].lower() == (name or "").lower()), None)


def phase_name(a, auto):
    """An agent's phase: its own, else the default for a known kind, else off (living spec §4, Inheritance)."""
    if "phase" in a:
        return a["phase"] if isinstance(a["phase"], str) and a["phase"] in auto["phases"] else "off"
    return auto["default_phase"] if a.get("kind") in auto["known_kinds"] else "off"


def phase_of(name, cfg=None):
    """(phase, its settings) for a factory.json agent; (None, None) where no phase rules apply."""
    cfg = factory() if cfg is None else cfg
    auto, a = table(cfg)[0], entry(name, cfg)
    if auto is None or a is None:
        return None, None
    p = phase_name(a, auto)
    return p, auto["phases"][p]


def lacks(name, action):
    """The agent's phase when that phase does not allow `action`, else None."""
    p, spec = phase_of(name)
    return p if spec is not None and action not in spec["may"] else None


def reviewer(cfg=None):
    """The configured reviewer, using the same effective phase as dispatch; $HUB_REVIEWER (default Hermes) without one."""
    cfg = factory() if cfg is None else cfg
    return next((a["name"] for a in agents(cfg)
                 if (phase_of(a["name"], cfg)[0] or a.get("phase")) == "reviewer"),
                os.environ.get("HUB_REVIEWER") or "Hermes")


def record(name, events, n):
    """[(task, flags)] for the agent's last n done tasks since its last phase change, oldest first; no flags is
    clean: verify passed first time, no override, within budget, no revert."""
    last_phase = max((i for i, e in enumerate(events) if e["event"] == "phase"
                      and hb.canon(e.get("agent")) == hb.canon(name)), default=-1)
    events = events[last_phase + 1:]
    by_task = {}
    for e in events:
        by_task.setdefault(e.get("task"), []).append(e)
    done = [e for e in events if e["event"] == "done" and hb.canon(e.get("by")) == hb.canon(name)]
    out = []
    for tid in reversed(list(dict.fromkeys(e["task"] for e in reversed(done)))[:n]):
        evs = by_task[tid]
        verify = [e.get("verify") for e in evs if e["event"] == "done"][-1]
        over = max((e.get("level", 1) for e in evs if e["event"] == "over_budget"), default=0)
        flags = [flag for flag, hit in (
            ("verify failed", any(e["event"] == "verify_failed" for e in evs)),
            ("no verify", verify != "passed" and not any(e["event"] == "verify_failed" for e in evs)),
            ("override", any(e["event"] == "override" for e in evs)),
            ("over 2x budget" if over > 1 else "over budget", over),
            ("reverted", any(e["event"] == "reopened" and "revert" in (e.get("why") or "") for e in evs))) if hit]
        out.append((tid, flags))
    return out


def show_record(rec):
    flagged = [f"{tid} {', '.join(flags)}" for tid, flags in rec if flags]
    return f"record {len(rec) - len(flagged)}/{len(rec)} clean" + (f": {'; '.join(flagged)}" if flagged else "")


def markdown(auto):
    """The phase table HUB.md points to instead of copying it."""
    yes = lambda v: "yes" if v is True else "per task" if v == "per-task" else "no"  # noqa: E731
    rows = ["| phase | dispatch | reset | budget | may |", "|---|---|---|---|---|"]
    for p, s in auto["phases"].items():
        budget = f"{s['budget_minutes']} min" if s["budget_minutes"] else "none"
        rows.append(f"| {p} | {yes(s['dispatch'])} | {yes(s['reset'])} | {budget} | {', '.join(s['may']) or 'nothing'} |")
    return "\n".join(rows)


def cmd_agents(a):
    cfg = factory()
    auto, bad = table(cfg)
    if auto is None:
        sys.exit("factory.json has no autonomy block: no phases are in use")
    events = hb.ledger()
    warnings = list(bad)
    for x in agents(cfg):
        p = phase_name(x, auto)
        print(f"{x['name']:<12}{p:<10}{show_record(record(x['name'], events, auto['promote_after']))}")
        dead = [k for k in ("dispatch", "reset") if k in x and "phase" in x]
        if dead:
            warnings.append(f"warning: {x['name']}: {', '.join(dead)} ignored; phase {p} decides them")
    print("\n".join(["", *warnings]) if warnings else "")
    print(f"\n{markdown(auto)}\n\nMerge and deploy are in no phase: only hub live does them, after its gates.")


def set_phase(name, to, why, by):
    """Write the agent's phase into factory.json, its dead dispatch/reset keys dropped, and log a `phase` event.
    Under the board lock, so two phase changes never interleave. Returns the phase it had."""
    with hb.board(write=True) as (_, events):
        try:  # strict here: factory() would read a broken file as {} and this write would erase it
            with open(factory_path()) as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            sys.exit(f"factory.json unreadable, not changed: {e}")
        auto, a = table(cfg)[0], entry(name, cfg)
        old = phase_name(a, auto)
        a["phase"] = to
        for k in ("dispatch", "reset"):
            a.pop(k, None)
        hb._write_json_atomic(factory_path(), cfg)
        hb.log(events, by, "phase", "-", agent=a["name"], why=why, **{"from": old, "to": to})
    return old


def cmd_phase(a):
    env = hb.addressable(hb.whoami(), "acting agent")  # the environment's identity, never --as
    cfg = factory()
    auto = table(cfg)[0]
    if auto is None:
        sys.exit("factory.json has no autonomy block: no phases are in use")
    if phase_of(env, cfg)[0] != "lead":
        sys.exit(f"only the lead phase changes phases; {env} is {phase_of(env, cfg)[0] or 'not in factory.json'}")
    target = entry(a.name, cfg)
    if target is None:
        sys.exit(f"{hb.canon(a.name)} is not in factory.json")
    if a.phase not in auto["phases"]:
        sys.exit(f"no phase {a.phase!r}; the phases are {', '.join(auto['phases'])}")
    old = set_phase(target["name"], a.phase, a.why, env)
    print(f"{target['name']}: {old} -> {a.phase} ({a.why})")


def task_for(data, project, pr):
    """The board task a PR builds: its task/T-n branch, else the issue it closes in that project."""
    from live_merge import CLOSES
    m = re.fullmatch(r"task/(T-\d+)", pr.get("headRefName") or "")
    if m:
        return next((t for t in data["tasks"] if t["id"] == m[1]), None)
    c = CLOSES.search(pr.get("body") or "")
    return c and next((t for t in data["tasks"] if t.get("project") == project and t.get("issue") == int(c[1])), None)


def cmd_review(a):
    """hub approve / hub changes: a board event naming the PR's head sha, the claimed and the environment's
    identity, so a mismatch shows in hub trace. Identity is self-declared: least upkeep over hardening."""
    import gh_sync
    env = hb.addressable(hb.whoami(), "acting agent")
    by = hb.whoami(a.as_agent)
    m = REF.fullmatch(a.ref)
    if not m:
        sys.exit(f"{a.ref!r}: give the PR as <owner/repo>#<pr>, e.g. you/webapp#13")
    repo = f"{m[1]}/{m[2]}" if m[1] else gh_sync.factory_entry(m[2]).get("repo")
    if not repo:
        sys.exit(f"{m[2]} is not a factory.json repo: give it as <owner/repo>#{m[3]}")
    ref, sha = f"{repo}#{m[3]}", a.sha.lower()
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        sys.exit(f"{a.sha!r} is not a commit sha (7 to 40 hex characters)")
    if a.event == "approved" and lacks(env, "review"):
        sys.exit(f"{env}'s phase {lacks(env, 'review')} has no review: its approval would not count")
    try:
        pr = gh_sync.Gh().json("pr", "view", m[3], "-R", repo, "--json", "headRefName,headRefOid,body") or {}
    except gh_sync.GhError as e:
        sys.exit(f"cannot read {ref} to find its builder: {e}")
    head = pr.get("headRefOid") or ""
    if not head.startswith(sha):
        sys.exit(f"{sha} is not the head of {ref} (head {head[:12] or 'unknown'}): review the head")
    with hb.board(write=True) as (data, events):
        t = task_for(data, repo.split("/")[-1], pr)
        builder = hb.canon(hb.actor(t)) if t and hb.actor(t) else None
        if builder and builder in (env, by):
            sys.exit(f"{builder} built {ref}: a builder never reviews its own PR")
        hb.log(events, by, a.event, t["id"] if t else "-", repo=repo, pr=int(m[3]), sha=head, builder=builder,
               env=env, **({"why": a.why} if a.event == "changes" else {}))
    print(f"{'approval' if a.event == 'approved' else 'changes'} recorded: {ref} at {head[:12]} by {by}"
          + (f" (environment {env})" if env != by else "") + (f", built by {builder}" if builder else ""))


def board_approvals(repo):
    """{(pr, sha): reviewer} for all currently approved PRs on the board for repo."""
    approvals = {}
    for e in hb.ledger():
        if e.get("event") in ("approved", "changes") and e.get("repo") == repo:
            key = (e.get("pr"), e.get("sha"))
            if e["event"] == "approved":
                by = hb.canon(e.get("by") or e.get("env"))
                builder = hb.canon(e.get("builder"))
                if by and by != builder and not lacks(by, "review"):
                    approvals[key] = by
            else:
                approvals.pop(key, None)
    return approvals


def weekly(dry):
    """Demotion is automatic and safe-direction: a trusted agent with a revert, or two 2x overruns in a row, in
    its record goes to trial and Zeus hears. Promotion is Zeus's call: a clean trial record opens a task."""
    cfg = factory()
    auto = table(cfg)[0]
    if auto is None:
        return
    events = hb.ledger()
    with hb.board() as (data, _):
        live = {t["title"] for t in data["tasks"] if t["status"] != "done"}
    for x in agents(cfg):
        name, p = x["name"], phase_name(x, auto)
        rec = record(name, events, auto["promote_after"])
        reverted = [tid for tid, flags in rec if "reverted" in flags]
        overran = len(rec) >= 2 and all("over 2x budget" in flags for _, flags in rec[-2:])
        if p == "trusted" and (reverted or overran):
            why = (f"{', '.join(reverted)} reverted" if reverted
                   else f"{rec[-2][0]} and {rec[-1][0]} each ran over twice their budget")
            print(f"{name}: trusted -> trial ({why})" + (" [dry run]" if dry else ""))
            if not dry:
                set_phase(name, "trial", why, "Dispatch")
                hb.deliver(hb.LEAD_AGENT, f"[weekly] {name} demoted to trial: {why}. Promote it again with hub agent "
                                   f"phase {name} trusted --why \"...\" when its record is clean.  (from Dispatch)")
        elif p == "trial" and len(rec) == auto["promote_after"] and not any(flags for _, flags in rec):
            title = f"Promote {name} to trusted?"
            if title in live:
                print(f"{title}: already open")
            elif dry:
                print(f"would open '{title}' for {hb.LEAD_AGENT}")
            else:
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "board.py"),
                                "new", title, "--owner", hb.LEAD_AGENT, "--project", "hub", "--detail",
                                f"Weekly (hub-weekly.timer). {name}'s last {len(rec)} done tasks are clean "
                                f"({', '.join(t for t, _ in rec)}): verify passed first time, no override, within "
                                f"budget, no revert. Read hub agents, then hub agent phase {name} trusted --why "
                                f"\"...\", or close this with one line why not."],
                               check=True, timeout=30, env={**os.environ, "HUB_AGENT": "Dispatch"})


def register(sub):
    p = sub.add_parser("agents", help="each agent's phase and record, then the phase table")
    p.set_defaults(fn=cmd_agents)
    ag = sub.add_parser("agent", help="change an agent's autonomy phase (lead phase only)")
    s = ag.add_subparsers(dest="agent_cmd", required=True)
    ph = s.add_parser("phase", help="set <name>'s phase in factory.json, logged with why")
    ph.add_argument("name")
    ph.add_argument("phase")
    ph.add_argument("--why", required=True, help="one line for the ledger")
    ph.set_defaults(fn=cmd_phase)
    ap = sub.add_parser("approve", help="record a review approval of a PR's head on the board")
    ch = sub.add_parser("changes", help="record a request for changes on a PR's head on the board")
    for x, event in ((ap, "approved"), (ch, "changes")):
        x.add_argument("ref", metavar="<owner/repo>#<pr>")
        x.add_argument("sha", help="the PR's head sha you reviewed (7+ hex characters)")
        if event == "changes":
            x.add_argument("why")
        x.set_defaults(fn=cmd_review, event=event)
