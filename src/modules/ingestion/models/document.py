import os
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class DocumentChunk(BaseModel):
    text:str
    metadata:Dict
    chunk_index: int
    page_number: int


class ProcessingConfig(BaseModel):
    chunk_size: int = Field(default=int(os.getenv("CHUNK_SIZE", 1000)), ge=100)
    chunk_overlap: int = Field(default=int(os.getenv("CHUNK_OVERLAP", 200)), ge=0)
    min_length: int = Field(default=int(os.getenv("MIN_LENGTH", 50)), ge=0)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    similarity_threshold: float = Field(default=float(os.getenv("SIMILARITY_THRESHOLD", 0.7)), ge=0.0, le=1.0)
    max_chunk_size: int = Field(default=int(os.getenv("MAX_CHUNK_SIZE", 2000)), ge=100)

