import boto3
import json
import os
from typing import List, Tuple
from src.modules.ingestion.models.document import DocumentChunk

class Generator:
    def __init__(self, model_name: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"):
        self.model_name = model_name
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=os.getenv("AWS_DEFAULT_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
    
    def generate(self, query: str, context_chunks: List[Tuple[DocumentChunk, float]]) -> str:
        context = self._build_context(context_chunks)
        
        prompt = self._build_prompt(query, context)
        

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = self.client.invoke_model(
            modelId=self.model_name,
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]
    
    def _build_context(self, context_chunks: List[Tuple[DocumentChunk, float]]) -> str:
        context_parts = []
        
        for i, (chunk, score) in enumerate(context_chunks, start=1):
            context_parts.append(
                f"[Trecho {i} - Página {chunk.page_number} - Relevância: {score:.2f}]\n{chunk.text}\n"
            )
        
        return "\n".join(context_parts)
    
    def _build_prompt(self, query: str, context: str) -> str:
        return f"""
Você é um assistente especializado **exclusivamente** no Projeto Pedagógico do Curso (PPC) de Engenharia de Software do IFSP São Carlos.

REGRAS OBRIGATÓRIAS PARA RESPONDER:
1. **Use somente** as informações presentes no CONTEXTO abaixo.
2. **Não invente, não deduza e não complete** nada que não esteja explicitamente no CONTEXTO.
3. Se a informação **não existir**, **não estiver clara** ou **não for possível concluir**, responda exatamente:
   "Não há informação suficiente no contexto fornecido."
4. Mantenha a resposta **objetiva, precisa e fundamentada** nos trechos apresentados.
5. Nunca cite documentos externos, normas, leis, Wikipedia ou conhecimento prévio.
6. Se o usuário pedir algo fora do PPC, responda que não é possível porque não está no CONTEXTO.

CONTEXTO FORNECIDO:
--------------------
{context}
--------------------

PERGUNTA DO USUÁRIO:
{query}

RESPOSTA (baseada somente no CONTEXTO):
"""
