# The finish loop's bookkeeping (judge.md §6): record each round's blind verdict, refuse a re-judge of
# unchanged screens, and print what the parent does next. The parent runs the judges and the fixes; this
# script only decides, so one parent can run the loop per brief without judgement of its own.
#   uv run python finish-loop.py TRAIL_DIR round --mode hackathon|planning --screens DIR --verdict FILE
#   uv run python finish-loop.py TRAIL_DIR confirm --verdict FILE     (the second judge, same screens)
# First stdout line is `next: fix | confirm | ship | stop plateau | stop cap | recapture`.
# Exit 0 ship, 2 keep going (fix or confirm), 3 stopped without ship, 1 refused or malformed.
# Writes TRAIL_DIR/trail.json (state) and TRAIL_DIR/trail.md (the score trail the lead and G3 read).
import argparse, hashlib, json, re, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

CAP = {"hackathon": 3, "planning": 5}
GATE, FLOOR = 22, 21  # ship: median >= 22 with B7 and B8 at 2; each of the two judges >= 21
B_ROW = re.compile(r"^\|\s*\**B(\d{1,2})\**\s*\|\s*\**([012])\**\s*\|", re.M)
R_LINE = re.compile(r"^R([12])\s+([012])\b", re.M)
DISPOSITION = re.compile(r"disposition\b[^:\n]*:\s*\**`?(ship|fix|rebuild|recapture)\b", re.I)


def refuse(msg):
    print(f"refused: {msg}")
    sys.exit(1)


def read_verdict(path):
    text = Path(path).read_text()
    m = DISPOSITION.search(text)
    b = {int(n): int(s) for n, s in B_ROW.findall(text)}
    if not m or sorted(b) != list(range(1, 13)):
        refuse(f"{path}: needs a disposition line and B1 to B12 rows (rubric.md §7); ask the judge again")
    r = dict(R_LINE.findall(text))
    return {"file": str(path), "disposition": m.group(1).lower(), "b": [b[n] for n in range(1, 13)],
            "total": sum(b.values()), "r": [r.get("1", "-"), r.get("2", "-")]}


def screens_hash(d):
    pngs = sorted(Path(d).glob("*.png"))
    if not pngs:
        refuse(f"no captures in {d}")
    h = hashlib.sha256()
    for p in pngs:
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()


def gate_one(v):
    return v["disposition"] == "ship" and v["total"] >= GATE and v["b"][6] == 2 and v["b"][7] == 2


def score(rnd):
    vs = rnd["verdicts"]
    return statistics.median(v["total"] for v in vs), [statistics.median(v["b"][i] for v in vs) for i in range(12)]


def shipped(rnd):
    a, b = rnd["verdicts"]
    total, bs = score(rnd)
    return (gate_one(a) and b["disposition"] in ("ship", "fix") and min(a["total"], b["total"]) >= FLOOR
            and total >= GATE and bs[6] == 2 and bs[7] == 2)


def keep_going(trail):
    scores = [score(r)[0] for r in trail["rounds"]]
    gains = [b - a for a, b in zip(scores, scores[1:])]
    if len(gains) >= 2 and gains[-1] < 1 and gains[-2] < 1:
        return "stop plateau"
    if len(scores) >= CAP[trail["mode"]]:
        return "stop cap"
    return "fix"


def write(tdir, trail):
    (tdir / "trail.json").write_text(json.dumps(trail, indent=1))
    lines = [f"# Finish loop score trail ({trail['mode']}, cap {CAP[trail['mode']]} rounds)", "",
             "| Round | UTC | Screens | Judges | Disposition | R1 | R2 | " + " | ".join(f"B{i}" for i in range(1, 13))
             + " | Total | Gain |", "|" + "---|" * 21]
    prev = None
    for r in trail["rounds"]:
        total, bs = score(r)
        fmt = lambda x: f"{x:g}"
        gain = "" if prev is None else f"{total - prev:+g}"
        lines.append(f"| {r['n']} | {r['utc']} | {r['hash'][:8]} | {len(r['verdicts'])} | "
                     f"{', '.join(v['disposition'] for v in r['verdicts'])} | "
                     + " | ".join("/".join(v.get("r", "--")[i] for v in r["verdicts"]) for i in (0, 1)) + " | "
                     + " | ".join(map(fmt, bs)) + f" | {fmt(total)}/24 | {gain} |")
        prev = total
    lines += ["", f"Outcome: {trail['next']}", ""]
    (tdir / "trail.md").write_text("\n".join(lines))


def finish(tdir, trail, nxt):
    trail["next"] = nxt
    write(tdir, trail)
    print(f"next: {nxt}")
    sys.exit(0 if nxt == "ship" else 2 if nxt in ("fix", "confirm") else 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trail_dir", type=Path)
    ap.add_argument("action", choices=["round", "confirm"])
    ap.add_argument("--mode", choices=list(CAP))
    ap.add_argument("--screens")
    ap.add_argument("--verdict", required=True)
    a = ap.parse_args()
    a.trail_dir.mkdir(parents=True, exist_ok=True)
    tf = a.trail_dir / "trail.json"
    trail = json.loads(tf.read_text()) if tf.exists() else {"mode": a.mode, "rounds": [], "next": "fix"}
    if trail["next"] not in ("fix", "confirm"):
        refuse(f"the loop has ended ({trail['next']})")
    v = read_verdict(a.verdict)
    last = trail["rounds"][-1] if trail["rounds"] else None

    if a.action == "confirm":
        if trail["next"] != "confirm":
            refuse("no round is waiting for a second judge")
        if screens_hash(last["screens"]) != last["hash"]:
            refuse("the screens changed since the first judge; the second judge scores the same screens")
        last["verdicts"].append(v)
        finish(a.trail_dir, trail, "ship" if shipped(last) else keep_going(trail))

    if not a.mode or not a.screens:
        refuse("round needs --mode and --screens")
    if trail["next"] == "confirm":
        refuse(f"round {last['n']} is waiting for its second judge (confirm)")
    if v["disposition"] == "recapture":
        print("next: recapture")  # a broken capture is not a round
        sys.exit(1)
    h = screens_hash(a.screens)
    if last and h == last["hash"]:
        refuse(f"screens unchanged since round {last['n']}: apply its changes before a re-judge")
    trail["rounds"].append({"n": len(trail["rounds"]) + 1, "utc": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                            "screens": str(Path(a.screens).resolve()), "hash": h, "verdicts": [v]})
    finish(a.trail_dir, trail, "confirm" if gate_one(v) else keep_going(trail))


if __name__ == "__main__":
    main()
