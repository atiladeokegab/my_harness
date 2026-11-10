# Optional: the hub on a cloud VM, and the Cloud Run spend guard

Three independent pieces, all Google Cloud. None is installed as a running service by default.

## 1. The hub host VM (`hub host`, `cloud/`)

`hub host up|down|status|ssh|tunnel` starts, stops and reaches one VM named `hub-host`, reachable
only by SSH through IAP (no public IP). It is meant to be stopped between busy weeks, when only its
disk is billed. `cloud/terraform/` creates it and its service accounts; `cloud/bootstrap.sh` sets it
up once it exists; `cloud/startup.sh` is its boot script. The full walk-through is
`runbooks/hub-on-a-vm.md`.

| Name | Where | What |
|---|---|---|
| `HUB_HOST_PROJECT` | env, on the laptop | the GCP project the VM lives in (default `my-hub-project`) |
| `hub_project`, `deploy_project`, `lead`, `zone`, `deploy_region`, `vm_image` | Terraform variables (`terraform.tfvars`) | the hub project, the project agents deploy to, the lead's Google account, placement |
| `HUB_GIT_NAME`, `HUB_GIT_EMAIL` | env, when running `bootstrap.sh` | the Git identity commits from the VM carry |

`host.py` uses zone `europe-west2-a`; change `ZONE` there if your VM is elsewhere. `hub host tunnel`
forwards the dashboard (8765) and `hub review` pages (`HUB_REVIEW_PORT`, 8766) to the laptop.

## 2. The spend guard (`cloudrun_check.py`, `hub-spend.timer`)

Hourly: scales warm Cloud Run revisions back to zero, and tells the lead's inbox about stray VMs,
long-running jobs and budget alerts at 50, 90 and 100%. **At 100% of the event budget it deletes
every Cloud Run service in the event project**, so point it only at a project whose products may
come down. `--dry-run` changes nothing.

| Name | What |
|---|---|
| `HUB_HOST_PROJECT` | the hub project (as above) |
| `HUB_SPEND_EVENT_PROJECT` | the project short-lived products are deployed to (default `my-events-project`) |
| `HUB_SPEND_EVENT_BUDGET` | the id of the one budget allowed to bring the event project down |
| `HUB_SPEND_STATE` | where it keeps what it has already reported (default `~/.local/state/hub/spend.json`) |

Budget alerts arrive through a Pub/Sub subscription named `hub-spend` in the hub project.

```bash
cp "$HUB_DIR"/systemd/hub-spend.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now hub-spend.timer
```

## 3. Disk housekeeping for a small VM

- `ops/janitor.sh` keeps `/` under a target: `TARGET_PCT` (default 75) and `ALERT_PCT` (85).
  `--dry-run` shows what it would free. Units: `ops/systemd/hub-janitor.{service,timer}`.
- `disk_gc.py` removes recoverable scratch checkouts and old test directories; `--dry-run` reports
  only. To run it nightly, uncomment its line in `systemd/hub-nightly.service`.
