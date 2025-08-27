resource "google_pubsub_topic" "ingestion" {
  name = "ingestion-tasks"
}

resource "google_pubsub_topic" "dlq" {
  name = "ingestion-dlq"
}

resource "google_pubsub_subscription" "ingestion_sub" {
  name  = "ingestion-sub"
  topic = google_pubsub_topic.ingestion.name

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

resource "google_pubsub_subscription" "dlq_sub" {
  name  = "ingestion-dlq-sub"
  topic = google_pubsub_topic.dlq.name
}
