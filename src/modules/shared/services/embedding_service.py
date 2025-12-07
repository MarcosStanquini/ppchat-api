from typing import List
from langchain_community.embeddings import HuggingFaceEmbeddings
import numpy as np

class EmbeddingService:
    def __init__(self, model_name: str):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={'device': 'cpu'},##Melhora para tarefas simples
            encode_kwargs={'normalize_embeddings': True}##Depois de gerar o embedding ele normaliza o vetor parar magnitude 1
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.embeddings.embed_documents(texts)
        
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        return float(np.dot(embedding1, embedding2))
