# YOLO GCP Application

**100GB+ friendly** pipeline using **GCP Cloud Run Jobs + Pub/Sub (DLQ)**, **MongoDB**, **Cloud Storage**, and **Ultralytics YOLO11n**.

> YOLO11n via Ultralytics:  
> `from ultralytics import YOLO; YOLO("yolo11n.pt")  # ultralytics>=8.3.0`

---

## Table of Contents

- [Modules](#modules)  
- [Configuration](#configuration)  
- [Quickstart (Local Dev)](#quickstart-local-dev)  
- [API (FastAPI)](#api-fastapi)  
- [Ingestion Flow](#ingestion-flow)  
- [GCP Deploy (Terraform)](#gcp-deploy-terraform)  
- [Observability & Alerts](#observability--alerts)  
- [CI/CD](#cicd)  
- [Local Tips](#local-tips)  
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)  
- [Troubleshooting](#troubleshooting)

---

## Modules

- **backend/** — FastAPI service to create ingestion requests, list datasets, list images+labels, and provide a status/health endpoint.  
- **worker/** — Cloud Run **Job** container that ingests from GCS, parses YOLO labels, and upserts documents **idempotently**.  
- **dispatcher/** — Cloud Run **Service** that receives Pub/Sub **push** and triggers the Cloud Run **Job** with the message payload.  
- **infra/terraform/** — “One-click” GCP infra: Pub/Sub with **DLQ**, buckets, Artifact Registry, Cloud Run (service + job), Monitoring alerts, etc.  
- **.github/workflows/ci-cd.yml** — Build & push containers to Artifact Registry, then Terraform plan/apply (requires repo/env secrets).

---

## Configuration

Create a `.env` (dev/local/prod). Example:

```ini
# Mongo
MONGO_URI=mongodb://localhost:27017
MONGO_DB=yoloapp

# GCP
GCP_PROJECT_ID=your-gcp-project
GCP_REGION=us-central1
GCS_BUCKET=your-datasets-bucket
PUBSUB_TOPIC=ingestion-tasks
PUBSUB_SUBSCRIPTION=ingestion-sub

# Backend URL modes for images
#   auto (default): try signed URLs, else fall back to proxy
#   proxy: always proxy via backend (dev-friendly)
#   signed-only: only signed URLs; may return null when not possible
SIGNED_URLS_MODE=auto
ALLOWED_ORIGINS=http://localhost:3000

# Dev convenience (remove/replace in prod)
AUTH_MODE=DEV_NO_AUTH
```

> **Production**: use Secret Manager / Workload Identity; never commit secrets.

---

## Quickstart (Local Dev)

1) **MongoDB**

```bash
docker run -d --name mongo -p 27017:27017 mongo:7
```

(Prod: set `MONGO_URI` to your managed cluster; e.g., `mongodb+srv://<user>:<pass>@cluster.mongodb.net`)

2) **Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SIGNED_URLS_MODE=proxy   # recommended for dev
uvicorn app.main:app --reload --port ${API_PORT:-8080}
```

Open: <http://localhost:8080/docs>

3) **Worker (local test)**

```bash
cd worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m job.main --help
```

**Example payloads:**

- Folder upload

```bash
python -m job.main --payload '{
  "dataset_name":"cars2dataset",
  "gcs_uri":"gs://yolo-datasets-yolo-gcp-470119/uploads/cars2dataset/b6006a7e-02a1-4489-87f7-a73bcdf58f8a/",
  "format":"yolo"
}'
```

- Zip upload

```bash
python -m job.main --payload '{
  "dataset_name":"cars3dataset",
  "gcs_uri":"gs://yolo-datasets-yolo-gcp-470119/uploads/cars3dataset/0c5b1446-2258-4a03-a13a-9a786e282808/Archive.zip",
  "format":"yolo"
}'
```

4) **Dispatcher (local)**

```bash
cd dispatcher
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port ${DISPATCHER_PORT:-8081}
```

---

## API (FastAPI)

- **POST `/ingestions`**  
  Body:
  ```json
  { "dataset_name": "...", "gcs_uri": "gs://bucket/path-or-zip", "format": "yolo" }
  ```
  Behavior: Publishes a Pub/Sub message with this payload.

- **GET `/datasets`** — list datasets.

- **GET `/datasets/{dataset_id}/images`** — paginated images with labels.

- **GET `/healthz`** — liveness.

---

## Ingestion Flow

1. Client calls **backend** → publishes Pub/Sub message.  
2. **Dispatcher** (push-subscriber) receives message → executes **Cloud Run Job** with payload.  
3. **Worker Job** downloads from GCS, unzips (if needed), parses YOLO labels, and **upserts**:
   - Unique indexes prevent duplicates.
   - Upserts keyed on `(dataset_id, image_path)`.
4. Pub/Sub retries transient failures; after `max_delivery_attempts`, message moves to **DLQ**.  
5. Alert policies notify on DLQ depth and Job failures.

---

## GCP Deploy (Terraform)

**Enable APIs**:  
`run.googleapis.com`, `artifactregistry.googleapis.com`, `pubsub.googleapis.com`, `secretmanager.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com`

**Authenticate**:

```bash
gcloud auth application-default login
gcloud auth login
```

**Configure** `infra/terraform/terraform.tfvars`:

```hcl
project_id    = "your-gcp-project"
region        = "us-central1"
bucket_name   = "yolo11n-datasets"
repo_location = "us"
```

**Apply**:

```bash
cd infra/terraform
terraform init
terraform apply -auto-approve
```

**Provisions**:

- Pub/Sub topic + subscription with **DLQ** (+ DLQ subscription)  
- Cloud Storage bucket for datasets  
- Artifact Registry  
- Cloud Run **Service** (backend API) + **Service** (dispatcher) + **Job** (worker)  
- Pub/Sub **push** to dispatcher and IAM to run jobs  
- Monitoring Alerts:
  - **DLQ backlog** (`num_undelivered_messages` on DLQ subscription)
  - **Forwarded-to-DLQ count** (`dead_letter_message_count` on source subscription)
  - **Cloud Run Job failures** (`run.googleapis.com/job/completed_execution_count{result="failed"}`)

---

## Observability & Alerts

- **DLQ backlog** — failsafe to catch stuck/poison messages.  
- **Forwarded-to-DLQ count** — early warning of systematic ingestion issues.  
- **Cloud Run Job failure rate** — spot data/permission regressions quickly.

---

## CI/CD

- GitHub OIDC → GCP Workload Identity (no long-lived keys).  
- Required GitHub secrets:
  - `GCP_PROJECT_ID`
  - `GCP_WORKLOAD_IDP`
  - `GCP_SERVICE_ACCOUNT`
  - `REGION`
- Push to `main` ⇒ build & push images to Artifact Registry ⇒ Terraform plan/apply.

---

## Local Tips

- Use **GCSFuse** or `gcloud storage cp` to upload test zips.  
- For large zips, prefer **compose uploads** or direct GCS uploads over API uploads.

---

## Design Decisions & Trade-offs

1. **Cloud Run Jobs + Pub/Sub (with DLQ) vs. Synchronous ingestion**
   - **Why**: Long-running CPU/IO tasks isolated from request path; retries & DLQ for reliability.  
   - **Trade-off**: More moving parts (IAM, dispatcher, job definitions) vs. much better resilience and scalability.

2. **Dispatcher as Push Subscriber vs. Pull**
   - **Why**: Push keeps infra simple; the dispatcher just validates and triggers the Job.  
   - **Trade-off**: Push requires stable, publicly reachable endpoint; pull gives more control but needs a worker loop.

3. **MongoDB for metadata vs. Postgres/BigQuery**
   - **Why**: Flexible, evolving metadata and labels; simple pagination and filtering for UI.  
   - **Trade-off**: We lose strong relational guarantees. If you need complex joins/constraints, a relational store or dual-write pattern may be better. BigQuery suits analytics but is costlier/slower for hot browsing.

4. **Idempotency via unique index + upserts**
   - **Why**: Safe replays, partial failure recovery, and reruns of the same dataset/version.  
   - **Trade-off**: Requires careful key choice and index maintenance; index mismatches can cause `IndexOptionsConflict`.

5. **Signed URL modes (`auto` / `proxy` / `signed-only`)**
   - **Why**: Fit different environments and security postures. `proxy` is simplest for dev; `signed-only` strongest for prod.  
   - **Trade-off**: Proxying increases egress/latency but centralizes auth & observability; signed URLs are fast/cheap but require IAM & time sync.

6. **YOLO11n choice**
   - **Why**: Fast, low-cost demo/browse.  
   - **Trade-off**: Lower accuracy vs. larger variants; swap model when accuracy > latency/cost.

7. **Terraform with deletion protection**
   - **Why**: Prevent accidental destroys of critical services/jobs.  
   - **Trade-off**: Extra steps needed to deliberately tear down (must disable protection first).

8. **OIDC to GCP (no static keys)**
   - **Why**: Reduce secret sprawl and rotation burden.  
   - **Trade-off**: Slightly more setup (Workload Identity Pool/Provider) upfront.

---

## Troubleshooting

- **Mongo `IndexOptionsConflict` (code 85)**  
  Symptom: `Index already exists with a different name: uq_image_path_per_dataset`.  
  Fix: Use a consistent index name/definition, or drop the conflicting one:
  ```js
  db.images.dropIndex("uq_image_path_per_dataset");
  // recreate with the expected keys/options
  ```

- **`NoneType` DB on startup**  
  Ensure the backend initializes Mongo (connect) **before** calling `ensure_indexes()` and serving requests.

- **Signed URL issues in dev**  
  Use `SIGNED_URLS_MODE=proxy` to avoid IAM/clock drift nuisance.

- **Cloud Run Job permissions**  
  Dispatcher service account needs `run.jobs.run` on the Job; Pub/Sub push service account must invoke the dispatcher.

- **Terraform destroy fails**  
  Some resources have `deletion_protection=true`. Set it to `false` and re-apply before destroying.
