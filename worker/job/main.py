import argparse, asyncio, json, os, structlog
from .logging_conf import setup_logging  # noqa: F401
from .gcs_io import download_gcs_uri, derive_target_prefix, upload_dir_to_gcs
from .parsing import parse_yolo_labels
from .mongo_io import upsert_dataset, bulk_upsert_images

log = structlog.get_logger()

def main():
    parser = argparse.ArgumentParser(description="YOLO11n ingestion worker")
    parser.add_argument("--payload", required=True,
                        help="JSON with dataset_name, gcs_uri or gcs_uris[], format=yolo")
    args = parser.parse_args()
    payload = json.loads(args.payload)
    asyncio.run(run(payload))

async def run(payload: dict):
    dataset_name: str = payload["dataset_name"]
    fmt: str = payload.get("format", "yolo")
    gcs_uri: str | None = payload.get("gcs_uri")
    gcs_uris: list[str] | None = payload.get("gcs_uris")  # optional: batch

    if not gcs_uri and not gcs_uris:
        raise ValueError("Provide gcs_uri or gcs_uris[]")

    # Resolve inputs (support either single or list)
    uris = gcs_uris or [gcs_uri]
    rep = uris[0]

    log.info("ingestion.start", dataset=dataset_name, gcs_uri=rep, fmt=fmt)

    # Download content locally; merge if multiple inputs
    local_root = None
    for i, u in enumerate(uris):
        local_dir = download_gcs_uri(u)
        if local_root is None:
            local_root = local_dir
        elif local_dir != local_root:
            # merge: move children of local_dir into local_root
            import shutil
            for dp, _, fns in os.walk(local_dir):
                for fn in fns:
                    src = os.path.join(dp, fn)
                    rel = os.path.relpath(src, local_dir)
                    dst = os.path.join(local_root, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)

    assert local_root is not None

    # Choose a destination prefix in the *same* bucket and upload extracted data
    target_prefix = derive_target_prefix(rep, dataset_name)
    log.info("extract.upload.start", dst_prefix=target_prefix)
    uploaded = upload_dir_to_gcs(local_root, target_prefix)
    log.info("extract.upload.done", files=uploaded, dst_prefix=target_prefix)

    # Parse YOLO labels and upsert dataset + images
    if fmt != "yolo":
        raise ValueError(f"Unsupported format: {fmt}")
    docs = parse_yolo_labels(local_root)
    with_labels = sum(1 for d in docs if d.get("labels"))
    log.info("ingestion.parsed", images=len(docs), with_labels=with_labels)
    log.info("ingestion.scan", files=len(docs), sample=(docs[0]["image_path"] if docs else None))

    # Set dataset to canonical prefix we just uploaded, then write image docs
    dataset_id = await upsert_dataset(dataset_name, target_prefix)  # sets source_prefix
    count = await bulk_upsert_images(dataset_id, docs)

    log.info("ingestion.done", dataset_id=dataset_id, images=count, source_prefix=target_prefix)

if __name__ == "__main__":
    main()
