from typing import List, Tuple
from src.modules.shared.services.embedding_service import EmbeddingService
from src.modules.shared.services.vector_store import VectorStore
from src.modules.ingestion.models.document import DocumentChunk

class Retriever:
    def __init__(self, embedding_service: EmbeddingService, vector_store: VectorStore, top_k: int = 3):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.top_k = top_k
    
    def retrieve(self, query: str) -> List[Tuple[DocumentChunk, float]]:
        query_embedding = self.embedding_service.embed_texts([query])[0]
        
        results = self.vector_store.similarity_search(query_embedding, top_k=self.top_k)
        
        return results