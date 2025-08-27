from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class DatasetIn(BaseModel):
    name: str
    description: Optional[str] = None

class DatasetOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
