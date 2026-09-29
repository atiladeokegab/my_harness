"""The event's GitHub Project board: a view of the hub's tasks, never a source of truth.

Copied once from the lead's "Hackathon board (template)" project at `gh-sync --init`, then kept
in step at the end of every sync. Any failure here is one warning line; the sync carries on.
"""

import re

from gh_sync import GhError, deadline

TEMPLATE_TITLE = "Hackathon board (template)"
ITEM_LIMIT, PR_LIMIT = 500, 200


def status_of(issue, open_prs, branches):
    """Todo / In progress / In review / Done, from facts GitHub already has."""
    n = issue["number"]
    if issue.get("state") == "CLOSED":
        return "Done"
    closes = re.compile(rf"(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#{n}\b")
    if any(closes.search(p.get("body") or "") for p in open_prs):
        return "In review"
    if any(b.startswith(f"{n}-") for b in branches):
        return "In progress"
    return "Todo"


def lead_login(cfg):
    return next(p["github"] for p in cfg["roster"] if p.get("lead"))


def init_board(cfg, gh, repo):
    if cfg.get("board"):
        return
    if gh.dry:
        print(f"would copy the board template {TEMPLATE_TITLE!r}, link it and make it public")
        return
    owner = lead_login(cfg)
    try:
        projects = gh.json("project", "list", "--owner", owner, "--format", "json", "--limit", "100")
        tpl = next((p for p in projects["projects"] if p["title"] == TEMPLATE_TITLE), None)
        if not tpl:
            print(f"warning: no project titled {TEMPLATE_TITLE!r} on {owner}; no board made")
            return
        new = gh.json("project", "copy", tpl["number"], "--source-owner", owner,
                      "--target-owner", owner, "--title", f"{repo.split('/')[1]} board",
                      "--format", "json")
        gh("project", "link", new["number"], "--owner", owner, "--repo", repo)
        # The template is private, so its copy is too, and teammates would get a 404.
        # Event repos are public anyway, so the event board is public.
        gh("project", "edit", new["number"], "--owner", owner, "--visibility", "PUBLIC")
        cfg["board"] = {"number": new["number"], "url": new["url"], "id": new["id"]}
        print(f"board: {new['url']}")
    except (GhError, KeyError, TypeError) as e:
        print(f"warning: board not made: {e}")


def sync_board(tasks, cfg, gh, repo, issues):
    b = cfg.get("board")
    if not b:
        return
    owner = lead_login(cfg)
    try:
        fields = {f["name"]: f for f in gh.json("project", "field-list", b["number"], "--owner",
                                                  owner, "--format", "json")["fields"]}
        options = {o["name"]: o["id"] for o in fields["Status"]["options"]}
        items = gh.json("project", "item-list", b["number"], "--owner", owner, "--format", "json",
                        "--limit", str(ITEM_LIMIT))["items"]
        if len(items) >= ITEM_LIMIT:
            print(f"warning: board has more than {ITEM_LIMIT - 1} items; some are not kept in step")
        by_issue = {(i.get("content") or {}).get("number"): i for i in items}
        prs = gh.json("pr", "list", "-R", repo, "--state", "open", "--json", "number,body",
                      "--limit", str(PR_LIMIT)) or []
        if len(prs) >= PR_LIMIT:
            print(f"warning: more than {PR_LIMIT - 1} open PRs; In review may miss some")
        refs = gh("api", f"repos/{repo}/git/matching-refs/heads/", "--jq", ".[].ref", write=False)
        branches = [r.removeprefix("refs/heads/") for r in (refs or "").split()]
        for t in tasks:
            i = issues.get(t.get("issue"))
            if not i:
                continue
            item = by_issue.get(i["number"])
            if not item:
                # GitHub lists a new card a few seconds after adding it, so this can re-add one
                # the last sync made. item-add is idempotent (same issue -> same card id,
                # checked 2026-09-28), so that edits the existing card, never a duplicate.
                item = {"id": gh.json("project", "item-add", b["number"], "--owner", owner,
                                      "--url", i["url"], "--format", "json")["id"]}
            want = {"Status": status_of(i, prs, branches), "Agent": t.get("agent") or "",
                    "Deadline": deadline(t.get("detail"))}
            # item-list reports field values keyed by the field's lower-case name.
            have = {name: item.get(name.lower()) or "" for name in want}
            for name, value in want.items():
                if have[name] == value:
                    continue
                args = ["project", "item-edit", "--id", item["id"], "--project-id", b["id"],
                        "--field-id", fields[name]["id"]]
                args += (["--single-select-option-id", options[value]] if name == "Status"
                         else ["--text", value])
                gh(*args)
    except (GhError, KeyError, TypeError) as e:
        print(f"warning: board not updated: {e}")
