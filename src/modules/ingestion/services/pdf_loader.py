from langchain_community.document_loaders import PyMuPDFLoader
from typing import List
from langchain_core.documents import Document

class PdfLoader:
    @staticmethod
    def load(pdf_path: str) -> List[Document]:
        loader = PyMuPDFLoader(pdf_path) #Extrai texto bruto e cria Document(Por página)
        return loader.load()