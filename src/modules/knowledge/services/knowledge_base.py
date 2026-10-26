from functools import cached_property, lru_cache
from pathlib import Path
from typing import List

from src.modules.ingestion.models.curriculum import Curriculo, Disciplina
from src.modules.ingestion.services.ingestion_pipeline import CURRICULUM_FILE, DOCUMENT_FILE
from src.modules.knowledge.services.curriculum_graph import CurriculumGraph
from src.modules.shared.services.settings import get_settings

ABORDAGEM = {"teorica": "teórica", "pratica": "prática", "teorico_pratica": "teórico-prática"}
TIPO = {"obrigatoria": "obrigatória", "optativa": "optativa", "eletiva": "eletiva"}


def _hours(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " h"


class KnowledgeBase:
    """Tudo que o modelo recebe sobre o curso: o PPC inteiro + o currículo estruturado com o grafo.

    O texto renderizado precisa ser byte a byte estável (nada de datas ou ordens aleatórias),
    porque ele forma o prefixo que fica no cache de prompt.
    """

    def __init__(self, processed_dir: Path):
        curriculum_path = processed_dir / CURRICULUM_FILE
        document_path = processed_dir / DOCUMENT_FILE
        if not curriculum_path.exists() or not document_path.exists():
            raise FileNotFoundError("Base não processada. Rode primeiro: python main.py ingest")

        self.curriculo = Curriculo.model_validate_json(curriculum_path.read_text("utf-8"))
        self.document_text = document_path.read_text("utf-8")
        self.graph = CurriculumGraph(self.curriculo)

    def _names(self, codes: List[str]) -> str:
        return "; ".join(f"{self.graph.by_code[c].nome} ({c})" for c in codes) or "nenhuma"

    def _render_disciplina(self, d: Disciplina) -> str:
        a = self.graph.analysis[d.codigo]
        semestre = f"{d.semestre}º semestre" if d.semestre else "sem semestre fixo"
        lines = [
            f"### {d.nome} ({d.codigo})",
            f"- {semestre} · {TIPO[d.tipo]} · {d.aulas_semanais} aulas/semana · {d.total_aulas} aulas · "
            f"{_hours(d.carga_horaria_total)} (extensão: {_hours(d.carga_horaria_extensao)})",
            f"- Abordagem {ABORDAGEM[d.abordagem]} · laboratório: {'sim' if d.usa_laboratorio else 'não'}"
            + (f" · plano de ensino na [Página {d.pagina_plano_ensino}]" if d.pagina_plano_ensino else ""),
            f"- Pré-requisitos diretos: {self._names(d.pre_requisitos)}",
        ]
        if len(a.pre_requisitos_transitivos) > len(d.pre_requisitos):
            lines.append(f"- Base acumulada (todos os pré-requisitos indiretos): {self._names(a.pre_requisitos_transitivos)}")
        if a.profundidade > 0:
            lines.append(f"- Cadeia mais longa até ela: {' → '.join(a.cadeia_mais_longa)}")
        lines.append(f"- Libera diretamente: {self._names(a.libera_diretamente)}")
        if len(a.libera_transitivamente) > len(a.libera_diretamente):
            lines.append(f"- Trava, se reprovada, {len(a.libera_transitivamente)} disciplinas: {self._names(a.libera_transitivamente)}")
        lines.append(
            f"- Complexidade estimada: {a.indice_complexidade}/10 ({a.nivel_estimado}) · profundidade {a.profundidade}"
        )
        if d.grupos_conhecimento:
            lines.append(f"- Grupos de conhecimento: {', '.join(d.grupos_conhecimento)}")
        if d.topicos_principais:
            lines.append(f"- Tópicos: {'; '.join(d.topicos_principais)}")
        return "\n".join(lines)

    @cached_property
    def curriculum_context(self) -> str:
        c = self.curriculo
        disciplinas = sorted(c.disciplinas, key=lambda d: (d.semestre or 99, d.nome))
        parts = [
            f"# Currículo estruturado — {c.curso} ({c.campus}, vigência {c.vigencia})",
            f"Duração: {c.duracao_semestres} semestres · carga horária total: {_hours(c.carga_horaria_total_curso)}",
            "",
            "Dados extraídos do PPC. A complexidade estimada (0–10) NÃO é oficial: é calculada a partir "
            "da profundidade na cadeia de pré-requisitos (35%), do tamanho da base acumulada (25%), "
            "do semestre (25%) e da carga horária (15%).",
            "",
            "## Cadeia crítica (a sequência de pré-requisitos mais longa do curso)",
            " → ".join(f"{self.graph.by_code[x].nome} ({x})" for x in self.graph.critical_path),
            "",
            "## Disciplinas-gargalo (mais disciplinas dependem delas)",
            *(
                f"- {self.graph.by_code[x].nome} ({x}): trava {len(self.graph.analysis[x].libera_transitivamente)}"
                for x in self.graph.bottlenecks()
            ),
            "",
            "## Requisitos gerais para avançar e se formar",
            *(
                f"- {r.item}: {r.descricao}" + (f" [Página {r.pagina}]" if r.pagina else "")
                for r in c.requisitos_gerais
            ),
            "",
            "## Disciplinas",
            *(self._render_disciplina(d) + "\n" for d in disciplinas),
        ]
        return "\n".join(parts)

    def render_disciplinas(self, codes: List[str]) -> str:
        """Ficha das disciplinas que o usuário selecionou no chat (códigos desconhecidos são ignorados)."""
        return "\n\n".join(
            self._render_disciplina(self.graph.by_code[code]) for code in codes if code in self.graph.by_code
        )

    @cached_property
    def full_context(self) -> str:
        return (
            f"<curriculo_estruturado>\n{self.curriculum_context}\n</curriculo_estruturado>\n\n"
            f"<ppc_completo>\n{self.document_text}\n</ppc_completo>"
        )


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase(get_settings().processed_dir)
