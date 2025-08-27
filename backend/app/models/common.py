from pydantic import BaseModel, Field
from typing import Optional

class Pagination(BaseModel):
    page: int = 1
    page_size: int = 50
