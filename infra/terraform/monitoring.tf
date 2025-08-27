# Alert: DLQ backlog on DLQ subscription
resource "google_monitoring_alert_policy" "dlq_backlog" {
  display_name = "Pub/Sub DLQ backlog > 0"
  combiner     = "OR"
  conditions {
    display_name = "DLQ backlog"
    condition_threshold {
      filter = "resource.type=\"pubsub_subscription\" AND resource.label.\"subscription_id\"=\"${google_pubsub_subscription.dlq_sub.name}\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration = "300s"
      comparison = "COMPARISON_GT"
      threshold_value = 0
      trigger { count = 1 }
    }
  }
}

# Alert: Forwarded to DLQ (dead letter count increasing)
resource "google_monitoring_alert_policy" "dead_letter_forwarded" {
  display_name = "Pub/Sub forwarding to DLQ"
  combiner     = "OR"
  conditions {
    display_name = "dead_letter_message_count > 0"
    condition_threshold {
      filter = "resource.type=\"pubsub_subscription\" AND resource.label.\"subscription_id\"=\"${google_pubsub_subscription.ingestion_sub.name}\" AND metric.type=\"pubsub.googleapis.com/subscription/dead_letter_message_count\""
      duration = "0s"
      comparison = "COMPARISON_GT"
      threshold_value = 0
      trigger { count = 1 }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }
}

# Alert: Cloud Run Job execution failed
resource "google_monitoring_alert_policy" "job_failed" {
  display_name = "Cloud Run Job: failed execution"
  combiner     = "OR"
  conditions {
    display_name = "job/completed_execution_count{result=failed}"
    condition_threshold {
      filter = "resource.type=\"cloud_run_job\" AND metric.type=\"run.googleapis.com/job/completed_execution_count\" AND metric.label.\"result\"=\"failed\""
      duration = "0s"
      comparison = "COMPARISON_GT"
      threshold_value = 0
      trigger { count = 1 }
    }
  }
}
