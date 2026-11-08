#!/usr/bin/env python3
"""Tests for the wake transport: hubmsg and hubwaked.

Written by Zeus, who did not write the code under test -- the same cross-assignment that
puts test_board.py in Prometheus's hands. Test the promised behaviour, not the
implementation that happens to exist.

Run:  python3 tests/test_messaging.py

These use throwaway tmux sessions as delivery targets. They never send keystrokes into a
real agent's pane, and never into one a human is attached to.
"""
import json, os, shlex, shutil, subprocess, sys, tempfile, time, uuid

HUB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HUBMSG, HUBWAKED = os.path.join(HUB, "hubmsg"), os.path.join(HUB, "hubwaked")
FAILURES, PASSES = [], []


def sh(cmd, env=None, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                          text=True, env=env, **kw)


def msg_id(r):
    """The id hubmsg reports, so an assertion can name THIS message rather than trusting
    that the shared bed contains only its own artefacts."""
    for tok in r.stdout.replace(")", " ").split():
        if tok.count("-") == 2 and tok[0].isdigit():
            return tok
    return None


def confirmed(r):
    """Careful: "confirmed" is a substring of "unconfirmed". Trust the exit status."""
    return r.returncode == 0 and "woke" in r.stdout


def check(name, cond, detail=""):
    (PASSES if cond else FAILURES).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n        {detail}" if detail and not cond else ""))


# What Codex 0.162.1 shows after /new: the empty composer, or in a git repo first the start-in picker.
COMPOSER = "› Ask Codex to do anything\n  ? for shortcuts"
PICKER = ("  Where should the new conversation run?\n"
          "› 1. Use current Git worktree  Keep using the current working directory\n"
          "  2. Create new Git worktree   Create a separate checkout of this repository in another directory\n"
          "  enter select · esc back")


class Bed:
    """A throwaway hub: its own HUB_DIR, board, wake dir and target panes."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="t12-")
        # Session names must be unique per run: two people running this suite at once
        # (which happens -- Zeus and Prometheus both run it) would otherwise create and
        # kill each other's panes and both see phantom failures. hubwaked validates the
        # target as ^hub-[a-z0-9_-]+$; the tag stays lowercase alphanumeric.
        self.tag = uuid.uuid4().hex[:6]
        json.dump({"next_id": 1, "tasks": []}, open(os.path.join(self.dir, "board.json"), "w"))
        # $HUB_DIR is the data directory only: hubmsg resolves the relay relative to its
        # own script path (T-016), so a throwaway board needs no copy of the executables.
        self.env = {**os.environ, "HUB_DIR": self.dir, "HUB_AGENT": "Zeus"}
        self.sessions = []

    def target(self, suffix, delay=0, slash_clears=False, preamble="", new_screen=COMPOSER):
        """A stand-in TUI.

        The pty echoes the typed wake and the loop consumes it like a TUI. hubwaked watches
        cursor movement rather than interpreting rendered pane history. With slash_clears,
        /clear and /new clear the screen as Claude and Codex do (spike T1), and /new then shows
        new_screen; without it a typed slash command stays on screen, like a Codex /new that never
        left the composer. The PICKER eats the next line, typed text and all, as the real one did.
        """
        sess = f"hub-{suffix}{self.tag}"
        out = os.path.join(self.dir, f"{suffix}.out")
        picker = f'[ -n "$p" ] && {{ p=; clear; printf "%s\\n" {shlex.quote(COMPOSER)}; continue; }}; '
        clears = (f'case "$l" in /clear) clear; continue ;; /new) clear; printf "%s\\n" {shlex.quote(new_screen)}; '
                  f'{"p=1; " if new_screen == PICKER else ""}continue ;; esac; ') if slash_clears else ""
        script = (f'printf "%s" {shlex.quote(preamble)}; sleep {delay}; while IFS= read -r l; do '
                  f'{picker}printf "%s\\n" "$l" >> {out}; {clears}printf "rendered: %s\\n" "$l"; done')
        sh(["tmux", "new-session", "-d", "-s", sess, "-c", self.dir, "bash", "-c", script])
        self.sessions.append(sess)
        return sess, out

    def busy_target(self, suffix, banner):
        """A stand-in TUI that shows `banner` (mid-turn, or a dialog) until the returned flag
        file exists, then reads lines like target(). Keys typed meanwhile wait in the tty and
        are read after the flag, so a wake typed during the banner shows up as an extra line."""
        sess = f"hub-{suffix}{self.tag}"
        out, flag = os.path.join(self.dir, f"{suffix}.out"), os.path.join(self.dir, f"{suffix}.idle")
        script = (f'printf "%s\\n" {shlex.quote(banner)}; while [ ! -e {flag} ]; do sleep 0.2; done; clear; '
                  f'while IFS= read -r l; do printf "%s\\n" "$l" >> {out}; printf "rendered: %s\\n" "$l"; done')
        # 200x50: the agy fixtures' geometry, so their footers do not wrap.
        sh(["tmux", "new-session", "-d", "-s", sess, "-x", "200", "-y", "50", "-c", self.dir, "bash", "-c", script])
        self.sessions.append(sess)
        time.sleep(1)
        return sess, out, flag

    def agent(self, suffix):
        """The board name hubmsg canonicalises a target to, which names wake/<Agent>.wake."""
        return f"{suffix.capitalize()}{self.tag}"

    def msg(self, target, text, *extra):
        return sh([HUBMSG, target, text, *extra], env=self.env)

    def receive(self, target, result):
        mid = msg_id(result)
        env = {**self.env, "HUB_AGENT": target}
        return sh([os.path.join(HUB, "board.py"), "receive", mid or "missing"], env=env)

    def cleanup(self):
        for s in self.sessions:
            sh(["tmux", "kill-session", "-t", s])


def wait_for(path, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return open(path).read()
        time.sleep(0.2)
    return open(path).read() if os.path.exists(path) else ""


def test_content_integrity(b):
    _, out = b.target("t12a")
    nasty = """quotes ' and " and `backticks` and $HOME and 100% and (parens) and [brackets] and emoji ✅🔥 and ünïcode"""
    r = b.msg(f"T12a{b.tag}", nasty)
    wake = wait_for(out)
    got = b.receive(f"T12a{b.tag}", r)
    check("content survives durable receive verbatim", nasty in got.stdout,
          f"sent: {nasty!r}\n        got: {got.stdout!r}\n        wake={wake!r}\n        {r.stdout}{r.stderr}")
    check("tmux carries only an idempotent receive instruction",
          "hub receive" in wake and nasty not in wake, repr(wake))
    check("reports confirmed", confirmed(r), r.stdout + r.stderr)


def test_newline_folding(b):
    _, out = b.target("t12b")
    r = b.msg(f"T12b{b.tag}", "line one\nline two\nline three")
    got = wait_for(out)
    lines = [l for l in got.splitlines() if l.strip()]
    check("multiline arrives as ONE submitted turn", len(lines) == 1, f"got {len(lines)} lines: {lines!r}")
    received = b.receive(f"T12b{b.tag}", r).stdout
    check("all content present after folding",
          all(w in received for w in ("line one", "line two", "line three")), repr(received))


def test_cold_target(b):
    """Regression: a slow-starting TUI must accept the idempotent receive wake."""
    _, out = b.target("t12c", delay=4)
    r = b.msg(f"T12c{b.tag}", "cold start message")
    wake = wait_for(out, timeout=25)
    got = b.receive(f"T12c{b.tag}", r).stdout
    check("cold/slow target still receives", "cold start message" in got, repr(wake) + repr(got) + r.stdout + r.stderr)
    check("cold target reports confirmed, not failed", confirmed(r), r.stdout + r.stderr)

    # The safety invariant that actually matters: a delivered message must never be left
    # in a state where a retry would duplicate it. Scoped to THIS message's id -- the bed
    # is shared, so checking merely that some marker exists would pass on a sibling's.
    mid = msg_id(r)
    marker = os.path.join(b.dir, "wake", "delivered", mid or "")
    arrived = "cold start message" in got
    check("a delivered message leaves a dedup marker (retry cannot duplicate it)",
          (not arrived) or (mid and os.path.exists(marker)),
          f"message arrived but no dedup marker for id={mid}; retrying the retained "
          f"request would deliver a second copy")


def test_asleep_vs_relay(b):
    """Conflating these two is the bug that made Prometheus look mute."""
    r = b.msg(f"T12nobody{b.tag}", "nobody home")
    check("absent target reports asleep", "asleep" in r.stdout, r.stdout + r.stderr)
    check("absent target still queues durably", "queued" in r.stdout, r.stdout)

    bad = {**b.env, "TMUX_TMPDIR": os.path.join(b.dir, "no-such-tmux")}
    os.makedirs(bad["TMUX_TMPDIR"], exist_ok=True)
    r2 = sh([HUBMSG, f"T12a{b.tag}", "sandbox routed"], env=bad)
    check("unreachable tmux routes to relay, not asleep",
          "relayed" in r2.stdout or "asleep" not in r2.stdout, r2.stdout + r2.stderr)


def test_relay_rejects_bad_targets(b):
    wake = os.path.join(b.dir, "wake")
    os.makedirs(wake, exist_ok=True)
    for label, sess in [("traversal", "../../etc/passwd"), ("non-hub session", "other-session"),
                        ("tmux target expr", "hub-x; kill-server")]:
        rid = f"probe-{uuid.uuid4().hex[:8]}"
        p = os.path.join(wake, f"{rid}.wake")
        with open(p, "w") as f:
            f.write(f"{sess}\n[hub:{rid}] payload\nversion=1\nid={rid}\nattempts=0\n")
        r = sh([HUBWAKED, "--deliver", p], env=b.env)
        check(f"relay rejects {label}", r.returncode != 0 and not os.path.exists(p),
              f"rc={r.returncode} still_present={os.path.exists(p)}")
    for label, agent, ids in [("v2 agent traversal", "../../etc", "1-1-1"), ("v2 glob id", "Probe", "*"),
                              ("v2 path id", "Probe", "1-1-1,../../x")]:
        p = os.path.join(wake, f"v2probe{uuid.uuid4().hex[:6]}.wake")
        with open(p, "w") as f:
            f.write(f"version=2\nagent={agent}\nids={ids}\ncreated=0\n")
        r = sh([HUBWAKED, "--deliver", p], env=b.env)
        check(f"relay rejects {label}", r.returncode != 0 and not os.path.exists(p),
              f"rc={r.returncode} still_present={os.path.exists(p)}")


def test_hyphenated_agent_name_is_woken(b):
    """board.py allows - and _ in agent names (e.g. a second hub's Prometheus-w), so the
    relay must accept the tmux session they map to rather than quarantine every wake."""
    _, out = b.target("t12h-w")
    r = b.msg(f"T12h-w{b.tag}", "hyphen ok")
    wait_for(out)
    got = b.receive(f"T12h-w{b.tag}", r).stdout
    check("agent with a hyphen in its name is woken", confirmed(r) and "hyphen ok" in got,
          r.stdout + r.stderr + got)


def test_asleep_request_returns_to_queue(b):
    """A request claimed for a target that is not running must go back to the live queue;
    left in inflight/, the scan loop never sees it again until a relay restart."""
    wake = os.path.join(b.dir, "wake")
    for sub in ("", "inflight", "failed", "delivered", "deferred"):
        os.makedirs(os.path.join(wake, sub), exist_ok=True)
    rid = f"sleepy-{uuid.uuid4().hex[:8]}"
    p = os.path.join(wake, f"{rid}.wake")
    with open(p, "w") as f:
        f.write(f"hub-sleepy{b.tag}\n[hub wake:{rid}] Run exactly: hub receive {rid}\n"
                f"version=1\nid={rid}\nattempts=0\n")
    r = sh([HUBWAKED, "--deliver", p], env=b.env)
    stuck = [n for n in os.listdir(os.path.join(wake, "inflight")) if rid in n]
    check("request for a sleeping target returns to the live queue",
          r.returncode == 2 and os.path.exists(p) and not stuck,
          f"rc={r.returncode} queued={os.path.exists(p)} inflight={stuck}")
    if os.path.exists(p):
        os.remove(p)


def test_dedup(b):
    sess, out = b.target("t12d")
    wake = os.path.join(b.dir, "wake"); os.makedirs(wake, exist_ok=True)
    rid = f"dedup-{uuid.uuid4().hex[:8]}"

    def request():
        p = os.path.join(wake, f"{rid}.wake")
        with open(p, "w") as f:
            f.write(f"{sess}\n[hub:{rid}] dedup payload\nversion=1\nid={rid}\nattempts=0\n")
        return p

    sh([HUBWAKED, "--deliver", request()], env=b.env)
    sh([HUBWAKED, "--deliver", request()], env=b.env)
    got = wait_for(out)
    check("same message id delivers exactly once", got.count("dedup payload") == 1,
          f"delivered {got.count('dedup payload')} times")


def test_stale_wakes_are_dropped(b):
    """Dry runs #3 and #4: dozens of wakes from earlier days, whose messages had long been
    read, were replayed into a live session and one landed in a question box. A wake whose
    message was already received, or that is hours old, is dropped; the inbox keeps the
    message either way."""
    wake = os.path.join(b.dir, "wake"); os.makedirs(wake, exist_ok=True)

    def deliver(sess, rid):
        p = os.path.join(wake, f"{rid}.wake")
        with open(p, "w") as f:
            f.write(f"{sess}\n[hub:{rid}] stale payload {rid}\nversion=1\nid={rid}\nattempts=0\n")
        return sh([HUBWAKED, "--deliver", p], env=b.env)

    sess, out = b.target("t12r")
    rid = f"{time.time_ns()}-1-1"
    agent = sess[len("hub-"):].capitalize()
    receipts = os.path.join(b.dir, "inbox", ".received", agent)
    os.makedirs(receipts, exist_ok=True)
    open(os.path.join(receipts, rid), "w").close()
    deliver(sess, rid)
    time.sleep(2)
    got = open(out).read() if os.path.exists(out) else ""
    check("a wake for an already-received message is not typed", rid not in got, got[-200:])

    sess2, out2 = b.target("t12o")
    old = f"{time.time_ns() - 7 * 3600 * 10**9}-1-2"
    deliver(sess2, old)
    time.sleep(2)
    got2 = open(out2).read() if os.path.exists(out2) else ""
    check("a wake older than 6 hours is not typed", old not in got2, got2[-200:])
    logf = os.path.join(b.dir, "wake", "hubwaked.log")
    text = open(logf).read() if os.path.exists(logf) else ""
    check("both drops are logged", "already received" in text and "older than" in text, text[-300:])

    sess3, out3 = b.target("t12f")
    fresh = f"{time.time_ns()}-1-3"
    deliver(sess3, fresh)
    check("a fresh, unread wake is still delivered", fresh in wait_for(out3), "")


def test_relay_health_and_recovery(b):
    """T-009. A relay that dies silently turns every wake into a lost message, so the
    health signal has to be trustworthy and queued work has to survive a restart."""
    def status():
        return sh([HUBWAKED, "--status"], env=b.env).stdout

    check("status reports down when no daemon runs", "relay=down" in status(), status())

    daemon = subprocess.Popen([HUBWAKED], env=b.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        check("status reports running once started", "relay=running" in status(), status())

        second = sh([HUBWAKED], env=b.env, timeout=10)
        check("a second daemon refuses to start", second.returncode != 0,
              f"rc={second.returncode} {second.stdout}{second.stderr}")
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)
    time.sleep(1)
    check("status reports down again after shutdown", "relay=down" in status(), status())

    # Stale recovery: a request queued while the relay is down must be delivered when it
    # comes back, not ignored because it predates the daemon.
    sess, out = b.target("t12e")
    wake = os.path.join(b.dir, "wake"); os.makedirs(wake, exist_ok=True)
    rid = f"stale-{uuid.uuid4().hex[:8]}"
    with open(os.path.join(wake, f"{rid}.wake"), "w") as f:
        f.write(f"{sess}\n[hub:{rid}] queued while relay was down\nversion=1\nid={rid}\nattempts=0\n")

    daemon = subprocess.Popen([HUBWAKED], env=b.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        got = wait_for(out, timeout=20)
        check("request queued while down is delivered on restart",
              "queued while relay was down" in got, repr(got))
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)


def test_stale_code_and_resolved_error_status(b):
    status_dir = tempfile.mkdtemp(prefix="t12-status-")
    json.dump({"next_id": 1, "tasks": []}, open(os.path.join(status_dir, "board.json"), "w"))
    status_env = {**b.env, "HUB_DIR": status_dir}
    copied = os.path.join(status_dir, "hubwaked-copy")
    shutil.copy2(HUBWAKED, copied)
    daemon = subprocess.Popen([copied], env=status_env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        running = sh([copied, "--status"], env=status_env)
        check("current relay code reports running", "relay=running" in running.stdout, running.stdout)
        with open(copied, "a") as f:
            f.write("\n# simulated code upgrade\n")
        stale = sh([copied, "--status"], env=status_env)
        check("live old-code relay reports stale", stale.returncode != 0 and "relay=stale" in stale.stdout,
              stale.stdout + stale.stderr)
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)

    log = os.path.join(status_dir, "wake", "hubwaked.log")
    with open(log, "a") as f:
        f.write("old failed error that has been resolved\n")
    resolved = sh([copied, "--status"], env=status_env)
    check("resolved historical error is not reported active", "last_error:" not in resolved.stdout,
          resolved.stdout)


def test_attached_pane_defers_without_collision(b):
    sess, out = b.target("t12g")
    daemon = subprocess.Popen([HUBWAKED], env=b.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = subprocess.Popen(
        ["script", "-qec", f"tmux attach-session -t {sess}", "/dev/null"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "TERM": "xterm"},
    )
    try:
        end = time.time() + 5
        while time.time() < end:
            attached = sh(["tmux", "display-message", "-p", "-t", sess, "#{session_attached}"])
            if attached.stdout.strip() not in ("", "0"):
                break
            time.sleep(0.1)
        r = b.msg(f"T12g{b.tag}", "must not collide")
        time.sleep(1)
        before = open(out).read() if os.path.exists(out) else ""
        check("attached pane is deferred without keystrokes", "deferred" in r.stdout and before == "",
              r.stdout + r.stderr + repr(before))
        sh(["tmux", "detach-client", "-s", sess])
        wake = wait_for(out, timeout=20)
        received = b.receive(f"T12g{b.tag}", r)
        check("deferred wake delivers after detach", "hub receive" in wake and "must not collide" in received.stdout,
              repr(wake) + received.stdout + received.stderr)
    finally:
        client.terminate()
        try:
            client.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client.kill()
        daemon.terminate()
        daemon.wait(timeout=10)


def test_single_delivery_with_daemon_running(b):
    """Production configuration: direct caller and daemon must not double-handle."""
    sess, out = b.target("t12f")
    daemon = subprocess.Popen([HUBWAKED], env=b.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        r = b.msg(f"T12f{b.tag}", "exactly once please")
        got = wait_for(out, timeout=20)
        time.sleep(3)
        got = open(out).read() if os.path.exists(out) else ""
        mid = msg_id(r)
        n = got.count("hub receive --pending")
        check("one hubmsg delivers exactly one turn with the daemon running", n == 1,
              f"delivered {n} times:\n        {got!r}\n        {r.stdout}")

        received = b.receive(f"T12f{b.tag}", r)
        check("single receive reveals durable payload", "exactly once please" in received.stdout,
              received.stdout + received.stderr)
        logf = os.path.join(b.dir, "wake", "hubwaked.log")
        handlers = sum(1 for l in open(logf) if mid and mid in l and "delivered" in l) \
            if os.path.exists(logf) else 0
        check("exactly one handler claims the request", handlers <= 1,
              f"{handlers} handlers logged a delivery for id={mid}")
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)


def test_modal_dialog_is_never_confirmed_by_a_wake(b):
    """A wake ends in Enter, and Enter CONFIRMS whatever dialog is on screen.

    Observed live: an agent sat on "Yes, and don't ask again for commands that start with
    `sleep 2`" while detached. A wake delivered then would have granted that permission on
    its behalf and reported success. The attached-pane guard does not cover it -- a
    DETACHED agent parked on a dialog is the more common and more dangerous case.
    """
    sess = f"hub-modal{b.tag}"
    approved = os.path.join(b.dir, "approved.txt")
    script = os.path.join(b.dir, "dialog.sh")
    with open(script, "w") as f:
        f.write(
            'echo "Do you want to proceed?"\n'
            'echo "  1. Yes"\n'
            'echo "  2. Yes, and don\'t ask again (p)"\n'
            'echo "  3. No, and tell Codex what to do differently (esc)"\n'
            'echo "Press enter to confirm or esc to cancel"\n'
            f'read -r _ && echo APPROVED > {approved}\n'
            'sleep 120\n'
        )
    sh(["tmux", "new-session", "-d", "-s", sess, "-c", b.dir, "bash", script])
    b.sessions.append(sess)
    time.sleep(1)

    daemon = subprocess.Popen([HUBWAKED], env=b.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sh([HUBMSG, f"Modal{b.tag}", "wake arriving during a dialog"], env=b.env)
        time.sleep(6)
        check("a wake never confirms a dialog it lands on", not os.path.exists(approved),
              "the dialog was CONFIRMED by the wake -- this grants permissions on the "
              "agent's behalf")
        logf = os.path.join(b.dir, "wake", "hubwaked.log")
        text = open(logf).read() if os.path.exists(logf) else ""
        check("the wake is deferred rather than dropped", "deferred" in text,
              f"expected a deferral in the log, got:\n        {text[-300:]!r}")
    finally:
        daemon.terminate()
        daemon.wait(timeout=10)


def test_codex_menu_defers_the_wake(b):
    """Dry run #4: Prometheus's Codex sat on its "Agent command center" task list; a wake typed
    there moved the cursor (so it looked delivered) and was lost. It must wait instead."""
    sess = f"hub-menu{b.tag}"
    typed = os.path.join(b.dir, "menu-typed.txt")
    script = os.path.join(b.dir, "menu.sh")
    with open(script, "w") as f:
        f.write('echo "  Agent command center  Group: Project"\n'
                'echo "  ? help  esc back  up/down move  enter open  n new"\n'
                f'read -r l && echo "$l" > {typed}\n'
                'sleep 120\n')
    sh(["tmux", "new-session", "-d", "-s", sess, "-c", b.dir, "bash", script])
    b.sessions.append(sess)
    time.sleep(1)
    daemon = subprocess.Popen([HUBWAKED], env=b.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        sh([HUBMSG, f"Menu{b.tag}", "wake arriving on a menu"], env=b.env)
        time.sleep(6)
        check("a wake is not typed into Codex's command-center menu", not os.path.exists(typed), "")
        logf = os.path.join(b.dir, "wake", "hubwaked.log")
        text = open(logf).read() if os.path.exists(logf) else ""
        check("the menu wake is deferred", "deferred" in text, text[-300:])
    finally:
        daemon.terminate()


def test_wake_into_trust_prompt_is_not_confirmed(b):
    """Dry run 2026-10-12: Codex opened on "Trust this folder?", the wake's keys backed it
    into the Agent Command Center, the cursor moved, and hubmsg said "confirmed"."""
    sess = f"hub-trust{b.tag}"
    script = os.path.join(b.dir, "trust.sh")
    with open(script, "w") as f:
        f.write('read -r _; clear\n'
                'echo "  Trust this folder?"\n'
                'echo "  1. Trust and continue"\n'
                'echo "  2. Back to Agent Command Center"\n'
                'sleep 120\n')
    sh(["tmux", "new-session", "-d", "-s", sess, "-c", b.dir, "bash", script])
    b.sessions.append(sess)
    time.sleep(1)
    wake = os.path.join(b.dir, "wake"); os.makedirs(wake, exist_ok=True)
    rid = f"{time.time_ns()}-9-9"
    p = os.path.join(wake, f"{rid}.wake")
    with open(p, "w") as f:
        f.write(f"{sess}\n[hub:{rid}] hub receive {rid}\nversion=1\nid={rid}\nattempts=0\n")
    r = sh([HUBWAKED, "--deliver", p], env=b.env)
    check("a wake that lands on the trust prompt is unconfirmed", r.returncode == 5,
          f"rc={r.returncode} {r.stdout}{r.stderr}")
    check("it stays queued for retry, with no delivered receipt",
          os.path.exists(p) and not os.path.exists(os.path.join(wake, "delivered", rid)), "")


WAKE_LINE = "[hub wake] Run exactly: hub receive --pending"


def lines_of(path):
    return [l for l in open(path).read().splitlines() if l.strip()] if os.path.exists(path) else []


def test_busy_pane_gets_no_keys_and_messages_coalesce(b):
    """Agent OS §5.3-4: nothing is typed while a turn runs; two messages make one wake."""
    sess, out, idle = b.busy_target("t8b", "  Working (5s - esc to interrupt)")
    agent = b.agent("t8b")
    r1, r2 = b.msg(agent, "first while busy"), b.msg(agent, "second while busy")
    check("hubmsg to a busy pane reports busy, exit 0",
          all(r.returncode == 0 and "busy" in r.stdout for r in (r1, r2)), r1.stdout + r2.stdout + r2.stderr)
    req = os.path.join(b.dir, "wake", f"{agent}.wake")
    text = open(req).read() if os.path.exists(req) else ""
    ids = [l[4:].split(",") for l in text.splitlines() if l.startswith("ids=")]
    check("two hubmsgs leave one wake file listing both ids",
          ids == [[msg_id(r1), msg_id(r2)]] and "version=2" in text, repr(text))
    open(idle, "w").close()
    time.sleep(1)
    check("the busy pane received no keys", lines_of(out) == [], repr(lines_of(out)))
    r = sh([HUBWAKED, "--deliver", req], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("once idle, the pane gets exactly one receive line",
          r.returncode == 0 and lines_of(out) == [WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r}")
    got = sh([os.path.join(HUB, "board.py"), "receive", "--pending"], env={**b.env, "HUB_AGENT": agent}).stdout
    check("receive --pending reveals both messages", "first while busy" in got and "second while busy" in got, got)
    # Received by the Stop hook before the relay got to it: no wake was ever typed for this id.
    mid = f"{time.time_ns()}-7-7"
    agent_env = {**b.env, "HUB_AGENT": agent}
    sh([os.path.join(HUB, "board.py"), "notify", agent, "handled at turn end", "--message-id", mid], env=b.env)
    sh([os.path.join(HUB, "board.py"), "receive", "--pending"], env=agent_env)
    with open(req, "w") as f:
        f.write(f"version=2\nagent={agent}\nids={mid}\ncreated={int(time.time())}\n")
    r = sh([HUBWAKED, "--deliver", req], env=b.env)
    time.sleep(1)
    logf = os.path.join(b.dir, "wake", "hubwaked.log")
    log = open(logf).read() if os.path.exists(logf) else ""
    check("a fully received request is dropped untyped",
          r.returncode == 0 and not os.path.exists(req) and lines_of(out) == [WAKE_LINE]
          and f"dropped id={agent} session=hub-t8b{b.tag} (already received)" in log, repr(lines_of(out)) + log[-300:])
    check("the busy deferral is logged", "busy" in log, log[-300:])


def test_busy_heartbeat_defers_the_wake(b):
    """A turn between tool calls may not show `esc to interrupt`; the heartbeat still says busy."""
    sess, out = b.target("t8h")
    agent = b.agent("t8h")
    state = os.path.join(b.dir, "state"); os.makedirs(state, exist_ok=True)
    beat = os.path.join(state, f"{agent}.json")
    with open(beat, "w") as f:
        json.dump({"at": "2026-10-18T10:00:00+00:00", "event": "PostToolUse", "tool": "Bash"}, f)
    r = b.msg(agent, "while a tool runs")
    time.sleep(2)
    check("a PostToolUse heartbeat defers the wake untyped", "busy" in r.stdout and lines_of(out) == [],
          r.stdout + repr(lines_of(out)))
    with open(beat, "w") as f:
        json.dump({"at": "2026-10-18T10:00:05+00:00", "event": "Stop", "tool": None}, f)
    sh([HUBWAKED, "--deliver", os.path.join(b.dir, "wake", f"{agent}.wake")], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("after Stop the wake is typed once", lines_of(out) == [WAKE_LINE], repr(lines_of(out)))


def test_codex_launch_dialogs_defer_the_wake(b):
    """Spike T1: Codex's "Update available" runs npm install -g on Enter; "Hooks need review"
    trusts hooks. Claude's select dialogs end "Esc to cancel", capitalised. None matched the old
    MODAL_MARKERS."""
    for suffix, banner in (("t8u", "  Update available! 0.162.1 -> 0.163.0   enter continue · esc skip"),
                           ("t8k", "  Hooks need review: 2 hooks are new or changed"),
                           ("t8c", "  Teach auto mode about your environment? Enter to confirm · Esc to cancel"),
                           ("t8p", PICKER)):
        sess, out, idle = b.busy_target(suffix, banner)
        b.msg(b.agent(suffix), "wake arriving on a launch dialog")
        time.sleep(2)
        open(idle, "w").close()
        time.sleep(1)
        check(f"no keys typed into {banner.split(':')[0].split('!')[0].strip()!r}", lines_of(out) == [],
              repr(lines_of(out)))


def test_quoted_markers_above_the_status_rows_do_not_defer(b):
    """Hermes, T-532 review: transcript text that quotes "esc to interrupt" or a dialog footer is not a
    busy status line or a dialog. Only the bottom rows count: 3 for the status line, 12 for dialogs."""
    filler = "".join(f"transcript line {n}\n" for n in range(15))
    for suffix, quote in (("q534i", "the pane shows `esc to interrupt` while a turn runs"),
                          ("q534d", "a dialog reads: Do you want to proceed? Esc to cancel")):
        b.target(suffix, preamble=f"{quote}\n{filler}")
        time.sleep(0.5)
        r = b.msg(b.agent(suffix), "quoted marker, idle pane")
        out = os.path.join(b.dir, f"{suffix}.out")
        wait_for(out)
        time.sleep(1)
        check(f"a quote above the status rows is not {'busy' if suffix.endswith('i') else 'a dialog'}",
              confirmed(r) and lines_of(out) == [WAKE_LINE], r.stdout + r.stderr + repr(lines_of(out)))


def reset_request(b, agent, kind, created=None):
    """The dispatcher's reset request (dispatch.py reset_wake): six lines, version=2 ... created=."""
    wake = os.path.join(b.dir, "wake"); os.makedirs(wake, exist_ok=True)
    req = os.path.join(wake, f"{agent}.wake")
    with open(req, "w") as f:
        f.write(f"version=2\nagent={agent}\nids={time.time_ns()}-534\nreset=1\nkind={kind}\n"
                f"created={int(time.time()) if created is None else created}\n")
    return req


def relay_log(b):
    p = os.path.join(b.dir, "wake", "hubwaked.log")
    return open(p).read() if os.path.exists(p) else ""


def test_reset_request_types_the_reset_then_the_line(b):
    """Agent OS §1 and spike T1: /clear for Claude, /new for Codex, then about 3 s, then the line."""
    for suffix, kind, cmd in (("r534c", "claude", "/clear"), ("r534x", "codex", "/new"), ("r557a", "agy", "/clear")):
        b.target(suffix, slash_clears=True)
        agent = b.agent(suffix)
        out = os.path.join(b.dir, f"{suffix}.out")
        start = time.time()
        r = sh([HUBWAKED, "--deliver", reset_request(b, agent, kind)], env=b.env)
        took = time.time() - start
        wait_for(out)
        time.sleep(1)
        check(f"{kind}: a reset request types {cmd}, then the receive line",
              r.returncode == 0 and lines_of(out) == [cmd, WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r} {r.stderr}")
        check(f"{kind}: the line waits for the fresh session (>= 3 s after the reset)", took >= 3.5, f"{took:.1f}s")
        check(f"{kind}: logged as reset delivered", f"reset delivered id={agent}" in relay_log(b), relay_log(b)[-400:])


def test_plain_wake_clears_leftover_input_first(b):
    """Live rollout: a relay killed mid-type left "[hub wake" in Hermes's composer; the next wake would
    have submitted "<leftover>[hub wake] ..." as one garbled prompt."""
    sess, out = b.target("p534u")
    time.sleep(0.5)
    sh(["tmux", "send-keys", "-t", sess, "-l", "[hub wake"])
    time.sleep(0.3)
    r = b.msg(b.agent("p534u"), "wake onto leftover input")
    wait_for(out)
    time.sleep(1)
    check("leftover input is cleared, so the pane receives only the receive line",
          confirmed(r) and lines_of(out) == [WAKE_LINE], r.stdout + r.stderr + repr(lines_of(out)))


def test_reset_clears_a_draft_first(b):
    """Hermes, T-534 review: a draft left in the composer would make "<draft>/clear", submitted as a prompt."""
    sess, out = b.target("r534d", slash_clears=True)
    agent = b.agent("r534d")
    time.sleep(0.5)
    sh(["tmux", "send-keys", "-t", sess, "-l", "half-typed draft"])
    time.sleep(0.3)
    r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "claude")], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("a draft is cleared, so /clear is the only input, then the line",
          r.returncode == 0 and lines_of(out) == ["/clear", WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r}")


def test_reset_that_stays_in_the_composer_falls_back(b):
    """Spike T1: a Codex /new can stay in the input box, and a prompt typed onto it can be lost."""
    b.target("r534s")
    agent = b.agent("r534s")
    out = os.path.join(b.dir, "r534s.out")
    r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "codex")], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("a /new left on screen is cleared and followed by a plain wake",
          r.returncode == 0 and lines_of(out) == ["/new", WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r}")
    check("the fallback is logged as a downgrade", "reset downgraded: /new not submitted" in relay_log(b),
          relay_log(b)[-400:])


def test_reset_answers_the_codex_start_in_picker(b):
    """Live, 2026-10-18 14:54Z: /new in a git repo opened "Where should the new conversation run?" and the
    receive line typed into it was lost. Enter takes the preselected current worktree, then the line."""
    b.target("r535p", slash_clears=True, new_screen=PICKER)
    agent = b.agent("r535p")
    out = os.path.join(b.dir, "r535p.out")
    r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "codex")], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("the picker is answered and the receive line reaches the fresh session",
          r.returncode == 0 and lines_of(out) == ["/new", WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r}")
    check("logged as reset delivered", f"reset delivered id={agent}" in relay_log(b), relay_log(b)[-400:])


def test_reset_onto_an_unknown_screen_falls_back(b):
    """Anything after /new but the empty composer: Escape back and send the plain wake, logged as a downgrade."""
    b.target("r535u", slash_clears=True, new_screen="  Something Codex has not shown before")
    agent = b.agent("r535u")
    out = os.path.join(b.dir, "r535u.out")
    r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "codex")], env=b.env)
    wait_for(out)
    time.sleep(1)
    check("an unknown screen after /new gets the plain wake",
          r.returncode == 0 and lines_of(out) == ["/new", WAKE_LINE], f"rc={r.returncode} {lines_of(out)!r}")
    check("logged as a downgrade", "reset downgraded: /new did not reach an empty composer" in relay_log(b),
          relay_log(b)[-400:])


def test_reset_onto_a_quoted_option_line_presses_no_enter(b):
    """Zeus, review of 6123a50: an old transcript quoting the picker's option line, with no picker title, is not the
    picker. No Enter (the fake records it as an empty line), Escape back, plain wake."""
    b.target("r535q", slash_clears=True,
             new_screen="• Earlier the pane read: › 1. Use current Git worktree  Keep using the current working directory")
    agent = b.agent("r535q")
    out = os.path.join(b.dir, "r535q.out")
    r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "codex")], env=b.env)
    wait_for(out)
    time.sleep(1)
    raw = open(out).read().splitlines() if os.path.exists(out) else []
    check("a quoted option line gets no Enter, only /new and the plain wake",
          r.returncode == 0 and raw == ["/new", WAKE_LINE], f"rc={r.returncode} {raw!r}")
    check("logged as a downgrade", "reset downgraded: /new did not reach an empty composer" in relay_log(b),
          relay_log(b)[-400:])


AGY = os.path.join(HUB, "tests", "fixtures", "agy")


def agy_screen(name):
    """A live agy 1.4.2 pane (T-556), without the empty rows below it."""
    return open(os.path.join(AGY, name)).read().rstrip()


def agy_state(b, agent, state, age=0):
    """What agy's statusLine command leaves in state/<Name>.agy.json; age backdates it."""
    d = os.path.join(b.dir, "state"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{agent}.agy.json")
    with open(p, "w") as f:
        json.dump({"agent_state": state, "at": "2026-10-19T12:40:00+00:00"}, f)
    os.utime(p, (time.time() - age,) * 2)


def test_agy_busy_pane_is_busy_not_a_dialog(b):
    """T-556: busy agy's footer reads `esc to cancel`, which is also a dialog marker. The statusLine file is an hour
    old, so only the pane says busy."""
    sess, out, idle = b.busy_target("a557b", agy_screen("busy-generating.txt"))
    agent = b.agent("a557b")
    agy_state(b, agent, "working", age=3600)
    r = b.msg(agent, "while agy generates")
    open(idle, "w").close()
    time.sleep(1)
    log = relay_log(b)
    check("agy busy pane: hubmsg reports busy", r.returncode == 0 and "busy" in r.stdout, r.stdout + r.stderr)
    check("agy busy pane: logged busy, not as a dialog",
          f"busy id={agent}" in log and f"deferred id={agent}" not in log, log[-400:])
    check("agy busy pane: no keys typed", lines_of(out) == [], repr(lines_of(out)))


def test_agy_dialogs_defer(b):
    """T-556: Enter on an agy dialog takes option 1, a Yes. Each one defers, logged as a dialog although the footer
    also reads `esc to cancel` and the statusLine says tool_use."""
    for suffix, name in (("a557r", "dialog-run-command.txt"), ("a557f", "dialog-create-file.txt"),
                         ("a557t", "dialog-trust-folder.txt")):
        sess, out, idle = b.busy_target(suffix, agy_screen(name))
        agent = b.agent(suffix)
        agy_state(b, agent, "tool_use")
        b.msg(agent, "wake arriving on an agy dialog")
        open(idle, "w").close()
        time.sleep(1)
        check(f"agy {name}: deferred as a dialog, no keys typed",
              f"deferred id={agent} session={sess} (confirmation dialog" in relay_log(b) and lines_of(out) == [],
              relay_log(b)[-300:] + repr(lines_of(out)))


def test_agy_idle_state_outranks_a_stale_turn_heartbeat(b):
    """T-556: denying an agy dialog ends the turn with no Stop hook, so the heartbeat still reads UserPromptSubmit.
    The statusLine's idle is the truth, and the pane is an empty composer: the wake goes in."""
    sess, out = b.target("a557i", preamble=agy_screen("after-edit-denied.txt") + "\n")
    agent = b.agent("a557i")
    agy_state(b, agent, "idle")
    with open(os.path.join(b.dir, "state", f"{agent}.json"), "w") as f:
        json.dump({"at": "2026-10-19T12:44:00+00:00", "event": "UserPromptSubmit", "tool": None}, f)
    r = b.msg(agent, "after a denied dialog")
    wait_for(out)
    time.sleep(1)
    check("agy idle statusLine outranks a mid-turn heartbeat", confirmed(r) and lines_of(out) == [WAKE_LINE],
          r.stdout + r.stderr + repr(lines_of(out)))


def test_plain_wake_pauses_before_enter(b):
    """Gemini-family TUIs (agy) can take an Enter that follows typed text within ~30 ms as a newline. The fake reads
    key by key and records the time of the last typed key and of Enter."""
    sess, out = f"hub-a557p{b.tag}", os.path.join(b.dir, "a557p.out")
    script = (f'stty -icanon; while IFS= read -r -N 1 c; do t=$EPOCHREALTIME; '
              f'[ "$c" = $\'\\n\' ] && echo "$p $t" >> {out}; p=$t; done')
    sh(["tmux", "new-session", "-d", "-s", sess, "-c", b.dir, "bash", "-c", script])
    b.sessions.append(sess)
    time.sleep(0.5)
    r = b.msg(b.agent("a557p"), "pause before Enter")
    wait_for(out)
    gaps = [float(t) - float(p) for p, t in (l.split() for l in lines_of(out))]
    check("a plain wake pauses >= 0.2 s between the typed line and Enter", confirmed(r) and gaps and min(gaps) >= 0.2,
          f"gaps={gaps} {r.stdout}{r.stderr}")


def test_reset_downgrades_to_the_plain_line(b):
    """Agent OS §1: any guard turns a reset into the plain receive line, and a reset is never retried."""
    state = os.path.join(b.dir, "state"); os.makedirs(state, exist_ok=True)
    board = os.path.join(b.dir, "board.json")
    saved = open(board).read()

    def plain_only(suffix, why, setup, req_created=None):
        b.target(suffix, slash_clears=True)
        agent, out = b.agent(suffix), os.path.join(b.dir, f"{suffix}.out")
        setup(agent)
        try:
            r = sh([HUBWAKED, "--deliver", reset_request(b, agent, "claude", req_created)], env=b.env)
        finally:
            open(board, "w").write(saved)
        wait_for(out)
        time.sleep(1)
        check(f"{why}: the line only, no /clear", r.returncode == 0 and lines_of(out) == [WAKE_LINE],
              f"rc={r.returncode} {lines_of(out)!r}")
        check(f"{why}: logged as reset downgraded", f"reset downgraded: {why} id={agent}" in relay_log(b),
              relay_log(b)[-400:])

    def beat(agent):
        with open(os.path.join(state, f"{agent}.json"), "w") as f:
            json.dump({"at": "2026-10-18T12:00:00+00:00", "event": "Stop", "tool": None}, f)
    plain_only("r534h", "heartbeat newer than the offer", beat, req_created=int(time.time()) - 30)

    for suffix, status in (("r534k", "claimed"), ("r534l", "blocked")):
        def holds(agent, status=status):
            json.dump({"next_id": 2, "tasks": [{"id": "T-001", "title": "held", "status": status, "owner": agent,
                                                 "notes": [], "deps": []}]}, open(board, "w"))
        plain_only(suffix, f"holds a {status} task", holds)

    # Attached, a dialog, or mid-turn: the request is deferred, and the retry is a plain wake.
    for suffix, banner, why in (("r534m", "  Do you want to proceed? Press enter to confirm", "confirmation dialog"),
                                ("r534w", "  Working (5s - esc to interrupt)", "busy")):
        sess, out, idle = b.busy_target(suffix, banner)
        agent = b.agent(suffix)
        req = reset_request(b, agent, "claude")
        r = sh([HUBWAKED, "--deliver", req], env=b.env)
        text = open(req).read() if os.path.exists(req) else ""
        open(idle, "w").close()
        time.sleep(1)
        r2 = sh([HUBWAKED, "--deliver", req], env=b.env)
        wait_for(out)
        time.sleep(1)
        check(f"{why}: deferred, then the line only", r.returncode in (4, 6) and r2.returncode == 0
              and "reset=" not in text and lines_of(out) == [WAKE_LINE],
              f"rc={r.returncode},{r2.returncode} {text!r} {lines_of(out)!r}")
        check(f"{why}: logged as reset downgraded", f"reset downgraded: {why} id={agent}" in relay_log(b),
              relay_log(b)[-400:])

    sess, out = b.target("r534a", slash_clears=True)
    agent = b.agent("r534a")
    client = subprocess.Popen(["script", "-qec", f"tmux attach-session -t {sess}", "/dev/null"],
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env={**os.environ, "TERM": "xterm"})
    try:
        end = time.time() + 5
        while time.time() < end and sh(["tmux", "display-message", "-p", "-t", sess,
                                        "#{session_attached}"]).stdout.strip() in ("", "0"):
            time.sleep(0.1)
        req = reset_request(b, agent, "claude")
        r = sh([HUBWAKED, "--deliver", req], env=b.env)
        text = open(req).read() if os.path.exists(req) else ""
        sh(["tmux", "detach-client", "-s", sess])
        time.sleep(0.5)
        r2 = sh([HUBWAKED, "--deliver", req], env=b.env)
        wait_for(out)
        time.sleep(1)
        check("attached: deferred, then the line only", r.returncode == 4 and r2.returncode == 0
              and "reset=" not in text and lines_of(out) == [WAKE_LINE],
              f"rc={r.returncode},{r2.returncode} {text!r} {lines_of(out)!r}")
        check("attached: logged as reset downgraded", f"reset downgraded: attached id={agent}" in relay_log(b),
              relay_log(b)[-400:])
    finally:
        client.terminate()
        try:
            client.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client.kill()


def main():
    # A private tmux server (its own socket directory, the effect of -L): no pane this suite makes or
    # types into can be a live agent's, whatever its hub-* name.
    os.environ.pop("TMUX", None)
    os.environ["TMUX_TMPDIR"] = tempfile.mkdtemp(prefix="hubtest-tmux-")
    # Every test drives tmux. Where it cannot start a server (no sockets: the Codex sandbox),
    # each would only wait out its timeouts and fail; skip instead, saying so.
    # The probe session lives until kill-server below. A probe that exited at once (`true`) let the
    # server shut down under the first test's new-session: "server exited unexpectedly", no session,
    # and test_content_integrity failed under make check's parallel load (2026-11-02).
    probe = shutil.which("tmux") and sh(["tmux", "new-session", "-d", "-s", f"hub-probe-{uuid.uuid4().hex[:6]}", "sleep 86400"])
    if not probe or probe.returncode:
        err = (probe.stderr.strip() if probe else "") or "no tmux"
        if probe and "duplicate session" in err:  # a name clash is a bug, never a reason to skip
            print(f"FAIL: tmux probe: {err}"); return 1
        print(f"skipped: tmux cannot start a server here ({err}; e.g. the Codex sandbox)")
        return 0
    b = Bed()
    print(f"bed: {b.dir}\n")
    try:
        for t in (test_content_integrity, test_newline_folding, test_cold_target,
                  test_asleep_vs_relay, test_relay_rejects_bad_targets,
                  test_hyphenated_agent_name_is_woken, test_asleep_request_returns_to_queue,
                  test_dedup, test_stale_wakes_are_dropped,
                  test_relay_health_and_recovery, test_stale_code_and_resolved_error_status,
                  test_attached_pane_defers_without_collision,
                  test_single_delivery_with_daemon_running,
                  test_modal_dialog_is_never_confirmed_by_a_wake,
                  test_codex_menu_defers_the_wake,
                  test_wake_into_trust_prompt_is_not_confirmed,
                  test_busy_pane_gets_no_keys_and_messages_coalesce,
                  test_busy_heartbeat_defers_the_wake,
                  test_codex_launch_dialogs_defer_the_wake,
                  test_quoted_markers_above_the_status_rows_do_not_defer,
                  test_reset_request_types_the_reset_then_the_line,
                  test_plain_wake_clears_leftover_input_first,
                  test_reset_clears_a_draft_first,
                  test_reset_that_stays_in_the_composer_falls_back,
                  test_reset_answers_the_codex_start_in_picker,
                  test_reset_onto_an_unknown_screen_falls_back,
                  test_reset_onto_a_quoted_option_line_presses_no_enter,
                  test_agy_busy_pane_is_busy_not_a_dialog,
                  test_agy_dialogs_defer,
                  test_agy_idle_state_outranks_a_stale_turn_heartbeat,
                  test_plain_wake_pauses_before_enter,
                  test_reset_downgrades_to_the_plain_line):
            print(f"{t.__name__}:")
            try:
                t(b)
            except Exception as e:
                check(f"{t.__name__} raised", False, repr(e))
            print()
    finally:
        b.cleanup()
        sh(["tmux", "kill-server"])
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if FAILURES:
        print("failed: " + ", ".join(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
