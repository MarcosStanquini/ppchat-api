from typing import List
import boto3
import os
import json
import numpy as np

class EmbeddingService:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.client = boto3.client(
            'bedrock-runtime',
            region_name = os.getenv("AWS_DEFAULT_REGION"),
            aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key= os.getenv("AWS_SECRET_ACCESS_KEY")
        )
    def embed_texts(self, chunks: List[str]) -> List[List[float]]:
        embeddings = []
        for i, chunk in enumerate(chunks):
            request = {
                "inputText": chunk,
                "dimensions": 1024,
                "normalize": True
            }
            request = json.dumps(request)

            response = self.client.invoke_model(modelId=self.model_name, body=request)
            model_response = json.loads(response["body"].read())

            embeddings.append(model_response["embedding"])
        return embeddings

        
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        return float(np.dot(embedding1, embedding2))
