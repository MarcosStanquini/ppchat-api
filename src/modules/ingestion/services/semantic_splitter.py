import os
from typing import List
from src.modules.shared.services.embedding_service import EmbeddingService
from src.modules.ingestion.services.text_splitter import TextSplitter

class SemanticSplitter:
    def __init__(
            self,
            embedding_service: EmbeddingService,
            base_splitter: TextSplitter,
            similarity_threshold: float,
            max_chunk_size: int,
    ):
        self.embedding_service = embedding_service
        self.base_splitter = base_splitter  
        self.similarity_threshold = similarity_threshold 
        self.max_chunk_size = max_chunk_size

    def split(self, text: str) -> List[str]:

        # initial_chunks = chunks DENTRO da página.
        initial_chunks = self.base_splitter.split(text)

        if len(initial_chunks) <= 1:
            return initial_chunks

        embeddings = self.embedding_service.embed_texts(initial_chunks) ##Pego os embeddings por pagina

        merged_chunks = []
        current_chunk = initial_chunks[0]
        current_embedding = embeddings[0]

        for i in range(1, len(initial_chunks)):
            next_chunk = initial_chunks[i]
            next_embedding = embeddings[i]

            similarity = self.embedding_service.calculate_similarity(current_embedding, next_embedding)

            combined_length = len(current_chunk) + len(next_chunk)

            if similarity >= self.similarity_threshold and combined_length <= self.max_chunk_size:
                current_chunk = current_chunk + " " + next_chunk
                ##Como o embed texts só recebe uma lista, transformo o chunk atual em uma lista de unico elemento e retorno ele mesmo
                current_embedding = self.embedding_service.embed_texts([current_chunk])[0]
            else:
                merged_chunks.append(current_chunk)
                current_chunk = next_chunk
                current_embedding = next_embedding
        
        merged_chunks.append(current_chunk)
        
        return merged_chunks