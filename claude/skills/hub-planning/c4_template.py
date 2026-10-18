# /// script
# requires-python = ">=3.11"
# dependencies = ["diagrams"]
# ///
"""C4 diagrams for <SYSTEM>. Copy this file, replace the example nodes, run it.

    uv run c4.py            # writes c4_context.png ... c4_code.png beside this file
    uv run c4.py context    # just one level

While planning it lives at $HUB_DIR/projects/<repo>/c4.py and draws the PLANNED system,
levels 1-3 only. After the build it moves to docs/architecture/c4.py in the repo and
draws the REAL code, level 4 included. The inline dependency above means nothing is
added to the repo's pyproject.
"""

import shutil
import sys
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.c4 import Container, Database, Person, Relationship, System, SystemBoundary
from functools import partial

# diagrams.c4 wraps text at 40 characters but draws 2.6in boxes, which fit about 34:
# lines of 35-40 characters were cut off, silently. 3.3in fits the full wrap width.
Container, Database, Person, System = (partial(f, width="3.3") for f in (Container, Database, Person, System))
from diagrams.programming.language import Python

SYSTEM = "Example"  # <- the system's name
# Look at every PNG before showing it to anyone.
OUT = Path(__file__).parent
GRAPH = {"splines": "spline", "nodesep": "0.8", "ranksep": "1.1"}


def draw(level, title):
    return Diagram(f"{SYSTEM} - {title}", filename=str(OUT / f"c4_{level}"), outformat="png",
                   show=False, direction="TB", graph_attr=GRAPH)


def context():
    """Level 1: who uses it and what it depends on. The system is ONE box."""
    with draw("context", "System Context"):
        user = Person("User", "Who they are and what they want")
        system = System(SYSTEM, "What it does, in one line")
        ext = System("External service", "What we rely on it for", external=True)
        user >> Relationship("uses") >> system
        system >> Relationship("calls") >> ext


def container():
    """Level 2: the separately running or deployed pieces, and how they talk."""
    with draw("container", "Containers"):
        user = Person("User", "")
        with SystemBoundary(SYSTEM):
            web = Container("Web app", "FastAPI", "Serves pages and the API")
            db = Database("Database", "SQLite", "What it stores")
        user >> Relationship("HTTPS") >> web
        web >> Relationship("reads/writes") >> db


def component():
    """Level 3: inside ONE container. Name the container in the title."""
    with draw("component", "Components of the web app"):
        with SystemBoundary("Web app"):
            routes = Container("Routes", "module", "HTTP handlers")
            store = Container("Store", "module", "All database access")
        routes >> Relationship("uses") >> store


def code():
    """Level 4: classes and key signatures. Real code only; skip it while planning."""
    with draw("code", "Code"):
        with Cluster("app/"):
            store = Python("Store\napp/store.py\n——\n+ add(item) → int\n+ list() → list[Item]")
            item = Python("Item(dataclass)\n——\n+ id: int\n+ name: str")
        store >> Edge(label="returns") >> item


# Only the levels defined above: while planning, code() is deleted, not stubbed.
LEVELS = {n: globals()[n] for n in ("context", "container", "component", "code") if n in globals()}

if __name__ == "__main__":
    if not shutil.which("dot"):
        sys.exit("c4: Graphviz is not installed (no `dot` on PATH). Run: sudo apt install -y graphviz")
    for name in sys.argv[1:] or LEVELS:
        LEVELS[name]()
        print(OUT / f"c4_{name}.png")
