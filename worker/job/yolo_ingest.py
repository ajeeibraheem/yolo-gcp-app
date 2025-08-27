from ultralytics import YOLO
from functools import lru_cache

@lru_cache(maxsize=1)
def get_model():
    # Ensure YOLO11n available for potential validation/preview
    return YOLO("yolo11n.pt")
