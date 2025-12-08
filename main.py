from src.modules.retrieval.services.retriever import Retriever
from src.modules.response.services.generator import Generator
from src.modules.shared.services.vector_store import VectorStore
import os
from src.modules.ingestion.models.document import ProcessingConfig
from src.modules.ingestion.services.document_processor import DocumentProcessor
from src.modules.shared.services.embedding_service import EmbeddingService
from dotenv import load_dotenv
load_dotenv()

def ingestion():
    try:
    #Cria o Banco
        vector_store = VectorStore()
        #Ingestion:
        if vector_store.get_count() <= 0:
            config = ProcessingConfig()
            print("Configuração feita!")
            processor = DocumentProcessor(config)
            print("Processando chunks...")
            chunks = processor.process_pdf("src/data/documents/PPCENGSOFTWARE.pdf")
            print("Chunks Processados!")
            embedding_service = EmbeddingService(os.getenv("EMBEDDING_MODEL"))

            chunk_texts = [chunk.text for chunk in chunks]
            print("Gerando embeddings...")
            embeddings = embedding_service.embed_texts(chunk_texts)
            print("Embeddings gerados!")
            print(f"Generated {len(embeddings)} embeddings")

            vector_store.add_chunks_embeddings(chunks, embeddings)
    except Exception as e:
        print(e)



def retrieval_example():
    try:
        generator = Generator(os.getenv("LLM_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"))
        vector_store = VectorStore()
        embedding_service = EmbeddingService(os.getenv("EMBEDDING_MODEL"))
        
        retriever = Retriever(
            embedding_service=embedding_service,
            vector_store=vector_store,
            top_k=3
        )
        
        query = ""
        print(f"Query: {query}\n")
        
        results = retriever.retrieve(query)
        
        response = generator.generate(query, results)
        
        print(f"RESPOSTA:\n{response}\n")
            
    except Exception as e:
        print(f"Erro: {e}")


ingestion()
retrieval_example()



