import chromadb
from src.modules.ingestion.models.document import DocumentChunk
from typing import List, Tuple
import os
from chromadb.config import Settings
class VectorStore:

    def __init__(
        self, 
        collection_name: str = "ppc_documents",
        persist_directory: str = os.getenv("DATA_PERSIST_DIRECTORY", "src\data\chroma_db")
    ):
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                allow_reset=True
            )
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks_embeddings(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]]
    ) -> None:
        
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks ({len(chunks)}) ≠ Embeddings ({len(embeddings)})")
        
        ids = [f"chunk_{chunk.chunk_index}_{chunk.page_number}" for chunk in chunks]
        
        documents = [chunk.text for chunk in chunks]

        metadatas = []
        for chunk in chunks:
            metadatas.append({
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "total_pages": chunk.metadata.get("total_pages", 0),
            "source": chunk.metadata.get("source", "unknown"),
        })
            
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
    
    def get_count(self) -> int:
        return self.collection.count()
    
    def similarity_search(self, query_embedding: List[float], top_k: int = 3) -> List[Tuple[DocumentChunk, float]]:

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        chunks_with_scores = []
        
        for i in range(len(results['ids'][0])):
            chunk = DocumentChunk(
                text=results['documents'][0][i],
                metadata=results['metadatas'][0][i],
                chunk_index=results['metadatas'][0][i]['chunk_index'],
                page_number=results['metadatas'][0][i]['page_number']
            )
            similarity = 1 - results['distances'][0][i]  
            chunks_with_scores.append((chunk, similarity))
        
        return chunks_with_scores

        


        

        