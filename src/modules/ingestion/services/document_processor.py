from src.modules.ingestion.models import DocumentChunk, ProcessingConfig
from src.modules.ingestion.services.pdf_loader import PdfLoader
from src.modules.ingestion.services.text_cleaner import TextCleaner
from src.modules.ingestion.services.text_splitter import TextSplitter
from src.modules.ingestion.services.semantic_splitter import SemanticSplitter
from src.modules.shared.services.embedding_service import EmbeddingService
from typing import List


class DocumentProcessor:
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.loader = PdfLoader()
        self.cleaner = TextCleaner()

        ##Nao uso self no base_splitter e no embedding service pq eles só vao ser instanciados no semantic
        base_splitter = TextSplitter(
            chunk_size= config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        embedding_service = EmbeddingService(config.embedding_model)

        self.splitter = SemanticSplitter(
            embedding_service=embedding_service,
            base_splitter=base_splitter,
            similarity_threshold=config.similarity_threshold,
            max_chunk_size=config.max_chunk_size

        )
    
    def process_pdf(self, pdf_path: str) -> List[DocumentChunk]:
        pages = self.loader.load(pdf_path)

        chunks = []
        chunk_counter = 0

        for page_num, page in enumerate(pages, start=1):

            cleaned_text =  self.cleaner.clean(page.page_content)

            if len(cleaned_text) < self.config.min_length:
                continue
        
            page_chunks = self.splitter.split(cleaned_text)##Chunks por página

            for chunk_text in page_chunks:
                chunks.append(DocumentChunk(
                    text=chunk_text,
                    metadata={
                        **page.metadata,
                        "total_pages": len(pages)
                    },
                    chunk_index = chunk_counter,
                    page_number = page_num
                ))
                chunk_counter +=1
            
        return chunks
    

    


