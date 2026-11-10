# Optional: WhatsApp to the lead (`hubwa`)

The lead can talk to the hub from a phone. Messages they send on WhatsApp land in the lead agent's
inbox as a wake; agents answer with `hubwa send "..."` in one or two plain sentences. When the lead
agent is down (rate limited, logged out, stuck at a prompt), the first healthy agent stands in and
the lead agent gets a copy for later.

It goes through [Wassist](https://wassist.app), which hosts the WhatsApp Business number. WhatsApp
only allows free text within 24 hours of the lead's last message; `hubwa send` holds anything sent
outside that window (up to 10) until the lead next writes, and refuses technical text (paths,
commands, hashes) outright.

## Configure

One value per file in `~/.config/hub/` (chmod 600; never in a repo):

| File | What |
|---|---|
| `wassist.key` | your Wassist API key |
| `wassist.agent` | the Wassist agent id messages go through |
| `wassist.number` | the Wassist WhatsApp number, digits only (used to print the connect link) |
| `whatsapp.number` | the lead's own WhatsApp number; only messages from it count as the lead's |

The lead agent's name comes from `HUB_LEAD` (default `Zeus`).

Run `hubwa read` once: until the lead has opened the connect link it prints, there is no chat.

## Run it

```bash
cp "$HUB_DIR"/systemd/hub-whatsapp.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now hub-whatsapp.service
```

The service runs `hubwa poll` every 5 seconds. Troubleshooting: `runbooks/whatsapp-send-fails.md`.
