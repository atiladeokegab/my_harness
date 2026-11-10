# Optional: a self-hosted Penpot for agents

[Penpot](https://penpot.app) is an open-source design tool. Self-hosted, agents can read and edit
design files with no browser through its RPC API, and draw through its official MCP server. The
`penpot-design` skill is how agents use it.

[Studio](https://github.com/atiladeokegab/studio) builds on this: it imports a live product's pages
as editable boards and files Penpot comments as hub tasks. The `studio-design` skill covers it.

## Run it

`templates/penpot/` holds a Docker Compose file based on upstream's, with pinned tags, every port on
`127.0.0.1` only, registration and SMTP off, access tokens and MCP on, and telemetry off.

```bash
mkdir -p ~/penpot && cp "$REPO"/templates/penpot/docker-compose.yaml ~/penpot/
cp "$REPO"/templates/penpot/env.example ~/penpot/.env && chmod 600 ~/penpot/.env
# fill in PENPOT_SECRET_KEY and PENPOT_DB_PASSWORD in ~/penpot/.env
cd ~/penpot && docker compose up -d && docker compose ps
```

It serves on `http://localhost:9001`. From another machine use an SSH forward
(`-L 9001:127.0.0.1:9001`). To expose it on a domain (`https://penpot.example.com`), put a TLS
reverse proxy in front, set `PENPOT_PUBLIC_URI` to that address, and think about login before you
do: registration is off, so accounts are made by hand (below). The images take about 6 GB of disk.

Upgrade: read the release notes, bump `PENPOT_VERSION` in `.env`, then
`docker compose pull && docker compose up -d`. Data lives in the `penpot_postgres_v15` and
`penpot_assets` volumes; back them up.

## Accounts and tokens

Create one profile for people and one for agents:

```bash
docker compose exec penpot-backend python3 ./manage.py create-profile   # prompts for email, name, password
```

Give the agents profile a personal access token: sign in as it in the UI, then
**Your account > Access tokens**, or by RPC (`login-with-password`, then `create-access-token`).
Store it outside every repo, chmod 600, and hand it to agents as an env var:

| Name | What |
|---|---|
| `PENPOT_URL` | the base address, e.g. `http://localhost:9001` |
| `PENPOT_TOKEN` | the agents profile's access token |
| `PENPOT_MCP_KEY` | optional: an access token of type `mcp`, for the MCP server below |

Agents call `"$PENPOT_URL/api/rpc/command/<name>"` with the header `Authorization: Token $PENPOT_TOKEN`,
JSON in and JSON out (`get-profile`, `get-projects`, `get-project-files`, `get-file`, `update-file`).
Never print a token or put it in a command line that is logged.

Two limits worth knowing:

- **The exporter does not take access tokens.** PNG and PDF export (`/api/export`) renders in a
  browser using a session cookie, so it needs a password login. Prefer MCP's `export_shape`.
- **Writing shapes by RPC means building Penpot's internal shape maps by hand** (selrect, points,
  transform, the text content tree). For anything beyond a frame and a text, use MCP.

## MCP (drawing)

The official MCP server ships in the stack (`penpot-mcp`, enabled by the `enable-mcp` flag) at
`$PENPOT_URL/mcp/stream?userToken=<PENPOT_MCP_KEY>`. Its `execute_code` tool runs JavaScript against
the Penpot Plugin API, so it can do anything the plugin API can.

It needs an open workspace tab for the same profile, which hosts the MCP plugin; with none open,
calls fail with "no plugin connected". A headless browser parked on a file works (enable MCP in the
profile's settings so the workspace connects the plugin without a click). Keep one tab per key: a
second tab with the same key takes the connection over. Penpot keeps one MCP key per profile, so
making a new one revokes the old.

Register it with Claude Code (the key ends up in clear text in your settings, and the frontend's
access log records it, because upstream puts it in the query string):

```bash
claude mcp add --transport http --scope user penpot "$PENPOT_URL/mcp/stream?userToken=$PENPOT_MCP_KEY"
```
