from ultralytics import YOLO
from functools import lru_cache

@lru_cache(maxsize=1)
def get_model():
    # Auto-downloads YOLO11n weights
    return YOLO("yolo11n.pt")
