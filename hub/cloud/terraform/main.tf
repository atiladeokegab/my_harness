# The hub's existing Google Cloud infrastructure, described so hub-host can be rebuilt from code.
# Everything below was created by hand or by a script first and is adopted with imports.tf.
# What is deliberately left out is listed in README.md.

locals {
  hub_region = "europe-west2"

  # The APIs the hub and the deploys depend on. A new project switches on a default bundle
  # (BigQuery, Logging, ...) by itself; those are not managed here.
  hub_apis = [
    "compute.googleapis.com",
    "iap.googleapis.com",
    "oslogin.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ]
  # The list scripts/bootstrap.sh enables in the starter repos (APIS=...).
  deploy_apis = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ]
  deployer_roles = [
    "roles/run.admin",
    "roles/run.sourceDeveloper",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/logging.viewer",
  ]
  # Cloud Run runs, and Cloud Build builds, as the deploy project's default compute account.
  deploy_runtime_sa = "${data.google_project.deploy.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "deploy" {
  project_id = var.deploy_project
}

# --- APIs -------------------------------------------------------------------------------------

resource "google_project_service" "hub" {
  for_each           = toset(local.hub_apis)
  project            = var.hub_project
  service            = each.value
  disable_on_destroy = false # removing it from this file must never switch an API off
}

resource "google_project_service" "deploy" {
  for_each           = toset(local.deploy_apis)
  project            = var.deploy_project
  service            = each.value
  disable_on_destroy = false
}

# --- Network: default VPC, no public IPs, egress through Cloud NAT, SSH only via IAP ------------

resource "google_compute_network" "default" {
  project                 = var.hub_project
  name                    = "default"
  description             = "Default network for the project"
  auto_create_subnetworks = true

  lifecycle {
    prevent_destroy = true # the VM's only network
  }
}

resource "google_compute_firewall" "allow_ssh_from_iap" {
  project       = var.hub_project
  name          = "allow-ssh-from-iap"
  network       = google_compute_network.default.self_link
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["35.235.240.0/20"] # Google's IAP TCP-forwarding range

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  lifecycle {
    prevent_destroy = true # the only way in: deleting it cuts SSH
  }
}

resource "google_compute_firewall" "default_allow_internal" {
  project       = var.hub_project
  name          = "default-allow-internal"
  description   = "Allow internal traffic on the default network"
  network       = google_compute_network.default.self_link
  direction     = "INGRESS"
  priority      = 65534
  source_ranges = ["10.128.0.0/9"]

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }
}

resource "google_compute_router" "hub" {
  project = var.hub_project
  name    = "hub-router"
  region  = local.hub_region
  network = google_compute_network.default.self_link
}

resource "google_compute_router_nat" "hub" {
  project                            = var.hub_project
  name                               = "hub-nat"
  router                             = google_compute_router.hub.name
  region                             = local.hub_region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# --- The VM -----------------------------------------------------------------------------------

resource "google_compute_instance" "hub_host" {
  project = var.hub_project
  zone    = var.zone
  name    = "hub-host"
  # Set by hand on 2026-10-18 (lead: as hands-off as possible): a plan can't delete the VM by accident.
  deletion_protection = true
  machine_type        = "e2-standard-4"

  boot_disk {
    auto_delete = true
    initialize_params {
      image = var.vm_image
      size  = 100
      type  = "pd-balanced"
    }
  }

  network_interface {
    network    = google_compute_network.default.self_link
    subnetwork = "projects/${var.hub_project}/regions/${local.hub_region}/subnetworks/default"
    # No access_config: no public IP. In by IAP, out by hub-nat.
  }

  # The opt-in idle stop (cloud/startup.sh) is set by hand (metadata hub-idle-stop=on): ignored below,
  # so an apply never turns it back off. An edit to cloud/startup.sh shows here as an expected change.
  metadata = {
    startup-script = file("${path.module}/../startup.sh")
  }

  # No service account, so no scopes: gcloud on the box runs as the lead's own login.

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
    provisioning_model  = "STANDARD"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  lifecycle {
    prevent_destroy = true # the hub's whole disk lives here: a plan that replaces it must fail
    ignore_changes  = [metadata["hub-idle-stop"]]
  }
}

# --- Snapshot bucket (snapshot.sh, runbooks/restore-hub.md) -------------------------------------

resource "google_storage_bucket" "hub_snapshots" {
  project                     = var.hub_project
  name                        = "my-hub-project-hub-snapshots"
  location                    = "EUROPE-WEST2"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  # Overwritten live/ copies and pruned nightly tarballs go a week after they stop being current.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      with_state                 = "ARCHIVED"
      days_since_noncurrent_time = 7
    }
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle {
    prevent_destroy = true
  }
}

# --- IAM: additive members only, never whole policies -----------------------------------------

resource "google_project_iam_member" "lead_iap_tunnel" {
  project = var.hub_project
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "user:${var.lead}"
}

# --- The deployer scripts/deploy.sh impersonates (made by scripts/bootstrap.sh) ---------------

resource "google_service_account" "deployer" {
  project      = var.deploy_project
  account_id   = "deployer"
  display_name = "scripts/deploy.sh"

  lifecycle {
    prevent_destroy = true # every repo's deploy.sh impersonates it
  }
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(local.deployer_roles)
  project  = var.deploy_project
  role     = each.value
  member   = google_service_account.deployer.member
}

resource "google_service_account_iam_member" "lead_impersonates_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.lead}"
}

resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  service_account_id = "projects/${var.deploy_project}/serviceAccounts/${local.deploy_runtime_sa}"
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}

# The live smoke at the end of deploy.sh logs in with this. The secret itself is bootstrap.sh's.
resource "google_secret_manager_secret_iam_member" "deployer_reads_admin_password" {
  project   = var.deploy_project
  secret_id = "admin-password"
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.deployer.member
}

# Where `gcloud run deploy --source` pushes images.
resource "google_artifact_registry_repository" "cloud_run_source_deploy" {
  project       = var.deploy_project
  location      = var.deploy_region
  repository_id = "cloud-run-source-deploy"
  description   = "Cloud Run Source Deployments"
  format        = "DOCKER"
}

# --- Daily disk snapshots (set 2026-10-18): the bucket keeps hub state, this keeps the whole machine. ------

resource "google_compute_resource_policy" "hub_daily" {
  project     = var.hub_project
  region      = local.hub_region
  name        = "hub-daily"
  description = "hub-host disk, daily, 7 days"
  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "03:00"
      }
    }
    retention_policy {
      max_retention_days    = 7
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "hub_daily" {
  project = var.hub_project
  zone    = var.zone
  disk    = google_compute_instance.hub_host.name
  name    = google_compute_resource_policy.hub_daily.name
}
