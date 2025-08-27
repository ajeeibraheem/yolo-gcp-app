resource "google_artifact_registry_repository" "repo" {
  location      = var.repo_location
  repository_id = "yolo"
  description   = "Containers for yolo gcp app"
  format        = "DOCKER"
}
