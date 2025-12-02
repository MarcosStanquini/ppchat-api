# PPChat - Sistema RAG para Projeto Pedagógico de Curso

Sistema de Retrieval-Augmented Generation (RAG) especializado no Projeto Pedagógico do Curso de Bacharelado em Engenharia de Software do IFSP São Carlos.

## 📋 Descrição

O PPChat é um sistema inteligente que permite fazer perguntas sobre o Projeto Pedagógico do Curso (PPC) de Engenharia de Software. Utiliza técnicas avançadas de processamento de documentos, incluindo:

- **Chunking Semântico**: Divisão inteligente do documento baseada em similaridade semântica
- **Embeddings**: Vetorização de texto usando `sentence-transformers`
- **RAG**: Recuperação e geração de respostas contextualizadas

## 🛠️ Tecnologias

- Python 3.13+
- LangChain
- Sentence Transformers
- PyMuPDF
- Pydantic
- Jupyter Notebooks

## 📦 Instalação

### 1. Pré-requisitos

- Python 3.13 ou superior
- pip (gerenciador de pacotes Python)
- Git (opcional)

### 2. Clone o repositório

```bash
git clone <url-do-repositorio>
cd PPChat
```

### 3. Crie um ambiente virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Instale as dependências

```bash
pip install -e .
```

### 5. Configure as variáveis de ambiente

Copie o arquivo de exemplo e configure as variáveis:

```bash
cp .env-example .env
```

O arquivo [`.env`](.env) contém:

```env
EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
THRESHOLD=0.7
MAX_CHUNK_SIZE=2000
```

### 6. Adicione o documento PDF

Coloque o arquivo `PPCENGSOFTWARE.pdf` na pasta:

```
src/data/documents/PPCENGSOFTWARE.pdf
```

## 🚀 Uso

### Processamento de Documentos

Você pode usar o notebook de exemplo para testar o processamento:

```bash
jupyter notebook notebooks/test-chunks.ipynb
```

### Exemplo de código

```python
from src.modules.ingestion.models.document import ProcessingConfig
from src.modules.ingestion.services.document_processor import DocumentProcessor

# Configure o processamento
config = ProcessingConfig(
    chunk_size=500,
    chunk_overlap=100,
    min_length=50,
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    similarity_threshold=0.75,
    max_chunk_size=1500
)

# Processe o PDF
processor = DocumentProcessor(config)
chunks = processor.process_pdf("src/data/documents/PPCENGSOFTWARE.pdf")

print(f"Total de chunks: {len(chunks)}")
```

## 📁 Estrutura do Projeto

```
PPChat/
├── src/
│   ├── modules/
│   │   ├── ingestion/          # Processamento de documentos
│   │   │   ├── models/         # Modelos de dados (DocumentChunk, Config)
│   │   │   └── services/       # Serviços (PDF loader, splitters, etc)
│   │   ├── retrieval/          # Recuperação de informações
│   │   └── shared/             # Serviços compartilhados (embeddings)
│   └── data/
│       └── documents/          # PDFs para processamento
├── notebooks/                  # Jupyter notebooks para testes
├── .env                       # Variáveis de ambiente
├── pyproject.toml            # Configuração do projeto
└── README.md                 # Este arquivo
```

## ⚙️ Configuração Avançada

### Parâmetros de Chunking

Ajuste os parâmetros no [`ProcessingConfig`](src/modules/ingestion/models/document.py):

- **chunk_size**: Tamanho base dos chunks (padrão: 1000 caracteres)
- **chunk_overlap**: Sobreposição entre chunks (padrão: 200 caracteres)
- **min_length**: Tamanho mínimo para processar uma página (padrão: 50 caracteres)
- **similarity_threshold**: Limiar para merge semântico (padrão: 0.7)
- **max_chunk_size**: Tamanho máximo após merge (padrão: 2000 caracteres)

### Modelos de Embedding

Você pode usar diferentes modelos do Hugging Face:

```python
config = ProcessingConfig(
    embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
```

## 🧪 Testando

Execute o notebook de testes:

```bash
cd notebooks
jupyter notebook test-chunks.ipynb
```

## 🔧 Desenvolvimento

### Instalação para desenvolvimento

```bash
pip install -e .
```

### Estrutura de módulos

- [`PdfLoader`](src/modules/ingestion/services/pdf_loader.py): Extrai texto do PDF
- [`TextCleaner`](src/modules/ingestion/services/text_cleaner.py): Normaliza texto
- [`TextSplitter`](src/modules/ingestion/services/text_splitter.py): Divisão recursiva
- [`SemanticSplitter`](src/modules/ingestion/services/semantic_splitter.py): Merge baseado em similaridade
- [`EmbeddingService`](src/modules/shared/services/embedding_service.py): Geração de embeddings
- [`DocumentProcessor`](src/modules/ingestion/services/document_processor.py): Orquestração do pipeline

## 📝 Como funciona

1. **Carregamento**: O [`PdfLoader`](src/modules/ingestion/services/pdf_loader.py) extrai o texto página por página
2. **Limpeza**: O [`TextCleaner`](src/modules/ingestion/services/text_cleaner.py) normaliza Unicode e espaços
3. **Chunking Base**: O [`TextSplitter`](src/modules/ingestion/services/text_splitter.py) divide o texto recursivamente
4. **Embeddings**: O [`EmbeddingService`](src/modules/shared/services/embedding_service.py) gera vetores semânticos
5. **Merge Semântico**: O [`SemanticSplitter`](src/modules/ingestion/services/semantic_splitter.py) mescla chunks similares
6. **Resultado**: Lista de [`DocumentChunk`](src/modules/ingestion/models/document.py) com metadados

## 📄 Licença

[Adicione sua licença aqui]

## 👥 Contribuindo

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## 📧 Contato

[Adicione suas informações de contato]