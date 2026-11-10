"""`hub host up|down|status|ssh|tunnel`: the cloud VM the hub lives on during event weeks.

Run from the laptop. The VM has no public IP, so the only way in is SSH through IAP. It is
stopped between events, when only its disk is billed. Creating it is a one-off: see
~/hub/runbooks/hub-on-a-vm.md.
"""

import os
import subprocess
import sys
import time

PROJECT = os.environ.get("HUB_HOST_PROJECT", "my-hub-project")
ZONE = "europe-west2-a"
VM = "hub-host"


def gcloud(*args):
    return ["gcloud", "compute", *args, f"--zone={ZONE}", f"--project={PROJECT}"]


def ssh_args(*extra):
    """The laptop's way in. Anything after "--" goes to ssh itself, e.g. "-L" forwards."""
    return [*gcloud("ssh", VM, "--tunnel-through-iap"), *extra]


def forwards():
    """-L for the dashboard (8765) and headless `hub review` pages (HUB_REVIEW_PORT, 8766)."""
    ports = (8765, int(os.environ.get("HUB_REVIEW_PORT", "8766")))
    return [arg for p in ports for arg in ("-L", f"{p}:localhost:{p}")], ports


def tunnel():
    """The forwards with no shell, reconnecting until Ctrl-C. ServerAlive notices a dead link."""
    fwd, ports = forwards()
    argv = ssh_args("--", "-N", *fwd, "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3")
    print("dashboard: http://127.0.0.1:%d/   reviews: http://127.0.0.1:%d/" % ports, flush=True)
    try:
        while True:
            print("tunnel: connecting", flush=True)
            code = subprocess.run(argv).returncode
            print(f"tunnel: dropped (exit {code}), reconnecting in 5s", flush=True)
            time.sleep(5)
    except FileNotFoundError:
        sys.exit("host: gcloud is not installed on this machine")
    except KeyboardInterrupt:
        print("\ntunnel: closed", flush=True)
        sys.exit(0)


def cmd_host(a):
    if a.action == "tunnel":
        tunnel()
    if a.action == "status":
        argv = gcloud("instances", "describe", VM, "--format=value(status)")
    elif a.action == "ssh":
        # The dashboard and review pages come along on the laptop while this is open.
        argv = ssh_args("--", *forwards()[0])
    else:
        argv = gcloud("instances", "start" if a.action == "up" else "stop", VM)
    try:
        code = subprocess.run(argv, timeout=None if a.action == "ssh" else 300).returncode
    except FileNotFoundError:
        sys.exit("host: gcloud is not installed on this machine")
    except subprocess.TimeoutExpired:
        sys.exit(f"host: {' '.join(argv)} gave no answer in 5 minutes")
    if a.action == "up" and code == 0:
        print("up. In: hub host ssh   (agents: zeus, hermes, prometheus; Ctrl-b d leaves them running)")
    sys.exit(code)


def register(sub):
    h = sub.add_parser("host", help="start, stop or enter the hub's cloud VM (event weeks only); "
                                       "tunnel: only the web pages, reconnecting")
    h.add_argument("action", choices=("up", "down", "status", "ssh", "tunnel"))
    h.set_defaults(fn=cmd_host)
