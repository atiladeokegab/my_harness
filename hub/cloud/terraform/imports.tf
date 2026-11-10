# Adopts the resources that already exist. Harmless once they are in state (an import of something
# already managed is a no-op), and on a rebuild into an empty project delete this file first:
# an import of something that does not exist fails the plan (README, "Rebuild from scratch").

import {
  for_each = toset(local.hub_apis)
  to       = google_project_service.hub[each.value]
  id       = "${var.hub_project}/${each.value}"
}

import {
  for_each = toset(local.deploy_apis)
  to       = google_project_service.deploy[each.value]
  id       = "${var.deploy_project}/${each.value}"
}

import {
  to = google_compute_network.default
  id = "projects/${var.hub_project}/global/networks/default"
}

import {
  to = google_compute_firewall.allow_ssh_from_iap
  id = "projects/${var.hub_project}/global/firewalls/allow-ssh-from-iap"
}

import {
  to = google_compute_firewall.default_allow_internal
  id = "projects/${var.hub_project}/global/firewalls/default-allow-internal"
}

import {
  to = google_compute_router.hub
  id = "projects/${var.hub_project}/regions/${local.hub_region}/routers/hub-router"
}

import {
  to = google_compute_router_nat.hub
  id = "${var.hub_project}/${local.hub_region}/hub-router/hub-nat"
}

import {
  to = google_compute_instance.hub_host
  id = "projects/${var.hub_project}/zones/${var.zone}/instances/hub-host"
}

import {
  to = google_storage_bucket.hub_snapshots
  id = "${var.hub_project}/my-hub-project-hub-snapshots"
}

import {
  to = google_project_iam_member.lead_iap_tunnel
  id = "${var.hub_project} roles/iap.tunnelResourceAccessor user:${var.lead}"
}

import {
  to = google_service_account.deployer
  id = "projects/${var.deploy_project}/serviceAccounts/deployer@${var.deploy_project}.iam.gserviceaccount.com"
}

import {
  for_each = toset(local.deployer_roles)
  to       = google_project_iam_member.deployer[each.value]
  id       = "${var.deploy_project} ${each.value} serviceAccount:deployer@${var.deploy_project}.iam.gserviceaccount.com"
}

import {
  to = google_service_account_iam_member.lead_impersonates_deployer
  id = "projects/${var.deploy_project}/serviceAccounts/deployer@${var.deploy_project}.iam.gserviceaccount.com roles/iam.serviceAccountTokenCreator user:${var.lead}"
}

import {
  to = google_service_account_iam_member.deployer_acts_as_runtime
  id = "projects/${var.deploy_project}/serviceAccounts/${local.deploy_runtime_sa} roles/iam.serviceAccountUser serviceAccount:deployer@${var.deploy_project}.iam.gserviceaccount.com"
}

import {
  to = google_secret_manager_secret_iam_member.deployer_reads_admin_password
  id = "projects/${var.deploy_project}/secrets/admin-password roles/secretmanager.secretAccessor serviceAccount:deployer@${var.deploy_project}.iam.gserviceaccount.com"
}

import {
  to = google_artifact_registry_repository.cloud_run_source_deploy
  id = "projects/${var.deploy_project}/locations/${var.deploy_region}/repositories/cloud-run-source-deploy"
}

import {
  to = google_compute_resource_policy.hub_daily
  id = "projects/${var.hub_project}/regions/${local.hub_region}/resourcePolicies/hub-daily"
}

import {
  to = google_compute_disk_resource_policy_attachment.hub_daily
  id = "projects/${var.hub_project}/zones/${var.zone}/disks/hub-host/hub-daily"
}
