from src.modules.ingestion.models.curriculum import Curriculo
from src.modules.shared.services.llm_client import get_llm_client
from src.modules.shared.services.settings import get_settings

EXTRACTION_INSTRUCTIONS = """\
Você vai receber o texto completo de um Projeto Pedagógico de Curso (PPC), com marcadores [Página N] \
indicando a página do PDF. Extraia a estrutura curricular para o schema pedido.

- Inclua todos os componentes curriculares: obrigatórios, optativos, extensão, TCC e estágio quando forem componentes.
- Cruze a tabela de estrutura curricular, o quadro de pré-requisitos (seção 6.4) e os planos de ensino (seção 18). \
Em caso de divergência, prefira o quadro de pré-requisitos e a tabela de estrutura curricular.
- Em `pre_requisitos`, use os códigos das disciplinas, não os nomes. O PPC às vezes varia o nome \
("PROGRAMAÇÃO PARA WEB 1" e "PROGRAMAÇÃO PARA A WEB 1" são a mesma disciplina).
- Em `requisitos_gerais`, registre regras que condicionam o avanço no curso: estágio, TCC, atividades \
complementares, curricularização da extensão, integralização e prazos.
- Não invente valores. Se um campo numérico não existir no documento, use 0; se uma página não existir, use null.
"""


class CurriculumExtractor:
    def __init__(self):
        self.settings = get_settings()
        self.client = get_llm_client()

    def extract(self, document_text: str) -> Curriculo:
        # Streaming porque a saída é longa; o SDK valida o JSON final contra o modelo Pydantic
        with self.client.beta.messages.stream(
            model=self.settings.extraction_model or self.settings.llm_model,
            max_tokens=self.settings.max_output_tokens,
            output_config={"effort": self.settings.extraction_effort},
            output_format=Curriculo,
            system=EXTRACTION_INSTRUCTIONS,
            messages=[{"role": "user", "content": f"<ppc>\n{document_text}\n</ppc>"}],
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            raise RuntimeError("O modelo recusou a extração do currículo.")
        if message.stop_reason == "max_tokens":
            raise RuntimeError("A extração estourou max_tokens; aumente MAX_OUTPUT_TOKENS.")
        if message.parsed_output is None:
            raise RuntimeError("A resposta não pôde ser validada contra o schema do currículo.")
        return message.parsed_output
