variable "project_id" { type = string }
variable "region" { type = string }
variable "repo_location" { type = string }
variable "bucket_name" { type = string }

variable "backend_image" {
  type    = string
  default = null
}

variable "dispatcher_image" {
  type    = string
  default = null
}

variable "worker_image" {
  type    = string
  default = null
}
