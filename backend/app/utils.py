from typing import Tuple
def parse_gs_uri(gcs_uri: str) -> Tuple[str, str]:
    assert gcs_uri.startswith("gs://"), "must be gs://"
    path = gcs_uri[len("gs://"):]
    if "/" in path: bucket, key = path.split("/", 1)
    else: bucket, key = path, ""
    return bucket, key
