import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .db.client import connect, close
from .routers import health, datasets, images, ingestion, dataset_detail, imports
from .logging_conf import setup_logging

app = FastAPI(title="YOLO GCP Backend API")
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")] if settings.ALLOWED_ORIGINS else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def on_startup():
    await connect()

@app.on_event("shutdown")
async def on_shutdown():
    await close()

app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(images.router)
app.include_router(ingestion.router)
app.include_router(dataset_detail.router)
app.include_router(imports.router)
