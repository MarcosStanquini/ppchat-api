from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class DocumentChunk(BaseModel):
    text:str
    metadata:Dict
    chunk_index: int
    page_number: int


class ProcessingConfig(BaseModel):
    chunk_size: int = Field(default=1000, ge=100)
    chunk_overlap: int = Field(default=200, ge=0)
    min_length: int = Field(default=50, ge=0)