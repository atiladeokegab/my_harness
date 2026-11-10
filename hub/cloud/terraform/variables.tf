variable "hub_project" {
  description = "Project that holds the hub VM and its snapshot bucket."
  type        = string
  default     = "my-hub-project"
}

variable "deploy_project" {
  description = "Project the starter repos deploy to on Cloud Run (scripts/deploy.sh)."
  type        = string
  default     = "my-events-project"
}

variable "zone" {
  type    = string
  default = "europe-west2-a"
}

variable "deploy_region" {
  type    = string
  default = "europe-west1"
}

variable "lead" {
  description = "The lead's Google account: IAP tunnel user, and the one who may impersonate the deployer."
  type        = string
  default     = "you@example.com"
}

variable "vm_image" {
  # The exact image the live disk was made from. It only matters on a rebuild; if Google has retired
  # it by then, use the family projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64
  # (checked 2026-10-18: the family also plans clean against the live VM).
  description = "Boot image for hub-host."
  type        = string
  default     = "projects/ubuntu-os-cloud/global/images/ubuntu-2404-noble-amd64-v20260918"
}
