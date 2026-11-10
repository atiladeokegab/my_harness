"""Hourly spend guard (hub-spend.timer): find a cloud cost leak within the hour and stop it.

A tagged revision keeps its own min instances running even at 0% traffic; 26 stale strata
tags cost ~£25/day in Nov 2026 while credits hid it. The credits are gone, so a leak now hits the
lead's card. Each hour, for both projects:
- a routed Cloud Run revision (live or tagged) with min instances >= 1 and older than MAX_AGE is
  scaled down (live: --min-instances 0 then traffic to latest; tag: the tag is removed);
- any VM other than hub-host, and any Cloud Run job execution running over JOB_MAX, is reported
  (never deleted);
- budget notifications (Pub/Sub, SUBSCRIPTION) are reported at 50/90/100%, and at 100% of the
  hackathon-starter budget every Cloud Run service in my-events-project is deleted. Nothing in
  my-hub-project is deleted automatically.
The journal gets the full technical report; the lead's WhatsApp gets only what needs them, in plain sentences
(budgets, the event shutdown, a stray VM or long job, a damaged state file). --dry-run changes nothing.
"""

import base64
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HUB_PROJECT = os.environ.get("HUB_HOST_PROJECT", "my-hub-project")
EVENT_PROJECT = os.environ.get("HUB_SPEND_EVENT_PROJECT", "my-events-project")  # products come down after an event
PROJECTS = (EVENT_PROJECT, HUB_PROJECT)
HOST = (HUB_PROJECT, "hub-host")  # the one VM that may exist
# Only this budget, by its stable id (display names are editable text), may bring EVENT_PROJECT down.
EVENT_BUDGET_ID = os.environ.get("HUB_SPEND_EVENT_BUDGET", "00000000-0000-0000-0000-000000000000")
SUBSCRIPTION = (HUB_PROJECT, "hub-spend")
MAX_AGE = timedelta(hours=6)
JOB_MAX = timedelta(hours=2)
THRESHOLDS = (0.5, 0.9, 1.0)
STATE = Path(os.environ.get("HUB_SPEND_STATE", "~/.local/state/hub/spend.json")).expanduser()


def gcloud(*args, parse=True):
    out = subprocess.run(["timeout", "120", "gcloud", *args, *(["--format=json"] if parse else ["--quiet"])],
                         capture_output=True, check=True, text=True).stdout
    return json.loads(out or "[]") if parse else out


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def region(obj):
    return obj["metadata"]["labels"]["cloud.googleapis.com/location"]


def stale_tags(services, revisions, now):
    """[(service, region, tag or None for live)] for routed revisions with min instances, older than MAX_AGE."""
    rev = {r["metadata"]["name"]: r for r in revisions}
    found = []
    for s in services:
        for t in s.get("status", {}).get("traffic", []):
            r = rev.get(t.get("revisionName"))
            if not r or not (t.get("tag") or t.get("percent")):
                continue
            meta = r["metadata"]
            if int(meta.get("annotations", {}).get("autoscaling.knative.dev/minScale", 0)) < 1:
                continue
            if now - ts(meta["creationTimestamp"]) < MAX_AGE:
                continue
            item = (s["metadata"]["name"], region(s), t.get("tag") if not t.get("percent") else None)
            if item not in found:
                found.append(item)
    return found


def fixes(found, project):
    """The gcloud commands that stop the warm revisions in `found`."""
    by_svc = {}
    for svc, reg, tag in found:
        by_svc.setdefault((svc, reg), []).append(tag)
    cmds = []
    for (svc, reg), tags in by_svc.items():
        where = ["--region", reg, "--project", project]
        if None in tags:
            cmds.append(["run", "services", "update", svc, *where, "--min-instances", "0"])
            # traffic pinned to a revision (e.g. a promoted tag) stays on the warm one until moved
            cmds.append(["run", "services", "update-traffic", svc, *where, "--to-latest"])
        if old := [t for t in tags if t]:
            cmds.append(["run", "services", "update-traffic", svc, *where, "--remove-tags", ",".join(old)])
    return cmds


def stray_vms(instances, project):
    """[(name, zone, status, gpus)] for every VM that is not hub-host."""
    return [(i["name"], i["zone"].rsplit("/", 1)[-1], i.get("status"),
             sum(a.get("acceleratorCount", 0) for a in i.get("guestAccelerators") or []))
            for i in instances if (project, i["name"]) != HOST]


def long_jobs(executions, now):
    """[(execution, region, hours)] for job executions still running after JOB_MAX."""
    out = []
    for e in executions:
        st = e.get("status", {})
        if st.get("completionTime") or not st.get("startTime"):
            continue
        age = now - ts(st["startTime"])
        if age > JOB_MAX:
            out.append((e["metadata"]["name"], region(e), round(age.total_seconds() / 3600, 1)))
    return out


def budget_alerts(messages, seen):
    """[(budget, threshold, cost, amount, currency, key, budget_id)] for thresholds crossed and not yet reported.
    `seen` holds keys already reported; a budget notification repeats several times a day."""
    out = []
    for m in messages:
        msg = m.get("message", m)
        try:
            d = json.loads(base64.b64decode(msg.get("data", "")))
            cost, amount = float(d["costAmount"]), float(d["budgetAmount"])
        except (ValueError, KeyError, TypeError):
            continue
        crossed = [t for t in THRESHOLDS if amount and cost >= t * amount]
        if not crossed:
            continue
        budget_id = msg.get("attributes", {}).get("budgetId", "")
        name = d.get("budgetDisplayName") or budget_id or "?"
        key = f"{budget_id or name}|{d.get('costIntervalStart', '')}|{crossed[-1]}"  # names are not unique
        if key in seen or any(a[5] == key for a in out):
            continue
        out.append((name, crossed[-1], cost, amount, d.get("currencyCode", ""), key, budget_id))
    return out


def is_event_budget(budget_id):
    return budget_id == EVENT_BUDGET_ID


def load_state():
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {"seen": []}
    except ValueError:
        # Corrupt state is not a verified 100% budget alert, so it never sets pending_delete (the lead's ruling):
        # warn, and run() sets the bad file aside as .corrupt for a human to recover any lost pending/unsent.
        print(f"WARNING {STATE} was corrupt and is kept as {STATE.name}.corrupt. Any pending {EVENT_PROJECT} "
              "deletion or unsent alert in it is lost: check it by hand", file=sys.stderr)
        return {"seen": [], "quarantined": True,
                "unsent": [hubwa.SPEND_CORRUPT]}


def save_state(state):
    """Atomic: a crash mid-write leaves the previous state, never a torn file."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + ".tmp")
    tmp.write_text(json.dumps(state))
    fd = os.open(tmp, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, STATE)


_loader = importlib.machinery.SourceFileLoader("hubwa", str(Path(__file__).resolve().parent / "hubwa"))
hubwa = importlib.util.module_from_spec(importlib.util.spec_from_loader("hubwa", _loader))
_loader.exec_module(hubwa)  # its filter (unfit) and plain wording, so the two never drift


def money(x, cur):
    return f"£{x:.0f}" if cur == "GBP" else f"{x:.0f} {cur if cur.isalpha() else ''}".strip()


def plain_budget(t, cost, amount, cur, event):
    """No budget display name: it is free text and may trip hubwa's filter (a budget called "disk backups")."""
    which = "The hackathon event's cloud budget" if event else "The hub's cloud budget"
    spent = f"about {money(cost, cur)} of {money(amount, cur)} spent"
    if t >= 1.0:
        return f"{which} is used up: {spent}."
    return f"{which} is {'nearly used up' if t >= 0.9 else 'over half used'}: {spent}."


def for_phone(text):
    """`text` if hubwa will send it, else its plain translation (old technical outbox entries); None when it holds
    only routine fixes, which stay in the journal."""
    if not hubwa.unfit(text):
        return text
    print(f"rewrote for WhatsApp, technical or legacy: {text}", file=sys.stderr)
    return hubwa.rewrite(text)


def run(dry, now=None, call=gcloud):
    """One pass. Returns (technical report for the journal or "", log lines); the lead's plain-English
    WhatsApp text is queued in the state's "unsent"."""
    now = now or datetime.now(UTC)
    state = load_state()
    seen = set(state.get("seen", []))
    report, plain, log = [], [], []
    if state.get("pending_delete") == "corrupt-state":  # written by 572734b from corrupt state, not by a budget
        state.pop("pending_delete")
        log.append(f"WARNING the legacy corrupt-state delete marker in {STATE} was neutralized; "
                   f"nothing in {EVENT_PROJECT} was deleted for it")
        state["unsent"] = state.get("unsent", []) + [hubwa.SPEND_NEUTRALIZED]
    outbox = state.get("unsent", [])
    if state.get("quarantined") is True and not dry:  # just loaded corrupt; a dry run writes nothing
        shutil.copyfile(STATE, STATE.with_name(STATE.name + ".corrupt"))
        state["quarantined"] = now.isoformat()  # stays in the state as the mark

    def checkpoint():
        # seen and the alerts that mark it seen go to disk in one write, so nothing seen is left unsent
        state["seen"] = sorted(seen)
        state["unsent"] = outbox + ([" ".join(dict.fromkeys(plain))] if plain else [])
        save_state(state)

    def act(cmd):
        log.append(("dry-run: " if dry else "ran: ") + "gcloud " + " ".join(cmd))
        if not dry:
            call(*cmd, parse=False)
        return True

    def safely(what, f):
        try:
            return f()
        except (subprocess.CalledProcessError, ValueError, KeyError) as e:
            # shortcut: a failing check reaches only the journal, not WhatsApp; alert on it if one ever hides a leak
            log.append(f"could not {what}: {getattr(e, 'stderr', '') or e}".strip())
            return None

    # Budget notifications first, and acked only once what they ask for is on disk: a crash or a failed
    # write leaves them on the subscription for the next run (well inside the 10s ack deadline).
    sub_project, sub = SUBSCRIPTION
    pull = ["pubsub", "subscriptions", "pull", sub, "--project", sub_project, "--limit", "100"]
    messages = safely("pull budget notifications", lambda: call(*pull)) or []
    for name, t, cost, amount, cur, key, budget_id in budget_alerts(messages, seen):
        seen.add(key)
        report.append(f"budget {name}: {cost:.2f} of {amount:.2f} {cur} spent ({int(t * 100)}% crossed)")
        plain.append(plain_budget(t, cost, amount, cur, is_event_budget(budget_id)))
        if t >= 1.0 and is_event_budget(budget_id):
            state["pending_delete"] = key
    acks = [m["ackId"] for m in messages if m.get("ackId")]
    if acks and not dry:
        checkpoint()
        safely("ack budget notifications", lambda: call(
            "pubsub", "subscriptions", "ack", sub, "--project", sub_project, "--ack-ids", ",".join(acks)))

    for project in PROJECTS:
        services = safely(f"list services in {project}", lambda: call("run", "services", "list", "--project", project))
        if services:
            revisions = []
            for reg in sorted({region(s) for s in services}):
                revisions += safely(f"list revisions in {project}/{reg}", lambda: call(
                    "run", "revisions", "list", "--region", reg, "--project", project)) or []
            for cmd in fixes(stale_tags(services, revisions, now), project):
                if safely(f"scale down in {project}", lambda: act(cmd)):
                    report.append(f"{'would run' if dry else 'ran'}: gcloud {' '.join(cmd)}")
        vms = safely(f"list VMs in {project}", lambda: call("compute", "instances", "list", "--project", project))
        for name, zone, status, gpus in stray_vms(vms or [], project):
            if (key := f"vm|{project}|{name}") not in seen:
                seen.add(key)
                report.append(f"VM {name} in {project} ({zone}, {status}, {gpus} GPU) is not hub-host: check it")
                plain.append(hubwa.machine(status))
        jobs = safely(f"list jobs in {project}", lambda: call("run", "jobs", "list", "--project", project))
        for reg in sorted({region(j) for j in jobs or []}):
            ex = safely(f"list executions in {project}/{reg}", lambda: call(
                "run", "jobs", "executions", "list", "--region", reg, "--project", project)) or []
            for name, reg_, hours in long_jobs(ex, now):
                if (key := f"job|{project}|{name}") not in seen:
                    seen.add(key)
                    report.append(f"job execution {name} in {project}/{reg_} has run {hours}h")
                    plain.append(f"A cloud job has been running for over {int(hours)} hours, longer than expected.")

    if state.get("pending_delete"):
        services = safely(f"list services in {EVENT_PROJECT}",
                          lambda: call("run", "services", "list", "--project", EVENT_PROJECT))
        done = services is not None
        for s in services or []:
            cmd = ["run", "services", "delete", s["metadata"]["name"], "--region", region(s),
                   "--project", EVENT_PROJECT]
            if safely(f"delete {s['metadata']['name']}", lambda: act(cmd)):
                report.append(f"{'would delete' if dry else 'deleted'} {EVENT_PROJECT} service "
                              f"{s['metadata']['name']} ({region(s)})")
                plain.append("To stop the charges, Hub switched off the hackathon event's apps.")
            else:
                done = False
        if done:
            state.pop("pending_delete")
        else:
            report.append(f"{EVENT_PROJECT} services are not all deleted yet: retrying next hour")
            plain.append("Some of the hackathon event's apps could not be switched off yet; Hub will try again "
                         "within the hour.")
    if not dry:
        checkpoint()
    return ("Cloud spend guard:\n" + "\n".join(report)) if report else "", log


def main():
    dry = "--dry-run" in sys.argv
    text, log = run(dry)
    for line in log:
        print(line)
    print(text or "spend guard: nothing to change or report")
    if dry:
        return 0
    state = load_state()  # run() queued its alert in "unsent"; one that fails to send stays for the next run
    for entry in dict.fromkeys(state.get("unsent", [])):  # one at a time: a bad entry never blocks the rest
        if (text := for_phone(entry)) is None:
            ok = True  # routine fixes only: the journal has them, the phone never needs them
        else:
            try:  # non-zero, including hubwa's "dropped", is never delivered
                ok = subprocess.run(["timeout", "60", "hubwa", "send", text], check=False).returncode == 0
            except OSError:
                ok = False
        if ok:
            state["unsent"] = [u for u in state["unsent"] if u != entry]
            save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
