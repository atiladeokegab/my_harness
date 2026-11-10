terraform {
  required_version = ">= 1.5" # import {} blocks

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.7"
    }
  }

  # Local state, gitignored (.gitignore here): it is the only copy, so back it up by hand if it matters.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Auth: GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token) (README); no key files.
provider "google" {}
