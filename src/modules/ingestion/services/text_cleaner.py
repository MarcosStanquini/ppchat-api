import unicodedata

class TextCleaner:
    @staticmethod
    def clean(text: str) -> str:
        text = unicodedata.normalize("NFKD", text) #Remove ligadores e unifica UNICODE
        text = " ".join(text.split())##Normaliza os espaços
        return text
    
    