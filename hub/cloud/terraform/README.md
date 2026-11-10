# Hub cloud infrastructure as code

Terraform 1.16.6 (`~/.local/bin/terraform`, HashiCorp release, SHA256SUMS signature and checksum
verified), provider `hashicorp/google` ~> 8.7. Written 2026-10-18 from read-only `gcloud describe`
of what exists; every resource was made by hand or by a script first and is adopted by `imports.tf`.

## What it covers

| Project | Resources |
|---|---|
| `my-hub-project` | VM `hub-host` (e2-standard-4, europe-west2-a, 100 GB pd-balanced, Ubuntu 24.04, shielded VM, no public IP, no service account, metadata `startup-script` = `../startup.sh`); `default` network; firewall `allow-ssh-from-iap` (tcp:22 from 35.235.240.0/20) and `default-allow-internal`; Cloud Router `hub-router` + NAT `hub-nat` (the VM's only way out); bucket `my-hub-project-hub-snapshots` (EUROPE-WEST2, versioned, uniform access, public access prevented, noncurrent versions deleted after 7 days, 7-day soft delete); the lead's `roles/iap.tunnelResourceAccessor`; APIs compute, iap, oslogin, storage, iam, iamcredentials |
| `my-events-project` | Service account `deployer` (what `scripts/deploy.sh` impersonates) with run.admin, run.sourceDeveloper, serviceusage.serviceUsageConsumer, logging.viewer; the lead's tokenCreator on it; its serviceAccountUser on the runtime (default compute) account; its accessor on secret `admin-password`; Artifact Registry `cloud-run-source-deploy` (europe-west1); the APIs `scripts/bootstrap.sh` enables |

IAM is additive (`*_iam_member`) only: nothing here can remove a grant it does not name.
The VM, the bucket, the default network, the IAP SSH firewall and the deployer SA carry `prevent_destroy`, so any plan that would replace or delete them errors out.
APIs have `disable_on_destroy = false`.

## Plan (read-only)

```bash
cd ~/hub/cloud/terraform
export PATH=/snap/bin:$PATH                                   # gcloud on the hub VM
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)   # an hour's token, never written to disk
terraform init
terraform plan
```

Expected today: `Plan: 32 to import, 0 to add, 0 to change, 0 to destroy.` Any `to change` or
`to destroy` is drift: someone changed the cloud by hand, or this code is wrong. Read the diff.
One expected exception: an edit to `cloud/startup.sh` shows as a metadata change on the VM; apply it
to ship the new startup script. The hand-set `hub-idle-stop` key is ignored and never shows.

`terraform apply` of that plan changes no cloud resource; it only writes the imports into the local
`terraform.tfstate` (gitignored, may hold secrets). Only the lead runs it. Once applied, `plan`
should say `No changes.`

## Rebuild from scratch

**The VM is gone, same project.** If state exists: `terraform plan` shows `hub-host` to create;
apply it. With no state: delete the `google_compute_instance.hub_host` import block (an import of
something missing fails the plan), plan, apply. Then the box itself, which no cloud API holds:
`runbooks/hub-on-a-vm.md` "Laptop → VM" steps 3 to 9 (copy `~/hub`, `cloud/bootstrap.sh`, logins),
the timers in `runbooks/install-factory-timers.md` step 3, and `runbooks/restore-hub.md` for the
board from the snapshot bucket.

**A new project.** Create it and link billing by hand (not covered here), then
`-var hub_project=<new>`. Delete `imports.tf`, except keep the `google_compute_network.default`
import if enabling the Compute API made a `default` network (it usually does; it also brings
`default-allow-ssh/rdp/icmp`, which this hub deleted: remove them). The bucket name is global and
fixed in `main.tf`: change it, and `snapshot_bucket` in `~/hub/factory.json`, if the old bucket
still exists. Then the box, as above.

## What is not covered, and who owns it

- **The projects themselves**, their billing link, and the budgets on billing account
  `XXXXXX-XXXXXX-XXXXXX`: `hub-host` £110/month and `hackathon-starter £10`, alerts at 50/90/100%.
- **The lead's `roles/owner`**, Google's service-agent grants, and the default compute accounts'
  `roles/editor`: project defaults; managing them here only adds a way to lock someone out.
- **Project metadata `ssh-keys`** in `my-hub-project`: written by `gcloud compute ssh`.
- **Cloud Run services** `hackathon-starter` and `factory-sandbox`, their secrets
  (`anthropic-api-key`, `admin-password`) and values, the state buckets
  (`my-events-project-state`, `my-events-project-factory-sandbox`,
  `run-sources-my-events-project-europe-west1`) and the runtime account's grants: each repo's
  `scripts/bootstrap.sh` and `scripts/deploy.sh` own them. A second owner would fight them.
- **The default API bundle** a new project switches on by itself (BigQuery, Logging, Monitoring,
  Pub/Sub, ...), and billingbudgets/cloudbilling.
- **Everything on the disk**: packages, logins, user systemd timers, `~/hub`. That is
  `cloud/bootstrap.sh` and the runbooks above. No disk snapshot schedule exists; only the board,
  ledger, inboxes and `projects/` are backed up, to the bucket.
