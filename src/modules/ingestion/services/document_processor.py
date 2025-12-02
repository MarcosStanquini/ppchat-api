from src.modules.ingestion.models import DocumentChunk, ProcessingConfig
from src.modules.ingestion.services.pdf_loader import PdfLoader
from src.modules.ingestion.services.text_cleaner import TextCleaner
from src.modules.ingestion.services.text_splitter import TextSplitter
from typing import List


class DocumentProcessor:
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.loader = PdfLoader()
        self.cleaner = TextCleaner()
        self.splitter = TextSplitter(
            chunk_size= config.chunk_size,
            chunk_overlap=config.chunk_overlap
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
    

        


