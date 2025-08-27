from pydantic import BaseModel
from typing import List, Optional

class BBox(BaseModel):
    x_center: float
    y_center: float
    width: float
    height: float
    class_id: int

class ImageOut(BaseModel):
    id: str
    dataset_id: str
    image_path: str
    labels: List[BBox] = []
