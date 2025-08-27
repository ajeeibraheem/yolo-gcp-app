resource "google_cloud_run_v2_service" "backend" {
  name     = "yolo-backend"
  location = var.region
  template {
    service_account = google_service_account.backend_sa.email
    containers {
      image = coalesce(var.backend_image, "${google_artifact_registry_repository.repo.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/backend:latest")
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GCS_BUCKET"
        value = var.bucket_name
      }
      env { name = "PUBSUB_TOPIC" value = google_pubsub_topic.ingestion.name }
    }
  }
}

resource "google_cloud_run_v2_service" "dispatcher" {
  name     = "yolo-dispatcher"
  location = var.region
  template {
    service_account = google_service_account.dispatcher_sa.email
    containers {
      image = coalesce(var.dispatcher_image, "${google_artifact_registry_repository.repo.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/dispatcher:latest")
      env { name = "GCP_PROJECT_ID" value = var.project_id }
      env { name = "GCP_REGION" value = var.region }
      env { name = "JOB_NAME" value = google_cloud_run_v2_job.worker.name }
    }
  }
}

resource "google_cloud_run_v2_job" "worker" {
  name     = "yolo-ingestion-job"
  location = var.region
  template {
    template {
      service_account = google_service_account.worker_sa.email
      containers {
        image = coalesce(var.worker_image, "${google_artifact_registry_repository.repo.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/worker:latest")
        env { name = "MONGO_URI" value = "mongodb://10.0.0.2:27017" } # replace with real
        env { name = "MONGO_DB" value = "yoloapp" }
      }
    }
  }
}

# Pub/Sub push to dispatcher
resource "google_pubsub_subscription" "ingestion_push" {
  name  = "ingestion-push"
  topic = google_pubsub_topic.ingestion.name

  push_config {
    push_endpoint = google_cloud_run_v2_service.dispatcher.uri
    oidc_token {
      service_account_email = google_service_account.dispatcher_sa.email
    }
    attributes = {
      x-dispatch-token = "required-if-set" # optional; remove if not using token
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
