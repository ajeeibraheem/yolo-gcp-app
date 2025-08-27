output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "dispatcher_url" {
  value = google_cloud_run_v2_service.dispatcher.uri
}

output "job_name" {
  value = google_cloud_run_v2_job.worker.name
}
