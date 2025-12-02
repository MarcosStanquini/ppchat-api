from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter

#Configura o splitter e expõe em um método
class TextSplitter:
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " "]##Tenta quebrar por parágrafo, se não der, quebra por linha, sentença e espaço.
        )
    
    def split(self, text: str) -> List[str]:
        return self.splitter.split_text(text)