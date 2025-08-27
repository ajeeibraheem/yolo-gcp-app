import base64, json, os, structlog, requests
from fastapi import FastAPI, Header, HTTPException, Request
from google.auth import default
from google.auth.transport.requests import Request as GARequest
log = structlog.get_logger(); app = FastAPI(title="Ingestion Dispatcher")
PROJECT = os.getenv("GCP_PROJECT_ID")
REGION  = os.getenv("GCP_REGION")
JOB_NAME= os.getenv("JOB_NAME")
DISPATCHER_TOKEN = os.getenv("DISPATCHER_TOKEN")
RUN_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
RUN_ENDPOINT = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB_NAME}:run"
def _auth_headers():
    creds, _ = default(scopes=[RUN_SCOPE])
    if creds.requires_scopes: creds = creds.with_scopes([RUN_SCOPE])
    authed = GARequest(); creds.refresh(authed)
    return {"Authorization": f"Bearer {creds.token}"}

@app.post("/pubsub/push")
async def pubsub_push(request: Request):
    if DISPATCHER_TOKEN and x_dispatch_token != DISPATCHER_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    body = await request.json(); msg = body.get("message", {}); data_b64 = msg.get("data")
    if not data_b64: raise HTTPException(400, "No data in Pub/Sub message")
    payload = json.loads(base64.b64decode(data_b64))
    log.info("pubsub.received", payload=payload)
    headers = _auth_headers()
    r = requests.post(RUN_ENDPOINT, headers=headers, json={
        "overrides": {"containerOverrides": [{"args": ["--payload", json.dumps(payload)]}]}
    }, timeout=30)
    if r.status_code >= 300:
        log.error("runjob.error", status=r.status_code, text=r.text); raise HTTPException(r.status_code, r.text)
    return {"status": "ok", "operation": r.json().get("name")}
