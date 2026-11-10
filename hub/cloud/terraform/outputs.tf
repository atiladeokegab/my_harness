output "vm" {
  value = "${google_compute_instance.hub_host.name} (${google_compute_instance.hub_host.machine_type}, ${var.zone}, internal ${google_compute_instance.hub_host.network_interface[0].network_ip})"
}

output "ssh" {
  value = "gcloud compute ssh ${google_compute_instance.hub_host.name} --zone=${var.zone} --project=${var.hub_project} --tunnel-through-iap"
}

output "snapshot_bucket" {
  value = google_storage_bucket.hub_snapshots.url
}

output "deployer" {
  value = google_service_account.deployer.email
}

output "image_repo" {
  value = "${var.deploy_region}-docker.pkg.dev/${var.deploy_project}/${google_artifact_registry_repository.cloud_run_source_deploy.repository_id}"
}
