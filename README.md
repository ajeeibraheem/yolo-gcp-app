# YOLO GCP Application

(100GB+ friendly) with **GCP Cloud Run Jobs + Pub/Sub (DLQ)**, **MongoDB**, **Cloud Storage**, and **Ultralytics YOLO11n**.

## Modules
- **backend/** — FastAPI service: create ingestion requests, list datasets, list images+labels, simple status endpoint.
- **worker/** — Cloud Run **Job** container that performs ingestion from GCS, parses YOLO labels, and upserts documents idempotently.
- **dispatcher/** — Cloud Run **Service** that receives Pub/Sub push and triggers the Cloud Run Job execution with message payload.
- **infra/terraform/** — One-click (ish) GCP infra: Pub/Sub + DLQ, buckets, Artifact Registry, Cloud Run (service + job), Monitoring alerts, etc.
- **.github/workflows/ci-cd.yml** — Build & push containers to Artifact Registry, then Terraform plan/apply (requires repo/env secrets).

> YOLO11n is loaded via Ultralytics: `from ultralytics import YOLO; YOLO("yolo11n.pt")` (ultralytics>=8.3.0).

## Quickstart (local dev)
1.  `.env` -> set values for dev, local, prod.
2. **MongoDB**: run local Mongo (Docker example):  
   ```bash
   docker run -d --name mongo -p 27017:27017 mongo:7
   ```
   for production set .env mongo variables to prod values
      MONGO_URI=mongodb://<use:password.mongodb.net>:27017
      MONGO_DB=yoloapp
3. **Backend**:
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   please set export SIGNED_URLS_MODE=proxy for dev
   #   auto (default): try to sign, else fall back to proxy
   #   proxy: always return proxy URLs (never sign)
   #   signed-only: only signed URLs; return None (frontend should handle)
   uvicorn app.main:app --reload --port ${API_PORT:-8080}
   ```
   - Open http://localhost:8080/docs

4. **Worker (local test)**:
   ```bash
   cd worker
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   # Dry run to ensure imports
   python -m job.main --help
   example payload
   for folder uploads
   python -m job.main --payload '{"dataset_name":"cars2dataset","gcs_uri":"gs://yolo-datasets-yolo-gcp-470119/uploads/cars2dataset/b6006a7e-02a1-4489-87f7-a73bcdf58f8a/", "format": "yolo"}'
   for zip uploads
   python -m job.main --payload '{"dataset_name": "cars3dataset",          
  "gcs_uri": "gs://yolo-datasets-yolo-gcp-470119/uploads/cars3dataset/0c5b1446-2258-4a03-a13a-9a786e282808/Archive.zip",
  "format": "yolo"}'
   ```
   
5. **Dispatcher (local)**:
   ```bash
   cd dispatcher
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app:app --reload --port ${DISPATCHER_PORT:-8081}
   ```

## GCP Deploy (Terraform)
- Ensure you have permissions and these APIs enabled: `run.googleapis.com`, `artifactregistry.   googleapis.com`,`pubsub.googleapis.com`, `secretmanager.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`.
- Authenticate: `gcloud auth application-default login` and `gcloud auth login`.
- In `infra/terraform/terraform.tfvars` (create), set your values:
  ```hcl
  project_id    = "your-gcp-project"
  region        = "us-central1"
  bucket_name   = "yolo11n-datasets"
  repo_location = "us"
  ```
- Then:
  ```bash
  cd infra/terraform
  terraform init
  terraform apply -auto-approve
  ```

This will:
- Create Pub/Sub topic + subscription with DLQ and a DLQ subscription.
- Create Cloud Storage bucket for datasets.
- Create Artifact Registry.
- Deploy Cloud Run **Service** (backend API), **Service** (dispatcher), and **Job** (worker).
- Wire Pub/Sub **push** to the dispatcher and grant IAM to run jobs.
- Create Monitoring Alerts:
  - **DLQ backlog** (`num_undelivered_messages` on the DLQ subscription).
  - **Forwarded-to-DLQ count** (`dead_letter_message_count` on the source subscription).
  - **Cloud Run Job failures** (`run.googleapis.com/job/completed_execution_count{result="failed"}`).
- Outputs URLs and resource IDs.

## API (FastAPI)
- `POST /ingestions` — body: `{ "dataset_name": "...", "gcs_uri": "gs://bucket/path-or-zip", "format": "yolo" }`
  - Publishes a Pub/Sub message with this payload.
- `GET /datasets` — list datasets.
- `GET /datasets/{dataset_id}/images` — paginated list with labels.
- `GET /healthz` — liveness.

## Ingestion Flow
1. Client calls **backend** → publishes Pub/Sub message.
2. **Dispatcher** (push-subscriber) receives message → executes **Cloud Run Job** with payload.
3. **Worker Job** downloads from GCS, unzips (if needed), parses YOLO labels, and **upserts**:
   - Unique indexes prevent duplicates.
   - Upserts are keyed on `(dataset_id, image_path)`.
4. On transient failure, Pub/Sub retries; after `max_delivery_attempts`, message moves to **DLQ**.
5. Alert policies notify on DLQ depth and job failures.

## Local tips
- Use `GCSFuse` or `gcloud storage cp` to put test zips into the bucket.
- For large zips, prefer **compose uploads** or direct GCS uploads over API uploads.

## CI/CD
- Configure GitHub OIDC to a GCP workload identity pool & provider.
- Set GitHub Secrets: `GCP_PROJECT_ID`, `GCP_WORKLOAD_IDP`, `GCP_SERVICE_ACCOUNT`, `REGION`.
- Push to `main` to build & deploy.


