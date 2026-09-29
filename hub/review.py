"""Local approval pages: `hub review <page.html>`.

Serves one review page on 127.0.0.1, opens it in a browser window, and waits
for the human to click. The decision is written to <page dir>/reviews/<name>.json and
printed as one JSON line, then the command exits. Zeus runs it in the background, so the
click itself wakes Zeus -- no claude.ai round trip, no typing "decided".

The page needs only four ids: #approve and #changes (buttons), #note (textarea), #status
(a line for feedback). The server injects the script that wires them, so a review page is
plain HTML with no JavaScript of its own.
"""

import glob
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

WIRE = """<script>
(() => {
  const $ = id => document.getElementById(id), s = $("status");
  const send = async decision => {
    const note = ($("note")?.value || "").trim();
    if (decision === "changes" && !note) { $("note")?.focus(); s.textContent = "Say what should change first."; return; }
    const r = await fetch("/decision", {method: "POST", body: JSON.stringify({decision, note})});
    s.textContent = r.ok ? (decision === "approve" ? "Approved. You can close this window." : "Changes sent to Zeus. You can close this window.")
                         : "Could not record that: " + await r.text();
    if (r.ok) document.querySelectorAll("button").forEach(b => b.disabled = true);
  };
  $("approve")?.addEventListener("click", () => send("approve"));
  $("changes")?.addEventListener("click", () => send("changes"));
})();
</script>"""


def browser():
    """$HUB_BROWSER, else a system Chrome/Chromium, else Playwright's download."""
    if os.environ.get("HUB_BROWSER"):
        return os.environ["HUB_BROWSER"]
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(mac):
        return mac
    found = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    return found[-1] if found else None


def serve(page, name, open_browser=True, roots=None):
    """Serve until a valid decision arrives; return it. Blocks."""
    page = Path(page).resolve()
    built = roots is not None
    roots = tuple(Path(root).resolve() for root in (roots or ()))
    html = page.read_text()
    html = html.replace("</body>", WIRE + "</body>") if "</body>" in html else html + WIRE
    out = page.parent / "reviews" / f"{name}.json"
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, body, ctype="text/plain; charset=utf-8"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                return self.reply(200, html, "text/html; charset=utf-8")
            request = unquote(self.path.split("?")[0].lstrip("/"))
            if request.startswith("_files/"):
                parts = request.split("/", 2)
                if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) >= len(roots):
                    return self.reply(404, "not found")
                root = roots[int(parts[1])]
                f = (root / parts[2]).resolve()
            else:
                root = page.parent
                f = (root / request).resolve()
            if not f.is_relative_to(root) or (not built and f.parent != root) or not f.is_file():
                return self.reply(404, "not found")
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/decision":
                return self.reply(404, "not found")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                return self.reply(400, "not JSON")
            decision, note = body.get("decision"), str(body.get("note", "")).strip()
            if decision not in ("approve", "changes"):
                return self.reply(400, "decision must be approve or changes")
            if decision == "changes" and not note:
                return self.reply(400, "a change request needs a note")
            result.update(name=name, decision=decision, note=note,
                          at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2) + "\n")
            self.reply(200, "recorded")
            # Shut down from another thread; shutdown() from inside a handler deadlocks.
            threading.Thread(target=httpd.shutdown, daemon=True).start()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"review {name}: {url}", file=sys.stderr, flush=True)
    proc = None
    if open_browser:
        exe = browser()
        if exe:
            # A throwaway profile: a second window on the user's real profile would be
            # swallowed by the running instance and --app ignored.
            prof = tempfile.mkdtemp(prefix="hub-review-")
            proc = subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={prof}", "--no-first-run",
                              "--no-default-browser-check"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        else:
            print("no Linux browser found; open the URL above yourself (or set HUB_BROWSER)",
                  file=sys.stderr, flush=True)
    with httpd:
        httpd.serve_forever()
    if proc and proc.poll() is None:
        time.sleep(1.5)  # let the page show "Approved" before the window goes
        proc.terminate()
    return result


def cmd_review(a):
    for raw in a.paths:
        if not Path(raw).is_file():
            sys.exit(f"review: no such file: {raw}")
    paths = [Path(raw).resolve() for raw in a.paths]
    name = a.name or paths[0].stem
    if Path(name).name != name or name in (".", ".."):
        sys.exit(f"review: invalid name: {name}")
    roots = []
    if len(paths) == 1 and paths[0].suffix.lower() == ".html" and 'id="approve"' in paths[0].read_text():
        page = paths[0]
        roots = None
    else:
        page = paths[0].parent / f"{name}-review.html"
        if page in paths:
            sys.exit(f"review: output would overwrite input: {page}")

        def src(path):
            if path.parent == page.parent:
                return quote(path.name)
            if path.parent not in roots:
                roots.append(path.parent)
            return f"_files/{roots.index(path.parent)}/{quote(path.name)}"

        images = [f'<img src="{src(p)}" alt="{html.escape(p.stem)}">' for p in paths
                  if p.suffix.lower() in (".png", ".jpg", ".svg")]
        excerpts = [f"<pre>{html.escape(p.read_text())}</pre>" for p in paths
                    if p.suffix.lower() in (".md", ".txt")]
        frames = [f'<iframe src="{src(p)}" style="width:100%;height:600px" title="{html.escape(p.stem)}"></iframe>'
                  for p in paths if p.suffix.lower() == ".html"]
        page.write_text('<!doctype html><html><head><meta charset="utf-8"><style>'
                        'body{font:15px system-ui;margin:24px;max-width:1300px}'
                        '.row{display:flex;gap:16px}img{max-height:460px;border:1px solid #ccc}'
                        'pre{white-space:pre-wrap;background:#f6f6f6;padding:12px}'
                        '</style></head><body>'
                        f'<h2>{html.escape(name if a.title is None else a.title)}</h2>'
                        f'<div class="row">{"".join(images)}</div>' + "".join(excerpts + frames) +
                        f'<textarea id="note">{html.escape("agreed" if a.note is None else a.note)}</textarea><br>'
                        '<button id="approve">Approve</button> <button id="changes">Request changes</button> '
                        '<span id="status"></span></body></html>')
    decision = serve(page, name, open_browser=not a.no_open, roots=roots)
    print(json.dumps(decision))


def register(sub):
    r = sub.add_parser("review", help="open a local approval page and wait for the decision")
    r.add_argument("paths", nargs="+", metavar="PATH", help="an approval page, or files to review")
    r.add_argument("--name", help="decision name, e.g. approval-1 (default: the page's file stem)")
    r.add_argument("--title", help="heading for a built review page")
    r.add_argument("--note", help="initial note for a built review page (default: agreed)")
    r.add_argument("--no-open", action="store_true", help="print the URL instead of opening a window")
    r.set_defaults(fn=cmd_review)
