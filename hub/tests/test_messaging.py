#!/usr/bin/env python3
"""Tests for the wake transport: hubmsg and hubwaked.

Written by Zeus, who did not write the code under test -- the same cross-assignment that
puts test_board.py in Prometheus's hands. Test the promised behaviour, not the
implementation that happens to exist.

Run:  python3 tests/test_messaging.py

These use throwaway tmux sessions as delivery targets. They never send keystrokes into a
real agent's pane, and never into one a human is attached to.
"""
import json, os, shutil, subprocess, sys, tempfile, time, uuid

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


class Bed:
    """A throwaway hub: its own HUB_DIR, board, wake dir and target panes."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="t12-")
        # Session names must be unique per run: two people running this suite at once
        # (which happens -- Zeus and Prometheus both run it) would otherwise create and
        # kill each other's panes and both see phantom failures. hubwaked validates the
        # target as ^hub-[a-z0-9]+$, so the tag stays lowercase alphanumeric.
        self.tag = uuid.uuid4().hex[:6]
        json.dump({"next_id": 1, "tasks": []}, open(os.path.join(self.dir, "board.json"), "w"))
        # $HUB_DIR is the data directory only: hubmsg resolves the relay relative to its
        # own script path (T-016), so a throwaway board needs no copy of the executables.
        self.env = {**os.environ, "HUB_DIR": self.dir, "HUB_AGENT": "Zeus"}
        self.sessions = []

    def target(self, suffix, delay=0):
        """A stand-in TUI.

        The pty echoes the typed wake and the loop consumes it like a TUI. hubwaked watches
        cursor movement rather than interpreting rendered pane history.
        """
        sess = f"hub-{suffix}{self.tag}"
        out = os.path.join(self.dir, f"{suffix}.out")
        script = (f'sleep {delay}; while IFS= read -r l; do '
                  f'printf "%s\\n" "$l" >> {out}; printf "rendered: %s\\n" "$l"; done')
        sh(["tmux", "new-session", "-d", "-s", sess, "-c", self.dir, "bash", "-c", script])
        self.sessions.append(sess)
        return sess, out

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
        n = got.count(f"hub receive {mid}")
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


def main():
    b = Bed()
    print(f"bed: {b.dir}\n")
    try:
        for t in (test_content_integrity, test_newline_folding, test_cold_target,
                  test_asleep_vs_relay, test_relay_rejects_bad_targets, test_dedup,
                  test_relay_health_and_recovery, test_stale_code_and_resolved_error_status,
                  test_attached_pane_defers_without_collision,
                  test_single_delivery_with_daemon_running,
                  test_modal_dialog_is_never_confirmed_by_a_wake):
            print(f"{t.__name__}:")
            try:
                t(b)
            except Exception as e:
                check(f"{t.__name__} raised", False, repr(e))
            print()
    finally:
        b.cleanup()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if FAILURES:
        print("failed: " + ", ".join(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
