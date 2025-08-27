resource "google_service_account" "backend_sa" {
  account_id   = "yolo-backend"
  display_name = "Backend API SA"
}

resource "google_service_account" "dispatcher_sa" {
  account_id   = "yolo-dispatcher"
  display_name = "Dispatcher SA"
}

resource "google_service_account" "worker_sa" {
  account_id   = "yolo-worker"
  display_name = "Worker SA"
}

# Allow dispatcher to run jobs
resource "google_project_iam_member" "dispatcher_run_jobs" {
  project = var.project_id
  role    = "roles/run.jobsRunner"
  member  = "serviceAccount:${google_service_account.dispatcher_sa.email}"
}

# Pub/Sub -> dispatcher push invoker
resource "google_cloud_run_v2_service_iam_member" "dispatcher_invoker" {
  name   = google_cloud_run_v2_service.dispatcher.name
  location = var.region
  role   = "roles/run.invoker"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_project" "project" {}
